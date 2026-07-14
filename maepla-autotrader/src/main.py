#!/usr/bin/env python3
"""
Mae Pla Inspired AI XAUUSD Auto Trader
========================================
Commands:
  /start      - Start automated trading
  /analyze    - Run one analysis cycle
  /backtest   - Run backtest
  /orders     - Show open orders
  /signals    - Show recent signals
  /risk       - Calculate position size
"""
import argparse
import sys
from datetime import datetime

from src.config import load, get
from src.logger import setup, get_logger
from src.connector import MT5Connector, SimConnector, get_connector
from src.database import Database
from src.market import run_analysis
from src.trading import TradingEngine
from src.risk import RiskManager
from src.backtest import run_backtest, print_backtest
from src.notifier import Notifier
from src.bot.auto_trader import start_monitoring
from src.status_web import run_status_server


def print_analysis(analysis):
    print(f"\n{'='*55}")
    print(f"  ><> MAE PLA AUTO ANALYSIS")
    print(f"{'='*55}")
    print(f"  Price:         ${analysis.price:.2f}")
    print(f"  Time:          {analysis.time}")
    print(f"  Spread:        {analysis.spread}")
    print(f"  Monthly:       {analysis.monthly}")
    print(f"  Weekly:        {analysis.weekly}")
    print(f"  Daily Zone:    {analysis.daily_zone}")
    print(f"  H4:            {analysis.h4}")
    print(f"  H1:            {analysis.h1}")
    print(f"  Position:      {analysis.range_position}")
    print(f"  Grid:          {analysis.grid_score}/2 (nearest ${analysis.grid_nearest})")
    print(f"  ATH Distance:  {analysis.ath_pct}%")
    print(f"  1000pt Frame:  {analysis.thousand_pt}")
    print(f"  PA:            {analysis.pa_overall} ({len(analysis.pa_patterns)} patterns)")
    print()
    print(f"  SCORE BREAKDOWN:")
    print(f"    Framework:   {analysis.framework_score}/2")
    print(f"    Trend:       {analysis.trend_score}/2")
    print(f"    Grid:        {analysis.grid_score_val}/2")
    print(f"    ATH:         {analysis.ath_score}/1")
    print(f"    PA:          {analysis.pa_score}/2")
    print(f"    RR:          {analysis.rr_score}/1")
    print(f"    {'='*25}")
    print(f"    TOTAL:       {analysis.total_score}/10")
    print(f"    Grade:       {analysis.grade}")
    print(f"    Decision:    {analysis.decision}")
    print()
    if analysis.trade_plan:
        tp = analysis.trade_plan
        print(f"  TRADE PLAN:")
        print(f"    Direction:  {tp['direction']}")
        print(f"    Entry:      ${tp['entry']:.2f}")
        print(f"    SL:         ${tp['sl']:.2f}")
        print(f"    TP1:        ${tp['tp1']:.2f}")
        print(f"    TP2:        ${tp.get('tp2','-'):.2f}")
        print(f"    RR:         {tp['rr']}:1")
        print(f"    Reason:     {tp['reason']}")
    print(f"{'='*55}\n")


def cmd_start(args):
    connector = SimConnector() if args.simulate else MT5Connector()
    if not connector.connect():
        print("ERROR: Cannot connect to MT5. Use --simulate for demo.")
        return 1
    start_monitoring(connector, connect_once=False)
    return 0


def cmd_analyze(args):
    connector = SimConnector() if args.simulate else MT5Connector()
    if not connector.connect():
        print("ERROR: Cannot connect.")
        return 1
    try:
        db = Database()
        data = connector.all_rates(count=300)
        bid, ask, spread = connector.tick()
        analysis = run_analysis(data, bid, ask, spread)
        print_analysis(analysis)
        db.save_analysis({
            "time": analysis.time, "price": analysis.price,
            "decision": analysis.decision, "score": analysis.total_score,
            "monthly": analysis.monthly, "weekly": analysis.weekly,
            "daily_zone": analysis.daily_zone, "h4": analysis.h4, "h1": analysis.h1,
            "supports": analysis.supports, "resistances": analysis.resistances,
            "grid_score": analysis.grid_score, "ath_pct": analysis.ath_pct,
            "thousand_pt": analysis.thousand_pt,
            "pa_bullish": analysis.pa_bullish, "pa_bearish": analysis.pa_bearish,
            "score_breakdown": {}, "trade_plan": analysis.trade_plan,
        })
    finally:
        connector.disconnect()
    return 0


