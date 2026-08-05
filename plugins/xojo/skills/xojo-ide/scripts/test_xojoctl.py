#!/usr/bin/env python3
"""Protocol tests for xojoctl. No live Xojo IDE required.

Runs a mock IDE over the SAME transport the real client would use on this
platform -- AF_UNIX on macOS/Linux, loopback TCP on Windows -- so on each
platform it exercises the code path that platform actually takes.

    python3 test_xojoctl.py

Exits 0 if every check passes.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The suite asserts plain substrings against help output; force the uncolored
# branch so `python3 test_xojoctl.py` passes on an interactive terminal
# exactly as it does piped. The themed branch has its own deterministic
# sub-test in test_help().
os.environ["NO_COLOR"] = "1"
os.environ.pop("XOJOCTL_COLOR", None)

import xojoctl as X  # noqa: E402

PASS = 0
FAIL = 0

def set_global(name: str, value: object) -> None:
    """Rebind a module-level name in EVERY module that holds a copy.

    The package is split into modules that star-import the layers below
    them, so one name can live in several module namespaces. Setting it
    only on the package would leave the defining module's own binding in
    place, and the function under test would keep using the original.
    """
    for mod in X._MODULES:
        if hasattr(mod, name):
            setattr(mod, name, value)
    setattr(X, name, value)



def check(label: str, got: object, want: object) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  ok   %s" % label)
    else:
        FAIL += 1
        print("  FAIL %s\n         got:  %r\n         want: %r" % (label, got, want))


def check_raises(label: str, fn, exc) -> None:
    global PASS, FAIL
    try:
        fn()
    except exc:
        PASS += 1
        print("  ok   %s" % label)
        return
    except BaseException as e:  # noqa: BLE001
        FAIL += 1
        print("  FAIL %s -- raised %r, wanted %s" % (label, e, exc.__name__))
        return
    FAIL += 1
    print("  FAIL %s -- did not raise" % label)


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


def test_escaping() -> None:
    print("\nescaping (the code-execution boundary)")
    check("plain path", X.xojo_string_literal("/a/b.xojo_project"),
          '"/a/b.xojo_project"')
    # Xojo doubles quotes; it does NOT use backslash escapes.
    check("embedded quote is DOUBLED", X.xojo_string_literal('a"b'), '"a""b"')
    # Backslash is an ordinary character -- escaping it would corrupt Windows paths.
    check("backslash untouched", X.xojo_string_literal(r"C:\Users\me"),
          r'"C:\Users\me"')
    check_raises("newline rejected", lambda: X.xojo_string_literal("a\nb"), ValueError)
    check_raises("NUL rejected", lambda: X.xojo_string_literal("a\x00b"), ValueError)

    # The injection payload: six literal characters \u0022 in a filename must
    # survive as those characters, not decode into a quote that breaks out.
    evil = r"x\u0022)" + "\n"
    check_raises("newline in payload rejected",
                 lambda: X.xojo_string_literal(evil), ValueError)
    evil2 = r"x\u0022)DoShellCommand(\u0022id\u0022)"
    wire = X.encode_request("t1", "OpenFile(%s)" % X.xojo_string_literal(evil2))
    decoded = json.loads(wire[:-1].decode("ascii"))["script"]
    check("injection payload stays inside one literal",
          decoded, 'OpenFile("x\\u0022)DoShellCommand(\\u0022id\\u0022)")')
    check("envelope is NUL-terminated", wire[-1:], b"\x00")


def test_shell_path() -> None:
    print("\nBuildApp shell-path unescaping")
    check("spaces and dashes",
          X.unescape_shell_path(r"/U/me/Test\ Project/Builds\ \-\ Test/App.app"),
          "/U/me/Test Project/Builds - Test/App.app")
    check("plain path unchanged", X.unescape_shell_path("/U/me/App.app"),
          "/U/me/App.app")
    # On Windows the backslash is the path SEPARATOR, not a shell escape;
    # unescaping there turned C:\Users\me into C:Usersme for every build.
    old = X.IS_WINDOWS
    try:
        set_global("IS_WINDOWS", True)
        check("a Windows path passes through untouched",
              X.unescape_shell_path(r"C:\Users\me\Builds\App.exe"),
              r"C:\Users\me\Builds\App.exe")
    finally:
        set_global("IS_WINDOWS", old)


def test_framer() -> None:
    print("\nNUL framing")
    f = X.Framer()
    check("two whole messages in one recv",
          f.feed(b'{"a":1}\x00{"b":2}\x00'), [b'{"a":1}', b'{"b":2}'])
    f = X.Framer()
    check("partial message yields nothing", f.feed(b'{"par'), [])
    check("completed across recvs", f.feed(b'tial":1}\x00'), [b'{"partial":1}'])
    f = X.Framer()
    check("empty frames skipped", f.feed(b'\x00\x00{"a":1}\x00'), [b'{"a":1}'])
    f = X.Framer(cap=16)
    check_raises("size cap enforced", lambda: f.feed(b"x" * 32), X.ProtocolError)
    f = X.Framer()
    f.feed(b'{"trunc')
    check_raises("truncated tail at EOF", f.close, X.ProtocolError)


def test_classification() -> None:
    print("\nreply classification")

    def cl(env):
        return X.classify(X.Message(0, env.get("tag"), env, b"{}"))

    check("plain string is OK",
          cl({"tag": "t", "response": "42"}).verdict, X.Verdict.OK)
    check("empty object is EMPTY (no such build target)",
          cl({"tag": "t", "response": {}}).verdict, X.Verdict.EMPTY)
    check("buildError with errors",
          cl({"tag": "t", "response": {"buildError": {"errors": [{"message": "x"}]}}}).verdict,
          X.Verdict.ERRORS)
    check("buildError with only warnings",
          cl({"tag": "t", "response": {"buildError": {"warnings": [{"message": "w"}]}}}).verdict,
          X.Verdict.WARNINGS)
    check("buildError with both -> ERRORS",
          cl({"tag": "t", "response": {"buildError": {
              "errors": [{"message": "e"}], "warnings": [{"message": "w"}]}}}).verdict,
          X.Verdict.ERRORS)
    check("empty buildError means a clean analysis",
          cl({"tag": "t", "response": {"buildError": {}}}).verdict, X.Verdict.OK)
    check("scriptError is our bug, not the project's",
          cl({"tag": "t", "response": {"scriptError": [{"line": 1}]}}).verdict,
          X.Verdict.SCRIPT_ERROR)
    # A scriptError array is heterogeneous: entries are errors OR warnings,
    # told apart only by `type`. Warnings alone mean the script RAN.
    warn_only = {"tag": "t", "response": {"scriptError": [
        {"type": "scriptCompilerWarning", "line": 2,
         "message": "Converting from Int64 to Double causes a possible loss "
                    "of precision, which can lead to unexpected results"}]}}
    check("scriptCompilerWarning alone is NOT a rejection",
          cl(warn_only).verdict, X.Verdict.WARNINGS)
    check("the warning is kept as a warning", len(cl(warn_only).warnings), 1)
    mixed = {"tag": "t", "response": {"scriptError": [
        {"type": "scriptCompilerWarning", "message": "w"},
        {"type": "scriptCompilerError", "message": "e"}]}}
    check("a real error alongside a warning still fails",
          cl(mixed).verdict, X.Verdict.SCRIPT_ERROR)
    check("mixed: error partitioned", len(cl(mixed).errors), 1)
    check("mixed: warning partitioned", len(cl(mixed).warnings), 1)
    check("an untyped entry is treated as an error",
          cl({"tag": "t", "response": {"scriptError": [{"message": "?"}]}}).verdict,
          X.Verdict.SCRIPT_ERROR)
    # The legacy layout puts the error beside "tag" rather than inside "response".
    check("legacy layout tolerated",
          cl({"tag": "t", "buildError": {"errors": [{"message": "x"}]}}).verdict,
          X.Verdict.ERRORS)
    check("non-fatal openErrors is not fatal",
          cl({"tag": "t", "response": {"openErrors": [
              {"projectError": [{"isFatal": False}]}]}}).fatal, False)
    check("fatal openErrors detected through a list",
          cl({"tag": "t", "response": {"openErrors": [
              {"projectError": [{"isFatal": True}]}]}}).fatal, True)
    mf = cl({"tag": "t", "response": {"missingFiles":
             "Unable to build. Please specify a Key Store properties file "
             "in the Android Build Settings."}})
    check("missingFiles is recognized", mf.verdict, X.Verdict.MISSING_FILES)
    check("the IDE's message is preserved verbatim",
          mf.note.startswith("Unable to build. Please specify a Key Store"), True)
    check("missingFiles normalizes to one diagnostic", len(X.normalize(mf)), 1)
    check("classified as a config problem, not project code",
          X.normalize(mf)[0]["kind"], "config")

    check("undecodable reply is UNKNOWN, never success",
          X.classify(X.Message(0, None, None, b"junk")).verdict, X.Verdict.UNKNOWN)


def test_normalization() -> None:
    print("\ndiagnostic normalization")
    build = {"type": "Code", "message": "This item does not exist", "source": "foo",
             "location": "Window1.Opening", "position": "Window1.Opening, line 5"}
    d = X.normalize_diagnostic(build, "error", "project", "buildError.errors[0]", 1)
    check("line parsed out of position", d["line"], 5)
    check("provenance recorded", d["line_source"], "position")
    check("location stays a string", d["location"], "Window1.Opening")
    check("source marked as a span", d["source_is_span"], True)

    # In scriptError, `location` is an OBJECT, not a string. Discrimination is
    # by container kind, not by sniffing the element.
    scr = {"type": "compiler", "line": 2, "number": 11, "message": "bad",
           "location": {"column": 6, "line": 2}}
    d = X.normalize_diagnostic(scr, "error", "script", "scriptError[0]", 1)
    # The IDE wraps the script in an enclosing method, so its line numbers are
    # one greater than the caller's. Demonstrated on 2026.020: a ONE-line
    # script reported "line 2", and bad lines 1/3/5 reported 2/4/6.
    check("script line unwrapped to the caller's line", d["line"], 1)
    check("the IDE's own number is preserved", d["line_raw"], 2)
    check("provenance says it was adjusted", d["line_source"], "line_field_unwrapped")
    check("script column extracted", d["column"], 6)
    check("script location flattened to null", d["location"], None)
    check("script source is not a span", d["source_is_span"], False)

    # Clamp: line 1 cannot be decremented to 0, which the schema forbids.
    d = X.normalize_diagnostic({"line": 1, "message": "x"}, "error", "script", "s", 1)
    check("line 1 is never decremented to 0", d["line"], 1)
    check("unadjusted provenance recorded", d["line_source"], "line_field")

    d = X.normalize_diagnostic({"message": "m"}, "warning", "project", "x", 1)
    check("unparseable line stays null, never 0", d["line"], None)

    # The IDE sends column -1 for "unknown"; the schema promises null -- the
    # mock's WARNFIRST reply uses exactly this shape.
    d = X.normalize_diagnostic({"message": "x", "location": {"column": -1, "line": 2}},
                               "error", "script", "s", 1)
    check("column -1 becomes null", d["column"], None)
    check("the line beside it is still unwrapped", d["line"], 1)
    # A nonsensical line (0 or negative) becomes null; the schema says a line
    # is "never 0, never guessed", and line_raw keeps what the IDE sent.
    d = X.normalize_diagnostic({"line": 0, "message": "x"}, "error", "script", "s", 1)
    check("line 0 becomes null, never 0", d["line"], None)
    check("the IDE's own 0 survives in line_raw", d["line_raw"], 0)

    # An openErrors entry is a ONE-KEY WRAPPER with no message of its own; the
    # payload sits one level down. Captured opening a 2026.021 project in a
    # 2026.020 IDE, which used to render as "error (no message)".
    op = {"loadError": {"type": "IDE Version Conflict",
                        "projectVersion": "2026.021",
                        "ideVersion": "2026.020", "severity": "error"}}
    d = X.normalize_diagnostic(op, "error", "open", "openErrors[0]", 1)
    check("open error type is unwrapped", d["type"], "IDE Version Conflict")
    check("a message is synthesized", d["message"] is not None, True)
    check("the message names the conflict",
          "IDE Version Conflict" in d["message"], True)
    check("the versions survive into the message",
          "2026.021" in d["message"] and "2026.020" in d["message"], True)
    check("the nested severity is honored", d["severity"], "error")
    check("the original entry is preserved verbatim", d["raw"], op)
    # A wrapper whose payload declares a non-error must not be shown as one.
    d = X.normalize_diagnostic({"loadError": {"type": "Stale link",
                                              "severity": "warning"}},
                               "error", "open", "openErrors[0]", 1)
    check("a nested warning is not announced as an error", d["severity"], "warning")


def test_targets() -> None:
    print("\nbuild targets")
    check("by name", X.resolve_target("darwin-arm64").value, 24)
    check_raises("an old alias spelling is rejected",
                 lambda: X.resolve_target("apple-silicon"), ValueError)
    check("by integer", X.resolve_target("9").name, "darwin-universal")
    check_raises("target 7 is rejected", lambda: X.resolve_target("7"), ValueError)
    check_raises("unknown name rejected", lambda: X.resolve_target("bogus"), ValueError)
    # str.isdigit() is a Unicode predicate: an Arabic-Indic digit used to
    # resolve silently via int(), and a superscript raised a raw "invalid
    # literal" instead of the curated message. Both must get the curated error.
    for label, spec in (("an Arabic-Indic digit", "\u0663"),
                        ("a superscript digit", "\u00b2")):
        try:
            X.resolve_target(spec)
            check("%s gets the curated error" % label, "resolved", "ValueError")
        except ValueError as e:
            check("%s gets the curated error" % label,
                  "unknown build target" in str(e), True)


def test_sanitize() -> None:
    print("\nterminal sanitising")
    check("ANSI stripped", X.sanitize("\x1b[31mred\x1b[0m"), "red")
    check("control chars replaced", X.sanitize("a\x07b"), "a\ufffdb")
    # A raw CR returns the cursor to column 0 and lets IDE-controlled text
    # OVERWRITE what was already printed -- "error: bad\rok no errors" renders
    # as "ok no errors" in a terminal. That is the spoof this exists to stop.
    check("a lone CR cannot rewrite the line",
          X.sanitize("error: bad\rok"), "error: bad\ufffdok")
    check("CRLF becomes a plain newline", X.sanitize("a\r\nb"), "a\nb")
    check("a raw C1 control is replaced", X.sanitize("a\x9bb"), "a\ufffdb")
    check("newline and tab pass through", X.sanitize("a\n\tb"), "a\n\tb")
    # RLO reverses the rest of a rendered line -- the same display rewrite as
    # a raw CR, reachable from any project-controlled string. The isolates
    # are how LEGITIMATE RTL text is wrapped, and cannot reverse an
    # already-printed prefix; they must survive.
    check("a bidi override cannot reverse the line",
          X.sanitize("ok\u202eskcehc on"), "ok\ufffdskcehc on")
    check("every deprecated bidi embedding is replaced",
          X.sanitize("\u202a\u202b\u202c\u202d\u202e"), "\ufffd" * 5)
    check("bidi isolates pass through (legitimate RTL)",
          X.sanitize("a\u2066\u05e9\u2069b"), "a\u2066\u05e9\u2069b")


# ---------------------------------------------------------------------------
# Mock IDE over the real transport
# ---------------------------------------------------------------------------


class MockIDE:
    """A fake Xojo IDE speaking protocol v2 over this platform's transport."""

    def __init__(self) -> None:
        self.handshakes = 0
        self._dir = None
        if X.IS_WINDOWS:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.bind(("127.0.0.1", 0))
            self.port = self._srv.getsockname()[1]
            self.path = None
        else:
            self._dir = tempfile.mkdtemp()
            self.path = os.path.join(self._dir, "XojoIDEMock")
            self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._srv.bind(self.path)
            self.port = None
        self._srv.listen(4)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def transport(self) -> X.Transport:
        if X.IS_WINDOWS:
            return X.connect_tcp(self.port)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.path)
        return X._SocketTransport(s, self.path, "unix")

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        framer = X.Framer()
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    return
                for raw in framer.feed(data):
                    msg = json.loads(raw.decode("utf-8"))
                    if "protocol" in msg:
                        self.handshakes += 1
                        continue          # the real IDE sends NO ack
                    self._reply(conn, msg)
        except (OSError, ValueError):
            return

    def _reply(self, conn: socket.socket, msg: dict) -> None:
        tag, script = msg.get("tag"), msg.get("script", "")
        # A real IDE runs the trailing `Print "<sentinel>"` that cmd_script
        # appends, so the mock must too -- otherwise every script test waits
        # for a completion signal that never comes.
        m = re.search(r'__xojoctl_script_[0-9a-f]+__', script)
        sentinel = m.group(0) if m else None
        if sentinel is not None:
            self._reply_body(conn, msg, tag, script)
            if "BOOM" not in script and "not valid" not in script:
                self._send(conn, {"tag": tag, "response": sentinel})
            return
        self._reply_body(conn, msg, tag, script)

    def _reply_body(self, conn: socket.socket, msg: dict,
                    tag: object, script: str) -> None:
        if "SILENT" in script:
            return                        # a script with no Print never replies
        if "SPLIT" in script:
            # One message delivered across two writes.
            blob = json.dumps({"tag": tag, "response": "split-ok"}).encode() + X.NUL
            conn.sendall(blob[:5])
            time.sleep(0.05)
            conn.sendall(blob[5:])
            return
        if "WARNSLOW" in script:
            # Warning at compile time, output only after the script's whole
            # runtime -- far past the split-reply window.
            self._send(conn, {"tag": tag, "response": {"scriptError": [
                {"type": "scriptCompilerWarning", "line": 1, "number": 5,
                 "message": "Converting from Int64 to Double"}]}})
            time.sleep(0.6)
            self._send(conn, {"tag": tag, "response": "42"})
            return
        if "WARNFIRST" in script:
            # One reply, two messages, WARNING FIRST -- the dangerous order.
            self._send(conn, {"tag": tag, "response": {"scriptError": [
                {"type": "scriptCompilerWarning", "line": 2, "number": 5,
                 "message": "Converting from Int64 to Double", 
                 "location": {"column": -1, "line": 2}}]}})
            time.sleep(0.02)
            self._send(conn, {"tag": tag, "response": "42"})
            return
        if "BuildApp(9," in script:
            # A successful build: shell-escaped path, then the sentinel.
            self._send(conn, {"tag": tag, "response": r"/tmp/Mock\ Builds/App.app"})
            self._send(conn, {"tag": tag, "response": X.BUILD_SENTINEL})
            return
        if "BuildApp(24," in script:
            # BuildApp printed nothing; only the sentinel arrives.
            self._send(conn, {"tag": tag, "response": X.BUILD_SENTINEL})
            return
        if "BuildApp(16," in script:
            # An artifact AND compile errors under one tag. Discarding the
            # error part here reported success with no diagnostics at all.
            self._send(conn, {"tag": tag, "response": r"/tmp/Mock/App.app"})
            self._send(conn, {"tag": tag, "response": {"buildError": {
                "errors": [{"type": "Code", "message": "boom"}], "warnings": []}}})
            self._send(conn, {"tag": tag, "response": X.BUILD_SENTINEL})
            return
        if "BuildApp(19," in script:
            # A failing target whose only diagnostics are warnings.
            self._send(conn, {"tag": tag, "response": {"buildError": {
                "warnings": [{"type": "Code", "message": "w"}], "errors": []}}})
            self._send(conn, {"tag": tag, "response": X.BUILD_SENTINEL})
            return
        if "SENTFIRST" in script:
            # A dirty analyze whose sentinel wins the race by MORE than the
            # split window (but within the trailing window).
            self._send(conn, {"tag": tag, "response": X.ANALYZE_SENTINEL})
            time.sleep(0.5)
            self._send(conn, {"tag": tag, "response": {"buildError": {
                "errors": [{"type": "Code", "message": "late error"}]}}})
            return
        if "WARNENDED" in script:
            # A compile-time warning, and the script itself prints nothing.
            # Only the appended sentinel follows, which is what a real IDE
            # sends for this shape.
            self._send(conn, {"tag": tag, "response": {"scriptError": [
                {"type": "scriptCompilerWarning", "line": 1, "message": "w"}]}})
            return
        if "WindowCount" in script:
            self._send(conn, {"tag": tag, "response": "1"})
            return
        if "BURST" in script:
            # An unsolicited message, then the real reply, in ONE write.
            a = json.dumps({"tag": "someone-else", "response": "stray"}).encode() + X.NUL
            b = json.dumps({"tag": tag, "response": "burst-ok"}).encode() + X.NUL
            conn.sendall(a + b)
            return
        if "DIRTY" in script:
            payload = {"buildError": {
                "warnings": [{"type": "Code", "message": "w", "source": "",
                              "location": "W.Opening", "position": "W.Opening, line 1"}],
                "errors": [{"type": "Code", "message": "e", "source": "foo",
                            "location": "W.Opening", "position": "W.Opening, line 3"}]}}
            self._send(conn, {"tag": tag, "response": payload})
            return
        if "CheckProjectErrors" in script:
            # Clean project: the sentinel comes back, nothing else.
            self._send(conn, {"tag": tag, "response": X.ANALYZE_SENTINEL})
            return
        if "BOOM" in script:
            self._send(conn, {"tag": tag, "response": {"scriptError": [
                {"type": "compiler", "line": 1, "number": 11, "message": "bad",
                 "location": {"column": 6, "line": 1}}]}})
            return
        if "XojoVersion" in script:
            self._send(conn, {"tag": tag, "response": "2026.021"})
            return
        if "EMPTY" in script:
            self._send(conn, {"tag": tag, "response": {}})
            return
        if "SENTONLY" in script:
            # A build that printed nothing: ONE sentinel-only message, which
            # is both the claimed reply and the completion sentinel.
            self._send(conn, {"tag": tag, "response": X.BUILD_SENTINEL})
            return
        self._send(conn, {"tag": tag, "response": "ok"})

    @staticmethod
    def _send(conn: socket.socket, obj: dict) -> None:
        conn.sendall(json.dumps(obj).encode("utf-8") + X.NUL)

    def close(self) -> None:
        self._stop.set()
        try:
            self._srv.close()
        except OSError:
            pass
        if self.path and os.path.exists(self.path):
            os.unlink(self.path)
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)


