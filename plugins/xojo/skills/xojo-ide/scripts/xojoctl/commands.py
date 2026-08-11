"""Commands."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403
from .client import *  # noqa: F401,F403
from .scripts import *  # noqa: F401,F403
from .targets import *  # noqa: F401,F403
from .diagnostics import *  # noqa: F401,F403
from .render import *  # noqa: F401,F403
from .connection import *  # noqa: F401,F403


# Severity order for judging a multi-part reply: every part arrived under one
# tag and the WORST one is the verdict, whatever order the transport delivered
# them in. ERRORS last: when a reply carries a diagnostics payload and anything
# else, the diagnostics are the answer.
_VERDICT_SEVERITY = (Verdict.OK, Verdict.WARNINGS, Verdict.EMPTY,
                     Verdict.UNKNOWN, Verdict.OPEN_ERRORS,
                     Verdict.MISSING_FILES, Verdict.SCRIPT_ERROR,
                     Verdict.ERRORS)


def worst_of(parts: Sequence[Classification]) -> Optional[Classification]:
    """The most severe classification; first wins on equal severity."""
    return max(parts, key=lambda c: _VERDICT_SEVERITY.index(c.verdict),
               default=None)


def apply_classification(res: Result, cl: Classification,
                         warnings_as_errors: bool) -> None:
    res.diagnostics = normalize(cl)
    res.recount()
    c = res.counts

    if cl.verdict is Verdict.SCRIPT_ERROR:
        res.ok, res.outcome, res.exit_code = False, "script_error", EX_SCRIPT_ERROR
        res.summary = ("the IDE rejected the script xojoctl sent (%d script error%s)"
                       % (c["script_errors"], "" if c["script_errors"] == 1 else "s"))
        return
    if cl.verdict is Verdict.MISSING_FILES:
        res.ok, res.outcome, res.exit_code = False, "missing_files", EX_PROJECT_ERRORS
        res.summary = cl.note or "the build needs something configured first"
        return

    if cl.verdict is Verdict.OPEN_ERRORS:
        res.ok = not cl.fatal
        res.outcome = "open_errors"
        res.exit_code = EX_PROJECT_ERRORS if cl.fatal else EX_OK
        res.summary = ("project load %s (%d issue%s)"
                       % ("failed" if cl.fatal else "reported non-fatal issues",
                          c["open_errors"], "" if c["open_errors"] == 1 else "s"))
        return
    if cl.verdict is Verdict.ERRORS:
        res.ok, res.outcome, res.exit_code = False, "project_errors", EX_PROJECT_ERRORS
        res.summary = "%d error%s, %d warning%s" % (
            c["errors"], "" if c["errors"] == 1 else "s",
            c["warnings"], "" if c["warnings"] == 1 else "s")
        return
    if cl.verdict is Verdict.WARNINGS:
        script_only = cl.key == "scriptError"
        res.outcome = "script_warnings" if script_only else "project_warnings"
        res.summary = "%d warning%s, 0 errors" % (
            c["warnings"], "" if c["warnings"] == 1 else "s")
        if script_only:
            res.notes.append(note(Note.SCRIPT_COMPILER_WARNING))
        if warnings_as_errors:
            res.ok, res.exit_code = False, EX_PROJECT_ERRORS
            res.notes.append(note(Note.WARNINGS_PROMOTED))
        else:
            res.notes.append(note(Note.WARNINGS_ONLY_EXIT_ZERO))
        res.result["warnings_as_errors"] = warnings_as_errors
        return
    if cl.verdict is Verdict.EMPTY:
        res.ok, res.outcome, res.exit_code = False, "empty_response", EX_PROJECT_ERRORS
        res.summary = "the command returned an empty response and did nothing"
        res.notes.append(note(Note.EMPTY_RESPONSE))
        return
    if cl.verdict is Verdict.UNKNOWN:
        res.ok, res.outcome, res.exit_code = False, "unknown_response", EX_INCOMPLETE
        res.summary = cl.note or "the IDE returned an unrecognized response"
        return
    res.outcome, res.summary = "success", "no errors, no warnings"


def cmd_status(args: argparse.Namespace, res: Result) -> None:
    started = time.monotonic()
    wall = time.time()
    with connected(args, res, wall) as client:
        health_check(client, res)
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    res.summary = "connected to Xojo %s at %s" % (
        res.ide.get("version") or "?", res.connection.get("endpoint"))
    res.result = {"reachable": True}


def cmd_version(args: argparse.Namespace, res: Result) -> None:
    cmd_status(args, res)
    res.command = "version"
    res.summary = res.ide.get("version") or "unknown"
    res.result = {"version": res.ide.get("version")}


def cmd_analyze(args: argparse.Namespace, res: Result) -> None:
    item = getattr(args, "item", None)
    if item is not None and not item.strip():
        # An empty --item (an unset shell variable, usually) would silently
        # fall through to a whole-project analyze -- pass or fail on
        # diagnostics the caller never asked about.
        raise XojoError("--item requires a non-empty item name")
    project = getattr(args, "project", None)
    if project is not None and not getattr(args, "discard", False):
        raise XojoError(
            "analyze --project runs a bracketed session that ends in a "
            "discarding close, and discard-closes a stale already-open copy "
            "of the project first.\nPass --discard to confirm.")
    if getattr(args, "discard", False) and project is None:
        raise XojoError("--discard only means something with --project")
    path = _validated_project_path(project, "--project") if project else None
    if path:
        res.project = {"identified": True, "path": path, "reason": None}
    session: Optional[Dict[str, Any]] = None
    started = time.monotonic()
    wall = time.time()
    with connected(args, res, wall) as client:
        health_check(client, res)
        opened = False
        if path:
            session = {"project": path, "was_open": False, "closed": False}
            # Attached NOW so the record survives every raise: a timeout
            # document must still say the session left the project open.
            res.result["session"] = session
            if not _session_open(client, res, path, session):
                res.timing = {"started_at": _iso_utc(wall),
                              "elapsed_ms": int((time.monotonic() - started) * 1000)}
                return          # a fatal load classified itself
            opened = True
        require_project(client, res, "analyze")
        script = (script_analyze_item(item) if item
                  else script_analyze_project())
        ex = client.exchange(script, ceiling=getattr(args, "analyze_timeout", WORK_CEILING))
        # A dirty analyze legitimately arrives as TWO same-tag messages (the
        # buildError and the Print sentinel), and their order is not
        # guaranteed. Judge every part below, not whichever message won the
        # race to be claimed -- sentinel-first must not read as clean.
        def _extras() -> List[Message]:
            return [m for m in client.collect_tag(ex.tag)
                    if m is not ex.reply
                    and not (isinstance(m.envelope, dict)
                             and m.envelope.get("response") == ANALYZE_SENTINEL)]

        extras = _extras()
        if not extras and (ex.result.verdict is Verdict.OK
                           and ex.result.text == ANALYZE_SENTINEL):
            # The claimed reply is the sentinel and nothing else has arrived:
            # either the analysis is clean, or it is dirty and the buildError
            # lost the race by MORE than the split window. Give it the
            # trailing window (2s, against observed millisecond jitter)
            # before declaring the project clean.
            #
            # That window is the real bound on this guarantee. A buildError
            # arriving later still lands in the journal and is reported as
            # an unsolicited message, but the verdict has already been
            # decided by then. The IDE has never been observed splitting a
            # reply that far apart; a genuinely slow analysis holds the
            # whole reply back instead.
            client.collect_tag(ex.tag, quiet=TRAILING_WINDOW)
            extras = _extras()
        if extras:
            res.notes.append(note(Note.SPLIT_REPLY, count=len(extras)))
        if opened:
            # The close is inside the session's bracket, at the end of the
            # body on purpose: a ReplyTimeout on the analyze skips it, since
            # a busy IDE answers the next few scripts with empty responses.
            session["closed"] = _session_close(client)
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000),
                  "reply_ms": int(ex.elapsed * 1000)}
    res.result = {"scope": "item" if item else "project",
                  "item": item, "complete": ex.complete}
    if session is not None:
        res.result["session"] = session

    cl = ex.result
    parts = [cl] + [classify(m) for m in extras]
    if any(c.verdict is Verdict.OK and c.text == ANALYZE_ITEM_MISSING
           for c in parts):
        raise XojoError(
            "no project item named %r in the front project, so nothing was "
            "analyzed. SelectProjectItem matches the navigator name exactly."
            % args.item)
    # The sentinel means analysis ran and found nothing. Distinguishing it from
    # an empty {} is exactly why the trailing Print exists. (extras never
    # contain the sentinel; only the claimed reply can be it.)
    if cl.verdict is Verdict.OK and cl.text == ANALYZE_SENTINEL:
        parts[0] = Classification(
            Verdict.OK, key="buildError",
            note="analysis reported zero errors and zero warnings")
    cl = worst_of(parts) or cl
    apply_classification(res, cl, getattr(args, "warnings_as_errors", False))

    sev = getattr(args, "severity", "all")
    if sev == "errors":
        res.diagnostics = [d for d in res.diagnostics if d["severity"] == "error"]
    elif sev == "warnings":
        res.diagnostics = [d for d in res.diagnostics if d["severity"] == "warning"]

    if session is not None and not session["closed"]:
        # The bracket broke: the project stayed open, which must not read
        # as safe-to-edit. The note goes on EVERY such document; the exit
        # promotion only where the analyze itself was clean -- a nonzero
        # analyze verdict is never overridden. The exit-0 advisory is
        # dropped the way cmd_build drops it: its text is false once the
        # exit code flips.
        res.notes = [n for n in res.notes
                     if n.get("code") != Note.WARNINGS_ONLY_EXIT_ZERO[0]]
        res.notes.append(note(Note.SESSION_NOT_CLOSED))
        if res.exit_code == EX_OK:
            res.ok = False
            res.outcome, res.exit_code = "incomplete", EX_INCOMPLETE


def cmd_build(args: argparse.Namespace, res: Result) -> None:
    started = time.monotonic()
    wall = time.time()
    targets = [resolve_target(t) for t in args.target]
    res.notes.append(note(Note.WARNINGS_NOT_REPORTED))
    artifacts: List[Dict[str, Any]] = []
    missing_artifact = False
    sentinel_lost = False
    worst: Optional[Classification] = None
    with connected(args, res, wall) as client:
        health_check(client, res)
        require_project(client, res, "build")
        for t in targets:
            ex = client.exchange(script_build(t.value, args.reveal),
                                 ceiling=getattr(args, "build_timeout", BUILD_CEILING))
            if ex.result.verdict is Verdict.SCRIPT_ERROR:
                # A rejected script never runs, so its Print sentinel can
                # never arrive -- waiting for it was 60s of guaranteed dead
                # time per target. The IDE is also idle (it did no work), so
                # it is safe to continue to the next target.
                completed = False
            else:
                # Wait for the trailing sentinel: it proves the script
                # finished and the IDE is idle, so the next target is not
                # issued into a busy IDE.
                completed = client.await_sentinel(ex.tag, BUILD_SENTINEL)
            entry: Dict[str, Any] = {"target": t.name, "value": t.value,
                                     "path": None, "raw_path": None, "ok": False,
                                     "script_completed": completed}
            # Judge every same-tag part. The sentinel can be delivered BEFORE
            # the real answer, and judging whichever was claimed first turned
            # a successful build into "empty response" -- or hid the errors.
            # The sentinel itself is completion proof, not an answer.
            def _is_sentinel(m: Message) -> bool:
                return (isinstance(m.envelope, dict)
                        and m.envelope.get("response") == BUILD_SENTINEL)

            # Only parts that plausibly belong to THIS exchange count. The
            # IDE reuses retired tags for unsolicited messages, and an
            # unsolicited string was otherwise reported as a build artifact
            # for a build that produced no binary.
            claimed_at = ex.reply.at

            def _ours(m: Message) -> bool:
                return m is ex.reply or abs(m.at - claimed_at) <= TRAILING_WINDOW

            def _parts(quiet: Optional[float] = None) -> List[Message]:
                got = (client.collect_tag(ex.tag) if quiet is None
                       else client.collect_tag(ex.tag, quiet=quiet))
                return [m for m in got if _ours(m)] or [ex.reply]

            tagged = _parts()
            answers = [classify(m) for m in tagged if not _is_sentinel(m)]
            if not answers:
                # Only the sentinel arrived. Either BuildApp printed nothing,
                # or the answer is trailing its own sentinel -- so give it the
                # trailing window before calling the build empty.
                tagged = _parts(quiet=TRAILING_WINDOW)
                answers = [classify(m) for m in tagged if not _is_sentinel(m)]
            extras = [m for m in tagged if m is not ex.reply
                      and not _is_sentinel(m)]
            if extras:
                res.notes.append(note(Note.SPLIT_REPLY, target=t.name,
                                      count=len(extras)))
            path_cl = next((c for c in answers
                            if c.verdict is Verdict.OK and c.text), None)
            if path_cl is not None:
                entry["raw_path"] = path_cl.text
                entry["path"] = unescape_shell_path(path_cl.text)
                entry["ok"] = True
            else:
                missing_artifact = True
            # Diagnostics count whether or not a path came back: a reply
            # carrying BOTH an artifact and compile errors used to report
            # success with an empty diagnostics list.
            cl = worst_of([c for c in answers if c.verdict is not Verdict.OK])
            if cl is None and path_cl is None:
                # The script finished; BuildApp itself printed nothing
                # (a sentinel-only reply). A real answer, distinct from
                # "we gave up waiting".
                cl = Classification(
                    Verdict.EMPTY,
                    note="BuildApp produced no output for target %d, "
                         "although the script ran to completion" % t.value)
            if cl is not None and (
                    worst is None or _VERDICT_SEVERITY.index(cl.verdict)
                    > _VERDICT_SEVERITY.index(worst.verdict)):
                worst = cl
            artifacts.append(entry)
            if not completed and ex.result.verdict is not Verdict.SCRIPT_ERROR:
                # No sentinel: the IDE may still be busy with this build, and
                # a busy IDE answers the next BuildApp with the empty
                # responses the ceilings were sized to prevent. Stop rather
                # than manufacture failures for the remaining targets.
                sentinel_lost = True
                res.notes.append(note(Note.SENTINEL_NOT_SEEN, target=t.name))
                break
            if (missing_artifact or worst is not None) and args.stop_on_error:
                break

    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    res.result = {"artifacts": artifacts,
                  "targets": [t.name for t in targets],
                  "reveal": args.reveal}
    if worst is not None:
        apply_classification(res, worst, getattr(args, "warnings_as_errors", False))
        built = sum(1 for a in artifacts if a["ok"])
        res.summary = "%d of %d targets built; %s" % (built, len(artifacts), res.summary)
        if missing_artifact and res.exit_code == EX_OK:
            # A target that produced no artifact must never exit 0, whatever
            # the worst classification maps to on its own (WARNINGS and
            # non-fatal openErrors are ok by themselves; a build that made
            # nothing is not). Drop the exit-0 advisory the classification
            # attached -- its text is false once the exit code flips.
            res.ok, res.outcome, res.exit_code = (
                False, "build_failed", EX_PROJECT_ERRORS)
            res.notes = [n for n in res.notes
                         if n.get("code") != Note.WARNINGS_ONLY_EXIT_ZERO[0]]
    elif missing_artifact:
        res.ok, res.outcome, res.exit_code = (
            False, "build_failed", EX_PROJECT_ERRORS)
        built = sum(1 for a in artifacts if a["ok"])
        res.summary = "%d of %d targets built" % (built, len(artifacts))
    else:
        res.summary = "built %d target%s" % (
            len(artifacts), "" if len(artifacts) == 1 else "s")
    if sentinel_lost:
        skipped = len(targets) - len(artifacts)
        if skipped:
            res.summary += "; %d target%s skipped" % (
                skipped, "" if skipped == 1 else "s")
        if res.exit_code == EX_OK:
            res.ok, res.outcome, res.exit_code = False, "incomplete", EX_INCOMPLETE
            res.summary += " (completion unconfirmed: no sentinel)"


def cmd_script(args: argparse.Namespace, res: Result) -> None:
    if args.file is not None and not args.file.strip():
        raise XojoError("--file requires a non-empty path")
    if args.file:
        # utf-8-sig, NOT utf-8: on Windows every ordinary way of producing a
        # file writes UTF-8 WITH a BOM (`>`, Out-File, Set-Content -Encoding
        # utf8), and a BOM left on the front of line 1 becomes part of the
        # first statement. Verified: it fails as "This item does not exist",
        # which points at the code rather than the encoding. utf-8-sig also
        # reads plain UTF-8 unchanged, so this is safe everywhere.
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            source = fh.read()
        origin = args.file
    elif args.stdin:
        # A PowerShell pipe carries the same BOM, and stdin has already been
        # decoded by the time we see it, so strip the character itself.
        source = strip_bom(sys.stdin.read())
        origin = "stdin"
    else:
        source = args.source
        origin = "argv"
    if source is None or not source.strip():
        # An empty script (an unset shell variable, usually) can never Print,
        # so it can never reply -- sending it would block for the full
        # first-reply ceiling before failing. Reject it up front instead.
        raise XojoError(
            "the script is empty (from %s). The IDE replies only when a "
            "script Prints, so an empty script would hang to the ceiling."
            % origin)
    started = time.monotonic()
    wall = time.time()
    # Append a completion sentinel, exactly as analyze and build do. The IDE
    # replies ONLY when a script Prints, so without one a silent script sends
    # nothing at all and "finished" is indistinguishable from "still running"
    # -- the read just blocks to the ceiling. With one, every script answers.
    # The sentinel goes on the END, so the caller's line numbers are unmoved.
    sentinel = "__xojoctl_script_%s__" % secrets.token_hex(8)
    wire = "%s\nPrint %s" % (source, xojo_string_literal(sentinel))
    with connected(args, res, wall) as client:
        health_check(client, res)
        ex = client.exchange(wire)
        # One reply can arrive as several same-tag messages: Print output and
        # a compile-time warning come back separately, and the output only
        # lands when the script FINISHES. Wait for the sentinel, then judge
        # every part together.
        def _is_sentinel(m: Message) -> bool:
            cl = classify(m)
            return cl.verdict is Verdict.OK and cl.text == sentinel

        collected = client.collect_tag(ex.tag)
        completed = any(_is_sentinel(m) for m in collected)
        rejected = any(classify(m).verdict is Verdict.SCRIPT_ERROR
                       for m in collected)
        if not completed and rejected:
            # A script the IDE REJECTED never runs, so its sentinel can
            # never arrive. Waiting for one is guaranteed dead time; build
            # skips the wait for the same reason.
            pass
        elif not completed:
            budget = max(0.0, getattr(args, "warm_timeout", REPLY_CEILING)
                         - ex.elapsed)
            completed = client.await_reply_part(
                ex.tag, _is_sentinel, budget) is not None
        tagged = client.collect_tag(ex.tag)
        parts = [classify(m) for m in tagged if not _is_sentinel(m)]
        if not completed and not rejected:
            # The script never reached its final Print. It may still be
            # running, or it returned early, or it died at runtime.
            res.notes.append(note(Note.SCRIPT_NOT_COMPLETED))
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000),
                  "reply_ms": int(ex.elapsed * 1000)}
    # Several Prints yield several parts; keep them all, in arrival order.
    outputs = [c.text for c in parts
               if c.verdict is Verdict.OK and c.text is not None]
    text = "\n".join(outputs) if outputs else None
    chosen = worst_of(parts) or Classification(Verdict.OK, text=text)
    res.result = {"source": source, "source_origin": origin, "output": text,
                  "reply_parts": len(parts), "completed": completed}
    apply_classification(res, chosen, getattr(args, "warnings_as_errors", False))
    if res.outcome == "success":
        res.summary = "script completed"


def _judged_parts(client: Client, ex: Exchange) -> List[Classification]:
    """Every part of a reply that is plausibly ours, classified.

    Every script here ends in a Print, so an operation that ALSO produced
    diagnostics arrives as TWO same-tag messages whose order is not
    guaranteed. Judging only the claimed reply reported exit 0 with zero
    diagnostics for a RunApp that failed to compile, and for a project
    whose load was FATAL, purely because the Print won the race. Only
    parts inside the trailing window count: the IDE reuses retired tags,
    and an unsolicited message must never flip a verdict.
    """
    claimed_at = ex.reply.at

    def _ours(m: Message) -> bool:
        return m is ex.reply or abs(m.at - claimed_at) <= TRAILING_WINDOW

    return [classify(m) for m in client.collect_tag(ex.tag)
            if _ours(m)] or [ex.result]


def _validated_project_path(raw: str, what: str) -> str:
    if not raw.strip():
        # abspath("") is the current directory, which exists -- an empty
        # argument would otherwise send OpenFile(<cwd>) to the IDE.
        raise XojoError("%s requires a non-empty project path" % what)
    path = os.path.abspath(os.path.expanduser(raw))
    if not os.path.exists(path):
        raise XojoError(
            "%s does not exist.\nOpenFile on a missing path returns an empty "
            "scriptRuntimeError, which is hard to diagnose." % path)
    return path


def _same_project_path(a: Optional[str], b: str) -> bool:
    """Whether two paths name the same project file.

    samefile is the robust comparison (file identity: symlinks, case, 8.3
    names) but needs both paths to exist and can raise. The fallback
    normalizes NFC -- a macOS filesystem hands the IDE NFD while the
    terminal produces NFC -- and normcase, for Windows.
    """
    if not a:
        return False
    try:
        return os.path.samefile(a, b)
    except OSError:
        def norm(p: str) -> str:
            return unicodedata.normalize(
                "NFC", os.path.normcase(os.path.realpath(p)))
        return norm(a) == norm(b)


def _front_project_path(client: Client) -> Optional[str]:
    """The front project's path, or None when it has never been saved."""
    text = reply_text(client, client.exchange(script_front_path()))
    return unescape_shell_path(text) if text else None


