#!/usr/bin/env python3
"""C0 proxy: measure keystroke->diagnostic latency of tlapm's LSP server.

Protocol: initialize/initialized, didOpen <file>, wait for
publishDiagnostics (t_open); then N didChange edits (insert/remove a
space inside a proof body), each timed to its publishDiagnostics
(t_change_i). Prints a CSV-ish summary.
"""
import json, os, subprocess, sys, tempfile, time

SRV = sys.argv[1]
FILE = os.path.abspath(sys.argv[2])
EDIT_LINE = int(sys.argv[3])  # 0-based line inside a proof to poke
N_EDITS = int(sys.argv[4]) if len(sys.argv) > 4 else 3

LOGDIR = os.environ.get("LSP_LOG_DIR") or tempfile.mkdtemp(prefix="lsp-keystroke-")
proc = subprocess.Popen(
    [SRV, "--stdio", "--log-io", "--log-to=%s/server.log" % LOGDIR],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=open(os.path.join(LOGDIR, "server.stderr"), "ab"))

_id = [0]
def send(method, params, notify=False):
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        _id[0] += 1
        msg["id"] = _id[0]
    b = json.dumps(msg).encode()
    proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(b) + b)
    proc.stdin.flush()
    return _id[0]

def recv(timeout=600):
    end = time.time() + timeout
    hdr = b""
    while b"\r\n\r\n" not in hdr:
        c = proc.stdout.read(1)
        if not c:
            raise EOFError("server closed")
        hdr += c
        if time.time() > end:
            raise TimeoutError
    n = int([l for l in hdr.split(b"\r\n") if b"Content-Length" in l][0].split(b":")[1])
    return json.loads(proc.stdout.read(n))

def pull_diags(want_ver):
    t0 = time.time()
    rid = send("textDocument/diagnostic", {"textDocument": {"uri": uri}})
    while True:
        m = recv()
        if (m.get("method") == "textDocument/publishDiagnostics"
                and m["params"].get("version") == want_ver):
            return time.time() - t0, m["params"]

uri = "file://" + FILE
text = open(FILE).read()
lines = text.split("\n")

send("initialize", {"processId": os.getpid(), "rootUri": "file://" + os.path.dirname(FILE),
                    "capabilities": {}})
while True:
    m = recv()
    if m.get("id") == 1: break
send("initialized", {}, notify=True)

t0 = time.time()
send("textDocument/didOpen", {"textDocument": {
    "uri": uri, "languageId": "tlaplus", "version": 1, "text": text}}, notify=True)
dt, diags = pull_diags(1)
print(f"open->markers: {time.time()-t0:.2f}s")

ver = 1
orig = lines[EDIT_LINE]
for i in range(N_EDITS):
    ver += 1
    # alternate: add / remove a trailing space on the edit line
    newline = orig + " " if ver % 2 == 0 else orig
    t0 = time.time()
    lines[EDIT_LINE] = newline
    send("textDocument/didChange", {
        "textDocument": {"uri": uri, "version": ver},
        "contentChanges": [{"text": "\n".join(lines)}]}, notify=True)
    dt, diags = pull_diags(ver)
    print(f"edit{i+1}->diag: {time.time()-t0:.2f}s (diags: {len(diags.get('diagnostics', []))})")

proc.kill()
