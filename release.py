#!/usr/bin/env python3
"""Cut a release: bump both plugin manifests, tag it, and publish it.

Run from the repository root with exactly one of --major, --minor, or
--patch. That component increases by one and every smaller component
resets to zero, so --minor takes 1.4.2 to 1.5.0.

Both manifests carry one version and are bumped together:

  plugins/xojo/.claude-plugin/plugin.json
  plugins/xojo/.codex-plugin/plugin.json

The tag is the new version with a "v" in front, the GitHub convention:
version 1.5.0 is tagged v1.5.0.

A release is cut only from a clean main that is not behind origin, and
only with the test gate green. A dirty tree refuses, untracked files
included, since a file that is not committed is not in the release;
--allow-untracked and --no-tests each waive one of those. Every
check runs before the first change is written, so a failed check leaves
nothing to undo. Once changes begin, the commit and tag are made locally
before anything is pushed, and a failure after that prints how far it
got and the commands that finish or reverse it. --dry-run stops before
the first change.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CLAUDE_MANIFEST = Path("plugins/xojo/.claude-plugin/plugin.json")
CODEX_MANIFEST = Path("plugins/xojo/.codex-plugin/plugin.json")
MANIFESTS = (CLAUDE_MANIFEST, CODEX_MANIFEST)

BRANCH = "main"
REMOTE = "origin"
BRANCH_REF = "refs/heads/" + BRANCH
REMOTE_BRANCH_REF = "refs/remotes/%s/%s" % (REMOTE, BRANCH)

# The value is rewritten in place rather than through json.dump, which
# would reformat every other line of the manifest.
VERSION_RE = re.compile(
    r'^(?P<lead>[ \t]*"version"[ \t]*:[ \t]*")(?P<version>[^"]*)(?P<tail>")',
    re.MULTILINE)
COMPONENT_RE = re.compile(r"^(0|[1-9][0-9]*)$")

# Milestones recorded as publish() proceeds; recovery() reads them to say
# what happened and what to run next. The two "in flight" markers are
# replaced on success -- an interrupted push may still have landed, and
# recovery must not claim otherwise.
STAGED, COMMITTED, TAGGED = "staged", "commit", "tag"
PUSHING, PUSHED = "push (in flight)", "push"
TAG_PUSHING, TAG_PUSHED = "tag push (in flight)", "tag push"

EX_USAGE = 64
EX_INTERRUPTED = 130


class ReleaseError(Exception):
    """A step failed; main() turns this into a message and a nonzero exit."""


class Interrupted(ReleaseError):
    """Ctrl-C, carried up so main() can exit 130 with the same report."""


class ReleaseParser(argparse.ArgumentParser):
    """Usage errors exit 64, as every other parser in this repository does."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        sys.exit(EX_USAGE)


def run(argv, **kwargs):
    """subprocess.run, with a missing binary reported the house way."""
    try:
        return subprocess.run(argv, **kwargs)
    except OSError as exc:
        raise ReleaseError("cannot run %s: %s" % (argv[0], exc))


def git(*args, check=True):
    """Run git in the repository and return its stdout and exit code.

    Only the trailing newline is removed: porcelain output carries
    meaning in its leading columns.
    """
    proc = run(["git", "-C", str(ROOT)] + list(args),
               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               universal_newlines=True)
    if check and proc.returncode != 0:
        raise ReleaseError(
            "git %s failed:\n%s" % (" ".join(args), (proc.stderr or "").strip()))
    return proc.stdout.rstrip("\n"), proc.returncode


