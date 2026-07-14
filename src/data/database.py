import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config_loader import get_config
from src.log_setup import get_logger

logger = get_logger()


class Database:
    def __init__(self, db_path: Optional[str] = None):
        cfg = get_config()
        self.db_path = db_path or cfg.database.path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                decision TEXT NOT NULL,
                score REAL NOT NULL,
                score_breakdown TEXT,
                monthly_bias TEXT,
                weekly_bias TEXT,
                daily_zone TEXT,
                h4_structure TEXT,
                h1_direction TEXT,
                support_zones TEXT,
                resistance_zones TEXT,
                frame_analysis TEXT,
                grid_levels TEXT,
                price_action TEXT,
                trade_plan TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit1 REAL,
                take_profit2 REAL,
                lot_size REAL,
                risk_percent REAL,
                risk_reward REAL,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_time TEXT,
                profit REAL,
                profit_pips REAL,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            );

            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                entry_date TEXT NOT NULL,
                exit_date TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                profit REAL,
                emotion TEXT,
                mistake TEXT,
                lesson TEXT,
                screenshot_path TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            );
        """)
        conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    # ---- Signals ----

    def save_signal(self, signal_data: dict) -> int:
        conn = self._connect()
        cursor = conn.execute(
            """INSERT INTO signals
               (timestamp, symbol, price, decision, score, score_breakdown,
                monthly_bias, weekly_bias, daily_zone, h4_structure, h1_direction,
                support_zones, resistance_zones, frame_analysis, grid_levels,
                price_action, trade_plan)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal_data.get("timestamp", datetime.now().isoformat()),
                signal_data.get("symbol", "XAUUSD"),
                signal_data.get("price", 0),
                signal_data.get("decision", "WAIT"),
                signal_data.get("score", 0),
                str(signal_data.get("score_breakdown", {})),
                signal_data.get("monthly_bias", ""),
                signal_data.get("weekly_bias", ""),
                signal_data.get("daily_zone", ""),
                signal_data.get("h4_structure", ""),
                signal_data.get("h1_direction", ""),
                str(signal_data.get("support_zones", [])),
                str(signal_data.get("resistance_zones", [])),
                str(signal_data.get("frame_analysis", {})),
                str(signal_data.get("grid_levels", [])),
                str(signal_data.get("price_action", {})),
                str(signal_data.get("trade_plan", {})),
            ),
        )
        conn.commit()
        signal_id = cursor.lastrowid
        logger.info(f"Signal #{signal_id} saved: {signal_data.get('decision')}")
        return signal_id

    def get_signals(self, limit: int = 20) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- Trades ----

    def save_trade(self, trade_data: dict) -> int:
        conn = self._connect()
        cursor = conn.execute(
            """INSERT INTO trades
               (signal_id, timestamp, symbol, direction, entry_price, stop_loss,
                take_profit1, take_profit2, lot_size, risk_percent, risk_reward, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade_data.get("signal_id"),
                trade_data.get("timestamp", datetime.now().isoformat()),
                trade_data.get("symbol", "XAUUSD"),
                trade_data.get("direction"),
                trade_data.get("entry_price"),
                trade_data.get("stop_loss"),
                trade_data.get("take_profit1"),
                trade_data.get("take_profit2"),
                trade_data.get("lot_size", 0.01),
                trade_data.get("risk_percent", 1.0),
                trade_data.get("risk_reward", 0),
                trade_data.get("status", "OPEN"),
            ),
        )
        conn.commit()
        trade_id = cursor.lastrowid
        logger.info(f"Trade #{trade_id} saved: {trade_data.get('direction')} @ {trade_data.get('entry_price')}")
        return trade_id

    def close_trade(self, trade_id: int, exit_price: float, profit: float):
        conn = self._connect()
        conn.execute(
            """UPDATE trades SET status='CLOSED', exit_price=?, exit_time=datetime('now'),
               profit=? WHERE id=?""",
            (exit_price, profit, trade_id),
        )
        conn.commit()
        logger.info(f"Trade #{trade_id} closed: {profit:.2f}")

    def get_trades(self, limit: int = 20) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_open_trades(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- Performance ----

    def update_performance(self):
        conn = self._connect()
        today = datetime.now().strftime("%Y-%m-%d")
        trades = conn.execute(
            "SELECT profit FROM trades WHERE status='CLOSED'"
        ).fetchall()

        total = len(trades)
        if total == 0:
            return

        winning = sum(1 for t in trades if t["profit"] and t["profit"] > 0)
        losing = total - winning
        total_profit = sum(t["profit"] for t in trades if t["profit"])

        conn.execute(
            """INSERT OR REPLACE INTO performance
               (date, total_trades, winning_trades, losing_trades, win_rate, total_profit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (today, total, winning, losing, (winning / total * 100) if total else 0, total_profit),
        )
        conn.commit()

    def get_performance(self) -> dict:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM performance ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else {}

    # ---- Journal ----

    def save_journal_entry(self, entry: dict) -> int:
        conn = self._connect()
        cursor = conn.execute(
            """INSERT INTO journal
               (trade_id, entry_date, exit_date, direction, entry_price, exit_price,
                profit, emotion, mistake, lesson, screenshot_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("trade_id"),
                entry.get("entry_date", datetime.now().isoformat()),
                entry.get("exit_date"),
                entry.get("direction"),
                entry.get("entry_price"),
                entry.get("exit_price"),
                entry.get("profit"),
                entry.get("emotion"),
                entry.get("mistake"),
                entry.get("lesson"),
                entry.get("screenshot_path"),
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def get_journal(self, limit: int = 20) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
