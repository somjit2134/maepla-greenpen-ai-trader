#!/usr/bin/env python3
"""
Mae Pla Green Pen AI Trader - CLI Entry Point
===============================================
Commands:
  /analyze    - Full XAUUSD analysis
  /scan       - Scan all setups
  /buysetup   - Find BUY setups only
  /sellsetup  - Find SELL setups only
  /backtest   - Run backtest
  /journal    - Record/View trading journal
  /risk       - Calculate position size
  /monitor    - Start continuous monitoring
"""

import argparse
import sys
import time
from datetime import datetime
from typing import Optional

from src.config_loader import load_config, get_config
from src.log_setup import setup_logging, get_logger
from src.data.mt5_connector import MT5Connector, SimulatedMT5Connector
from src.data.database import Database
from src.engine.analysis_engine import AnalysisEngine
from src.engine.trading_engine import TradingEngine
from src.engine.risk_engine import RiskEngine
from src.notification.line_notify import LINENotifier


def print_banner():
    banner = """
    ===========================================================
    ><> MAE PLA GREEN PEN AI TRADER
    XAUUSD Professional Analyst Engine v1.0
    ===========================================================
    """
    print(banner)


def print_analysis(result):
    """Print analysis result in the Mae Pla Green Pen format."""
    print()
    print("=" * 50)
    print("><> MAE PLA GREEN PEN AI ANALYSIS")
    print("=" * 50)
    print(f"Symbol:         {result.symbol}")
    print(f"Current Price:  ${result.current_price:.2f}")
    print(f"Time:           {result.timestamp}")
    print(f"Market Condition: {result.monthly_bias}")
    print("-" * 50)

    print()
    print("FRAME ANALYSIS")
    print(f"  ATH Distance:   {result.ath_distance_percent:.1f}% below ATH")
    print(f"  1000pt Frame:   {result.thousand_point_position}")
    print(f"  Grid Score:     {result.grid_score}/4")

    print()
    print("PRICE LOCATION")
    print(f"  Position:       {result.current_position}")
    print(f"  Range High:     ${result.range_high:.2f}")
    print(f"  Range Low:      ${result.range_low:.2f}")
    print(f"  Mid Range:      ${result.mid_range:.2f}")

    print()
    print("MULTI TIMEFRAME")
    print(f"  Monthly Bias:   {result.monthly_bias}")
    print(f"  Weekly Bias:    {result.weekly_bias}")
    print(f"  Daily Zone:     {result.daily_zone}")
    print(f"  H4 Structure:   {result.h4_structure}")
    print(f"  H4 Bias:        {result.h4_bias}")
    print(f"  H1 Direction:   {result.h1_direction}")

    print()
    print("SUPPORT / RESISTANCE")
    if result.support_zones:
        print(f"  Support:        {', '.join(result.support_zones[:3])}")
    if result.resistance_zones:
        print(f"  Resistance:     {', '.join(result.resistance_zones[:3])}")

    print()
    print("PRICE ACTION")
    if result.price_action_patterns:
        for p in result.price_action_patterns[:3]:
            print(f"  {p['pattern']}: {p['direction']} (strength {p['strength']})")
    else:
        print("  No significant patterns detected")
    print(f"  Bullish Confirmed: {result.price_action_bullish}")
    print(f"  Bearish Confirmed: {result.price_action_bearish}")

    print()
    print("SETUP SCORE")
    if result.buy_score:
        s = result.buy_score
        print(f"  BUY  Location:{s.location}/2  Trend:{s.trend}/2  Grid:{s.grid}/2  Frame:{s.frame}/2  PA:{s.price_action}/2  TOTAL:{s.total}/10")
        print(f"       Grade: {s.grade}")
    if result.sell_score:
        s = result.sell_score
        print(f"  SELL Location:{s.location}/2  Trend:{s.trend}/2  Grid:{s.grid}/2  Frame:{s.frame}/2  PA:{s.price_action}/2  TOTAL:{s.total}/10")
        print(f"       Grade: {s.grade}")

    print()
    print("-" * 50)
    print(f"FINAL DECISION: {result.final_decision}")
    print("-" * 50)

    if result.trade_plan:
        tp = result.trade_plan
        print()
        print("TRADE PLAN")
        print(f"  Direction:    {tp.get('direction', 'N/A')}")
        print(f"  Entry:        ${tp.get('entry', 0):.2f}")
        print(f"  Stop Loss:    ${tp.get('stop_loss', 0):.2f}")
        print(f"  Take Profit 1: ${tp.get('take_profit_1', 0):.2f}")
        print(f"  Take Profit 2: ${tp.get('take_profit_2', 0):.2f}")
        print(f"  Risk/Reward:  {tp.get('risk_reward', 0)}:1")
        print(f"  Reason:       {tp.get('reason', '')}")
    else:
        print()
        print("  No trade plan generated.")

    if result.news_risk:
        print(f"  [WARN] NEWS RISK: {result.news_detail}")

    print()
    print("=" * 50)