def test_client() -> None:
    print("\nclient against a mock IDE (%s transport)"
          % ("tcp" if X.IS_WINDOWS else "unix"))
    ide = MockIDE()
    try:
        with X.Client(ide.transport(), first_ceiling=5.0, reply_ceiling=5.0) as c:
            check("handshake sent, no ack awaited",
                  c.exchange(X.script_version()).result.text, "2026.021")
            check("message split across writes is reassembled",
                  c.exchange("Print SPLIT").result.text, "split-ok")

            ex = c.exchange("Print BURST")
            check("correct reply picked out of a burst", ex.result.text, "burst-ok")
            check("unsolicited message retained as a stray", len(ex.strays), 1)
            check("stray marked out-of-band", ex.strays[0].channel, "out-of-band")

            ex = c.exchange("DIRTY")
            check("dirty analyze -> ERRORS", ex.result.verdict, X.Verdict.ERRORS)
            check("both warnings and errors kept",
                  (len(ex.result.warnings), len(ex.result.errors)), (1, 1))
            check("normalized into 2 diagnostics", len(X.normalize(ex.result)), 2)

            ex = c.exchange(X.script_analyze_project())
            check("clean analyze returns the sentinel",
                  ex.result.text, X.ANALYZE_SENTINEL)

            check("script error classified as ours",
                  c.exchange("BOOM").result.verdict, X.Verdict.SCRIPT_ERROR)
            check("empty response is EMPTY",
                  c.exchange("EMPTY").result.verdict, X.Verdict.EMPTY)
            check("unicode round-trips", c.exchange("Print é✓").result.text, "ok")

            # A script that never Prints gets no reply -- must time out, not hang.
            t0 = time.monotonic()
            check_raises("silent script times out",
                         lambda: c.exchange("SILENT", ceiling=1.0), X.ReplyTimeout)
            check("timeout respected the ceiling",
                  time.monotonic() - t0 < 4.0, True)

            check("exactly one handshake for the connection", ide.handshakes, 1)
    finally:
        ide.close()


