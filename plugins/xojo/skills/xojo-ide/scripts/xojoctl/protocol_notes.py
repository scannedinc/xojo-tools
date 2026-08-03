PROTOCOL_NOTES = r'''
xojoctl -- drive a running Xojo IDE over its IDE Communicator socket.

Triggers Analyze and Build in a running Xojo IDE and returns structured errors
and warnings, as human-readable text or as JSON for other tools.

    xojoctl status
    xojoctl analyze
    xojoctl analyze --json | jq '.diagnostics[]'
    xojoctl build --target darwin-arm64

The Xojo IDE must already be RUNNING: it creates the socket, and this only dials
it. There is no way to start the IDE through this protocol.

================================================================================
PROTOCOL NOTES
================================================================================

Framing     UTF-8 JSON terminated by a single NUL byte. No length prefix. One
            recv() may carry several messages, or part of one.

Handshake   Send {"protocol":2}<NUL> on connect. NO acknowledgement is sent --
            never wait for one.

Request     {"script": "...", "tag": "..."}<NUL>
Reply       {"tag": "...", "response": <string | object>}
            Errors nest INSIDE "response": buildError / scriptError / openErrors.

THE FINDINGS THAT SHAPE THIS CLIENT
-----------------------------------

1.  THE IDE REPLIES ONLY WHEN A SCRIPT PRINTS.
    A script with no output gets no reply at all and the read blocks to the
    ceiling -- but the script still ran.

2.  A CLEAN ANALYZE RETURNS NOTHING.
    `DoCommand("CheckProjectErrors")` on a project with zero errors and zero
    warnings emits NOTHING -- not {}, not an empty buildError. Silence.
    Therefore the analyze script MUST end with a Print sentinel, or every clean
    project hangs for the full 900s ceiling.

3.  A TRAILING PRINT DOES NOT CLOBBER DIAGNOSTICS.
    Tested both ways: with diagnostics present, `CheckProjectErrors` + a
    trailing Print still returns the buildError object: the diagnostics win
    over the Print value. Combined with (2) this makes the sentinel strictly
    correct:
        dirty project -> {"response": {"buildError": {...}}}
        clean project -> {"response": "<sentinel>"}

4.  THE SOCKET CHURNS. The IDE unlinks and recreates /tmp/XojoIDE after a
    client disconnects. Two connects in quick succession will hit ENOENT or
    ECONNREFUSED on the second. Connecting therefore RETRIES with backoff --
    this is normal operation, not an error.

5.  THE IDE SENDS UNSOLICITED MESSAGES, REUSING A TAG IT WAS PREVIOUSLY SENT.
    Reproduced: connect, send one request (tag "X-1"), then click
    Project > Analyze Project in the IDE by hand. 5.9s later an unrequested
    message arrives carrying the FULL buildError -- tagged "X-1", the tag of
    the already-completed request. Xojo staff have acknowledged this as a bug.

    Consequence: tags are never reused by this client, but that is NOT complete
    protection. The observed message reused the LAST TAG SENT, so if analysis
    is triggered in the IDE while an exchange is genuinely in flight, its
    payload can be mistaken for that exchange's reply. Benign for `analyze`
    (the payload is the analysis result, which is what was wanted); for `build`
    it could report analysis diagnostics as build diagnostics. There is no way
    to tell them apart at the protocol level -- both are a buildError object.
    Keep the IDE untouched during unattended runs.

    A message is therefore only labeled "tagged" once an exchange has actually
    CLAIMED it; everything else stays "out-of-band" in raw.messages.

6.  BuildApp RETURNS A SHELL-ESCAPED PATH, e.g.
        /Users/me/Test\\ Project/Builds\\ \\-\\ Test/macOS\\ ARM\\ 64\\ bit/Test.app
    It must be unescaped before use as a filesystem path -- on POSIX only.
    Windows paths use the backslash as their SEPARATOR, so they are passed
    through untouched there.

OTHER VERIFIED BEHAVIOR
------------------------
*   The endpoint EXISTS and answers with NO project open, on both macOS
    and Windows; `analyze` then fails with no_project_open
    rather than a connection error. Older notes claimed the Windows listener
    required an open project. That is no longer true.
*   BuildApp NEVER reports warnings; only analyze does. A clean build does not
    mean the project has no warnings.
*   There is no build target 7, despite Xojo's own docs using BuildApp(7,False)
    as their example. It returns {} -- no path, no error, no build.
*   Xojo is single-instance. With several projects open, commands act on the
    frontmost workspace and the protocol gives no way to tell which.

TRANSPORT
---------
    macOS/Linux  AF_UNIX at /tmp/<name> (default XojoIDE, override XOJO_IPCPATH)
    Windows      Loopback TCP. NO socket file and NO named pipe exist. The port
                 is unpublished, so it is discovered from Xojo.exe's listening
                 ports and probed.

SECURITY
--------
IDE Script includes DoShellCommand. Anything that can write to this socket has
code execution as the user running the IDE. Never pass untrusted input to
`xojoctl script`. Interpolated values are escaped in two layers -- see
xojo_string_literal() -- and the POSIX socket's ownership is checked before use.
'''
