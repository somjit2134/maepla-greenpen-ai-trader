"""Backtesting engine for Mae Pla strategy."""

import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

from src.logger import get_logger

logger = get_logger()


@dataclass
class TradeRecord:
    time: str = ""
    direction: str = ""
    entry: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    exit_time: str = ""
    exit_price: float = 0.0
    profit: float = 0.0
    pips: float = 0.0
    rr: float = 0.0
    score: int = 0
    result: str = ""  # WIN / LOSS / BE


@dataclass
class BacktestResult:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_dd: float = 0.0
    max_dd_pct: float = 0.0
    sharpe: float = 0.0
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


def run_backtest(data: dict[str, pd.DataFrame], initial_balance: float = 10000,
                 rr_target: float = 2.0, sl_atr_mult: float = 1.5) -> BacktestResult:
    from src.market import run_analysis

    result = BacktestResult()
    d1 = data.get("D1")
    if d1 is None or d1.empty:
        logger.error("No D1 data for backtest")
        return result

    equity = initial_balance
    equity_curve = [equity]
    trades = []
    peak = equity

    n = len(d1)
    chunk = max(n // 5, 1)

    for i in range(50, n - 1):
        # Simulate having data up to index i
        sim_data = {}
        for tf, df in data.items():
            sim_data[tf] = df.iloc[:max(i, 1)]

        row = d1.iloc[i]
        price = row["close"]
        bid = price - 0.2
        ask = price + 0.2

        analysis = run_analysis(sim_data, bid, ask, 0.4)

        if analysis.total_score >= 7 and analysis.decision in ("BUY", "SELL"):
            dir = analysis.decision
            sl_dist = (row["high"] - row["low"]) * sl_atr_mult

            if dir == "BUY":
                entry = price
                sl = entry - sl_dist
                tp = entry + sl_dist * rr_target
            else:
                entry = price
                sl = entry + sl_dist
                tp = entry - sl_dist * rr_target

            risk_pct = 1.0
            risk_amt = equity * (risk_pct / 100)
            lots = risk_amt / (abs(entry - sl) * 100) if abs(entry - sl) > 0 else 0
            lots = max(0.01, min(lots, 10.0))

            # Simulate exit
            exit_idx = min(i + 10, n - 1)
            exit_price = tp
            exit_time = str(d1.iloc[exit_idx]["time"])
            outcome = "WIN"

            for j in range(i + 1, exit_idx + 1):
                bar = d1.iloc[j]
                if dir == "BUY":
                    if bar["low"] <= sl:
                        exit_price = sl
                        exit_time = str(bar["time"])
                        outcome = "LOSS"
                        break
                    if bar["high"] >= tp:
                        exit_price = tp
                        exit_time = str(bar["time"])
                        outcome = "WIN"
                        break
                else:
                    if bar["high"] >= sl:
                        exit_price = sl
                        exit_time = str(bar["time"])
                        outcome = "LOSS"
                        break
                    if bar["low"] <= tp:
                        exit_price = tp
                        exit_time = str(bar["time"])
                        outcome = "WIN"
                        break
            else:
                exit_price = d1.iloc[exit_idx]["close"]
                if dir == "BUY":
                    outcome = "WIN" if exit_price > entry else "LOSS"
                else:
                    outcome = "WIN" if exit_price < entry else "LOSS"

            profit = (exit_price - entry) * 100 * lots if dir == "BUY" else (entry - exit_price) * 100 * lots
            pips = abs(exit_price - entry) * 10000

            trades.append(TradeRecord(
                time=str(row["time"]), direction=dir, entry=round(entry, 2),
                sl=round(sl, 2), tp=round(tp, 2), exit_time=exit_time,
                exit_price=round(exit_price, 2), profit=round(profit, 2),
                pips=round(pips, 1), rr=round(abs(tp-entry)/abs(sl-entry), 2),
                score=analysis.total_score, result=outcome,
            ))

            if outcome == "WIN":
                result.wins += 1
                result.gross_profit += profit
            else:
                result.losses += 1
                result.gross_loss += abs(profit)

            equity += profit
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > result.max_dd:
                result.max_dd = dd

            equity_curve.append(equity)

    result.total_trades = len(trades)
    result.trades = trades
    result.equity_curve = equity_curve
    result.net_profit = round(result.gross_profit - result.gross_loss, 2)
    result.win_rate = round(result.wins / result.total_trades * 100, 2) if result.total_trades else 0
    result.avg_win = round(result.gross_profit / result.wins, 2) if result.wins else 0
    result.avg_loss = round(result.gross_loss / result.losses, 2) if result.losses else 0
    result.profit_factor = round(result.gross_profit / result.gross_loss, 2) if result.gross_loss else 0
    result.max_dd_pct = round(result.max_dd / peak * 100, 2) if peak else 0

    # Sharpe (simplified)
    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if np.std(returns) > 0:
            result.sharpe = round(np.mean(returns) / np.std(returns) * np.sqrt(252), 2)

    return result


def print_backtest(r: BacktestResult):
    print("\n" + "=" * 55)
    print("  MAE PLA BACKTEST RESULTS")
    print("=" * 55)
    print(f"  Total Trades:    {r.total_trades}")
    print(f"  Wins:            {r.wins} ({r.win_rate}%)")
    print(f"  Losses:          {r.losses}")
    print(f"  Net Profit:      ${r.net_profit:,.2f}")
    print(f"  Profit Factor:   {r.profit_factor}")
    print(f"  Avg Win:         ${r.avg_win:,.2f}")
    print(f"  Avg Loss:        ${r.avg_loss:,.2f}")
    print(f"  Max Drawdown:    ${r.max_dd:,.2f} ({r.max_dd_pct}%)")
    print(f"  Sharpe Ratio:    {r.sharpe}")
    print("-" * 55)

    if r.trades:
        print(f"\n  Last {min(10, len(r.trades))} trades:")
        for t in r.trades[-10:]:
            icon = "+" if t.result == "WIN" else "-"
            print(f"    {icon} {t.direction} @ ${t.entry:.0f} -> ${t.exit_price:.0f} "
                  f"({t.result}) ${t.profit:+.0f} | RR {t.rr}")
    print("=" * 55)