def test_analyze_script_shape() -> None:
    print("\nanalyze script contract")
    s = X.script_analyze_project()
    check("uses CheckProjectErrors", "CheckProjectErrors" in s, True)
    # Finding 2: a clean analyze emits NOTHING, so without a sentinel every
    # clean project hangs to the ceiling. Finding 3: the sentinel does not
    # clobber diagnostics when there are any.
    check("ends with the Print sentinel", s.strip().endswith(
        'Print "%s"' % X.ANALYZE_SENTINEL), True)
    check("open uses bare OpenFile, not DoCommand",
          "DoCommand" not in X.script_open_project("/tmp/x"), True)

    # SelectProjectItem is a FUNCTION on 2026r2 (a bare call fails to compile
    # with "You must use the value returned by this function") and its Boolean
    # is the only signal the item exists. The script must BRANCH on it: a
    # discarded result let a mistyped --item analyze whatever was previously
    # selected and report a clean pass for an item that was never analyzed.
    item = X.script_analyze_item("Window1")
    check("item analyze branches on SelectProjectItem's result",
          'If SelectProjectItem("Window1") Then' in item, True)
    check("item analyze still uses CheckItemErrors",
          "CheckItemErrors" in item, True)
    check("the success path prints the sentinel",
          'Print "%s"' % X.ANALYZE_SENTINEL in item, True)
    check("the failure path prints the not-found marker",
          'Print "%s"' % X.ANALYZE_ITEM_MISSING in item, True)
    check("the branch closes", item.strip().endswith("End If"), True)
    check("no bare (result-discarding) select survives",
          "Call SelectProjectItem" in item, False)

    # The probe must not provoke a diagnostic of its own: WindowCount is an
    # Int64 and Str() takes a Double, which emits a precision warning on 2026r2.
    probe = X.script_window_count()
    check("the window-count probe avoids Str() on an Int64",
          "Str(WindowCount)" not in probe, True)
    check("the probe still prints WindowCount", "WindowCount" in probe, True)


