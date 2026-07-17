"""
MT5 Autonomous Trading System - Main Entry Point
==================================================
Commands:
  /analyze     - Full analysis with signal
  /scan        - Scan for setups
  /monitor     - Continuous monitoring
  /status      - System status
  /journal     - View trade journal
  /risk        - Calculate position size
  /backtest    - Run backtest
"""
import sys
import time
import argparse
import logging
import numpy as np
from datetime import datetime

from src.config import load_config, get_config
from src.data.mt5_connector import MT5Connector, SimulatedMT5Connector
from src.engine.signal_engine import SignalEngine
from src.engine.risk_manager import RiskManager
from src.engine.trade_executor import TradeExecutor
from src.data.journal import Journal
from src.backtest import BacktestEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/trader.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def print_banner():
    print("""
    ===========================================================
    ><> MT5 AUTONOMOUS TRADING SYSTEM
    Price Action + Frame + Cycle Based
    ===========================================================
    """)


def _get_connector(args) -> object:
    cfg = get_config()
    if getattr(args, "simulate", False):
        return SimulatedMT5Connector()
    connector = MT5Connector()
    if not connector.connect():
        print("ERROR: Cannot connect to MT5. Use --simulate for demo.")
        return None
    return connector


def _calculate_atr(data: dict, period: int = 14) -> float:
    h1 = data.get("H1")
    if h1 is None or len(h1) < period:
        return 0.0
    high = h1["high"].values
    low = h1["low"].values
    close = h1["close"].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    if len(tr) < period:
        return 0.0
    return float(np.mean(tr[-period:]))


