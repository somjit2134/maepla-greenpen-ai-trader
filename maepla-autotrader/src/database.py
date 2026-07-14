import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import get
from src.logger import get_logger

logger = get_logger()


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = path or get().database.path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init(self):
        c = self._connect()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL, price REAL, decision TEXT, score INTEGER,
                monthly TEXT, weekly TEXT, daily_zone TEXT,
                h4 TEXT, h1 TEXT, supports TEXT, resistances TEXT,
                grid_score INTEGER, ath_pct REAL, thousand_pt TEXT,
                pa_bullish INTEGER, pa_bearish INTEGER,
                score_breakdown TEXT, trade_plan TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER, time TEXT NOT NULL, price REAL,
                direction TEXT, score INTEGER, grade TEXT, source TEXT DEFAULT 'AUTO',
                executed INTEGER DEFAULT 0, alert_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER, ticket INTEGER, time TEXT NOT NULL,
                symbol TEXT, direction TEXT, volume REAL, entry_price REAL,
                stop_loss REAL, take_profit REAL, risk_pct REAL, rr REAL,
                status TEXT DEFAULT 'PENDING',
                close_time TEXT, close_price REAL, profit REAL, profit_pips REAL,
                exit_reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS daily_pnl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE, trades INTEGER, wins INTEGER, losses INTEGER,
                win_rate REAL, gross_profit REAL, gross_loss REAL,
                net_pnl REAL, max_dd REAL, created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER, entry_date TEXT, exit_date TEXT,
                direction TEXT, entry_price REAL, exit_price REAL,
                profit REAL, emotion TEXT, mistake TEXT, lesson TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        c.commit()

    def save_analysis(self, data: dict) -> int:
        c = self._connect()
        cur = c.execute(
            """INSERT INTO analysis (time,price,decision,score,monthly,weekly,daily_zone,
               h4,h1,supports,resistances,grid_score,ath_pct,thousand_pt,
               pa_bullish,pa_bearish,score_breakdown,trade_plan)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("time"), data.get("price"), data.get("decision"), data.get("score"),
             data.get("monthly"), data.get("weekly"), data.get("daily_zone"),
             data.get("h4"), data.get("h1"), str(data.get("supports",[])),
             str(data.get("resistances",[])), data.get("grid_score"), data.get("ath_pct"),
             data.get("thousand_pt"), int(data.get("pa_bullish",False)),
             int(data.get("pa_bearish",False)), str(data.get("score_breakdown",{})),
             str(data.get("trade_plan",{})))
        )
        c.commit()
        return cur.lastrowid

    def save_signal(self, data: dict) -> int:
        c = self._connect()
        cur = c.execute(
            """INSERT INTO signals (analysis_id,time,price,direction,score,grade,source)
               VALUES (?,?,?,?,?,?,?)""",
            (data.get("analysis_id"), data.get("time"), data.get("price"),
             data.get("direction"), data.get("score"), data.get("grade"), data.get("source","AUTO"))
        )
        c.commit()
        return cur.lastrowid

    def save_order(self, data: dict) -> int:
        c = self._connect()
        cur = c.execute(
            """INSERT INTO orders (signal_id,ticket,time,symbol,direction,volume,
               entry_price,stop_loss,take_profit,risk_pct,rr,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("signal_id"), data.get("ticket"), data.get("time"),
             data.get("symbol"), data.get("direction"), data.get("volume"),
             data.get("entry_price"), data.get("stop_loss"), data.get("take_profit"),
             data.get("risk_pct"), data.get("rr"), data.get("status","OPEN"))
        )
        c.commit()
        return cur.lastrowid

    def close_order(self, order_id: int, close_price: float, profit: float, reason: str = ""):
        c = self._connect()
        c.execute(
            """UPDATE orders SET status='CLOSED', close_time=datetime('now'),
               close_price=?, profit=?, exit_reason=? WHERE id=?""",
            (close_price, profit, reason, order_id)
        )
        c.commit()

    def get_signals(self, limit: int = 20) -> list[dict]:
        return [dict(r) for r in self._connect().execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))]

    def get_orders(self, status: str = "") -> list[dict]:
        q = "SELECT * FROM orders ORDER BY id DESC"
        if status:
            q = f"SELECT * FROM orders WHERE status='{status}' ORDER BY id DESC"
        return [dict(r) for r in self._connect().execute(q)]

    def get_open_orders(self) -> list[dict]:
        return self.get_orders("OPEN")

    def get_daily_pnl(self) -> dict:
        row = self._connect().execute(
            "SELECT * FROM daily_pnl WHERE date=date('now')"
        ).fetchone()
        return dict(row) if row else {"net_pnl": 0, "trades": 0}

    def update_daily_pnl(self):
        today = datetime.now().strftime("%Y-%m-%d")
        orders = self._connect().execute(
            "SELECT profit FROM orders WHERE status='CLOSED' AND date(close_time)=date('now')"
        ).fetchall()

        total = len(orders)
        if total == 0:
            return

        profits = [o["profit"] for o in orders if o["profit"] is not None]
        wins = sum(1 for p in profits if p > 0)
        losses = sum(1 for p in profits if p < 0)
        gross_profit = sum(p for p in profits if p > 0)
        gross_loss = sum(p for p in profits if p < 0)
        net = sum(profits)

        self._connect().execute(
            """INSERT INTO daily_pnl (date,trades,wins,losses,win_rate,gross_profit,gross_loss,net_pnl)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(date) DO UPDATE SET
               trades=excluded.trades, wins=excluded.wins, losses=excluded.losses,
               win_rate=excluded.win_rate, gross_profit=excluded.gross_profit,
               gross_loss=excluded.gross_loss, net_pnl=excluded.net_pnl""",
            (today, total, wins, losses, (wins/total*100) if total else 0,
             round(gross_profit,2), round(gross_loss,2), round(net,2))
        )
        self._connect().commit()

    def save_journal(self, data: dict) -> int:
        c = self._connect()
        cur = c.execute(
            """INSERT INTO journal (order_id,entry_date,exit_date,direction,
               entry_price,exit_price,profit,emotion,mistake,lesson)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (data.get("order_id"), data.get("entry_date"), data.get("exit_date"),
             data.get("direction"), data.get("entry_price"), data.get("exit_price"),
             data.get("profit"), data.get("emotion"), data.get("mistake"), data.get("lesson"))
        )
        c.commit()
        return cur.lastrowid

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