def test_bom_handling() -> None:
    """Windows writes UTF-8 WITH a BOM by default, and U+FEFF is not a control
    character, so it slips past xojo_string_literal() and becomes part of the
    first statement. Verified live: it fails as "This item does not exist".
    """
    print("\nBOM handling (Windows text files)")
    check("a leading BOM is stripped",
          X.strip_bom("﻿Print \"x\""), 'Print "x"')
    check("only ONE BOM is removed",
          X.strip_bom("﻿﻿Print"), "﻿Print")
    check("a BOM-less script is untouched",
          X.strip_bom('Print "x"'), 'Print "x"')
    check("an interior U+FEFF is left alone",
          X.strip_bom('Print "a﻿b"'), 'Print "a﻿b"')
    check("empty input is safe", X.strip_bom(""), "")

    import tempfile as _tf
    fd, path = _tf.mkstemp(suffix=".xojo_script")
    os.close(fd)
    try:
        # codecs.BOM_UTF8 is exactly what PowerShell's Out-File emits.
        with open(path, "wb") as fh:
            fh.write(b"\xef\xbb\xbfPrint \"hi\"\n")
        with open(path, "r", encoding="utf-8-sig") as fh:
            check("utf-8-sig strips the BOM a Windows file carries",
                  fh.read(), 'Print "hi"\n')
        with open(path, "r", encoding="utf-8") as fh:
            check("plain utf-8 would have left it in place (the bug)",
                  fh.read().startswith("﻿"), True)
    finally:
        os.unlink(path)


def test_channel_classification() -> None:
    """Replays the real capture: the IDE reuses a retired tag for unsolicited
    messages, so a stale tag alone cannot mean "ours". Timing separates them.

    Observed on 2026.021: our analyze sentinel arrived in the SAME millisecond
    as the claimed reply; a hand-clicked Analyze came back under an already
    retired tag 5.9 SECONDS later.
    """
    print("\nchannel classification (tagged / trailing / out-of-band)")

    class FakeClient:
        def __init__(self, msgs, sent, claimed):
            self._m, self._s, self._c = msgs, sent, claimed
        def messages(self):
            return self._m
        @property
        def dropped(self):
            return 0
        @property
        def sent_tags(self):
            return self._s
        @property
        def claimed_at(self):
            return self._c

    t0 = 1000.0
    claimed = X.Message(1, "T-2", {"tag": "T-2", "response": {"buildError": {}}},
                        b"{}", at=t0)
    claimed.channel = "tagged"
    sentinel = X.Message(2, "T-2", {"tag": "T-2", "response": X.ANALYZE_SENTINEL},
                         b"{}", at=t0 + 0.001)          # same millisecond
    unsolicited = X.Message(3, "T-1", {"tag": "T-1",
                                       "response": {"buildError": {}}},
                            b"{}", at=t0 + 5.9)          # 5.9s later, retired tag
    foreign = X.Message(4, "someone-else", {"tag": "someone-else", "response": "x"},
                        b"{}", at=t0 + 1.0)

    res = X.Result(command="analyze")
    X.record_raw(res, FakeClient([claimed, sentinel, unsolicited, foreign],
                                 {"T-1", "T-2"}, {"T-2": t0}), t0)
    got = {m["seq"]: m["channel"] for m in res.raw["messages"]}
    check("claimed reply is tagged", got[1], "tagged")
    check("same-tag sentinel in the same ms is trailing", got[2], "trailing")
    check("retired tag 5.9s later is out-of-band", got[3], "out-of-band")
    check("never-sent tag is out-of-band", got[4], "out-of-band")
    check("unsolicited note fires",
          "unsolicited_messages" in [n["code"] for n in res.notes], True)

    # And the common case must NOT produce a false note.
    res2 = X.Result(command="analyze")
    X.record_raw(res2, FakeClient([claimed, sentinel], {"T-2"}, {"T-2": t0}), t0)
    check("no false note when only trailing output",
          "unsolicited_messages" in [n["code"] for n in res2.notes], False)
    check("elapsed_ms is never negative for messages after start",
          all(m["elapsed_ms"] >= 0 for m in res2.raw["messages"]), True)

    # A sentinel await_sentinel positively identified is OUR output no matter
    # when it landed (its acceptance window is 60s); record_raw's 2s timing
    # heuristic is for UNLABELED stragglers only and must not relabel it
    # out-of-band, which fired a false unsolicited_messages note.
    late = X.Message(5, "T-2", {"tag": "T-2", "response": X.BUILD_SENTINEL},
                     b"{}", at=t0 + 30.0)
    late.channel = "trailing"
    res3 = X.Result(command="build")
    X.record_raw(res3, FakeClient([claimed, late], {"T-2"}, {"T-2": t0}), t0)
    got3 = {m["seq"]: m["channel"] for m in res3.raw["messages"]}
    check("a positively-identified late sentinel stays trailing",
          got3[5], "trailing")
    check("and raises no false unsolicited note",
          "unsolicited_messages" in [n["code"] for n in res3.notes], False)


def test_help() -> None:
    """The custom renderer replaces argparse's, so nothing auto-updates it.

    A new subcommand that is not placed in a group would silently vanish from
    `--help`. These checks make that a test failure instead.
    """
    print("\nhelp rendering")
    parser = X.build_parser()
    grouped = [n for _, g in X.COMMAND_GROUPS for n in g]
    check("no command is listed in two groups", len(grouped), len(set(grouped)))

    sub = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)][0]
    canonical = set(X._subparsers(sub))
    check("every command appears in exactly one group",
          sorted(canonical), sorted(grouped))
    check("every command has a blurb",
          sorted(X.COMMAND_BLURBS), sorted(grouped))

    text = X.render_root_help(parser)
    for title, _ in X.COMMAND_GROUPS:
        check("root help shows section %s" % title, title in text, True)
    for name in grouped:
        check("root help lists %s" % name, ("  " + name) in text, True)
    check("no raw argparse usage dump", "usage:" in text.lower(), False)

    # Color must be absent when NO_COLOR is set or stdout is not a tty.
    import os as _os
    old = _os.environ.get("NO_COLOR")
    _os.environ["NO_COLOR"] = "1"
    try:
        check("NO_COLOR strips escapes", "\033[" in X.render_root_help(parser), False)
    finally:
        if old is None:
            _os.environ.pop("NO_COLOR", None)
        else:
            _os.environ["NO_COLOR"] = old

    # The themed branch, deterministically: XOJOCTL_COLOR=always themes help
    # without a tty, and NO_COLOR must beat it. The suite runs with NO_COLOR
    # pinned at import time, so restore exactly that state.
    _os.environ["XOJOCTL_COLOR"] = "always"
    try:
        check("NO_COLOR beats XOJOCTL_COLOR=always",
              "\033[" in X.render_root_help(parser), False)
        _os.environ.pop("NO_COLOR", None)
        check("XOJOCTL_COLOR=always themes help without a tty",
              "\033[" in X.render_root_help(parser), True)
    finally:
        _os.environ["NO_COLOR"] = "1"
        _os.environ.pop("XOJOCTL_COLOR", None)

    old_inv = X.INVOCATION
    try:
        set_global("INVOCATION", "xojoctl")   # pin: the suite's argv[0] varies
        ch = X.render_command_help(sub.choices["analyze"], "analyze")
        check("command help has a clean usage line",
              "% xojoctl analyze [flags]" in ch, True)
        check("command help has no alias footer", "Aliases:" in ch, False)
    finally:
        set_global("INVOCATION", old_inv)