def _session_open(client: Client, res: Result, path: str,
                  session: Dict[str, Any]) -> bool:
    """Make PATH the front project, freshly loaded from disk.

    OpenFile on an already-open project is a no-op, so an open-then-analyze
    against a project the IDE already holds would silently judge the stale
    in-memory copy, not the disk. The rules: only PATH itself is ever
    discard-closed -- a non-matching front project belongs to someone else
    and is never touched -- and success means the workspace count grew AND
    the front path is PATH. Returns True once verified; returns False after
    classifying a fatal load; raises for what a classification cannot say.
    """
    count = project_window_count(client)
    if count is None:
        raise ProtocolError("could not count the open workspaces, so this "
                            "session cannot prove what it analyzed")
    if count > 0 and _same_project_path(_front_project_path(client), path):
        client.exchange(script_close_project(save=False))
        session["was_open"] = True
    front = None
    for attempt in (1, 2):
        before = project_window_count(client)
        if before is None:
            raise ProtocolError("could not count the open workspaces, so "
                                "this session cannot prove what it analyzed")
        ex = client.exchange(script_open_project(path))
        worst = worst_of(_judged_parts(client, ex))
        if worst is not None and worst.verdict is Verdict.OPEN_ERRORS:
            if worst.fatal:
                # The project would not load; that verdict IS the result.
                apply_classification(res, worst, False)
                return False
            # A partially loaded project can under-report deprecations;
            # the session must not read cleaner than a manual open would.
            session["open_issues"] = True
        after = project_window_count(client)
        front = _front_project_path(client)
        if after == before + 1 and _same_project_path(front, path):
            return True
        if attempt == 1 and _same_project_path(front, path):
            # The count did not grow but PATH is frontmost: the IDE raised
            # an already-open stale copy. Close it and open once more.
            client.exchange(script_close_project(save=False))
            continue
        break
    raise XojoError(
        "could not open %s fresh as the front project (frontmost: %s).\n"
        "Close the copy the IDE has open, or bring it front with "
        "'%s projects --select' and close it, then retry."
        % (path, front or "unknown", INVOCATION))


