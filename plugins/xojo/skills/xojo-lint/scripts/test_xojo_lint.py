#!/usr/bin/env python3
"""Regression tests for xojo_lint.py."""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import xojo_lint

SCRIPTS = Path(__file__).resolve().parent


class XojoLintTests(unittest.TestCase):
    def validate(
        self, path: Path, *, warn_unknown: bool = False
    ) -> list[xojo_lint.Diagnostic]:
        return xojo_lint.validate_file(
            path, warn_unknown=warn_unknown, check_paths=False
        )

    def test_valid_tagged_file_accepts_unknown_properties(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Future.xojo_code"
            path.write_text(
                "#tag Class\n"
                "Protected Class Future\n"
                "FutureProperty = NewValue\n"
                "\t#tag FutureMetadata, NewKey = NewValue\n"
                "#tag EndClass\n",
                encoding="utf-8",
            )
            self.assertEqual(self.validate(path), [])
            warnings = self.validate(path, warn_unknown=True)
            self.assertEqual([item.code for item in warnings], ["XJT101"])
            self.assertEqual(warnings[0].severity, "warning")

    def test_known_opaque_and_unknown_extensions_have_distinct_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            known = Path(folder) / "Legacy.xojo_xml_code"
            known.write_text("<?xml version='1.0'?><block/>", encoding="utf-8")
            unknown = Path(folder) / "Future.xojo_new_container"
            unknown.write_bytes(b"opaque")

            self.assertEqual(self.validate(known), [])
            self.assertEqual(self.validate(unknown), [])
            self.assertEqual(
                [item.code for item in self.validate(known, warn_unknown=True)],
                ["XJC102"],
            )
            self.assertEqual(
                [item.code for item in self.validate(unknown, warn_unknown=True)],
                ["XJC103"],
            )

    def test_mismatched_known_tag_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Broken.xojo_code"
            path.write_text(
                "#tag Class\n\t#tag Method\n\t#tag EndProperty\n#tag EndClass\n",
                encoding="utf-8",
            )
            codes = {item.code for item in self.validate(path)}
            self.assertIn("XJT002", codes)

    def test_future_project_version_warns_but_unknown_key_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Future.xojo_project"
            path.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2099.123\n"
                "BrandNewProjectSetting={structured:value}\n",
                encoding="utf-8",
            )
            diagnostics = self.validate(path)
            self.assertEqual([item.code for item in diagnostics], ["XJP102"])
            self.assertEqual(diagnostics[0].severity, "warning")

    def test_project_item_extra_fields_are_forward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Extra.xojo_project"
            path.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Picture=Logo;logo.png;&h1;&h0;false;0;&h0;future\n",
                encoding="utf-8",
            )
            self.assertEqual(self.validate(path), [])

    def test_resources_checks_chunk_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder) / "Placeholder.xojo_resources"
            empty.write_bytes(b"")
            empty_diagnostics = self.validate(empty)
            self.assertEqual([item.code for item in empty_diagnostics], ["XJR102"])
            self.assertEqual(empty_diagnostics[0].severity, "warning")

            good = Path(folder) / "Good.xojo_resources"
            chunk = b"DATA" + struct.pack(">I", 0)
            good.write_bytes(b"ICNS" + struct.pack(">II", 8, len(chunk)) + chunk)
            self.assertEqual(self.validate(good), [])

            legacy = Path(folder) / "Legacy.xojo_resources"
            legacy.write_bytes(b"ICNS" + struct.pack(">II", 8, 0) + chunk)
            legacy_diagnostics = self.validate(legacy)
            self.assertEqual(
                [item.code for item in legacy_diagnostics], ["XJR103"]
            )
            self.assertEqual(legacy_diagnostics[0].severity, "warning")

            bad = Path(folder) / "Bad.xojo_resources"
            bad.write_bytes(good.read_bytes()[:-1])
            codes = {item.code for item in self.validate(bad)}
            self.assertIn("XJR004", codes)

            trailing = Path(folder) / "Trailing.xojo_resources"
            trailing.write_bytes(good.read_bytes() + b"BROKEN")
            trailing_codes = {item.code for item in self.validate(trailing)}
            self.assertIn("XJR002", trailing_codes)

    def test_project_duplicate_and_orphan_ids_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "First.xojo_code").write_text("", encoding="utf-8")
            (root / "Second.xojo_code").write_text("", encoding="utf-8")
            path = root / "Broken.xojo_project"
            path.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Class=First;First.xojo_code;&h1;&h0;false\n"
                "Class=Second;Second.xojo_code;&h1;&h2;false\n",
                encoding="utf-8",
            )
            codes = {item.code for item in self.validate(path)}
            self.assertIn("XJP003", codes)
            self.assertIn("XJP007", codes)

    def test_project_symlink_resolves_companions_beside_real_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "Project"
            project.mkdir()
            (project / "App.xojo_code").write_text("", encoding="utf-8")
            manifest = project / "Example.xojo_project"
            manifest.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Class=App;App.xojo_code;&h1;&h0;false\n",
                encoding="utf-8",
            )
            link = root / "Example.xojo_project"
            try:
                link.symlink_to(Path("Project") / manifest.name)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")

            discovered = list(
                xojo_lint.iter_files([root], include_unknown=False)
            )
            manifests = [
                path for path in discovered if path.suffix == ".xojo_project"
            ]
            self.assertEqual(manifests, [manifest.resolve()])
            self.assertEqual(self.validate(manifests[0]), [])

    def test_missing_submodule_companion_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "Project"
            dependency = project / "Dependency"
            dependency.mkdir(parents=True)
            (root / ".gitmodules").write_text(
                '[submodule "Project/Dependency"]\n'
                "\tpath = Project/Dependency\n"
                "\turl = https://example.invalid/Dependency.git\n",
                encoding="utf-8",
            )
            manifest = project / "Example.xojo_project"
            manifest.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Class=Thing;Dependency/Thing.xojo_code;&h1;&h0;false\n",
                encoding="utf-8",
            )
            diagnostics = self.validate(manifest)
            self.assertEqual([item.code for item in diagnostics], ["XJP008"])
            self.assertIn("uninitialized git submodule", diagnostics[0].message)
            self.assertIn("git submodule update --init", diagnostics[0].message)

    def test_designer_parser_handles_compact_begin_without_reading_properties(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Legacy.xojo_window"
            path.write_text(
                "#tag Window\n"
                "Begin Window Legacy\n"
                "  BeginDesktopSegmentedButton Control Button1\n"
                "    BeginOnClassLessSubnet=   False\n"
                "  End\n"
                "End\n"
                "#tag EndWindow\n",
                encoding="utf-8",
            )
            self.assertEqual(self.validate(path), [])

    def test_uistate_accepts_an_integer_record(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "State.xojo_uistate"
            path.write_bytes(b"TestInt " + struct.pack(">I", 42))
            self.assertEqual(self.validate(path), [])

    def test_library_checks_metadata_and_embedded_api(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Example.xojo_library"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Example/LibraryInfo.json", json.dumps({"name": "Example"}))
                archive.writestr(
                    "Example/API/Thing.xojo_code",
                    "#tag Class\nProtected Class Thing\n#tag EndClass\n",
                )
            self.assertEqual(self.validate(path), [])

    def test_formatter_repairs_serialized_indentation_and_is_idempotent(self) -> None:
        source = (
            "#TAG Class\r\n"
            "Protected Class Thing\r\n"
            "#TAG Method\r\n"
            "Sub Run()\r\n"
            "End Sub\r\n"
            "#TAG EndMethod\r\n"
            "#TAG EndClass\r\n"
        )
        document = xojo_lint.TextDocument(source, False, source.encode("utf-8"))
        options = xojo_lint.FormatOptions()
        path = Path("Thing.xojo_code")
        first = xojo_lint.format_document(path, document, options)
        expected = (
            "#tag Class\r\n"
            "Protected Class Thing\r\n"
            "\t#tag Method\r\n"
            "\t\tSub Run()\r\n"
            "\t\tEnd Sub\r\n"
            "\t#tag EndMethod\r\n"
            "#tag EndClass\r\n"
        ).encode("utf-8")
        self.assertEqual(first, expected)
        second_document = xojo_lint.TextDocument(
            expected.decode("utf-8"), False, expected
        )
        self.assertEqual(
            xojo_lint.format_document(path, second_document, options), expected
        )

    def test_missing_final_newline_is_a_notice_that_never_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Trailing.xojo_code"
            path.write_bytes(b"#tag Class\nProtected Class Trailing\n#tag EndClass")

            diagnostics = self.validate(path)
            self.assertEqual([item.code for item in diagnostics], ["XJC201"])
            self.assertEqual(diagnostics[0].severity, "notice")

            reported = io.StringIO()
            with redirect_stdout(reported), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["check", str(path)]), 0)
            self.assertIn("XJC201", reported.getvalue())

            hidden = io.StringIO()
            with redirect_stdout(hidden), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    xojo_lint.main(["check", "--no-notices", str(path)]), 0
                )
            self.assertEqual(hidden.getvalue(), "")

    def test_formatter_adds_a_missing_final_newline_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Trailing.xojo_code"
            source = b"#tag Class\r\nProtected Class Trailing\r\n#tag EndClass"
            path.write_bytes(source)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["format", "--check", str(path)]), 1)
                self.assertEqual(
                    xojo_lint.main(
                        ["format", "--final-newline", "preserve", "--check", str(path)]
                    ),
                    0,
                )
                self.assertEqual(xojo_lint.main(["format", str(path)]), 0)
            # The appended line break matches the file's own endings.
            self.assertTrue(path.read_bytes().endswith(b"#tag EndClass\r\n"))
            self.assertEqual(self.validate(path), [])

            empty = Path(folder) / "Placeholder.xojo_code"
            empty.write_bytes(b"")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["format", "--check", str(empty)]), 0)
            self.assertEqual(empty.read_bytes(), b"")

    def test_formatter_splits_only_on_real_line_endings(self) -> None:
        # str.splitlines would split on the form feed and U+2028 inside the
        # note body and rewrite content; the formatter must not.
        source = (
            "#tag Class\n"
            "Protected Class Thing\n"
            "\t#tag Note, Name = Oddities\n"
            "\t\tpage one\x0cpage two and line break\n"
            "\t#tag EndNote\n"
            "#tag EndClass\n"
        )
        document = xojo_lint.TextDocument(source, False, source.encode("utf-8"))
        path = Path("Thing.xojo_code")
        formatted = xojo_lint.format_document(path, document, xojo_lint.FormatOptions())
        self.assertIn("page one\x0cpage two and line break".encode("utf-8"), formatted)
        forced = xojo_lint.format_document(
            path, document, xojo_lint.FormatOptions(line_ending="lf")
        )
        self.assertIn("page one\x0cpage two and line break".encode("utf-8"), forced)

    def test_final_newline_matches_cr_only_files(self) -> None:
        source = b"#tag Class\rProtected Class CrOnly\r#tag EndClass"
        document = xojo_lint.TextDocument(source.decode(), False, source)
        formatted = xojo_lint.format_document(
            Path("CrOnly.xojo_code"), document, xojo_lint.FormatOptions()
        )
        self.assertTrue(formatted.endswith(b"#tag EndClass\r"))

    def test_xml_project_is_a_recognized_opaque_format(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Old.xojo_xml_project"
            path.write_text("<?xml version='1.0'?><RBProject/>", encoding="utf-8")
            self.assertEqual(self.validate(path), [])
            diagnostics = self.validate(path, warn_unknown=True)
            self.assertEqual([item.code for item in diagnostics], ["XJC102"])

    def test_cli_exit_statuses_support_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Hook.xojo_code"
            path.write_text(
                "#tag Class\nProtected Class Hook\n#tag EndClass\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["check", str(path)]), 0)
                self.assertEqual(
                    xojo_lint.main(["format", "--check", str(path)]), 0
                )

    def test_help_uses_the_shared_documentation_tool_style(self) -> None:
        root_output = io.StringIO()
        with redirect_stdout(root_output):
            self.assertEqual(xojo_lint.main([]), 0)
        root_help = root_output.getvalue()
        self.assertIn("  USAGE\n", root_help)
        self.assertIn("  COMMANDS\n", root_help)
        self.assertIn("  EXAMPLES\n", root_help)
        self.assertIn("for details on a command.", root_help)
        self.assertTrue(root_help.endswith("\n\n"))

        check_output = io.StringIO()
        with redirect_stdout(check_output):
            with self.assertRaises(SystemExit) as raised:
                xojo_lint.main(["check", "--help"])
        self.assertEqual(raised.exception.code, 0)
        check_help = check_output.getvalue()
        self.assertIn("  ARGUMENTS\n", check_help)
        self.assertIn("  FLAGS\n", check_help)
        self.assertIn("--all", check_help)
        self.assertNotIn("-Wall", check_help)

        error_output = io.StringIO()
        with redirect_stderr(error_output):
            with self.assertRaises(SystemExit) as raised:
                xojo_lint.main(["format", "--check", "--diff"])
        self.assertEqual(raised.exception.code, 64)
        rendered_error = error_output.getvalue()
        self.assertIn("  error:", rendered_error)
        self.assertIn("  USAGE\n", rendered_error)
        self.assertIn("format --help", rendered_error)

    @unittest.skipUnless(os.name == "posix", "POSIX file modes required")
    def test_formatter_write_preserves_permissions_without_leftovers(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Trailing.xojo_code"
            path.write_bytes(b"#tag Class\nProtected Class Trailing\n#tag EndClass")
            os.chmod(path, 0o600)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["format", str(path)]), 0)
            self.assertTrue(path.read_bytes().endswith(b"#tag EndClass\n"))
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(list(Path(folder).glob("*.part")), [])

    @unittest.skipUnless(os.name == "posix", "POSIX file modes required")
    def test_formatter_fails_closed_on_a_read_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Trailing.xojo_code"
            source = b"#tag Class\nProtected Class Trailing\n#tag EndClass"
            path.write_bytes(source)
            os.chmod(path, 0o444)
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["format", str(path)]), 1)
            self.assertIn("XJF002", output.getvalue())
            self.assertEqual(path.read_bytes(), source)
            self.assertEqual(list(Path(folder).glob("*.part")), [])

    @unittest.skipUnless(os.name == "posix", "symbolic links required")
    def test_formatter_writes_through_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            real = root / "Real.xojo_code"
            real.write_bytes(b"#tag Class\nProtected Class Real\n#tag EndClass")
            link = root / "Link.xojo_code"
            link.symlink_to(real.name)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["format", str(link)]), 0)
            self.assertTrue(link.is_symlink())
            self.assertTrue(real.read_bytes().endswith(b"#tag EndClass\n"))

    def test_all_enables_every_optional_check_but_not_failure_policy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Future.xojo_new_container").write_bytes(b"opaque")
            (root / "Example.xojo_project").write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Picture=Logo;missing.png;&h1;&h0;false;0;&h0\n",
                encoding="utf-8",
            )

            default_output = io.StringIO()
            with redirect_stdout(default_output), redirect_stderr(io.StringIO()):
                self.assertEqual(xojo_lint.main(["check", str(root)]), 0)
            self.assertEqual(default_output.getvalue(), "")

            all_output = io.StringIO()
            with redirect_stdout(all_output), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    xojo_lint.main(["check", "--all", str(root)]),
                    0,
                )
            self.assertIn("XJC103", all_output.getvalue())
            self.assertIn("XJP103", all_output.getvalue())

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    xojo_lint.main(
                        ["check", "--all", "--warnings-as-errors", str(root)]
                    ),
                    1,
                )