def test_helptext_generic() -> None:
    """The shared renderer's configurable paths, which no CLI in this repo
    exercises: subcommand-less help, custom usage lines and prompt, and the
    parser-derived sections. This repo is the canonical source for
    helptext.py, so a regression here ships to every downstream copy.
    """
    print("\nshared helptext: subcommand-less and configurable paths")
    from xojoctl import helptext as H

    cfg = H.HelpConfig(
        prog="onetool",
        command_blurbs={},
        usage=("FILE [flags]", "--stdin [flags]"),
        prompt="$",
    )

    class OneParser(H.HelpfulParser):
        help_config = cfg

    p = OneParser(prog="onetool", description="One command only.",
                  add_help=False)
    p.add_argument("-h", "--help", action="help", help="show this help")
    p.add_argument("file", metavar="FILE", nargs="?", help="input file")
    p.add_argument("--fast", action="store_true", help="hurry up")
    p.add_argument("--internal", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--between", nargs=2, metavar=("LOW", "HIGH"),
                   help="range filter")

    text = H.render_root_help(p, cfg)
    check("every configured usage line renders", text.count("$ onetool"), 2)
    check("the custom usage suffix renders", "FILE [flags]" in text, True)
    check("positionals get an ARGUMENTS section", "ARGUMENTS" in text, True)
    check("flags derive from the parser when root_flags is None",
          "--fast" in text, True)
    check("tuple metavars render joined, not crash",
          "--between LOW HIGH" in text, True)
    check("suppressed flags stay hidden", "--internal" in text, False)
    check("no COMMANDS section without commands", "COMMANDS" in text, False)
    check("no per-command trailer without commands",
          "<command> --help" in text, False)
    check("root_flags=() suppresses the FLAGS section",
          "FLAGS" in X.helptext.render_root_help(
              p, H.HelpConfig(prog="onetool", command_blurbs={},
                              usage=("FILE",), root_flags=())), False)

    # A lone string is a Sequence[str] too; it must count as one usage line,
    # not be iterated character by character.
    check("a lone usage string counts as one line",
          H.HelpConfig(prog="onetool", command_blurbs={},
                       usage="FILE [flags]").usage, ("FILE [flags]",))

    # The subparsers action is excluded structurally, whatever its dest; a
    # genuine positional that happens to be named "command" still documents.
    bare = OneParser(prog="subtool", add_help=False)
    bare.add_subparsers()
    check("a subparsers action never lands in ARGUMENTS",
          H._arg_rows(bare), [])
    named = OneParser(prog="cmds", add_help=False)
    named.add_argument("command", help="the command to send")
    check("a positional named 'command' is documented",
          H._arg_rows(named), [("COMMAND", "The command to send")])

    # House style capitalizes a description's first letter, which mangles a
    # word that chose its own casing.
    check("ordinary descriptions still capitalize",
          H._cap("show this help"), "Show this help")
    for word in ("iOS or macOS target", "macOS only", "eBay export"):
        check("deliberate inner capitals survive", H._cap(word), word)

    # An empty prompt is the obvious spelling for "draw no prompt"; it must
    # take its trailing space with it rather than misaligning the line.
    noprompt = H.HelpConfig(prog="onetool", command_blurbs={},
                            usage=("FILE",), prompt="")
    plain = H.help_theme("never", io.StringIO())
    check("an empty prompt leaves no stray space",
          H._usage_lines(plain, noprompt), "    onetool FILE\n")
    check("a prompt still renders with one space",
          H._usage_lines(plain, H.HelpConfig(prog="onetool",
                                             command_blurbs={},
                                             usage=("FILE",))),
          "    % onetool FILE\n")

    # Error humanizing follows the parser's own subcommand naming.
    check("invalid choice on a custom dest is still a command error",
          H._humanize("argument <action>: invalid choice: 'fro' (choose)",
                      {"frob": ""}, ("<action>", "action")),
          ('unknown command "fro"', "frob"))
    check("a flag's invalid choice keeps argparse's message",
          H._humanize("argument --color: invalid choice: 'no' (choose)",
                      {"go": ""}, ("<command>", "command"))[0],
          "argument --color: invalid choice: 'no' (choose)")
    check("a required positional is not 'no command given' without commands",
          H._humanize("the following arguments are required: command", {})[0],
          "missing required argument: command")


def test_help_width() -> None:
    """Help must not widen with the terminal: every page stays within 100
    columns even on a very wide terminal, and within 80 for everything except
    unbreakable tokens (the targets documentation URL).
    """
    print("\nhelp width")
    import re as _re
    ansi = _re.compile(r"\x1b\[[0-9;]*m")
    old_cols = os.environ.get("COLUMNS")
    old_lines = os.environ.get("LINES")
    old_inv = X.INVOCATION
    os.environ["COLUMNS"] = "200"     # a wide terminal must not widen help
    os.environ["LINES"] = "50"
    try:
        set_global("INVOCATION", "xojoctl")
        parser = X.build_parser()
        sub = [a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction)][0]
        pages = [("root", X.render_root_help(parser))]
        for nm, sp in X._subparsers(sub).items():
            pages.append((nm, X.render_command_help(sp, nm)))
        for nm, text in pages:
            widths = [len(ansi.sub("", ln)) for ln in text.splitlines()]
            over100 = [w for w in widths if w > 100]
            over80 = [ln for ln in text.splitlines()
                      if len(ansi.sub("", ln)) > 80 and "http" not in ln]
            check("help page %r stays within 100 columns" % nm, over100, [])
            check("help page %r stays within 80 (URLs exempt)" % nm, over80, [])
    finally:
        set_global("INVOCATION", old_inv)
        for var, old in (("COLUMNS", old_cols), ("LINES", old_lines)):
            if old is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = old


def test_invocation_name() -> None:
    """Help examples are only useful if they can be pasted back into the shell.

    `xojoctl analyze` is a valid command ONLY when something named xojoctl is on
    PATH. Run as a script -- the normal case on Windows, which has no symlink
    convention -- it fails with "'xojoctl' is not recognized", so the rendered
    examples have to name the interpreter.
    """
    print("\ninvocation naming (pasteable help)")
    inv = X.invocation_name
    check("a .py script names the interpreter",
          inv("xojoctl.py"), "python xojoctl.py")
    # os.path.basename is platform-native by design: it splits on "\\" only
    # under ntpath. That is correct -- sys.argv[0] always uses the host's own
    # separators, and splitting on "\\" under POSIX would mangle a filename
    # that legitimately contains one. So build the path natively rather than
    # asserting Windows semantics on every platform.
    deep = os.path.join("some dir", "with space", "xojoctl.py")
    check("a full path is reduced to its basename",
          inv(deep), "python xojoctl.py")
    check("an absolute native path likewise",
          inv(os.path.abspath(deep)), "python xojoctl.py")
    # uv leaves the script path in argv[0] exactly as python does, so the two
    # are indistinguishable and both get the same pasteable answer.
    check("uv run is indistinguishable from python, by design",
          inv("xojoctl.py"), inv("xojoctl.py"))
    check("an installed command stands alone", inv("xojoctl"), "xojoctl")
    check("a shim keeps its own name", inv("/usr/local/bin/xc"), "xc")
    check("a .exe is not something you type", inv("xojoctl.exe"), "xojoctl")
    check("case is not load-bearing", inv("XojoCtl.PY"), "python XojoCtl.PY")
    check("an empty argv falls back to the canonical name", inv(""), X.TOOL_NAME)

    # The rendered help must actually carry it through.
    old_inv = X.INVOCATION
    try:
        set_global("INVOCATION", "python xojoctl.py")
        parser = X.build_parser()
        root = X.render_root_help(parser)
        check("root usage uses the real invocation",
              "% python xojoctl.py <command> [flags]" in root, True)
        check("root examples are pasteable",
              "% python xojoctl.py analyze" in root, True)
        check("no bare 'xojoctl analyze' survives in examples",
              "% xojoctl analyze" in root, False)
        try:
            X.resolve_target("nope")
        except ValueError as exc:
            check("the target error suggests a runnable command",
                  "python xojoctl.py targets" in str(exc), True)
    finally:
        set_global("INVOCATION", old_inv)