def _session_close(client: Client) -> bool:
    """Best-effort discarding close; cleanup must never mask the verdict."""
    try:
        ex = client.exchange(script_close_project(save=False))
        worst = worst_of(_judged_parts(client, ex))
        return worst is None or worst.verdict in (Verdict.OK, Verdict.WARNINGS)
    except (XojoError, OSError):
        return False


def _simple(args: argparse.Namespace, res: Result, script: str, ok_summary: str,
            needs_project: Optional[str] = None,
            ceiling: Optional[float] = None) -> None:
    started = time.monotonic()
    wall = time.time()
    with connected(args, res, wall) as client:
        health_check(client, res)
        if needs_project:
            require_project(client, res, needs_project)
        ex = client.exchange(script, ceiling=ceiling)
        parts = _judged_parts(client, ex)
    if len(parts) > 1:
        res.notes.append(note(Note.SPLIT_REPLY, count=len(parts) - 1))
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    res.result = {"output": next(
        (c.text for c in parts
         if c.verdict is Verdict.OK and c.text is not None), ex.result.text)}
    apply_classification(res, worst_of(parts) or ex.result,
                         getattr(args, "warnings_as_errors", False))
    if res.outcome == "success":
        res.summary = ok_summary


def cmd_run(args: argparse.Namespace, res: Result) -> None:
    res.notes.append(note(Note.WARNINGS_NOT_REPORTED))
    # RunApp compiles before it launches, so it needs a build-sized ceiling.
    _simple(args, res, script_run(), "project is running in the debugger", "run",
            ceiling=BUILD_CEILING)


