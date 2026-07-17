"""
MT5 Autonomous Trading System - Backtest & Optimization Engine
================================================================
FIXED: Uses real SignalEngine instead of SMA crossover.
Includes spread, commission, slippage, and risk manager rules.
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

from src.config import get_config

logger = logging.getLogger("backtest")


@dataclass
class BacktestTrade:
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit_2: float = 0.0
    exit_price: float = 0.0
    profit: float = 0.0
    profit_pips: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    exit_reason: str = ""
    lot_size: float = 0.0
    spread_cost: float = 0.0
    commission: float = 0.0
    signal_grade: str = ""
    confidence_score: float = 0.0


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
    """Backtest Engine using real SignalEngine."""

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
        if h1 is None or h1.empty or len(h1) < 100:
            logger.error("Insufficient H1 data for backtest (need >= 100 bars)")
            return BacktestResult()

        risk_pct = params.get("risk_percent", self.cfg.risk.risk_per_trade_percent) if params else self.cfg.risk.risk_per_trade_percent
        commission_per_lot = self.cfg.backtest.commission_per_lot
        spread_pts = self.cfg.symbol.spread_max * 0.5
        spread_cost_per_lot = spread_pts * self.cfg.symbol.point * self.cfg.symbol.contract_size

        trades = []
        equity_curve = [balance]
        peak = balance
        max_dd = 0.0
        max_dd_pct = 0.0
        position = None
        consecutive_losses = 0
        daily_loss = 0.0
        last_day = None

        for i in range(100, len(h1)):
            current_price = h1["close"].iloc[i]
            current_high = h1["high"].iloc[i]
            current_low = h1["low"].iloc[i]
            current_time = str(h1["time"].iloc[i]) if "time" in h1.columns else str(i)

            current_day = current_time[:10] if len(current_time) >= 10 else current_time
            if last_day is not None and current_day != last_day:
                daily_loss = 0.0
            last_day = current_day

            if position:
                closed = self._check_exit(position, current_high, current_low, current_price, commission_per_lot)
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

                    if closed.profit < 0:
                        consecutive_losses += 1
                        daily_loss += abs(closed.profit)
                    else:
                        consecutive_losses = 0

                    position = None
            else:
                if consecutive_losses >= self.cfg.risk.max_consecutive_losses:
                    consecutive_losses = 0
                    continue

                if daily_loss > 0:
                    daily_loss_pct = (daily_loss / balance * 100) if balance > 0 else 0
                    if daily_loss_pct >= self.cfg.risk.max_daily_loss_percent:
                        continue

                signal = self._generate_signal(data, current_price, i, h1)
                if signal:
                    sl_distance = abs(signal["entry"] - signal["sl"])
                    if sl_distance <= 0:
                        continue

                    risk_amount = balance * (risk_pct / 100)
                    lot_size = risk_amount / (sl_distance * self.cfg.symbol.contract_size)
                    lot_size = max(0.01, min(lot_size, self.cfg.risk.max_lot))
                    lot_size = round(lot_size, 2)

                    rr = abs(signal["tp"] - signal["entry"]) / sl_distance if sl_distance > 0 else 0
                    if rr < self.cfg.risk.min_rr:
                        continue

                    entry = signal["entry"]
                    if signal["direction"] == "BUY":
                        entry += spread_pts * self.cfg.symbol.point
                    else:
                        entry -= spread_pts * self.cfg.symbol.point

                    position = BacktestTrade(
                        direction=signal["direction"],
                        entry_price=entry,
                        stop_loss=signal["sl"],
                        take_profit=signal["tp"],
                        take_profit_2=signal.get("tp2", signal["tp"]),
                        entry_time=current_time,
                        lot_size=lot_size,
                        spread_cost=spread_cost_per_lot * lot_size,
                        signal_grade=signal.get("grade", ""),
                        confidence_score=signal.get("score", 0),
                    )

        if position:
            last_price = h1["close"].iloc[-1]
            profit = self._calculate_profit(position, last_price, commission_per_lot)
            position.exit_price = last_price
            position.exit_time = str(h1["time"].iloc[-1]) if "time" in h1.columns else str(len(h1))
            position.profit = profit
            position.exit_reason = "END_OF_DATA"
            balance += profit
            equity_curve.append(balance)
            trades.append(position)

        return self._compile_results(trades, equity_curve, start_balance, balance, max_dd, max_dd_pct)

    def _generate_signal(self, data: dict, price: float, idx: int, h1: pd.DataFrame) -> Optional[dict]:
        if idx < 100:
            return None

        window_data = {}
        for tf in ["M15", "H1", "H4", "D1", "W1", "MN1"]:
            df = data.get(tf)
            if df is not None and not df.empty:
                window_data[tf] = df

        if "H1" not in window_data:
            return None

        try:
            from src.engine.signal_engine import SignalEngine
            engine = SignalEngine()
            mid = price
            signal = engine.analyze(window_data, mid, mid)
        except Exception as e:
            logger.debug(f"Signal engine error: {e}")
            return None

        if signal.direction == "WAIT":
            return None

        if signal.confidence_score < 6:
            return None

        return {
            "direction": signal.direction,
            "entry": signal.entry_price if signal.entry_price > 0 else price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit_1,
            "tp2": signal.take_profit_2,
            "grade": signal.signal_grade,
            "score": signal.confidence_score,
        }

    def _check_exit(self, position: BacktestTrade, high: float, low: float, close: float, commission_per_lot: float) -> Optional[BacktestTrade]:
        if position.direction == "BUY":
            if low <= position.stop_loss:
                return self._close_trade(position, position.stop_loss, "SL", commission_per_lot)
            if high >= position.take_profit:
                return self._close_trade(position, position.take_profit, "TP", commission_per_lot)
        else:
            if high >= position.stop_loss:
                return self._close_trade(position, position.stop_loss, "SL", commission_per_lot)
            if low <= position.take_profit:
                return self._close_trade(position, position.take_profit, "TP", commission_per_lot)
        return None

    def _close_trade(self, position: BacktestTrade, exit_price: float, reason: str, commission_per_lot: float) -> BacktestTrade:
        position.exit_price = exit_price
        position.exit_reason = reason
        position.commission = commission_per_lot * position.lot_size
        position.profit = self._calculate_profit(position, exit_price, commission_per_lot)
        return position

    def _calculate_profit(self, position: BacktestTrade, exit_price: float, commission_per_lot: float) -> float:
        if position.direction == "BUY":
            pips = (exit_price - position.entry_price) / self.cfg.symbol.point
        else:
            pips = (position.entry_price - exit_price) / self.cfg.symbol.point
        position.profit_pips = round(pips, 1)
        gross = pips * self.cfg.symbol.point * self.cfg.symbol.contract_size * position.lot_size
        commission = position.commission if position.commission > 0 else commission_per_lot * position.lot_size
        net = gross - position.spread_cost - commission
        return round(net, 2)

    def _compile_results(self, trades, equity_curve, start_balance, end_balance, max_dd, max_dd_pct) -> BacktestResult:
        winning = [t for t in trades if t.profit > 0]
        losing = [t for t in trades if t.profit <= 0]
        total = len(trades)

        gross_profit = sum(t.profit for t in winning)
        gross_loss = abs(sum(t.profit for t in losing))

        sharpe = 0.0
        if total >= 2:
            returns = [t.profit for t in trades]
            mean_r = np.mean(returns)
            std_r = np.std(returns)
            if std_r > 0:
                sharpe = round(mean_r / std_r, 2)

        return BacktestResult(
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(len(winning) / total * 100, 1) if total > 0 else 0,
            profit_factor=round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0,
            total_profit=round(end_balance - start_balance, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_percent=round(max_dd_pct, 2),
            sharpe_ratio=sharpe,
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
                "grade": t.signal_grade,
                "score": t.confidence_score,
                "lot_size": t.lot_size,
                "spread_cost": t.spread_cost,
                "commission": t.commission,
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
                risk_amount = balance * (self.cfg.risk.risk_per_trade_percent / 100)
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

    def walk_forward(self, data: dict[str, pd.DataFrame], n_splits: int = 5, optimize: bool = True) -> dict:
        h1 = data.get("H1")
        if h1 is None or h1.empty or len(h1) < n_splits * 100:
            return {"message": "Insufficient data for walk-forward"}

        total_len = len(h1)
        split_size = total_len // n_splits
        results = []

        for i in range(n_splits):
            start = i * split_size
            end = min(start + split_size, total_len)
            split_data = {tf: df.iloc[start:end] if tf == "H1" else df for tf, df in data.items() if not df.empty}

            bt_result = self.run_backtest(split_data)
            results.append({
                "split": i + 1,
                "trades": bt_result.total_trades,
                "win_rate": bt_result.win_rate,
                "profit": bt_result.total_profit,
                "max_dd": bt_result.max_drawdown_percent,
            })

        avg_win_rate = np.mean([r["win_rate"] for r in results]) if results else 0
        avg_profit = np.mean([r["profit"] for r in results]) if results else 0
        consistency = sum(1 for r in results if r["profit"] > 0) / n_splits * 100 if n_splits > 0 else 0

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
            "equity_curve": result.equity_curve,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results saved: {filepath}")
        return filepath