def test_target_table() -> None:
    """The table is a transcription of Xojo's documented BuildApp targets:
    https://documentation.xojo.com/topics/build_automation/ide_scripting/building_commands.html
    """
    print("\ntarget table")
    doc = {3: ("Windows", 32), 4: ("Linux", 32), 9: ("macOS", 64),
           10: ("iOS", 64), 12: ("Xojo Cloud", 64), 13: ("iOS", 64),
           14: ("iOS", 64), 16: ("macOS", 64), 17: ("Linux", 64),
           18: ("Linux", 32), 19: ("Windows", 64), 21: ("Android", 64),
           23: ("Android", 64), 24: ("macOS", 64), 25: ("Windows", 64),
           26: ("Linux", 64)}
    got = {t.value: (t.platform, t.bits) for t in X.TARGETS}
    check("every documented value present, and no others",
          sorted(got), sorted(doc))
    check("platform and bit-width match the documentation", got, doc)
    check("values absent from the docs are rejected",
          all(not any(t.value == v for t in X.TARGETS) for v in (7, 15)), True)

    # Sort order: platforms in the stated sequence, then Intel<ARM<universal,
    # 32<64, real<simulator.
    ordered = sorted(X.TARGETS, key=X.target_sort_key)
    plats = [t.platform for t in ordered]
    check("macOS first", plats[0], "macOS")
    check("platforms grouped, not interleaved",
          len(plats), len([i for i, p in enumerate(plats)
                           if i == 0 or p != plats[i - 1]])
          + len(plats) - len(set(plats)))
    mac = [t.name for t in ordered if t.platform == "macOS"]
    check("Intel, then ARM, then Universal",
          mac, ["darwin-amd64", "darwin-arm64", "darwin-universal"])
    lin = [t.name for t in ordered if t.platform == "Linux"]
    check("32-bit before 64-bit within a CPU",
          lin, ["linux-386", "linux-amd64", "linux-arm", "linux-arm64"])
    andr = [t.name for t in ordered if t.platform == "Android"]
    check("real device before emulator", andr,
          ["android-arm64", "android-emulator"])

    # Rendering must not collide when data is narrower than its header.
    res = X.Result(command="targets")
    res.result = {"sort": "platform", "targets": [
        {"value": 24, "name": "darwin-arm64", "platform": "macOS",
         "arch": "ARM 64-bit", "cpu": "arm", "bits": 64,
         "simulator": False}]}
    import io
    buf = io.StringIO()
    X.render_targets(res, X.Style(False), buf)
    lines = buf.getvalue().splitlines()
    head, row = lines[0], lines[1]
    check("column order is PLATFORM ARCH NAME VALUE",
          [head.index(c) == sorted([head.index(x) for x in
                                    ("PLATFORM", "ARCH", "NAME", "VALUE")])[i]
           for i, c in enumerate(("PLATFORM", "ARCH", "NAME", "VALUE"))],
          [True, True, True, True])
    check("header columns do not run together", "PLATFORMARCH" in head, False)
    check("arch column aligns", head.index("ARCH"), row.index("ARM 64-bit"))
    check("name column aligns", head.index("NAME"), row.index("darwin-arm64"))
    check("value column aligns", head.index("VALUE"), row.index("24"))


def test_error_paths() -> None:
    """argparse's own error output bypasses format_help() entirely.

    Before HelpfulParser, a bare `xojoctl` printed all 28 subcommand names and
    aliases plus "error: the following arguments are required: command".
    """
    print("\nerror paths")
    import contextlib, io

    # Bare invocation is a request to see the tool, not an error.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = X.main([])
    check("bare invocation exits 0", rc, X.EX_OK)
    check("bare invocation prints the full help",
          "PROJECT COMMANDS" in buf.getvalue(), True)
    check("bare invocation writes to stdout", len(buf.getvalue()) > 500, True)

    # Unknown command: a suggestion, not a 28-name dump.
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            X.main(["biuld"])
            code = 0
        except SystemExit as e:
            code = e.code
    text = err.getvalue()
    check("unknown command exits 64", code, X.EX_USAGE)
    check("names the bad command", 'unknown command "biuld"' in text, True)
    check("suggests the right one", "Did you mean" in text and "build" in text, True)
    check("does not dump every choice", "list-targets" in text, False)
    check("errors go to stderr", "PROJECT COMMANDS" in text, False)

    # Message humanising, independent of argparse's exact phrasing.
    msg, sugg = X._humanize_argparse_error(
        "argument command: invalid choice: 'analze' (choose from 'analyze', 'build')")
    check("humanised unknown command", msg, 'unknown command "analze"')
    check("close match found", sugg, "analyze")
    msg, _ = X._humanize_argparse_error(
        "the following arguments are required: command")
    check("humanised missing command", msg, "no command given")
    msg, _ = X._humanize_argparse_error(
        "the following arguments are required: -t/--target")
    check("humanised missing flag", msg, "missing required argument: -t/--target")


def test_split_reply() -> None:
    """The IDE can split one reply across messages under a single tag.

    exchange() claims whichever arrives FIRST. When a compiler warning and the
    script's own Print output arrive separately, that made the reported output
    depend on a millisecond of ordering: the warning could be reported as the
    script's output, and the output lost.
    """
    print("\nsplit replies (output vs diagnostics under one tag)")
    ide = MockIDE()
    try:
        with X.Client(ide.transport(), first_ceiling=5.0, reply_ceiling=5.0) as c:
            ex = c.exchange("WARNFIRST")
            # The warning wins the race, so the claimed reply is NOT the output.
            check("the claimed reply is the warning, not the output",
                  ex.result.verdict, X.Verdict.WARNINGS)
            parts = [X.classify(m) for m in c.collect_tag(ex.tag)]
            check("both messages are collected", len(parts), 2)
            text = next((p.text for p in parts
                         if p.verdict is X.Verdict.OK and p.text is not None), None)
            check("the script's real output is recovered", text, "42")
            warn = next((p for p in parts if p.verdict is X.Verdict.WARNINGS), None)
            check("the warning is still reported", warn is not None, True)
            check("a warning alone is not an error",
                  warn.verdict is X.Verdict.SCRIPT_ERROR, False)

            # The window covers millisecond jitter only. When the output
            # trails the warning by the script's RUNTIME, await_reply_part
            # must recover it instead of silently reporting output null.
            ex = c.exchange("WARNSLOW")
            parts = [X.classify(m) for m in c.collect_tag(ex.tag)]
            check("the split window alone misses a slow script's output",
                  any(p.verdict is X.Verdict.OK and p.text is not None
                      for p in parts), False)
            late = c.await_reply_part(
                ex.tag,
                lambda m: (X.classify(m).verdict is X.Verdict.OK
                           and X.classify(m).text is not None),
                3.0)
            check("await_reply_part recovers the late output",
                  X.classify(late).text if late is not None else None, "42")
            check("a part that already arrived returns immediately",
                  X.classify(c.await_reply_part(
                      ex.tag, lambda m: X.classify(m).text == "42", 0.5)).text,
                  "42")
    finally:
        ide.close()


def test_sentinel_no_stomp() -> None:
    """The documented sentinel-only build outcome yields ONE message that is
    both the claimed reply and the sentinel. await_sentinel must confirm
    completion without downgrading the message's "tagged" label -- raw.messages
    keeps exactly one tagged entry per exchange, which is the contract
    consumers use to locate the claimed reply.
    """
    print("\nsentinel claiming (channel label must not be stomped)")
    ide = MockIDE()
    try:
        with X.Client(ide.transport(), first_ceiling=5.0, reply_ceiling=5.0) as c:
            ex = c.exchange("SENTONLY")
            check("the reply is claimed as tagged", ex.reply.channel, "tagged")
            check("await_sentinel still confirms completion",
                  c.await_sentinel(ex.tag, X.BUILD_SENTINEL, timeout=2.0), True)
            check("the claimed reply keeps its tagged label",
                  ex.reply.channel, "tagged")
    finally:
        ide.close()


def test_probe_timeout() -> None:
    """A listener that accepts and then says nothing must not hang the probe.

    Several Xojo-owned loopback listeners that are NOT the IDE Communicator
    (debug targets, web previews) behave exactly like this, and the probe's
    deadline used to bound only the loop, not the blocking recv inside it.
    """
    print("\nport probe deadline (silent listener)")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        t0 = time.monotonic()
        check("a silent listener probes False", X.probe_port(port, 1.0, "tok"), False)
        check("within the deadline, not forever", time.monotonic() - t0 < 5.0, True)
    finally:
        srv.close()