def cmd_backtest(args):
    connector = SimConnector() if args.simulate else MT5Connector()
    if not connector.connect():
        print("ERROR: Cannot connect.")
        return 1
    try:
        print(f"\nRunning backtest with {args.periods} candles...")
        data = connector.all_rates(count=args.periods)
        result = run_backtest(data, initial_balance=args.balance, rr_target=args.rr)
        print_backtest(result)
    finally:
        connector.disconnect()
    return 0


def cmd_orders(args):
    db = Database()
    orders = db.get_orders()
    if not orders:
        print("No orders found.")
        return 0
    print(f"\nORDERS ({len(orders)})")
    print("-" * 60)
    for o in orders[:20]:
        status = o.get("status", "")
        profit = o.get("profit", 0) or 0
        print(f"  #{o['id']:3d} {o.get('direction','?'):4s} ${o.get('entry_price',0):.2f} "
              f"-> {o.get('close_price',0):.2f} "
              f"[{status:6s}] P/L ${profit:.2f}")
    print()
    return 0


def cmd_signals(args):
    db = Database()
    signals = db.get_signals(limit=args.limit)
    if not signals:
        print("No signals found.")
        return 0
    print(f"\nSIGNALS ({len(signals)})")
    print("-" * 60)
    for s in signals:
        print(f"  #{s['id']:3d} | {s.get('time',''):19s} | ${s.get('price',0):.2f} | "
              f"{s.get('direction','?'):4s} | Score:{s.get('score',0):2d} | {s.get('grade','')}")
    print()
    return 0


def cmd_risk(args):
    if not all([args.entry, args.stop]):
        print("ERROR: --entry and --stop required")
        return 1
    rm = RiskManager()
    lots = rm.position_size(args.balance or 10000, args.entry, args.stop, args.risk_pct)
    rr = rm.rr(args.entry, args.stop, args.target) if args.target else 0
    print(f"\n  RISK CALCULATOR")
    print(f"  Balance:    ${args.balance:,.2f}")
    print(f"  Risk:       {args.risk_pct:.1f}%")
    print(f"  Entry:      ${args.entry:.2f}")
    print(f"  Stop:       ${args.stop:.2f}")
    print(f"  Distance:   {abs(args.entry-args.stop):.2f}")
    print(f"  Lot Size:   {lots:.2f}")
    if args.target:
        print(f"  Target:     ${args.target:.2f}")
        print(f"  R:R:        {rr}:1")
    return 0


def cmd_status_web(args):
    run_status_server(host=args.host, port=args.port)
    return 0


def main():
    load()
    setup()

    p = argparse.ArgumentParser(
        description="Mae Pla Inspired AI XAUUSD Auto Trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp = p.add_subparsers(dest="cmd")

    a1 = sp.add_parser("/start", help="Start auto-trading loop")
    a1.add_argument("--simulate", action="store_true")

    a2 = sp.add_parser("/analyze", help="Single analysis")
    a2.add_argument("--simulate", action="store_true")

    a3 = sp.add_parser("/backtest", help="Run backtest")
    a3.add_argument("--simulate", action="store_true")
    a3.add_argument("--periods", type=int, default=500)
    a3.add_argument("--balance", type=float, default=10000)
    a3.add_argument("--rr", type=float, default=2.0)

    a4 = sp.add_parser("/orders", help="Show orders")
    a5 = sp.add_parser("/signals", help="Show signals")
    a5.add_argument("--limit", type=int, default=20)

    a6 = sp.add_parser("/risk", help="Position size calculator")
    a6.add_argument("--entry", type=float, required=True)
    a6.add_argument("--stop", type=float, required=True)
    a6.add_argument("--target", type=float)
    a6.add_argument("--balance", type=float, default=10000)
    a6.add_argument("--risk-pct", type=float, default=1.0)

    a7 = sp.add_parser("/status-web", help="Run web status dashboard")
    a7.add_argument("--host", default="127.0.0.1")
    a7.add_argument("--port", type=int, default=8765)

    args = p.parse_args()

    if not args.cmd:
        p.print_help()
        return 0

    cmds = {
        "/start": cmd_start,
        "/analyze": cmd_analyze,
        "/backtest": cmd_backtest,
        "/orders": cmd_orders,
        "/signals": cmd_signals,
        "/risk": cmd_risk,
        "/status-web": cmd_status_web,
    }

    return cmds.get(args.cmd, lambda _: 0)(args)


if __name__ == "__main__":
    sys.exit(main())