def cmd_stop(args: argparse.Namespace, res: Result) -> None:
    _simple(args, res, script_stop(), "stopped the running project")


def cmd_open(args: argparse.Namespace, res: Result) -> None:
    path = _validated_project_path(args.project, "open")
    res.project = {"identified": True, "path": path, "reason": None}
    _simple(args, res, script_open_project(path), "opened %s" % path)


def reply_text(client: Client, ex: Exchange) -> Optional[str]:
    """The OK text of a reply, judged over EVERY part it arrived as.

    A compiler warning can arrive as a separate message under the same tag
    and win the race to be claimed. Reading only the claimed reply turned
    working commands into false errors -- a successful select reported as
    "no open workspace matches", an empty title list, a null project path.
    project_window_count solves the same problem the same way.
    """
    for cl in [classify(m) for m in client.collect_tag(ex.tag)] or [ex.result]:
        if cl.verdict is Verdict.OK and cl.text is not None:
            return cl.text
    return None


def cmd_projects(args: argparse.Namespace, res: Result) -> None:
    if args.select is not None and not args.select.strip():
        # Empty --select (an unset shell variable) would silently select
        # nothing and list as if the flag had never been passed.
        raise XojoError("--select requires a non-empty title or index")
    started = time.monotonic()
    wall = time.time()
    with connected(args, res, wall) as client:
        health_check(client, res)
        if args.select and _ascii_digits(args.select):
            # SelectWindow ignores an out-of-range INDEX silently, and the
            # echo check below cannot catch that the way it catches a bad
            # title. WindowCount is the authority: counting the tab-joined
            # title list instead miscounts as soon as one title contains a
            # tab, which a file name may. Validate BEFORE selecting.
            count = project_window_count(client)
            if count == 0:
                # Same state bare `projects` reports as no_project_open;
                # a range error here would garble into "(indexes 0--1)"
                # and misfile the failure as exit 64.
                raise NoProjectOpen(
                    "no project is open in the Xojo IDE, so there is "
                    "nothing to select.\nOpen one first:  %s open "
                    "<path>.xojo_project" % INVOCATION)
            if count is not None and int(args.select) >= count:
                raise XojoError(
                    "--select %s is out of range: %d workspace%s open "
                    "(indexes 0-%d)."
                    % (args.select, count, "" if count == 1 else "s",
                       count - 1))
        if args.select:
            ex = client.exchange(script_select_window(args.select))
            # SelectWindow with a title that matches nothing is a SILENT
            # no-op, and the probe's WindowTitle(0) then prints whatever was
            # already frontmost -- so verdict-plus-text alone reported
            # success for a mistyped title while the wrong workspace stayed
            # selected, and a follow-up save or close --discard acted on the
            # wrong project. Title matching is exact apart from case, with
            # no prefix matching, so a mismatched echo is an error. This
            # mirrors the --item precedent.
            front = reply_text(client, ex)
            if not front:
                raise XojoError("no open workspace matches %r" % args.select)
            # NFC-normalize both sides: a macOS filesystem hands the IDE an
            # NFD title while the terminal produces NFC, and those must not
            # read as a mismatch.
            if (not _ascii_digits(args.select)
                    and unicodedata.normalize("NFC", front).casefold()
                    != unicodedata.normalize("NFC", args.select).casefold()):
                raise XojoError(
                    "--select %r did not change the front workspace; the "
                    "front is still %r. SelectWindow matches the window "
                    "title exactly (case-insensitive). Run '%s projects' to "
                    "list the open titles."
                    % (args.select, sanitize(front), INVOCATION))
        titles_ex = client.exchange(script_list_windows())
        raw = reply_text(client, titles_ex) or ""
        # Workspace titles are project-controlled text that gets printed and
        # column-aligned; sanitize before either. raw.messages keeps verbatim.
        titles = [sanitize(t) for t in raw.split("\t") if t]
        front_ex = client.exchange(script_front_path())
        front_raw = reply_text(client, front_ex)

    entries = [{"index": i, "title": t, "front": i == 0,
                "path": unescape_shell_path(front_raw) if (i == 0 and front_raw) else None}
               for i, t in enumerate(titles)]
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    res.result = {"count": len(entries), "projects": entries,
                  "selected": args.select}
    if entries:
        res.project = {"identified": True, "path": entries[0]["path"],
                       "window_count": len(entries), "reason": None}
    res.summary = ("%d project%s open; front is %r"
                   % (len(entries), "" if len(entries) == 1 else "s",
                      entries[0]["title"]) if entries else "no projects open")
    if not entries:
        res.ok, res.outcome, res.exit_code = False, "no_project_open", EX_NO_PROJECT
        res.error = {"code": "no_project_open",
                     "message": "no project is open in the Xojo IDE",
                     "remedy": ["%s open <path>.xojo_project" % INVOCATION]}


