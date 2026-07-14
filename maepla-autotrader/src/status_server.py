import re
import os
import json
import time
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "autotrader.log")
HOST = "127.0.0.1"
PORT = 8888


def get_status():
    status = {
        "running": False,
        "pid": None,
        "last_update": "-",
        "price": "-",
        "score": "-",
        "decision": "WAIT",
        "cycles": 0,
        "uptime": "-",
    }

    try:
        out = subprocess.run(
            ["powershell", "-Command",
             "Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, StartTime | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5
        )
        if out.stdout.strip() and out.stdout.strip() != "null":
            data = json.loads(out.stdout.strip())
            if isinstance(data, list):
                data = data[-1]
            status["pid"] = data.get("Id")
            start = data.get("StartTime")
            if start:
                elapsed = datetime.now() - datetime.fromisoformat(start.replace("Z", ""))
                mins = int(elapsed.total_seconds() // 60)
                status["uptime"] = f"{mins // 60}h {mins % 60}m"
                status["running"] = True
    except Exception:
        pass

    if os.path.exists(LOG):
        try:
            with open(LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines[-50:]):
                m = re.search(r'\[(\d{2}:\d{2}:\d{2})\]\s+\$?([\d.]+)?\s*\|\s*(\w+)\s*\|\s*Score:\s*(\d+)', line)
                if m:
                    status["last_update"] = m.group(1)
                    status["price"] = m.group(2) or "-"
                    status["decision"] = m.group(3)
                    status["score"] = m.group(4)
                    break
            status["cycles"] = sum(1 for l in lines if "Score:" in l)
        except Exception:
            pass

    return status


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status = get_status()
        color = "#22c55e" if status["running"] else "#ef4444"
        html = f"""<!DOCTYPE html>
<html lang="th">
<head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<title>Mae Pla Auto Trader</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0;
          display:flex; justify-content:center; align-items:center; min-height:100vh; }}
  .card {{ background:#1e293b; border-radius:24px; padding:40px 56px; width:520px;
           box-shadow:0 25px 50px rgba(0,0,0,0.5); text-align:center; }}
  .dot {{ display:inline-block; width:16px; height:16px; border-radius:50%;
          background:{color}; margin-right:8px;
          box-shadow:0 0 12px {color}; animation:pulse 1.5s infinite; }}
  @keyframes pulse {{ 0%{{opacity:1}} 50%{{opacity:0.4}} 100%{{opacity:1}} }}
  .status {{ display:flex; align-items:center; justify-content:center; font-size:28px; font-weight:700; margin-bottom:8px; }}
  .sub {{ color:#94a3b8; font-size:14px; margin-bottom:24px; }}
  .row {{ display:flex; justify-content:space-between; padding:12px 0; border-bottom:1px solid #334155; font-size:18px; }}
  .label {{ color:#94a3b8; }} .value {{ font-weight:600; }}
  .big {{ font-size:40px; font-weight:800; }}
  .badge {{ display:inline-block; padding:4px 16px; border-radius:999px; font-size:14px;
            background:#334155; }}
  .good {{ color:{color}; }}
</style>
</head>
<body>
<div class="card">
  <div class="status"><span class="dot"></span>{"RUNNING" if status["running"] else "STOPPED"}</div>
  <div class="sub">PID: {status["pid"] or "-"} | Uptime: {status["uptime"]}</div>
  <div class="row"><span class="label">ราคาล่าสุด</span><span class="value">${status["price"]}</span></div>
  <div class="row"><span class="label">Decision</span><span class="value">{status["decision"]}</span></div>
  <div class="row"><span class="label">Score</span><span class="big">{status["score"]}</span></div>
  <div class="row"><span class="label">รอบทั้งหมด</span><span class="value">{status["cycles"]}</span></div>
  <div class="row"><span class="label">อัปเดตล่าสุด</span><span class="value">{status["last_update"]}</span></div>
  <div style="margin-top:20px;font-size:13px;color:#64748b;">Auto-refresh ทุก 5 วิ</div>
</div>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode())))
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass


def run():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Dashboard: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