def read_text(path):
    # newline="" keeps CRLF intact: only the version value may change.
    with open(str(ROOT / path), "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text(path, text):
    with open(str(ROOT / path), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_version(path):
    try:
        document = json.loads(read_text(path))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReleaseError("%s is not valid JSON: %s" % (path, exc))
    except OSError as exc:
        raise ReleaseError("cannot read %s: %s" % (path, exc))
    version = document.get("version")
    if not isinstance(version, str):
        raise ReleaseError("%s has no string \"version\" key" % path)
    return version


def version_line_count(path):
    """How many lines write_version would consider rewriting."""
    return len(VERSION_RE.findall(read_text(path)))


def bump(version, part):
    components = version.split(".")
    if len(components) != 3 or not all(
            COMPONENT_RE.match(c) for c in components):
        raise ReleaseError(
            "version %r is not major.minor.patch with plain numbers"
            % version)
    major, minor, patch = (int(c) for c in components)
    if part == "major":
        return "%d.0.0" % (major + 1)
    if part == "minor":
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


def write_version(path, new_version):
    text = read_text(path)
    match = VERSION_RE.search(text)
    if match is None:
        # preflight counted one match; the file changed since then.
        raise ReleaseError(
            "the \"version\" line in %s changed after the checks ran" % path)
    updated = (text[:match.start()] + match.group("lead") + new_version
               + match.group("tail") + text[match.end():])
    # Parse before writing: a manifest that no longer reads as JSON must
    # never reach the commit.
    if json.loads(updated).get("version") != new_version:
        raise ReleaseError("rewriting %s did not produce the new version"
                           % path)
    write_text(path, updated)


def preflight(part, run_tests, allow_untracked):
    """Refuse everything that would make a release wrong, before any change."""
    # The full ref, not --abbrev-ref or --short: both of those shorten
    # refs/heads/main to "heads/main" when a tag named main exists, which
    # would refuse a perfectly good release. --quiet exits nonzero on a
    # detached HEAD.
    head, code = git("symbolic-ref", "--quiet", "HEAD", check=False)
    head = head.strip()
    if code != 0 or not head:
        raise ReleaseError("HEAD is detached; a release is cut from " + BRANCH)
    if head != BRANCH_REF:
        raise ReleaseError(
            "on branch %s; a release is cut from %s"
            % (head[len("refs/heads/"):] if head.startswith("refs/heads/")
               else head, BRANCH))

    status, _ = git("status", "--porcelain")
    lines = [ln for ln in status.splitlines() if ln.strip()]
    tracked = [ln for ln in lines if not ln.startswith("??")]
    if tracked:
        raise ReleaseError(
            "uncommitted changes to tracked files:\n%s"
            % "\n".join("  " + ln for ln in tracked))
    untracked = [ln[3:] for ln in lines if ln.startswith("??")]
    if untracked and not allow_untracked:
        raise ReleaseError(
            "untracked files present; commit, delete, or ignore them, or "
            "pass --allow-untracked to release anyway:\n%s"
            % "\n".join("  " + name for name in untracked))

    for path in MANIFESTS:
        if not (ROOT / path).is_file():
            raise ReleaseError("missing manifest: %s" % path)
    versions = {path: read_version(path) for path in MANIFESTS}
    if len(set(versions.values())) != 1:
        raise ReleaseError(
            "the manifests disagree, so there is no version to bump:\n%s"
            % "\n".join("  %s: %s" % (p, v) for p, v in versions.items()))
    # write_version needs exactly one rewritable line per manifest. That
    # is checked here, not there, so a manifest it cannot handle stops
    # the release before the other manifest has been touched.
    for path in MANIFESTS:
        found = version_line_count(path)
        if found != 1:
            raise ReleaseError(
                "expected one \"version\" line in %s, found %d"
                % (path, found))
    current = versions[CLAUDE_MANIFEST]
    new_version = bump(current, part)
    tag = "v" + new_version

    # The local tag list is read before the fetch, which would otherwise
    # bring the remote's tags in and make every tag look local.
    local_tag, _ = git("tag", "--list", tag)

    _, code = git("fetch", REMOTE, "--quiet", "--tags", check=False)
    if code != 0:
        raise ReleaseError(
            "cannot fetch from %s; run `git fetch %s --tags` to see why"
            % (REMOTE, REMOTE))
    counts, code = git(
        "rev-list", "--left-right", "--count",
        "%s...%s" % (REMOTE_BRANCH_REF, BRANCH_REF), check=False)
    if code != 0:
        raise ReleaseError(
            "cannot compare with %s/%s; the remote has no %s branch yet, "
            "so push it once before cutting a release"
            % (REMOTE, BRANCH, BRANCH))
    behind, ahead = (int(n) for n in counts.split())
    if behind:
        raise ReleaseError(
            "%d commit(s) behind %s/%s; pull first"
            % (behind, REMOTE, BRANCH))

    remote_tag, _ = git("ls-remote", "--tags", REMOTE, "refs/tags/" + tag)
    if remote_tag.strip():
        raise ReleaseError(
            "tag %s is already on %s, so %s has been released"
            % (tag, REMOTE, new_version))
    if local_tag.strip():
        raise ReleaseError(
            "tag %s exists here but not on %s; delete it with "
            "`git tag -d %s` if that release was abandoned"
            % (tag, REMOTE, tag))

    # gh is checked now, not after the tag exists, so a missing login
    # cannot strand a half-published release.
    proc = run(["gh", "auth", "status"],
               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               universal_newlines=True)
    if proc.returncode != 0:
        raise ReleaseError(
            "gh is not logged in (gh auth status failed); run gh auth login")

    if run_tests:
        print("Running the test gate...")
        # The gate inherits this stdout, so flush first or its output
        # lands ahead of the line announcing it.
        sys.stdout.flush()
        gate = run([sys.executable, str(ROOT / "run-tests.py")], cwd=str(ROOT))
        if gate.returncode != 0:
            raise ReleaseError("the test gate failed; nothing was changed")

    return current, new_version, tag, ahead, untracked


def publish(new_version, tag):
    """Write, commit, tag, push, release; report how far it got on failure."""
    done = []
    try:
        for path in MANIFESTS:
            # Recorded before the write, and per manifest: whatever fails,
            # the report can never describe less than what was attempted.
            done.append("wrote %s/%s" % (path.parent.name, path.name))
            write_version(path, new_version)

        git("add", *[str(path) for path in MANIFESTS])
        done.append(STAGED)

        git("commit", "-m", "chore(release): %s" % tag)
        done.append(COMMITTED)

        git("tag", "-a", tag, "-m", tag)
        done.append(TAGGED)

        done.append(PUSHING)
        # The full ref: "main" alone is an ambiguous refspec when a
        # tag of the same name exists.
        git("push", REMOTE, BRANCH_REF)
        done[-1] = PUSHED

        done.append(TAG_PUSHING)
        git("push", REMOTE, "refs/tags/" + tag)
        done[-1] = TAG_PUSHED

        proc = run(["gh", "release", "create", tag,
                    "--title", tag, "--generate-notes"],
                   cwd=str(ROOT), stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, universal_newlines=True)
        if proc.returncode != 0:
            raise ReleaseError(
                "gh release create failed:\n%s" % (proc.stderr or "").strip())
        print((proc.stdout or "").strip())
    except KeyboardInterrupt:
        raise Interrupted("interrupted.\n\n%s" % recovery(done, tag))
    except Exception as exc:
        # A git command that reported failure did not leave the ref on the
        # remote; only an interrupt is genuinely ambiguous.
        settled = [step for step in done if not step.endswith("(in flight)")]
        raise ReleaseError("%s\n\n%s" % (exc, recovery(settled, tag)))


def finish(tag, with_tag_push):
    lines = []
    if with_tag_push:
        lines.append("  git push %s refs/tags/%s" % (REMOTE, tag))
    lines.append("  gh release create %s --title %s --generate-notes"
                 % (tag, tag))
    return lines


def undo(done, tag):
    lines = []
    if TAGGED in done:
        lines.append("  git tag -d %s" % tag)
    if COMMITTED in done:
        lines.append("  git reset --hard HEAD~1")
    elif any(step.startswith("wrote ") for step in done):
        # checkout HEAD, not checkout: the manifests may be staged, and a
        # plain checkout would restore them from the index.
        lines.append("  git checkout HEAD -- %s"
                     % " ".join(str(path) for path in MANIFESTS))
    return lines


def recovery(done, tag):
    """Say how far it got, and give commands that finish or reverse it."""
    if not done:
        return "Nothing was changed."
    lines = ["Completed: %s." % ", ".join(done)]
    if TAG_PUSHED in done:
        lines.append("%s and its tag are on %s; only the release is left:"
                     % (BRANCH, REMOTE))
        lines += finish(tag, with_tag_push=False)
    elif TAG_PUSHING in done:
        lines.append(
            "%s is on %s already, so there is no undo. The tag push was "
            "cut short and may or may not have landed; check with:"
            % (BRANCH, REMOTE))
        lines.append("  git ls-remote %s refs/tags/%s" % (REMOTE, tag))
        lines.append("Then finish the release, skipping the push if the "
                     "tag is already there:")
        lines += finish(tag, with_tag_push=True)
    elif PUSHED in done:
        lines.append(
            "%s is on %s already, so there is no undo. The tag exists "
            "here but not there. To finish the release:" % (BRANCH, REMOTE))
        lines += finish(tag, with_tag_push=True)
    elif PUSHING in done:
        lines.append(
            "The push was cut short and may or may not have landed. Compare:")
        lines.append("  git ls-remote %s %s" % (REMOTE, BRANCH_REF))
        lines.append("  git rev-parse %s" % BRANCH)
        lines.append("If they match, %s is public; finish the release with:"
                     % BRANCH)
        lines += finish(tag, with_tag_push=True)
        lines.append("If they do not, undo the local state:")
        lines += undo(done, tag)
    else:
        lines.append("Nothing was pushed. To undo the local state:")
        lines += undo(done, tag)
    return "\n".join(lines)


def build_parser():
    parser = ReleaseParser(
        prog="./release.py",
        description="Bump both plugin manifests, tag the commit, and "
                    "publish the GitHub release.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  ./release.py --patch --dry-run\n"
               "  ./release.py --minor\n")
    part = parser.add_mutually_exclusive_group(required=True)
    part.add_argument("--major", dest="part", action="store_const",
                      const="major",
                      help="breaking change: 1.4.2 -> 2.0.0")
    part.add_argument("--minor", dest="part", action="store_const",
                      const="minor",
                      help="new work, still compatible: 1.4.2 -> 1.5.0")
    part.add_argument("--patch", dest="part", action="store_const",
                      const="patch",
                      help="fixes only: 1.4.2 -> 1.4.3")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan and change nothing")
    parser.add_argument("--no-tests", dest="tests", action="store_false",
                        help="skip the test gate (not recommended)")
    parser.add_argument("--allow-untracked", action="store_true",
                        help="release with untracked files present")
    return parser


def current_version_line():
    """What the manifests say today, for the bare-invocation help.

    Never raises: help is the one place that has to render whatever
    state the repository is in, including a broken one.
    """
    try:
        versions = {path: read_version(path) for path in MANIFESTS}
    except ReleaseError as exc:
        return "Current version: cannot tell -- %s" % exc
    if len(set(versions.values())) == 1:
        return "Current version: %s" % versions[CLAUDE_MANIFEST]
    return "Current version: the manifests disagree -- %s" % ", ".join(
        "%s %s" % (path.parent.name, version)
        for path, version in versions.items())


def fail(message, status):
    # stdout is block-buffered when redirected; flush it or the plan
    # printed earlier lands after this message in the log.
    sys.stdout.flush()
    print("release: %s" % message, file=sys.stderr)
    return status


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    if not argv:
        parser.print_help()
        print("\n%s" % current_version_line())
        return 0
    args = parser.parse_args(argv)

    try:
        current, new_version, tag, ahead, untracked = preflight(
            args.part, args.tests and not args.dry_run,
        args.allow_untracked)
    except Interrupted as exc:
        return fail(exc, EX_INTERRUPTED)
    except ReleaseError as exc:
        return fail(exc, 1)
    except KeyboardInterrupt:
        return fail("interrupted. Nothing was changed.", EX_INTERRUPTED)

    print("\n%s -> %s  (%s)" % (current, new_version, tag))
    for path in MANIFESTS:
        print("  %s" % path)
    if ahead:
        print("  %d unpushed commit(s) go out with this release" % ahead)
    if untracked:
        print("  %d untracked path(s) stay behind (--allow-untracked)"
              % len(untracked))
    if args.dry_run:
        print("\n--dry-run: nothing was released. The test gate does not run"
              " in a dry run, and the preflight fetch has updated this"
              " clone's remote-tracking refs and tags.")
        return 0
    print("")

    try:
        publish(new_version, tag)
    except Interrupted as exc:
        return fail(exc, EX_INTERRUPTED)
    except ReleaseError as exc:
        return fail(exc, 1)
    print("\nReleased %s." % tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