def render_projects(res: Result, st: Style, out: Any) -> None:
    rows = res.result.get("projects", [])
    if not rows:
        print("no projects open", file=out)
        return
    w = max(max(len(r["title"]) for r in rows), len("PROJECT")) + 2
    print(st.dim("%-3s %s%s" % ("#", "PROJECT".ljust(w), "PATH")), file=out)
    for r in rows:
        mark = st.green("*") if r["front"] else " "
        # The path is IDE-supplied (ProjectShellPath) and filesystems allow CR
        # and ESC in names; sanitize at print time like the other echo paths.
        print("%-3s%s%s%s" % (r["index"], mark, " " + st.bold(r["title"].ljust(w - 1)),
                              sanitize(r["path"]) if r["path"] else ""), file=out)
    print("\n  %s" % st.dim("* frontmost -- commands act on this workspace"), file=out)


def cmd_save(args: argparse.Namespace, res: Result) -> None:
    _simple(args, res, script_save_project(), "saved the front project", "save")


def cmd_close(args: argparse.Namespace, res: Result) -> None:
    _simple(args, res, script_close_project(save=args.save),
            "closed the front project (%s)" % ("saving" if args.save else "discarding"),
            "close")


def cmd_reload(args: argparse.Namespace, res: Result) -> None:
    item = getattr(args, "item", None)
    if item is not None and not item.strip():
        # Same trap as analyze --item: an unset shell variable would silently
        # fall through to a whole-project reload.
        raise XojoError("--item requires a non-empty item name")
    if not args.discard:
        # The same confirmation as a discarding close, on purpose: the flag
        # that names the data loss is the acknowledgment of it.
        raise XojoError(
            "reload re-reads the project from disk and discards unsaved "
            "changes in the IDE without prompting.\n"
            "Pass --discard to confirm.")
    started = time.monotonic()
    wall = time.time()
    path = None
    with connected(args, res, wall) as client:
        health_check(client, res)
        raw = (res.ide or {}).get("version") or ""
        try:
            # ReloadProject arrived in 2026r3. An older IDE would reject the
            # script as a compile error, and an unreadable version reply
            # takes the fallback too -- it works on every release.
            supported = float(raw) >= RELOAD_MIN_XOJO_VERSION
        except ValueError:
            supported = False
        if item and not supported:
            raise XojoError(
                "reload --item needs Xojo %s or later; this IDE is %s.\n"
                "A whole-project 'reload --discard' works here: it closes "
                "the project without saving and reopens it."
                % (RELOAD_MIN_XOJO_NAME, raw or "unreadable"))
        require_project(client, res, "reload")
        if supported:
            ex = client.exchange(script_reload_item(item) if item
                                 else script_reload_project())
            parts = _judged_parts(client, ex)
            mechanism = "reload_project"
        else:
            path = _front_project_path(client)
            if not path:
                raise XojoError(
                    "the front project has no saved path to reload from; "
                    "save it once in the IDE first.")
            ex = client.exchange(script_close_and_reopen())
            parts = _judged_parts(client, ex)
            if any(c.verdict is Verdict.OK and c.text == RELOAD_NO_PATH
                   for c in parts):
                raise XojoError(
                    "the front project has no saved path to reload from; "
                    "save it once in the IDE first.")
            front = _front_project_path(client)
            if not _same_project_path(front, path):
                raise XojoError(
                    "after the close and reopen the front project is %s, "
                    "not %s; check the IDE before editing anything."
                    % (front or "unknown", path))
            mechanism = "close_and_reopen"
    if len(parts) > 1:
        res.notes.append(note(Note.SPLIT_REPLY, count=len(parts) - 1))
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    res.result = {"output": next(
        (c.text for c in parts
         if c.verdict is Verdict.OK and c.text is not None), ex.result.text),
        "scope": "item" if item else "project",
        "item": item, "mechanism": mechanism}
    if path:
        res.result["path"] = path
    apply_classification(res, worst_of(parts) or ex.result, False)
    if item and res.result.get("output") == RELOAD_ITEM_MISSING:
        raise XojoError(
            "no project item matching %r in the front project, so nothing "
            "was reloaded. ReloadProjectItem takes the item's path, per the "
            "2026r3 release notes." % item)
    if res.outcome == "success":
        if item:
            res.summary = "reloaded %s from disk" % item
        elif mechanism == "close_and_reopen":
            res.summary = ("reloaded the front project from disk "
                           "(close and reopen)")
        else:
            res.summary = "reloaded the front project from disk"