def get_connector(use_simulated: bool = False):
    if use_simulated:
        return SimulatedMT5Connector()
    return MT5Connector()


def cmd_analyze(args):
    """Full XAUUSD analysis."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5. Use --simulate for demo mode.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)
        notifier = LINENotifier()

        result = engine.run_full_analysis()
        print_analysis(result)

        if args.notify:
            notifier.send_analysis(result)

        if result.trade_plan and args.risk_check:
            account = connector.get_account_info()
            if account:
                risk_engine = RiskEngine()
                check = risk_engine.validate_trade_plan(result.trade_plan, account["balance"])
                print(f"\nRISK CHECK:")
                print(f"  Passed: {check.passed}")
                print(f"  Position Size: {check.position_size:.2f} lots")
                print(f"  Risk Amount: ${check.risk_amount:.2f}")
                print(f"  R:R Ratio: {check.rr_ratio}:1")
                if check.warnings:
                    for w in check.warnings:
                        print(f"  [WARN] {w}")

    finally:
        connector.disconnect()

    return 0


def cmd_scan(args):
    """Scan for all setups."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)

        result = engine.run_full_analysis()
        print_analysis(result)

    finally:
        connector.disconnect()

    return 0


def cmd_buy(args):
    """Find BUY setups only."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)

        result = engine.run_full_analysis()
        if result.final_decision == "BUY":
            print_analysis(result)
        else:
            print("\n[NO] No BUY setup found.")
            print(f"Buy Score: {result.buy_score.total if result.buy_score else 0}/10")
            if result.buy_score:
                print(f"Grade: {result.buy_score.grade}")

    finally:
        connector.disconnect()

    return 0


def cmd_sell(args):
    """Find SELL setups only."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)

        result = engine.run_full_analysis()
        if result.final_decision == "SELL":
            print_analysis(result)
        else:
            print("\n[NO] No SELL setup found.")
            print(f"Sell Score: {result.sell_score.total if result.sell_score else 0}/10")
            if result.sell_score:
                print(f"Grade: {result.sell_score.grade}")

    finally:
        connector.disconnect()

    return 0