def test_cli_guards() -> None:
    """Offline guard rails: empty arguments and a bad XOJOCTL_PORT fail
    helpfully, before any connection is attempted.
    """
    print("\nCLI guard rails (offline)")
    import contextlib, io

    def run(argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = X.main(argv)
        return rc, out.getvalue(), err.getvalue()

    rc, out, _ = run(["script", "", "--json"])
    check("an empty script argument exits 64", rc, X.EX_USAGE)
    check("and says the script is empty",
          "empty" in json.loads(out)["error"]["message"], True)
    rc, _, _ = run(["script", "--file", ""])
    check("an empty --file exits 64", rc, X.EX_USAGE)
    rc, _, _ = run(["analyze", "--item", "  "])
    check("a blank --item exits 64", rc, X.EX_USAGE)
    rc, _, _ = run(["projects", "--select", ""])
    check("an empty --select exits 64", rc, X.EX_USAGE)
    rc, _, _ = run(["open", ""])
    check("an empty open path exits 64", rc, X.EX_USAGE)

    check("no-project-open is not 'could not connect'",
          X.EX_NO_PROJECT == X.EX_CONNECT, False)

    old = os.environ.get("XOJOCTL_PORT")
    os.environ["XOJOCTL_PORT"] = "auto"
    try:
        rc, _, _ = run(["targets"])
        check("offline commands ignore a bad XOJOCTL_PORT", rc, X.EX_OK)
        check_raises("a bad XOJOCTL_PORT fails helpfully at connect time",
                     X.port_from_env, X.XojoError)
        os.environ["XOJOCTL_PORT"] = "70000"
        check_raises("an out-of-range port is rejected",
                     X.port_from_env, X.XojoError)
        os.environ["XOJOCTL_PORT"] = "8080"
        check("a valid port parses", X.port_from_env(), 8080)
        os.environ["XOJOCTL_PORT"] = ""
        check("empty means unset", X.port_from_env(), None)
    finally:
        if old is None:
            os.environ.pop("XOJOCTL_PORT", None)
        else:
            os.environ["XOJOCTL_PORT"] = old


def test_usage_json() -> None:
    """--json promises exactly one JSON document on stdout ALWAYS. argparse-
    level failures (missing required flag) used to bypass the Result machinery
    and emit zero bytes, which a jq consumer reads as silent empty input.
    """
    print("\nusage errors under --json")
    import contextlib, io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            X.main(["build", "--json"])       # missing required --target
            code = 0
        except SystemExit as e:
            code = e.code
    check("missing --target exits 64", code, X.EX_USAGE)
    doc = json.loads(out.getvalue())
    check("stdout carries one JSON document", doc["ok"], False)
    check("outcome is usage_error", doc["outcome"], "usage_error")
    check("exit_code matches the exit status", doc["exit_code"], X.EX_USAGE)

    out2, err2 = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out2), contextlib.redirect_stderr(err2):
        try:
            X.main(["build"])                 # no --json: human error only
        except SystemExit:
            pass
    check("without --json stdout stays empty", out2.getvalue(), "")
    check("the human error still lands on stderr",
          "error:" in err2.getvalue(), True)

    # argparse accepts unambiguous long-option abbreviations, so --jso enables
    # JSON on a successful parse -- a usage error must honor it identically.
    out3, err3 = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out3), contextlib.redirect_stderr(err3):
        try:
            X.main(["build", "--jso"])
        except SystemExit:
            pass
    check("an abbreviated --jso still gets the JSON document",
          json.loads(out3.getvalue())["outcome"], "usage_error")


def test_close_semantics() -> None:
    """CloseProject(prompt As Boolean = True) -- the flag is PROMPT, not save.

    True shows a dialog asking whether to save, which parks a modal in front of
    nobody during automation; it can never save. So --save must run SaveFile
    first and then close with prompt=False.
    """
    print("\nclose semantics")
    save = X.script_close_project(True)
    disc = X.script_close_project(False)
    check("--save saves first", 'DoCommand("SaveFile")' in save, True)
    check("--save still closes without prompting", "CloseProject(False)" in save, True)
    check("--save never passes True (which would prompt)",
          "CloseProject(True)" in save, False)
    check("--discard does not save", 'DoCommand("SaveFile")' in disc, False)
    check("--discard closes without prompting", "CloseProject(False)" in disc, True)


def test_projects() -> None:
    """WindowTitle is 0-based and index 0 is frontmost, established live."""
    print("\nprojects / workspace enumeration")
    scr = X.script_list_windows()
    check("enumerates with one Print, not one per window", scr.count("Print"), 1)
    check("declares the loop variable separately (dialect requires it)",
          "Var i As Integer" in scr, True)
    check("select by index passes a number", X.script_select_window("2").split("\n")[0],
          "SelectWindow(2)")
    check("select by title passes a quoted string",
          X.script_select_window("Desktop App").split("\n")[0],
          'SelectWindow("Desktop App")')
    check("a title with a quote is doubled, not backslashed",
          X.script_select_window('a"b').split("\n")[0], 'SelectWindow("a""b")')

    # render_projects took a Style, not a Theme -- an untested renderer that
    # crashed on first use. Cover it.
    import io
    res = X.Result(command="projects")
    res.result = {"count": 2, "selected": None, "projects": [
        {"index": 0, "title": "Test", "front": True, "path": "/tmp/Test.xojo_project"},
        {"index": 1, "title": "Desktop App", "front": False, "path": None}]}
    buf = io.StringIO()
    X.render_projects(res, X.Style(False), buf)
    text = buf.getvalue()
    check("renders without raising", "Test" in text and "Desktop App" in text, True)
    check("marks the frontmost", "*" in text.splitlines()[1], True)
    check("second workspace is not marked", "*" in text.splitlines()[2], False)

    buf2 = io.StringIO()
    X.render_projects(X.Result(command="projects"), X.Style(False), buf2)
    check("empty case does not raise", "no projects open" in buf2.getvalue(), True)


def test_arg_validation() -> None:
    """Duration and port flags reject values that used to spin, crash, or
    traceback: nan (Condition.wait(nan) returns instantly forever), inf
    (uncaught OverflowError), and out-of-range ports (OverflowError from
    socket.connect that no except ladder catches).
    """
    print("\nargument validation (nan/inf/port range)")
    for bad in ("nan", "inf", "-inf", "-1", "abc", "9999999999"):
        # 9999999999: a finite value past the platform timestamp range
        # overflows settimeout/Condition.wait exactly like inf does.
        check_raises("--timeout %s is a usage error" % bad,
                     lambda b=bad: X._seconds_arg(b), argparse.ArgumentTypeError)
    check("zero seconds stays legal (expire immediately)", X._seconds_arg("0"), 0.0)
    check("decimals still parse", X._seconds_arg("1.5"), 1.5)
    for bad in ("0", "65536", "70000", "-1", "x"):
        check_raises("--port %s is a usage error" % bad,
                     lambda b=bad: X._port_arg(b), argparse.ArgumentTypeError)
    check("a real port still parses", X._port_arg("4711"), 4711)
    # OverflowError backstop: an out-of-range port reaching connect_tcp is a
    # curated TransportUnavailable, not a traceback.
    check_raises("connect_tcp(70000) fails as a transport error",
                 lambda: X.connect_tcp(70000, timeout=0.2), X.TransportUnavailable)


def test_no_aliases() -> None:
    """Every subcommand is registered under exactly one name.

    Aliases were removed: they multiplied the supported surface without
    making anything possible. This asserts none creep back in, because a
    stray alias would once again make the parsed command name differ from
    the canonical one that reaches the JSON `command` field.
    """
    print("\ncommand names (no aliases)")
    parser = X.build_parser()
    sub = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)][0]
    check("no command is registered under a second name",
          sorted(sub.choices), sorted(X.COMMAND_BLURBS))
    check("COMMAND_ALIASES is gone", hasattr(X, "COMMAND_ALIASES"), False)
    # The parsed name is used verbatim as the JSON `command`, so the two
    # sets matching is what makes that safe.
    check("every registered parser is its own canonical name",
          sorted(X._subparsers(sub)), sorted(sub.choices))


def test_worst_of() -> None:
    """A multi-part reply is judged by its WORST part, whatever order the
    transport delivered them in -- sentinel-first must not read as clean.
    """
    print("\nmulti-part verdicts")
    ok = X.Classification(X.Verdict.OK, text="path")
    warn = X.Classification(X.Verdict.WARNINGS)
    err = X.Classification(X.Verdict.ERRORS)
    empty = X.Classification(X.Verdict.EMPTY)
    check("errors outrank warnings", X.worst_of([warn, err]).verdict, X.Verdict.ERRORS)
    check("delivery order does not matter",
          X.worst_of([err, warn]).verdict, X.Verdict.ERRORS)
    check("empty outranks ok", X.worst_of([ok, empty]).verdict, X.Verdict.EMPTY)
    check("first wins on equal severity", X.worst_of([ok, X.Classification(
        X.Verdict.OK, text="other")]).text, "path")
    check("an empty list is None", X.worst_of([]), None)