def cmd_capture(args: argparse.Namespace, res: Result) -> None:
    started = time.monotonic()
    wall = time.time()
    with connected(args, res, wall) as client:
        health_check(client, res)
        if args.script:
            try:
                client.exchange(args.script, ceiling=args.seconds)
            except ReplyTimeout:
                pass
        if not args.quiet:
            _stderr_note("capturing for %.0fs -- use the IDE now if you want "
                         "to see unsolicited events" % args.seconds)
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            time.sleep(min(0.5, max(0.0, end - time.monotonic())))
    res.timing = {"started_at": _iso_utc(wall),
                  "elapsed_ms": int((time.monotonic() - started) * 1000)}
    # The health check (and any --script) contributes tagged messages of our
    # own making; count the IDE-initiated traffic separately so an idle IDE
    # does not read as having produced events.
    msgs = res.raw["messages"]
    unsolicited = sum(1 for m in msgs if m["channel"] == "out-of-band")
    res.result = {"seconds": args.seconds,
                  "message_count": len(msgs),
                  "unsolicited_count": unsolicited}
    res.summary = ("captured %d message(s), %d unsolicited"
                   % (len(msgs), unsolicited))


def cmd_targets(args: argparse.Namespace, res: Result) -> None:
    rows = host_targets() if args.host else list(TARGETS)
    if args.query:
        q = args.query.strip().lower()
        try:
            resolved = resolve_target(q)
            # Resolve within the --host filter, not around it: an exact
            # match for another platform's target filters to nothing
            # rather than silently overriding the flag.
            rows = [resolved] if resolved in rows else []
        except ValueError:
            rows = [t for t in rows
                    if q in t.name or q in t.platform.lower()]
    order = getattr(args, "sort", "platform")
    if order == "platform":
        rows = sorted(rows, key=target_sort_key)
    elif order == "value":
        rows = sorted(rows, key=lambda t: t.value)
    else:
        rows = sorted(rows, key=lambda t: t.name)
    res.result = {"sort": order, "targets": [
        {"value": t.value, "name": t.name, "platform": t.platform,
         "arch": t.arch,
         "cpu": t.cpu, "bits": t.bits, "simulator": t.simulator}
        for t in rows]}
    res.connection = {"attempted": False, "connected": False, "transport": None,
                      "endpoint": None, "ipc_name": None, "port": None,
                      "handshake": "not_attempted", "protocol": None}
    res.summary = "%d build target%s" % (len(rows), "" if len(rows) == 1 else "s")