def cmd_backtest(args):
    """Run backtest on historical data."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)

        print(f"\n[CHART] Running backtest for {args.periods} periods...\n")

        data = connector.get_all_timeframes(count=args.periods)
        bid, ask = connector.get_current_price()
        price = (bid + ask) / 2

        result = engine.run_analysis_with_data(data, price, bid, ask)

        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0

        print(f"Backtest period: {args.periods} candles\n")
        print(f"Final decision: {result.final_decision}")
        if result.buy_score:
            print(f"Buy score: {result.buy_score.total}/10")
        if result.sell_score:
            print(f"Sell score: {result.sell_score.total}/10")

        print("\n=== BACKTEST RESULTS ===")
        trades = db.get_trades(limit=50)
        if trades:
            for t in trades:
                print(f"  {t['direction']} @ ${t['entry_price']:.2f} -> "
                      f"{'CLOSED' if t['status']=='CLOSED' else 'OPEN'} "
                      f"(P/L: ${t['profit'] if t['profit'] else 0:.2f})")
                if t['status'] == 'CLOSED':
                    total_trades += 1
                    if t['profit'] and t['profit'] > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    total_profit += (t['profit'] or 0)

            if total_trades > 0:
                print(f"\nTotal Trades: {total_trades}")
                print(f"Winning: {winning_trades} ({winning_trades/total_trades*100:.1f}%)")
                print(f"Losing: {losing_trades} ({losing_trades/total_trades*100:.1f}%)")
                print(f"Total P/L: ${total_profit:.2f}")
        else:
            print("No historical trades found in database.")

    finally:
        connector.disconnect()

    return 0


def cmd_journal(args):
    """Record or view trading journal."""
    db = Database()

    if args.action == "view":
        entries = db.get_journal(limit=args.limit)
        if not entries:
            print("\n[BOOK] No journal entries found.")
            return 0

        print(f"\n[BOOK] TRADING JOURNAL (last {len(entries)} entries)")
        print("=" * 60)
        for e in entries:
            print(f"  #{e['id']} | {e['entry_date']}")
            print(f"       {e.get('direction', 'N/A')} @ ${e.get('entry_price', 0):.2f} "
                  f"-> ${e.get('exit_price', 0):.2f} (P/L: ${e.get('profit', 0):.2f})")
            if e.get('lesson'):
                print(f"       Lesson: {e['lesson']}")
            if e.get('emotion'):
                print(f"       Emotion: {e['emotion']}")
            print()

    elif args.action == "add":
        entry = {
            "trade_id": args.trade_id,
            "entry_date": args.entry_date or datetime.now().isoformat(),
            "exit_date": args.exit_date,
            "direction": args.direction,
            "entry_price": args.entry_price,
            "exit_price": args.exit_price,
            "profit": args.profit,
            "emotion": args.emotion,
            "mistake": args.mistake,
            "lesson": args.lesson,
        }
        jid = db.save_journal_entry(entry)
        print(f"[OK] Journal entry #{jid} saved.")

    return 0


def cmd_risk(args):
    """Calculate position size."""
    if not all([args.entry, args.stop]):
        print("ERROR: --entry and --stop are required")
        return 1

    account_balance = args.balance or 10000.0
    risk_percent = args.risk_percent or 1.0

    risk_engine = RiskEngine()
    lot_size = risk_engine.calculate_position_size(
        account_balance, args.entry, args.stop, risk_percent
    )

    risk_amount = account_balance * (risk_percent / 100)
    sl_distance = abs(args.entry - args.stop)

    print(f"\n[CALC] RISK CALCULATOR")
    print("=" * 40)
    print(f"  Balance:        ${account_balance:.2f}")
    print(f"  Risk:           {risk_percent:.1f}% (${risk_amount:.2f})")
    print(f"  Entry:          ${args.entry:.2f}")
    print(f"  Stop Loss:      ${args.stop:.2f}")
    print(f"  Distance:       {sl_distance:.2f} points")
    print(f"  Lot Size:       {lot_size:.2f} lots")

    if args.target:
        rr = risk_engine.calculate_rr(args.entry, args.stop, args.target)
        print(f"  Target:         ${args.target:.2f}")
        print(f"  Risk/Reward:    {rr}:1")
        if rr >= 2.0:
            print(f"  [OK] R:R acceptable (>= 2:1)")
        else:
            print(f"  [WARN] R:R below minimum (need >= 2:1)")

    return 0


def cmd_monitor(args):
    """Continuous monitoring mode."""
    connector = get_connector(args.simulate)
    if not connector.connect():
        print("ERROR: Cannot connect to MT5.")
        return 1

    try:
        db = Database()
        engine = AnalysisEngine(connector=connector, db=db)
        notifier = LINENotifier()
        interval = args.interval or 60

        print(f"\n[REFRESH] Monitoring XAUUSD every {interval}s. Press Ctrl+C to stop.\n")

        while True:
            result = engine.run_full_analysis()
            now = datetime.now().strftime("%H:%M:%S")
            decision = result.final_decision
            buy_s = result.buy_score.total if result.buy_score else 0
            sell_s = result.sell_score.total if result.sell_score else 0

            status = f"[{now}] ${result.current_price:.2f} | DECISION: {decision}"
            if decision == "BUY":
                status += f" [BULL] (Score: {buy_s}/10)"
            elif decision == "SELL":
                status += f" [BEAR] (Score: {sell_s}/10)"
            else:
                status += f" [WAIT] Buy:{buy_s} Sell:{sell_s}"

            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.write(status)
            sys.stdout.flush()

            if decision != "WAIT" and args.notify:
                notifier.send_analysis(result)

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
    finally:
        connector.disconnect()

    return 0


def main():
    load_config()
    setup_logging()
    logger = get_logger()

    parser = argparse.ArgumentParser(
        description="Mae Pla Green Pen AI Trader - XAUUSD Professional Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main /analyze
  python -m src.main /analyze --simulate
  python -m src.main /scan --simulate
  python -m src.main /buysetup --simulate
  python -m src.main /sellsetup --simulate
  python -m src.main /risk --entry 4075 --stop 4060 --target 4100 --balance 10000
  python -m src.main /journal view
  python -m src.main /backtest --simulate --periods 500
  python -m src.main /monitor --simulate --interval 30
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # /analyze
    p_analyze = subparsers.add_parser("/analyze", help="Full XAUUSD analysis")
    p_analyze.add_argument("--simulate", action="store_true", help="Use simulated data")
    p_analyze.add_argument("--notify", action="store_true", help="Send LINE notification")
    p_analyze.add_argument("--risk-check", action="store_true", help="Show risk assessment")

    # /scan
    p_scan = subparsers.add_parser("/scan", help="Scan all setups")
    p_scan.add_argument("--simulate", action="store_true")

    # /buysetup
    p_buy = subparsers.add_parser("/buysetup", help="Find BUY setups")
    p_buy.add_argument("--simulate", action="store_true")

    # /sellsetup
    p_sell = subparsers.add_parser("/sellsetup", help="Find SELL setups")
    p_sell.add_argument("--simulate", action="store_true")

    # /backtest
    p_bt = subparsers.add_parser("/backtest", help="Run backtest")
    p_bt.add_argument("--simulate", action="store_true")
    p_bt.add_argument("--periods", type=int, default=500, help="Number of candles")

    # /journal
    p_journal = subparsers.add_parser("/journal", help="Trading journal")
    p_journal.add_argument("action", choices=["view", "add"], default="view", nargs="?")
    p_journal.add_argument("--limit", type=int, default=20)
    p_journal.add_argument("--trade-id", type=int)
    p_journal.add_argument("--entry-date")
    p_journal.add_argument("--exit-date")
    p_journal.add_argument("--direction", choices=["BUY", "SELL"])
    p_journal.add_argument("--entry-price", type=float)
    p_journal.add_argument("--exit-price", type=float)
    p_journal.add_argument("--profit", type=float)
    p_journal.add_argument("--emotion")
    p_journal.add_argument("--mistake")
    p_journal.add_argument("--lesson")

    # /risk
    p_risk = subparsers.add_parser("/risk", help="Calculate position size")
    p_risk.add_argument("--entry", type=float, required=True)
    p_risk.add_argument("--stop", type=float, required=True)
    p_risk.add_argument("--target", type=float)
    p_risk.add_argument("--balance", type=float, default=10000)
    p_risk.add_argument("--risk-percent", type=float, default=1.0)

    # /monitor
    p_mon = subparsers.add_parser("/monitor", help="Continuous monitoring mode")
    p_mon.add_argument("--simulate", action="store_true")
    p_mon.add_argument("--interval", type=int, default=60, help="Seconds between checks")
    p_mon.add_argument("--notify", action="store_true", help="Send LINE on signal")

    args = parser.parse_args()

    if not args.command:
        print_banner()
        parser.print_help()
        return 0

    cmd_map = {
        "/analyze": cmd_analyze,
        "/scan": cmd_scan,
        "/buysetup": cmd_buy,
        "/sellsetup": cmd_sell,
        "/backtest": cmd_backtest,
        "/journal": cmd_journal,
        "/risk": cmd_risk,
        "/monitor": cmd_monitor,
    }

    handler = cmd_map.get(args.command)
    if handler:
        return handler(args)

    print(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