def cmd_analyze(args):
    cfg = load_config()
    connector = _get_connector(args)
    if connector is None:
        return 1

    try:
        signal_engine = SignalEngine()
        risk_mgr = RiskManager()
        journal = Journal()

        data = connector.get_all_timeframes(count=300)
        bid, ask = connector.get_current_price()
        account = connector.get_account_info()

        signal = signal_engine.analyze(data, bid, ask)

        print()
        print("=" * 60)
        print("><> MT5 AUTONOMOUS TRADING SYSTEM - ANALYSIS")
        print("=" * 60)
        print(f"Symbol:    {cfg.symbol.name}")
        print(f"Bid/Ask:   ${bid:.2f} / ${ask:.2f}")
        print(f"Time:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)

        if signal.frame:
            f = signal.frame
            print(f"\nFRAME ANALYSIS:")
            print(f"  ATH: ${f.ath.ath:.2f} (dist: {f.ath.distance_percent:.1f}%)")
            print(f"  Cycle: {f.cycle.position} ({f.cycle.progress_percent:.0f}%)")
            print(f"  Sideway: {'Yes' if f.sideway.in_range else 'No'}")
            print(f"  Overall: {f.overall_frame}")

        if signal.cycle:
            c = signal.cycle
            print(f"\nCYCLE ANALYSIS:")
            print(f"  Position: {c.position}")
            print(f"  Progress: {c.progress_percent:.0f}%")
            print(f"  Remaining: {c.remaining_potential:.0f} pts")
            print(f"  Exhaustion: {'Yes' if c.exhaustion_risk else 'No'}")
            print(f"  RSI: {c.rsi_value:.1f}")

        if signal.trend:
            t = signal.trend
            print(f"\nTREND ANALYSIS:")
            print(f"  D1:  {t.d1.bias}")
            print(f"  H4:  {t.h4.bias}")
            print(f"  H1:  {t.h1.bias}")
            print(f"  M15: {t.m15.bias}")
            print(f"  Alignment: {t.alignment_score:.1f}")

        if signal.price_action:
            pa = signal.price_action
            print(f"\nPRICE ACTION:")
            print(f"  Overall: {pa.overall}")
            print(f"  Grade: {pa.signal_grade}")
            print(f"  Patterns: {len(pa.patterns)}")
            for p in pa.patterns[:3]:
                print(f"    - {p.name}: {p.direction} (strength {p.strength})")

        print()
        print("-" * 60)
        print(f"SIGNAL: {signal.direction}")
        print(f"Grade:  {signal.signal_grade}")
        print(f"Score:  {signal.confidence_score}/10")
        print(f"Reasons: {', '.join(signal.reasons)}")

        if signal.direction != "WAIT":
            print(f"\nTRADE PLAN:")
            print(f"  Entry:     ${signal.entry_price:.2f}")
            print(f"  Stop Loss: ${signal.stop_loss:.2f}")
            print(f"  TP1:       ${signal.take_profit_1:.2f}")
            print(f"  TP2:       ${signal.take_profit_2:.2f}")
            print(f"  RR:        {signal.risk_reward}:1")

            if account:
                symbol_info = connector.get_symbol_info()
                risk_check = risk_mgr.validate_trade(
                    signal.direction, signal.entry_price, signal.stop_loss,
                    signal.take_profit_1, account["balance"],
                    open_positions=len(connector.get_positions()),
                    current_spread=connector.get_spread(),
                    margin_free=account.get("margin_free", 0.0),
                    symbol_info=symbol_info,
                )
                print(f"\nRISK CHECK:")
                print(f"  Passed:   {risk_check.passed}")
                print(f"  Lot Size: {risk_check.position_size:.2f}")
                print(f"  Risk:     ${risk_check.risk_amount:.2f} ({risk_check.actual_risk_percent:.1f}%)")
                if risk_check.warnings:
                    for w in risk_check.warnings:
                        print(f"  [WARN] {w}")

        print("=" * 60)

        if getattr(args, "trade", False) and signal.direction != "WAIT" and account:
            symbol_info = connector.get_symbol_info()
            risk_check = risk_mgr.validate_trade(
                signal.direction, signal.entry_price, signal.stop_loss,
                signal.take_profit_1, account["balance"],
                open_positions=len(connector.get_positions()),
                current_spread=connector.get_spread(),
                margin_free=account.get("margin_free", 0.0),
                symbol_info=symbol_info,
            )
            if risk_check.passed:
                executor = TradeExecutor(connector)
                result = executor.place_order(
                    signal.direction, signal.entry_price, signal.stop_loss,
                    signal.take_profit_1, risk_check.position_size,
                )
                print(f"\nTRADE: {result.message}")
                if result.success:
                    journal.log_trade({
                        "ticket": result.ticket,
                        "direction": signal.direction,
                        "entry_price": result.price,
                        "stop_loss": signal.stop_loss,
                        "take_profit_1": signal.take_profit_1,
                        "take_profit_2": signal.take_profit_2,
                        "lot_size": risk_check.position_size,
                        "risk_reward": signal.risk_reward,
                        "signal_grade": signal.signal_grade,
                        "score": signal.confidence_score,
                        "frame_analysis": {"overall": signal.frame.overall_frame if signal.frame else ""},
                        "cycle_position": signal.cycle.position if signal.cycle else "",
                        "trend_alignment": str(signal.trend.alignment_score) if signal.trend else "",
                        "entry_reasons": signal.reasons,
                    })
            else:
                print(f"\nTRADE REJECTED: {'; '.join(risk_check.warnings)}")

    finally:
        if hasattr(connector, "disconnect"):
            connector.disconnect()

    return 0


def cmd_scan(args):
    cfg = load_config()
    connector = _get_connector(args)
    if connector is None:
        return 1

    try:
        signal_engine = SignalEngine()
        data = connector.get_all_timeframes(count=300)
        bid, ask = connector.get_current_price()

        signal = signal_engine.analyze(data, bid, ask)

        print(f"\nSCAN RESULT: {signal.direction} ({signal.signal_grade})")
        print(f"Score: {signal.confidence_score}/10")
        print(f"RR: {signal.risk_reward}:1")
        print(f"Reasons: {', '.join(signal.reasons)}")

    finally:
        if hasattr(connector, "disconnect"):
            connector.disconnect()

    return 0


def cmd_monitor(args):
    cfg = load_config()
    connector = _get_connector(args)
    if connector is None:
        return 1

    try:
        signal_engine = SignalEngine()
        executor = TradeExecutor(connector)
        risk_mgr = RiskManager()
        journal = Journal()
        interval = args.interval or 60

        print(f"\nMonitoring {cfg.symbol.name} every {interval}s. Press Ctrl+C to stop.\n")

        while True:
            try:
                if not connector.ensure_connected():
                    logger.warning("Connection lost, reconnecting...")
                    time.sleep(5)
                    continue

                data = connector.get_all_timeframes(count=300)
                bid, ask = connector.get_current_price()
                account = connector.get_account_info()

                signal = signal_engine.analyze(data, bid, ask)
                now = datetime.now().strftime("%H:%M:%S")

                status = f"[{now}] ${bid:.2f}/${ask:.2f} | {signal.direction} ({signal.signal_grade}) Score:{signal.confidence_score}"
                sys.stdout.write("\r" + " " * 80 + "\r")
                sys.stdout.write(status)
                sys.stdout.flush()

                executor.manage_positions(atr_value=_calculate_atr(data))

                mt5_positions = connector.get_positions()
                my_positions = [p for p in mt5_positions if p.get("magic") == cfg.trade.magic_number]

                if signal.direction != "WAIT":
                    for pos in my_positions:
                        pos_type = pos.get("type", "")
                        if (pos_type == "BUY" and signal.direction == "SELL") or \
                           (pos_type == "SELL" and signal.direction == "BUY"):
                            result = executor.close_position(pos["ticket"], comment="SignalReversal")
                            if result.success:
                                profit = pos.get("profit", 0.0)
                                price_open = pos.get("price_open", 0)
                                price_current = pos.get("price_current", 0)
                                if pos_type == "BUY":
                                    profit_pips = (price_current - price_open) / cfg.symbol.point
                                else:
                                    profit_pips = (price_open - price_current) / cfg.symbol.point
                                risk_mgr.record_trade_result(profit)
                                journal.close_trade(
                                    ticket=pos["ticket"],
                                    exit_price=price_current,
                                    profit=profit,
                                    profit_pips=profit_pips,
                                    exit_reason="Signal reversed",
                                )
                                logger.info(f"Signal exit: {pos_type} #{pos['ticket']} closed P/L ${profit:.2f} ({profit_pips:.0f} pips)")

                open_journal_trades = journal.get_open_trades()
                mt5_tickets = {p["ticket"] for p in my_positions}

                for jt in open_journal_trades:
                    jt_ticket = jt.get("ticket")
                    if jt_ticket and jt_ticket not in mt5_tickets:
                        history = connector.get_history_orders(days=1)
                        for deal in history:
                            if deal.get("position_id") == jt_ticket and deal.get("entry") == 1:
                                profit = deal.get("profit", 0.0)
                                price = deal.get("price", 0.0)
                                entry_price = jt.get("entry_price", 0)
                                direction = jt.get("direction", "")
                                if direction == "BUY":
                                    profit_pips = (price - entry_price) / cfg.symbol.point
                                else:
                                    profit_pips = (entry_price - price) / cfg.symbol.point
                                journal.close_trade(
                                    ticket=jt_ticket,
                                    exit_price=price,
                                    profit=profit,
                                    profit_pips=profit_pips,
                                    exit_reason="MT5 closed",
                                    swap=deal.get("swap", 0.0),
                                    commission=deal.get("commission", 0.0),
                                )
                                risk_mgr.record_trade_result(profit)
                                logger.info(f"Journal synced: #{jt_ticket} closed P/L ${profit:.2f}")
                                break

                if signal.direction != "WAIT" and account:
                    has_position = len(my_positions) > 0
                    if not has_position:
                        symbol_info = connector.get_symbol_info()
                        risk_check = risk_mgr.validate_trade(
                            signal.direction, signal.entry_price, signal.stop_loss,
                            signal.take_profit_1, account["balance"],
                            open_positions=len(mt5_positions),
                            current_spread=connector.get_spread(),
                            margin_free=account.get("margin_free", 0.0),
                            symbol_info=symbol_info,
                        )
                        if risk_check.passed:
                            result = executor.place_order(
                                signal.direction, signal.entry_price, signal.stop_loss,
                                signal.take_profit_1, risk_check.position_size,
                            )
                            if result.success:
                                logger.info(f"Auto trade: {result.message}")
                                journal.log_ticket(result.ticket, signal)

                time.sleep(interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(10)

    finally:
        print("\nMonitoring stopped.")
        if hasattr(connector, "disconnect"):
            connector.disconnect()

    return 0


def cmd_status(args):
    cfg = load_config()
    connector = _get_connector(args)
    journal = Journal()
    risk_mgr = RiskManager()

    print("\n=== SYSTEM STATUS ===")
    print(f"Symbol: {cfg.symbol.name}")
    print(f"Risk: {cfg.risk.risk_per_trade_percent}% per trade")
    print(f"Max positions: {cfg.risk.max_open_positions}")
    print(f"Min RR: {cfg.risk.min_rr}:1")

    if connector:
        if connector.is_connected():
            account = connector.get_account_info()
            positions = connector.get_positions()

            if account:
                print(f"\nACCOUNT:")
                print(f"  Balance:  ${account['balance']:.2f}")
                print(f"  Equity:   ${account['equity']:.2f}")
                print(f"  Profit:   ${account['profit']:.2f}")
                print(f"  Free:     ${account['margin_free']:.2f}")

            print(f"\nOPEN POSITIONS: {len(positions)}")
            for p in positions:
                print(f"  #{p['ticket']} {p['type']} {p['volume']} lots @ ${p['price_open']:.2f} P/L: ${p['profit']:.2f}")

        if hasattr(connector, "disconnect"):
            connector.disconnect()

    report = journal.performance_report()
    if "message" not in report:
        print(f"\nJOURNAL:")
        print(f"  Total trades: {report['total_trades']}")
        print(f"  Win rate: {report['win_rate']}%")
        print(f"  Profit factor: {report['profit_factor']}")
        print(f"  Total P/L: ${report['total_profit']:.2f}")
        print(f"  Max drawdown: {report['max_drawdown']}%")

    risk_status = risk_mgr.get_status()
    print(f"\nRISK STATUS:")
    print(f"  Daily loss: ${risk_status['daily_loss']:.2f}")
    print(f"  Consecutive losses: {risk_status['consecutive_losses']}")

    return 0


def cmd_journal(args):
    journal = Journal()
    report = journal.performance_report()

    if "message" in report:
        print(f"\n{report['message']}")
        return 0

    print("\n=== TRADING JOURNAL ===")
    print(f"Total trades:   {report['total_trades']}")
    print(f"Winning:        {report['winning_trades']}")
    print(f"Losing:         {report['losing_trades']}")
    print(f"Win rate:       {report['win_rate']}%")
    print(f"Profit factor:  {report['profit_factor']}")
    print(f"Total P/L:      ${report['total_profit']:.2f}")
    print(f"Max drawdown:   {report['max_drawdown']}%")
    print(f"Avg win:        ${report['avg_win']:.2f}")
    print(f"Avg loss:       ${report['avg_loss']:.2f}")
    print(f"Best trade:     ${report['best_trade']:.2f}")
    print(f"Worst trade:    ${report['worst_trade']:.2f}")

    last_n = getattr(args, "last", 10) or 10
    trades = journal.get_closed_trades(limit=last_n)
    if trades:
        print(f"\nLAST {len(trades)} TRADES:")
        print("-" * 80)
        for t in trades:
            direction = t.get("direction", "?")
            entry = t.get("entry_price", 0)
            exit_p = t.get("exit_price", 0)
            profit = t.get("profit", 0) or 0
            grade = t.get("signal_grade", "?")
            print(f"  {direction} @ ${entry:.2f} -> ${exit_p:.2f} "
                  f"{'WIN' if profit > 0 else 'LOSS'} ${profit:.2f} [{grade}]")

    return 0


def cmd_risk(args):
    cfg = load_config()
    risk_mgr = RiskManager()

    entry = getattr(args, "entry", None)
    sl = getattr(args, "sl", None)
    tp = getattr(args, "tp", None)

    if entry and sl:
        lot = risk_mgr.calculate_position_size(
            getattr(args, "balance", None) or cfg.backtest.initial_balance,
            entry, sl,
            getattr(args, "risk_percent", None) or cfg.risk.risk_per_trade_percent,
        )
        rr = 0
        if tp:
            rr = risk_mgr.calculate_rr(entry, sl, tp)

        print(f"\n=== RISK CALCULATOR ===")
        print(f"Entry:     ${entry:.2f}")
        print(f"SL:        ${sl:.2f}")
        print(f"TP:        ${tp:.2f}" if tp else "TP: N/A")
        print(f"Lot Size:  {lot:.2f}")
        print(f"RR:        {rr}:1" if rr else "RR: N/A")
        print(f"Risk:      {getattr(args, 'risk_percent', None) or cfg.risk.risk_per_trade_percent}%")

    return 0


def cmd_backtest(args):
    cfg = load_config()
    bt = BacktestEngine()

    connector = _get_connector(args)
    if connector is None:
        return 1

    try:
        periods = getattr(args, "periods", 500) or 500
        balance = getattr(args, "balance", 10000) or 10000
        print(f"\nRunning backtest with {periods} periods...")
        data = connector.get_all_timeframes(count=periods)

        result = bt.run_backtest(data, initial_balance=balance)

        print(f"\n=== BACKTEST RESULTS ===")
        print(f"Total trades:   {result.total_trades}")
        print(f"Winning:        {result.winning_trades}")
        print(f"Losing:         {result.losing_trades}")
        print(f"Win rate:       {result.win_rate}%")
        print(f"Profit factor:  {result.profit_factor}")
        print(f"Total P/L:      ${result.total_profit:.2f}")
        print(f"Max drawdown:   {result.max_drawdown_percent}%")
        print(f"Sharpe ratio:   {result.sharpe_ratio}")
        print(f"Expectancy:     ${result.expectancy:.2f}")
        print(f"Start balance:  ${result.start_balance:.2f}")
        print(f"End balance:    ${result.end_balance:.2f}")

        mc_runs = getattr(args, "monte_carlo", 0) or 0
        if mc_runs > 0:
            mc = bt.monte_carlo(result.trades, mc_runs)
            print(f"\n=== MONTE CARLO ({mc['simulations']} simulations) ===")
            print(f"Median balance:   ${mc['median_balance']:.2f}")
            print(f"Mean balance:     ${mc['mean_balance']:.2f}")
            print(f"Worst case:       ${mc['worst_balance']:.2f}")
            print(f"Best case:        ${mc['best_balance']:.2f}")
            print(f"5th percentile:   ${mc['percentile_5']:.2f}")
            print(f"95th percentile:  ${mc['percentile_95']:.2f}")
            print(f"Profit prob:      {mc['probability_of_profit']}%")
            print(f"Median max DD:    {mc['median_max_dd']}%")

        filepath = bt.save_results(result)
        print(f"\nResults saved: {filepath}")

    finally:
        if hasattr(connector, "disconnect"):
            connector.disconnect()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="MT5 Autonomous Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command")

    p_analyze = subparsers.add_parser("/analyze", help="Full analysis")
    p_analyze.add_argument("--trade", action="store_true", help="Auto execute trade")
    p_analyze.add_argument("--simulate", action="store_true")

    p_scan = subparsers.add_parser("/scan", help="Scan for setups")
    p_scan.add_argument("--simulate", action="store_true")

    p_monitor = subparsers.add_parser("/monitor", help="Continuous monitoring")
    p_monitor.add_argument("--interval", type=int, default=60)
    p_monitor.add_argument("--simulate", action="store_true")

    p_status = subparsers.add_parser("/status", help="System status")
    p_status.add_argument("--simulate", action="store_true")

    p_journal = subparsers.add_parser("/journal", help="Trade journal")
    p_journal.add_argument("--last", type=int, default=10)

    p_risk = subparsers.add_parser("/risk", help="Calculate position size")
    p_risk.add_argument("--entry", type=float)
    p_risk.add_argument("--sl", type=float)
    p_risk.add_argument("--tp", type=float)
    p_risk.add_argument("--balance", type=float)
    p_risk.add_argument("--risk-percent", type=float)

    p_bt = subparsers.add_parser("/backtest", help="Run backtest")
    p_bt.add_argument("--periods", type=int, default=500)
    p_bt.add_argument("--balance", type=float, default=10000)
    p_bt.add_argument("--monte-carlo", type=int, default=0)
    p_bt.add_argument("--simulate", action="store_true")

    args = parser.parse_args()

    if not args.command:
        print_banner()
        parser.print_help()
        return 0

    cmd_map = {
        "/analyze": cmd_analyze,
        "/scan": cmd_scan,
        "/monitor": cmd_monitor,
        "/status": cmd_status,
        "/journal": cmd_journal,
        "/risk": cmd_risk,
        "/backtest": cmd_backtest,
    }

    handler = cmd_map.get(args.command)
    if handler:
        return handler(args)

    print(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
