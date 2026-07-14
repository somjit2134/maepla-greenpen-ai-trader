"""Simple runtime status web server for auto-trader."""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.connector import MT5Connector, get_connector
from src.database import Database
from src.trading import TradingEngine

STATUS_PATH = os.path.join("runtime", "status.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def read_status() -> dict:
    if not os.path.exists(STATUS_PATH):
        return {
            "is_running": False,
            "status_text": "NOT RUNNING",
            "reason": "No heartbeat file found yet",
            "updated_at": _iso_now(),
        }

    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "is_running": False,
            "status_text": "UNKNOWN",
            "reason": f"Cannot read status file: {e}",
            "updated_at": _iso_now(),
        }

    interval = data.get("monitor_interval_seconds", 60)
    updated_at = _to_utc_naive(_parse_iso(data.get("updated_at")))
    stale = True
    if updated_at is not None:
        stale = (datetime.utcnow() - updated_at).total_seconds() > (interval * 2 + 15)

    is_running = bool(data.get("is_running", False)) and not stale
    data["is_running"] = is_running
    data["status_text"] = "RUNNING" if is_running else "STOPPED"
    data["stale"] = stale
    data.setdefault("updated_at", _iso_now())
    return data


def _build_manual_plan(side: str) -> tuple[dict, str]:
    connector = get_connector()
    if not connector.connect():
        return {}, "Cannot connect to MT5"

    try:
        bid, ask, _spread = connector.tick()
        if bid <= 0 or ask <= 0:
            return {}, "Invalid market price"

        entry = ask if side == "BUY" else bid
        sl_distance = 10.0

        if side == "BUY":
            sl = round(entry - sl_distance, 2)
            tp1 = round(entry + (sl_distance * 2), 2)
            tp2 = round(entry + (sl_distance * 3), 2)
        else:
            sl = round(entry + sl_distance, 2)
            tp1 = round(entry - (sl_distance * 2), 2)
            tp2 = round(entry - (sl_distance * 3), 2)

        plan = {
            "direction": side,
            "entry": round(entry, 2),
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "rr": 2.0,
            "reason": "Manual order from status dashboard",
        }
        return plan, "ok"
    finally:
        pass


def place_manual_order(side: str) -> dict:
    side = (side or "").upper()
    if side not in ("BUY", "SELL"):
        return {"success": False, "msg": "side must be BUY or SELL"}

    plan, err = _build_manual_plan(side)
    if not plan:
        return {"success": False, "msg": err}

    connector = get_connector()
    if not connector.connect():
        return {"success": False, "msg": "Cannot connect to MT5"}

    try:
        db = Database()
        engine = TradingEngine(connector, db)
        account = engine.get_account()
        balance = account.get("balance", 10000)
        result = engine.execute(plan, analysis_id=0, balance=balance)
        return result
    finally:
        pass


HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MaePla Auto Trader Status</title>
  <style>
    :root {
      --bg: #0d1b2a;
      --panel: #1b263b;
      --text: #e0e1dd;
      --muted: #9aa7b2;
      --ok: #2ec27e;
      --bad: #ff6b6b;
      --warn: #f6c177;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: radial-gradient(circle at 20% 20%, #1b263b 0%, #0d1b2a 55%, #09111f 100%);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      place-items: center;
    }
    .card {
      width: min(760px, 92vw);
      background: color-mix(in oklab, var(--panel) 92%, black 8%);
      border: 1px solid #2d3f58;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(0,0,0,.35);
    }
    h1 { margin: 0 0 10px; font-size: 24px; }
    .pill {
      display: inline-block;
      padding: 6px 12px;
      border-radius: 999px;
      font-weight: 700;
      letter-spacing: .4px;
    }
    .ok { background: rgba(46,194,126,.18); color: var(--ok); border: 1px solid rgba(46,194,126,.45); }
    .bad { background: rgba(255,107,107,.18); color: var(--bad); border: 1px solid rgba(255,107,107,.45); }
    .warn { background: rgba(246,193,119,.16); color: var(--warn); border: 1px solid rgba(246,193,119,.45); }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; margin-top: 16px; }
    .item { background: #132238; border: 1px solid #29405f; border-radius: 12px; padding: 12px; }
    .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
    .v { margin-top: 6px; font-size: 18px; font-weight: 600; }
    .tiny { margin-top: 16px; color: var(--muted); font-size: 12px; }
    .controls { margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap; }
    .btn {
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      font-weight: 700;
      color: #fff;
      cursor: pointer;
    }
    .btn:disabled { opacity: .55; cursor: not-allowed; }
    .buy { background: linear-gradient(135deg, #0da16b, #2ec27e); }
    .sell { background: linear-gradient(135deg, #c23636, #ff6b6b); }
    .log {
      margin-top: 12px;
      background: #0d182a;
      border: 1px solid #26405e;
      border-radius: 12px;
      padding: 10px;
      color: #c8d6e5;
      font-size: 13px;
      min-height: 20px;
    }
    @media (max-width: 720px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <section class=\"card\">
    <h1>MaePla Auto Trader Monitor</h1>
    <div id=\"statusPill\" class=\"pill warn\">LOADING...</div>

    <div class=\"grid\">
      <div class=\"item\"><div class=\"k\">Symbol</div><div id=\"symbol\" class=\"v\">-</div></div>
      <div class=\"item\"><div class=\"k\">Last Action</div><div id=\"action\" class=\"v\">-</div></div>
      <div class=\"item\"><div class=\"k\">Decision</div><div id=\"decision\" class=\"v\">-</div></div>
      <div class=\"item\"><div class=\"k\">Score</div><div id=\"score\" class=\"v\">-</div></div>
      <div class=\"item\"><div class=\"k\">Price</div><div id=\"price\" class=\"v\">-</div></div>
      <div class=\"item\"><div class=\"k\">Last Update</div><div id=\"updated\" class=\"v\">-</div></div>
    </div>

    <div class=\"tiny\">Auto-refresh every 2 seconds.</div>
    <div class=\"controls\">
      <button id=\"buyBtn\" class=\"btn buy\">Manual BUY</button>
      <button id=\"sellBtn\" class=\"btn sell\">Manual SELL</button>
    </div>
    <div id=\"orderLog\" class=\"log\">Manual order not sent yet.</div>
  </section>

  <script>
    function setPill(el, text, cls) {
      el.className = "pill " + cls;
      el.textContent = text;
    }

    function setOrderButtonsDisabled(disabled) {
      document.getElementById('buyBtn').disabled = disabled;
      document.getElementById('sellBtn').disabled = disabled;
    }

    async function sendManualOrder(side) {
      const ok = confirm('Send real ' + side + ' order to MT5 now?');
      if (!ok) return;

      setOrderButtonsDisabled(true);
      const log = document.getElementById('orderLog');
      log.textContent = 'Sending ' + side + ' order...';

      try {
        const r = await fetch('/api/manual-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ side })
        });
        const data = await r.json();
        if (data.success) {
          log.textContent = side + ' sent successfully. Ticket: ' + (data.ticket ?? '-') + ' | Lot: ' + (data.lot_size ?? '-');
        } else {
          log.textContent = side + ' failed: ' + (data.msg || 'unknown error');
        }
      } catch (e) {
        log.textContent = side + ' failed: API error';
      } finally {
        setOrderButtonsDisabled(false);
        tick();
      }
    }

    async function tick() {
      try {
        const r = await fetch('/api/status?_=' + Date.now());
        const s = await r.json();

        const pill = document.getElementById('statusPill');
        if (s.is_running) setPill(pill, 'RUNNING', 'ok');
        else if (s.stale) setPill(pill, 'STOPPED (STALE HEARTBEAT)', 'warn');
        else setPill(pill, 'STOPPED', 'bad');

        const lr = s.last_result || {};
        document.getElementById('symbol').textContent = s.symbol || '-';
        document.getElementById('action').textContent = lr.action || '-';
        document.getElementById('decision').textContent = lr.decision || '-';
        document.getElementById('score').textContent = (lr.score ?? '-').toString();
        document.getElementById('price').textContent = lr.price ? ('$' + Number(lr.price).toFixed(2)) : '-';
        document.getElementById('updated').textContent = s.updated_at || '-';
      } catch (e) {
        const pill = document.getElementById('statusPill');
        setPill(pill, 'STATUS API ERROR', 'bad');
      }
    }

    tick();
    setInterval(tick, 2000);
    document.getElementById('buyBtn').addEventListener('click', () => sendManualOrder('BUY'));
    document.getElementById('sellBtn').addEventListener('click', () => sendManualOrder('SELL'));
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
  def do_POST(self):
    if self.path == "/api/manual-order":
      content_length = int(self.headers.get("Content-Length", "0"))
      raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
      try:
        payload = json.loads(raw.decode("utf-8"))
      except Exception:
        payload = {}

      side = str(payload.get("side", "")).upper()
      result = place_manual_order(side)
      body = json.dumps(result, ensure_ascii=False).encode("utf-8")

      status_code = 200 if result.get("success") else 400
      self.send_response(status_code)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Cache-Control", "no-cache")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)
      return

    self.send_response(404)
    self.end_headers()

  def do_GET(self):
    if self.path.startswith("/api/status"):
      payload = read_status()
      body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Cache-Control", "no-cache")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)
      return

    if self.path == "/" or self.path.startswith("/?"):
      body = HTML.encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)
      return

    self.send_response(404)
    self.end_headers()

    def log_message(self, format, *args):
        # Silence default HTTP request logs to keep terminal clean.
        return


def run_status_server(host: str = "127.0.0.1", port: int = 8765):
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Status web running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