def render_targets(res: Result, st: Style, out: Any) -> None:
    rows = res.result.get("targets", [])
    if not rows:
        print("no matching targets", file=out)
        return
    # Widths must consider the HEADER too: filtered views can have data
    # narrower than its own column title (e.g. "macOS" under "PLATFORM").
    p = max(max(len(t["platform"]) for t in rows), len("PLATFORM")) + 2
    a = max(max(len(t["arch"]) for t in rows), len("ARCH")) + 2
    n = max(max(len(t["name"]) for t in rows), len("NAME")) + 2
    # ljust() already supplies the inter-column gap, so no line adds one.
    print(st.dim("%s%s%s%s" % ("PLATFORM".ljust(p), "ARCH".ljust(a),
                               "NAME".ljust(n), "VALUE")), file=out)
    for t in rows:
        print("%s%s%s%s" % (t["platform"].ljust(p), t["arch"].ljust(a),
                            st.bold(t["name"].ljust(n)), t["value"]), file=out)


__all__ = [
    "_VERDICT_SEVERITY",
    "_front_project_path",
    "_judged_parts",
    "_same_project_path",
    "_session_close",
    "_session_open",
    "_simple",
    "_validated_project_path",
    "apply_classification",
    "cmd_analyze",
    "cmd_build",
    "cmd_capture",
    "cmd_close",
    "cmd_open",
    "cmd_projects",
    "cmd_reload",
    "cmd_run",
    "cmd_save",
    "cmd_script",
    "cmd_status",
    "cmd_stop",
    "cmd_targets",
    "cmd_version",
    "render_projects",
    "render_targets",
    "reply_text",
    "worst_of",
]