@unittest.skipUnless(shutil.which("git"), "git is required for hook tests")
class PreCommitHookTests(unittest.TestCase):
    """The sample hook lints staged content, not the working tree."""

    VALID = "#tag Class\nProtected Class Hook\n#tag EndClass\n"
    INVALID = "#tag Class\n\t#tag Method\n\t#tag EndProperty\n#tag EndClass\n"

    def git(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["XOJO_LINT"] = str(SCRIPTS / "xojo_lint.py")
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_CONFIG_SYSTEM"] = os.devnull
        # A GIT_DIR (or friend) exported by the caller would override cwd
        # discovery and point every command at the caller's real repository.
        for name in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_COMMON_DIR",
            "GIT_OBJECT_DIRECTORY",
        ):
            env.pop(name, None)
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def init_repo(self, root: Path) -> None:
        for args in (
            ("init", "--quiet"),
            ("config", "user.name", "Tester"),
            ("config", "user.email", "tester@example.invalid"),
        ):
            completed = self.git(root, *args)
            self.assertEqual(completed.returncode, 0, completed.stderr)
        hook = root / ".git" / "hooks" / "pre-commit"
        shutil.copy(SCRIPTS / "pre-commit.sample", hook)
        hook.chmod(0o755)

    def commit(self, root: Path) -> subprocess.CompletedProcess:
        return self.git(root, "commit", "--quiet", "-m", "test")

    def test_invalid_staged_content_blocks_despite_a_fixed_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            (root / "App.xojo_code").write_text(self.INVALID, encoding="utf-8")
            self.git(root, "add", "App.xojo_code")
            (root / "App.xojo_code").write_text(self.VALID, encoding="utf-8")
            completed = self.commit(root)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("XJT002", completed.stdout + completed.stderr)

    def test_valid_staged_content_passes_despite_a_broken_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            nested = root / "Sources" / "App.xojo_code"
            nested.parent.mkdir()
            nested.write_text(self.VALID, encoding="utf-8")
            self.git(root, "add", "Sources/App.xojo_code")
            nested.write_text(self.INVALID, encoding="utf-8")
            completed = self.commit(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_a_leading_dash_filename_is_linted_not_parsed_as_a_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            (root / "-evil.xojo_code").write_text(self.VALID, encoding="utf-8")
            self.git(root, "add", "--", "-evil.xojo_code")
            completed = self.commit(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_a_staged_file_deleted_from_the_worktree_still_passes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            (root / "App.xojo_code").write_text(self.VALID, encoding="utf-8")
            self.git(root, "add", "App.xojo_code")
            (root / "App.xojo_code").unlink()
            completed = self.commit(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_a_staged_manifest_finds_its_unchanged_companions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            (root / "App.xojo_code").write_text(self.VALID, encoding="utf-8")
            # The non-xojo asset proves the whole index is materialized for
            # the lint, not only the .xojo_* files the manifest sits among.
            (root / "logo.png").write_bytes(b"png bytes")
            manifest = root / "Example.xojo_project"
            manifest.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.020\n"
                "Class=Hook;App.xojo_code;&h1;&h0;false\n"
                "Picture=logo;logo.png;&h2;&h0;false\n",
                encoding="utf-8",
            )
            self.git(root, "add", "App.xojo_code", "logo.png", "Example.xojo_project")
            completed = self.commit(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Class=Hook;App.xojo_code;&h1;&h0;false\n"
                "Picture=logo;logo.png;&h2;&h0;false\n",
                encoding="utf-8",
            )
            self.git(root, "add", "Example.xojo_project")
            completed = self.commit(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_a_manifest_companion_inside_a_submodule_commits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            dependency = base / "dependency"
            dependency.mkdir()
            for args in (
                ("init", "--quiet"),
                ("config", "user.name", "Tester"),
                ("config", "user.email", "tester@example.invalid"),
            ):
                completed = self.git(dependency, *args)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            (dependency / "Thing.xojo_code").write_text(self.VALID, encoding="utf-8")
            self.git(dependency, "add", "Thing.xojo_code")
            completed = self.git(dependency, "commit", "--quiet", "-m", "dep")
            self.assertEqual(completed.returncode, 0, completed.stderr)

            root = base / "super"
            root.mkdir()
            self.init_repo(root)
            # Submodule content is absent from the superproject's index, so
            # this only passes if the hook copies the submodule's worktree.
            completed = self.git(
                root,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "--quiet",
                dependency.as_uri(),
                "Dependency",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = root / "Example.xojo_project"
            manifest.write_text(
                "Type=Desktop\n"
                "RBProjectVersion=2026.021\n"
                "Class=Thing;Dependency/Thing.xojo_code;&h1;&h0;false\n",
                encoding="utf-8",
            )
            self.git(root, "add", "Example.xojo_project")
            completed = self.commit(root)
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )

    def test_format_divergence_blocks_with_the_restage_hint(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.init_repo(root)
            (root / "App.xojo_code").write_bytes(
                b"#tag Class\nProtected Class Hook\n#tag EndClass"
            )
            self.git(root, "add", "App.xojo_code")
            completed = self.commit(root)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("format", completed.stderr)
            self.assertIn("commit again", completed.stderr)


if __name__ == "__main__":
    unittest.main()