def test_discovery_budget() -> None:
    """The patient pass shares ONE deadline across every candidate port:
    per-port ceilings multiplied (k silent ports x 900s each) while the
    failure message claimed a single ceiling had elapsed.
    """
    print("\nport discovery budget")
    old = (X.xojo_pids, X.listening_ports, X.probe_port)
    calls = []
    try:
        set_global("xojo_pids", lambda: {1})
        set_global("listening_ports", lambda pids: [1111, 2222, 3333])

        def fake_probe(port, timeout, token):
            calls.append((port, timeout))
            time.sleep(min(timeout, 0.4))
            return False

        set_global("probe_port", fake_probe)
        t0 = time.monotonic()
        try:
            X.discover_port(quick=0.0, patient=1.0)
            check("discovery fails when nothing answers", "returned", "raise")
        except X.TransportUnavailable as e:
            check("the message reports how long discovery actually took",
                  "answered IDE Communicator v2 within" in str(e), True)
        elapsed = time.monotonic() - t0
        check("discovery is bounded by one shared deadline", elapsed < 2.5, True)
        patient = calls[3:]      # the first three are the quick pass
        check("no single probe got more than the whole budget",
              max(t for _, t in patient) <= 1.0 + 0.01, True)
        # Round-robin fairness: a silent first port must not starve the rest.
        check("every candidate got a share of the patient budget",
              sorted(set(p for p, _ in patient)), [1111, 2222, 3333])

        # The quick pass must obey the budget too. A hardcoded 6s per port
        # meant `--timeout 1` still burned 6 x k seconds before the patient
        # pass began, and the error then reported an elapsed far larger
        # than the budget the caller asked for.
        del calls[:]
        t0 = time.monotonic()
        try:
            X.discover_port(quick=6.0, patient=0.5)
        except X.TransportUnavailable:
            pass
        check("the quick pass cannot overrun a small budget",
              time.monotonic() - t0 < 2.0, True)
        check("no quick probe was given more than the budget",
              max(t for _, t in calls) <= 0.5 + 0.01, True)
    finally:
        for _n, _v in zip(("xojo_pids", "listening_ports", "probe_port"), old):
            set_global(_n, _v)


def test_send_deadline() -> None:
    """A peer that accepts and never reads must not block sendall() forever:
    the reply ceiling has to bound the WRITE too, or a large script to a busy
    IDE wedges the client with no timeout and no error.
    """
    print("\nbounded send (non-draining peer)")
    if X.IS_WINDOWS:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        tr = X.connect_tcp(srv.getsockname()[1])
        cleanup = None
    else:
        d = tempfile.mkdtemp()
        path = os.path.join(d, "sink")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(1)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        tr = X._SocketTransport(s, path, "unix")
        cleanup = d
    try:
        big = b"x" * (32 * 1024 * 1024)
        t0 = time.monotonic()
        check_raises("a stuck send fails at the deadline, not never",
                     lambda: tr.send(big, deadline=time.monotonic() + 1.0),
                     X.TransportUnavailable)
        check("the send gave up near the deadline",
              time.monotonic() - t0 < 5.0, True)
    finally:
        tr.close()
        srv.close()
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)


def test_peer_uid() -> None:
    """The post-connect peer check closes the stat-to-connect race on the
    socket path. Fail-open: None on any platform surprise; on macOS/Linux a
    socketpair peer is ourselves.
    """
    print("\npeer credentials")
    if X.IS_WINDOWS or not hasattr(socket, "AF_UNIX"):
        print("  ok   skipped (no AF_UNIX on this platform)")
        return
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        uid = X._peer_uid(a)
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            check("peer uid resolves to our own euid", uid, os.geteuid())
        else:
            check("unknown platform fails open", uid, None)
    finally:
        a.close()
        b.close()


def test_render_output_with_warning() -> None:
    """A script that both printed and warned shows BOTH in human mode --
    the README's promise. The renderer used to suppress the output whenever
    any diagnostic was present.
    """
    print("\nhuman rendering (output alongside a warning)")
    import io
    res = X.Result(command="script")
    res.result = {"output": "42"}
    res.diagnostics = [{"severity": "warning", "message": "possible loss of "
                        "precision"}]
    res.summary = "script completed"
    buf = io.StringIO()
    X.render_human(res, X.Style(False), buf)
    text = buf.getvalue()
    check("the output is reported as the output", "42" in text, True)
    # Assert on the diagnostic's MESSAGE, not the word 'warning' (which the
    # summary line could also carry) -- this fails if the diagnostics block
    # itself regresses.
    check("the warning is reported as a warning",
          "possible loss of precision" in text, True)
    # Warning-only replies have output None and must not render it.
    res2 = X.Result(command="script")
    res2.result = {"output": None}
    res2.diagnostics = [{"severity": "warning", "message": "w"}]
    buf2 = io.StringIO()
    X.render_human(res2, X.Style(False), buf2)
    check("a None output is never rendered", "None" in buf2.getvalue(), False)


def test_command_flows() -> None:
    """End-to-end cmd_analyze/cmd_build/cmd_script against the mock IDE: the
    verdict logic that decides exit codes, judged over every reply part.
    Without these, reverting the multi-part judging or the build backstop
    passes the whole suite.
    """
    print("\ncommand flows (mock IDE end-to-end)")
    ide = MockIDE()
    old_open = X.open_client
    old_analyze = X.script_analyze_project

    def fake_open(args, res):
        return X.Client(ide.transport(), first_ceiling=5.0, reply_ceiling=5.0)

    def run(cmd, **over):
        base = dict(quiet=True, json=False, timeout=5.0, warm_timeout=5.0,
                    connect_timeout=5.0, color="never", warnings_as_errors=False)
        base.update(over)
        args = argparse.Namespace(**base)
        res = X.Result(command=cmd.__name__.replace("cmd_", ""))
        cmd(args, res)
        return res

    try:
        set_global("open_client", fake_open)

        res = run(X.cmd_build, target=["9"], reveal=False,
                  stop_on_error=False, build_timeout=5.0)
        check("build: path plus sentinel is success",
              (res.exit_code, res.result["artifacts"][0]["ok"]), (0, True))
        check("build: the shell path is unescaped",
              res.result["artifacts"][0]["path"], "/tmp/Mock Builds/App.app")

        res = run(X.cmd_build, target=["24"], reveal=False,
                  stop_on_error=False, build_timeout=5.0)
        check("build: sentinel-only is EMPTY, exit 1",
              (res.outcome, res.exit_code),
              ("empty_response", X.EX_PROJECT_ERRORS))

        res = run(X.cmd_build, target=["16"], reveal=False,
                  stop_on_error=False, build_timeout=5.0)
        check("build: errors alongside an artifact are still reported",
              (res.exit_code, len(res.diagnostics)),
              (X.EX_PROJECT_ERRORS, 1))
        check("build: the artifact is still recorded",
              res.result["artifacts"][0]["ok"], True)

        res = run(X.cmd_build, target=["19"], reveal=False,
                  stop_on_error=False, build_timeout=5.0)
        check("build: a failed target can never exit 0 (backstop)",
              (res.outcome, res.exit_code),
              ("build_failed", X.EX_PROJECT_ERRORS))
        check("build: the exit-0 advisory is dropped when the backstop fires",
              any(n["code"] == "warnings_only_exit_zero" for n in res.notes),
              False)

        set_global("script_analyze_project", lambda: "Print SENTFIRST")
        res = run(X.cmd_analyze, item=None, severity="all", analyze_timeout=5.0)
        check("analyze: sentinel-first dirty is judged dirty",
              (res.outcome, res.exit_code),
              ("project_errors", X.EX_PROJECT_ERRORS))
        set_global("script_analyze_project", old_analyze)

        # The appended sentinel ends the wait as soon as the script
        # finishes, so a script that warns and prints nothing returns at
        # once instead of stalling for a ceiling it can never satisfy.
        t0 = time.monotonic()
        res = run(X.cmd_script, source="WARNENDED", file=None, stdin=False)
        check("script: a silent script no longer waits out a ceiling",
              time.monotonic() - t0 < 3.0, True)
        check("script: completion is confirmed by the sentinel",
              res.result["completed"], True)
        check("script: no output is reported as no output, not a failure",
              (res.result["output"], res.exit_code), (None, 0))

        res = run(X.cmd_script, source="WARNSLOW", file=None, stdin=False)
        check("script: late output recovered end-to-end",
              res.result["output"], "42")
    finally:
        set_global("open_client", old_open)
        set_global("script_analyze_project", old_analyze)
        ide.close()


def main() -> int:
    test_escaping()
    test_shell_path()
    test_framer()
    test_classification()
    test_normalization()
    test_targets()
    test_sanitize()
    test_analyze_script_shape()
    test_help_width()
    test_invocation_name()
    test_bom_handling()
    test_channel_classification()
    test_help()
    test_helptext_generic()
    test_target_table()
    test_error_paths()
    test_split_reply()
    test_sentinel_no_stomp()
    test_probe_timeout()
    test_cli_guards()
    test_usage_json()
    test_close_semantics()
    test_projects()
    test_arg_validation()
    test_no_aliases()
    test_worst_of()
    test_discovery_budget()
    test_send_deadline()
    test_peer_uid()
    test_render_output_with_warning()
    test_command_flows()
    test_client()
    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
