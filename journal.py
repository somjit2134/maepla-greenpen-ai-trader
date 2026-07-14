"""
MT5 Autonomous Trading System - Trading Journal System
========================================================
Logs every trade with full context:
  - Entry reasons (frame, signal, cycle, trend)
  - Entry/exit prices, SL, TP
  - Result, P/L, win rate, drawdown
  - Performance reports
"""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from config import get_config

logger = logging.getLogger("journal")


class Journal:
    """Trading Journal - log and analyze all trades."""

    def __init__(self, db_path: Optional[str] = None):
        self.cfg = get_config()
        self.db_path = db_path or self.cfg.database.path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                lot_size REAL,
                risk_reward REAL,
                signal_grade TEXT,
                score REAL,
                frame_analysis TEXT,
                cycle_position TEXT,
                trend_alignment TEXT,
                price_action TEXT,
                entry_reasons TEXT,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_time TEXT,
                profit REAL,
                profit_pips REAL,
                swap REAL,
                commission REAL,
                exit_reason TEXT,
                emotion TEXT,
                mistake TEXT,
                lesson TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                balance_eod REAL DEFAULT 0
            );
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
        expected = {
            "ticket", "stop_loss", "take_profit_1", "take_profit_2",
            "lot_size", "risk_reward", "signal_grade", "score",
            "frame_analysis", "cycle_position", "trend_alignment",
            "price_action", "entry_reasons", "swap", "commission",
            "exit_reason", "emotion", "mistake", "lesson",
        }
        for col in expected - columns:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} TEXT")
        conn.commit()

    def log_trade(self, trade_data: dict) -> int:
        conn = self._connect()
        cursor = conn.execute("""
            INSERT INTO trades
            (ticket, timestamp, symbol, direction, entry_price, stop_loss,
             take_profit_1, take_profit_2, lot_size, risk_reward,
             signal_grade, score, frame_analysis, cycle_position,
             trend_alignment, price_action, entry_reasons, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data.get("ticket"),
            trade_data.get("timestamp", datetime.now().isoformat()),
            trade_data.get("symbol", "XAUUSD"),
            trade_data.get("direction"),
            trade_data.get("entry_price"),
            trade_data.get("stop_loss"),
            trade_data.get("take_profit_1"),
            trade_data.get("take_profit_2"),
            trade_data.get("lot_size"),
            trade_data.get("risk_reward"),
            trade_data.get("signal_grade"),
            trade_data.get("score"),
            json.dumps(trade_data.get("frame_analysis", {})),
            trade_data.get("cycle_position"),
            trade_data.get("trend_alignment"),
            json.dumps(trade_data.get("price_action", {})),
            json.dumps(trade_data.get("entry_reasons", [])),
            trade_data.get("status", "OPEN"),
        ))
        conn.commit()
        trade_id = cursor.lastrowid
        logger.info(f"Trade #{trade_id} logged: {trade_data.get('direction')} @ {trade_data.get('entry_price')}")
        return trade_id

    def close_trade(self, ticket: int, exit_price: float, profit: float,
                    profit_pips: float = 0.0, exit_reason: str = "",
                    swap: float = 0.0, commission: float = 0.0):
        conn = self._connect()
        conn.execute("""
            UPDATE trades SET
                status='CLOSED', exit_price=?, exit_time=datetime('now'),
                profit=?, profit_pips=?, exit_reason=?, swap=?, commission=?
            WHERE ticket=?
        """, (exit_price, profit, profit_pips, exit_reason, swap, commission, ticket))
        conn.commit()
        logger.info(f"Trade #{ticket} closed: P/L ${profit:.2f} ({profit_pips:.1f} pips)")

    def update_notes(self, ticket: int, emotion: str = "", mistake: str = "", lesson: str = ""):
        conn = self._connect()
        conn.execute("""
            UPDATE trades SET emotion=?, mistake=?, lesson=? WHERE ticket=?
        """, (emotion, mistake, lesson, ticket))
        conn.commit()

    def get_trades(self, limit: int = 50, status: Optional[str] = None) -> list[dict]:
        conn = self._connect()
        if status:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_open_trades(self) -> list[dict]:
        return self.get_trades(status="OPEN")

    def get_closed_trades(self, limit: int = 100) -> list[dict]:
        return self.get_trades(status="CLOSED", limit=limit)

    def win_rate(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        if not closed:
            return 0.0
        winning = sum(1 for t in closed if t.get("profit", 0) and t["profit"] > 0)
        return round(winning / len(closed) * 100, 1)

    def profit_factor(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        if not closed:
            return 0.0
        gross_profit = sum(t["profit"] for t in closed if t.get("profit") and t["profit"] > 0)
        gross_loss = abs(sum(t["profit"] for t in closed if t.get("profit") and t["profit"] < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 2)

    def max_drawdown(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        if not closed:
            return 0.0

        balance = self.cfg.backtest.initial_balance
        peak = balance
        max_dd = 0.0

        for t in reversed(closed):
            profit = t.get("profit", 0) or 0
            balance += profit
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return round(max_dd, 2)

    def total_profit(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        return round(sum(t.get("profit", 0) or 0 for t in closed), 2)

    def avg_win(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        wins = [t["profit"] for t in closed if t.get("profit") and t["profit"] > 0]
        return round(np.mean(wins), 2) if wins else 0.0

    def avg_loss(self) -> float:
        closed = self.get_closed_trades(limit=10000)
        losses = [t["profit"] for t in closed if t.get("profit") and t["profit"] < 0]
        return round(np.mean(losses), 2) if losses else 0.0

    def sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        closed = self.get_closed_trades(limit=10000)
        if len(closed) < 2:
            return 0.0

        returns = [(t.get("profit", 0) or 0) for t in closed]
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        return round((mean_return - risk_free_rate) / std_return, 2)

    def performance_report(self) -> dict:
        closed = self.get_closed_trades(limit=10000)
        if not closed:
            return {"message": "No closed trades yet"}

        return {
            "total_trades": len(closed),
            "winning_trades": sum(1 for t in closed if (t.get("profit") or 0) > 0),
            "losing_trades": sum(1 for t in closed if (t.get("profit") or 0) < 0),
            "win_rate": self.win_rate(),
            "profit_factor": self.profit_factor(),
            "total_profit": self.total_profit(),
            "max_drawdown": self.max_drawdown(),
            "avg_win": self.avg_win(),
            "avg_loss": self.avg_loss(),
            "sharpe_ratio": self.sharpe_ratio(),
            "best_trade": max((t.get("profit", 0) or 0) for t in closed),
            "worst_trade": min((t.get("profit", 0) or 0) for t in closed),
        }

    def grade_report(self) -> dict:
        closed = self.get_closed_trades(limit=10000)
        grades = {}
        for t in closed:
            grade = t.get("signal_grade", "UNKNOWN")
            if grade not in grades:
                grades[grade] = {"count": 0, "wins": 0, "total_pnl": 0.0}
            grades[grade]["count"] += 1
            pnl = t.get("profit", 0) or 0
            grades[grade]["total_pnl"] += pnl
            if pnl > 0:
                grades[grade]["wins"] += 1

        for g in grades:
            count = grades[g]["count"]
            grades[g]["win_rate"] = round(grades[g]["wins"] / count * 100, 1) if count > 0 else 0
            grades[g]["total_pnl"] = round(grades[g]["total_pnl"], 2)

        return grades

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def log_ticket(self, ticket, signal):
        self.log_trade({
            "ticket": ticket,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "take_profit_2": signal.take_profit_2,
            "lot_size": signal.lot_size,
            "risk_reward": signal.risk_reward,
            "signal_grade": signal.signal_grade,
            "score": signal.confidence_score,
            "frame_analysis": {"overall": signal.frame.overall_frame if signal.frame else ""},
            "cycle_position": signal.cycle.position if signal.cycle else "",
            "trend_alignment": str(signal.trend.alignment_score) if signal.trend else "",
            "entry_reasons": signal.reasons,
        })
