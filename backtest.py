"""
MT5 Autonomous Trading System - Backtest & Optimization Engine
================================================================
Supports:
  - Historical backtest
  - Parameter optimization
  - Walk forward testing
  - Monte Carlo simulation
"""
import logging
import sqlite3
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config import get_config

logger = logging.getLogger("backtest")


@dataclass
class BacktestTrade:
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_price: float = 0.0
    profit: float = 0.0
    profit_pips: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    exit_reason: str = ""


@dataclass
class BacktestResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    equity_curve: list = field(default_factory=list)
    trades: list = field(default_factory=list)
    start_balance: float = 0.0
    end_balance: float = 0.0


class BacktestEngine:
    """Backtest & Optimization Engine."""

    def __init__(self):
        self.cfg = get_config()

    def run_backtest(
        self,
        data: dict[str, pd.DataFrame],
        params: Optional[dict] = None,
        initial_balance: Optional[float] = None,
    ) -> BacktestResult:
        balance = initial_balance or self.cfg.backtest.initial_balance
        start_balance = balance

        h1 = data.get("H1")
        if h1 is None or h1.empty or len(h1) < 50:
            logger.error("Insufficient H1 data for backtest")
            return BacktestResult()

        trades = []
        equity_curve = [balance]
        peak = balance
        max_dd = 0.0
        max_dd_pct = 0.0
        position = None

        min_rr = params.get("min_rr", self.cfg.risk.min_rr) if params else self.cfg.risk.min_rr
        risk_pct = params.get("risk_percent", self.cfg.risk.risk_per_trade_percent) if params else self.cfg.risk.risk_per_trade_percent

        for i in range(50, len(h1)):
            window = h1.iloc[max(0, i - 100):i + 1]
            current_price = h1["close"].iloc[i]
            current_high = h1["high"].iloc[i]
            current_low = h1["low"].iloc[i]
            current_time = str(h1["time"].iloc[i]) if "time" in h1.columns else str(i)

            if position:
                closed = self._check_exit(position, current_high, current_low, current_price)
                if closed:
                    closed.exit_time = current_time
                    balance += closed.profit
                    equity_curve.append(balance)

                    if balance > peak:
                        peak = balance
                    dd = (peak - balance) / peak * 100 if peak > 0 else 0
                    max_dd = max(max_dd, balance - peak) if balance < peak else max_dd
                    max_dd_pct = max(max_dd_pct, dd)

                    trades.append(closed)
                    position = None
            else:
                signal = self._generate_signal(window, current_price, min_rr)
                if signal:
                    sl_distance = abs(signal["entry"] - signal["sl"])
                    if sl_distance > 0:
                        risk_amount = balance * (risk_pct / 100)
                        lot_size = risk_amount / (sl_distance * self.cfg.symbol.contract_size)
                        lot_size = max(0.01, min(lot_size, self.cfg.risk.max_lot))

                        position = BacktestTrade(
                            direction=signal["direction"],
                            entry_price=signal["entry"],
                            stop_loss=signal["sl"],
                            take_profit=signal["tp"],
                            entry_time=current_time,
                        )

        if position:
            last_price = h1["close"].iloc[-1]
            profit = self._calculate_profit(position, last_price)
            position.exit_price = last_price
            position.exit_time = str(h1["time"].iloc[-1]) if "time" in h1.columns else str(len(h1))
            position.profit = profit
            position.exit_reason = "END_OF_DATA"
            balance += profit
            equity_curve.append(balance)
            trades.append(position)

        return self._compile_results(trades, equity_curve, start_balance, balance, max_dd, max_dd_pct)

    def _generate_signal(self, df: pd.DataFrame, price: float, min_rr: float) -> Optional[dict]:
        if len(df) < 20:
            return None

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        sma20 = np.mean(close[-20:])
        sma50 = np.mean(close[-50:]) if len(close) >= 50 else sma20

        atr = np.mean(high[-14:] - low[-14:]) if len(high) >= 14 else 10

        last_close = close[-1]
        prev_close = close[-2]
        last_high = high[-1]
        last_low = low[-1]
        body = abs(last_close - close[-2] if len(close) > 1 else 0)

        if last_close > sma20 and prev_close <= sma20:
            entry = price
            sl = price - atr * 1.5
            tp = price + atr * 3
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
            if rr >= min_rr:
                return {"direction": "BUY", "entry": entry, "sl": sl, "tp": tp}

        elif last_close < sma20 and prev_close >= sma20:
            entry = price
            sl = price + atr * 1.5
            tp = price - atr * 3
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0
            if rr >= min_rr:
                return {"direction": "SELL", "entry": entry, "sl": sl, "tp": tp}

        return None

    def _check_exit(self, position: BacktestTrade, high: float, low: float, close: float) -> Optional[BacktestTrade]:
        if position.direction == "BUY":
            if low <= position.stop_loss:
                return self._close_trade(position, position.stop_loss, "SL")
            if high >= position.take_profit:
                return self._close_trade(position, position.take_profit, "TP")
        else:
            if high >= position.stop_loss:
                return self._close_trade(position, position.stop_loss, "SL")
            if low <= position.take_profit:
                return self._close_trade(position, position.take_profit, "TP")
        return None

    def _close_trade(self, position: BacktestTrade, exit_price: float, reason: str) -> BacktestTrade:
        position.exit_price = exit_price
        position.exit_reason = reason
        position.profit = self._calculate_profit(position, exit_price)
        return position

    def _calculate_profit(self, position: BacktestTrade, exit_price: float) -> float:
        if position.direction == "BUY":
            pips = (exit_price - position.entry_price) / self.cfg.symbol.point
        else:
            pips = (position.entry_price - exit_price) / self.cfg.symbol.point
        position.profit_pips = round(pips, 1)
        return round(pips * self.cfg.symbol.point * self.cfg.symbol.contract_size * 0.01, 2)

    def _compile_results(self, trades, equity_curve, start_balance, end_balance, max_dd, max_dd_pct) -> BacktestResult:
        winning = [t for t in trades if t.profit > 0]
        losing = [t for t in trades if t.profit <= 0]
        total = len(trades)

        gross_profit = sum(t.profit for t in winning)
        gross_loss = abs(sum(t.profit for t in losing))

        return BacktestResult(
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(len(winning) / total * 100, 1) if total > 0 else 0,
            profit_factor=round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0,
            total_profit=round(end_balance - start_balance, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_percent=round(max_dd_pct, 2),
            sharpe_ratio=0.0,
            avg_win=round(np.mean([t.profit for t in winning]), 2) if winning else 0,
            avg_loss=round(np.mean([t.profit for t in losing]), 2) if losing else 0,
            expectancy=round((end_balance - start_balance) / total, 2) if total > 0 else 0,
            equity_curve=equity_curve,
            trades=[{
                "direction": t.direction,
                "entry": t.entry_price,
                "exit": t.exit_price,
                "profit": t.profit,
                "pips": t.profit_pips,
                "reason": t.exit_reason,
            } for t in trades],
            start_balance=start_balance,
            end_balance=end_balance,
        )

    def monte_carlo(self, trades: list[dict], n_simulations: int = 1000) -> dict:
        if not trades:
            return {"message": "No trades"}

        profits = [t.get("profit", 0) for t in trades]
        n_trades = len(profits)

        final_balances = []
        max_dds = []

        for _ in range(n_simulations):
            shuffled = random.sample(profits, n_trades)
            balance = self.cfg.backtest.initial_balance
            peak = balance
            max_dd = 0

            for p in shuffled:
                balance += p
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)

            final_balances.append(balance)
            max_dds.append(max_dd)

        return {
            "simulations": n_simulations,
            "median_balance": round(np.median(final_balances), 2),
            "mean_balance": round(np.mean(final_balances), 2),
            "worst_balance": round(np.min(final_balances), 2),
            "best_balance": round(np.max(final_balances), 2),
            "percentile_5": round(np.percentile(final_balances, 5), 2),
            "percentile_95": round(np.percentile(final_balances, 95), 2),
            "median_max_dd": round(np.median(max_dds), 2),
            "worst_max_dd": round(np.max(max_dds), 2),
            "probability_of_profit": round(
                sum(1 for b in final_balances if b > self.cfg.backtest.initial_balance) / n_simulations * 100, 1
            ),
        }

    def walk_forward(self, data: dict[str, pd.DataFrame], n_splits: int = 5) -> dict:
        h1 = data.get("H1")
        if h1 is None or h1.empty:
            return {"message": "No H1 data"}

        total_len = len(h1)
        split_size = total_len // n_splits
        results = []

        for i in range(n_splits):
            start = i * split_size
            end = min(start + split_size, total_len)
            split_data = {"H1": h1.iloc[start:end]}

            bt_result = self.run_backtest(split_data)
            results.append({
                "split": i + 1,
                "trades": bt_result.total_trades,
                "win_rate": bt_result.win_rate,
                "profit": bt_result.total_profit,
                "max_dd": bt_result.max_drawdown_percent,
            })

        avg_win_rate = np.mean([r["win_rate"] for r in results])
        avg_profit = np.mean([r["profit"] for r in results])
        consistency = sum(1 for r in results if r["profit"] > 0) / n_splits * 100

        return {
            "splits": n_splits,
            "results": results,
            "avg_win_rate": round(avg_win_rate, 1),
            "avg_profit": round(avg_profit, 2),
            "consistency": round(consistency, 1),
        }

    def save_results(self, result: BacktestResult, filename: str = "backtest"):
        Path("data/backtest_results").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"data/backtest_results/{filename}_{timestamp}.json"

        data = {
            "timestamp": timestamp,
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "total_profit": result.total_profit,
            "max_drawdown": result.max_drawdown_percent,
            "sharpe_ratio": result.sharpe_ratio,
            "start_balance": result.start_balance,
            "end_balance": result.end_balance,
            "trades": result.trades,
            "equity_curve": result.equity_curve[-100:],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results saved: {filepath}")
        return filepath
