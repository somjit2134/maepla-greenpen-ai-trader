"""Main automated trading loop."""

import time
import sys
import os
import json
from datetime import datetime

from src.config import get
from src.connector import MT5Connector
from src.database import Database
from src.market import run_analysis
from src.trading import TradingEngine
from src.notifier import Notifier
from src.logger import get_logger

logger = get_logger()


def _status_file_path() -> str:
    return os.path.join("runtime", "status.json")


def _write_runtime_status(payload: dict):
    os.makedirs("runtime", exist_ok=True)
    path = _status_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def run_one_cycle(connector, engine, db, notifier, cfg) -> dict:
    result = {"status": "ok", "decision": "WAIT", "action": "none"}

    try:
        data = connector.all_rates(count=300)
        if not data:
            logger.warning("No market data received")
            return {"status": "nodata", "decision": "WAIT", "action": "none"}

        bid, ask, spread = connector.tick()
        analysis = run_analysis(data, bid, ask, spread)

        # Save analysis
        analysis_id = db.save_analysis({
            "time": analysis.time, "price": analysis.price,
            "decision": analysis.decision, "score": analysis.total_score,
            "monthly": analysis.monthly, "weekly": analysis.weekly,
            "daily_zone": analysis.daily_zone, "h4": analysis.h4,
            "h1": analysis.h1, "supports": analysis.supports,
            "resistances": analysis.resistances, "grid_score": analysis.grid_score,
            "ath_pct": analysis.ath_pct, "thousand_pt": analysis.thousand_pt,
            "pa_bullish": analysis.pa_bullish, "pa_bearish": analysis.pa_bearish,
            "score_breakdown": {"framework": analysis.framework_score,
                                "trend": analysis.trend_score,
                                "grid": analysis.grid_score_val,
                                "ath": analysis.ath_score,
                                "pa": analysis.pa_score,
                                "rr": analysis.rr_score},
            "trade_plan": analysis.trade_plan,
        })

        result["analysis_id"] = analysis_id
        result["decision"] = analysis.decision
        result["score"] = analysis.total_score
        result["price"] = analysis.price

        # Scoring decision
        if (
            analysis.total_score >= cfg.trading.execute_score_threshold
            and cfg.trading.auto_trade
            and analysis.trade_plan
        ):
            logger.info(f"SCORE {analysis.total_score} >= {cfg.trading.execute_score_threshold} - AUTO TRADE")

            # Check if already in a position
            positions = engine.get_positions()
            if len(positions) >= cfg.risk.max_open_trades:
                logger.info(f"Max positions ({cfg.risk.max_open_trades}) reached, skipping")
                result["action"] = "skipped_max_positions"
            else:
                daily = db.get_daily_pnl()
                ok, reason = RiskManager().can_open_trade(len(positions), daily)
                if not ok:
                    logger.warning(f"Cannot open trade: {reason}")
                    result["action"] = f"blocked_{reason}"
                else:
                    account = engine.get_account()
                    balance = account.get("balance", 10000)
                    exec_result = engine.execute(analysis.trade_plan, analysis_id, balance)

                    if exec_result["success"]:
                        logger.info(f"TRADE EXECUTED: {analysis.decision} {exec_result['lot_size']} lots")
                        result["action"] = f"executed_{exec_result['ticket']}"

                        # Save signal
                        db.save_signal({
                            "analysis_id": analysis_id, "time": analysis.time,
                            "price": analysis.price, "direction": analysis.decision,
                            "score": analysis.total_score, "grade": analysis.grade,
                            "source": "AUTO",
                        })

                        # Notify
                        if cfg.line_notify.enabled:
                            notifier.trade_signal(analysis)
                    else:
                        logger.warning(f"Trade execution failed: {exec_result['msg']}")
                        result["action"] = f"exec_failed_{exec_result['msg']}"

        elif analysis.total_score >= cfg.trading.execute_score_threshold and cfg.trading.auto_trade and not analysis.trade_plan:
            logger.info(
                f"SCORE {analysis.total_score} >= {cfg.trading.execute_score_threshold} but no trade plan - skip execute"
            )
            result["action"] = "skipped_no_plan"

        elif analysis.total_score >= cfg.trading.alert_score_threshold:
            result["action"] = "alert"
            logger.info(f"SCORE {analysis.total_score} >= {cfg.trading.alert_score_threshold} - ALERT")

            db.save_signal({
                "analysis_id": analysis_id, "time": analysis.time,
                "price": analysis.price, "direction": analysis.decision,
                "score": analysis.total_score, "grade": analysis.grade,
                "source": "ALERT",
            })

            if cfg.line_notify.enabled:
                notifier.trade_signal(analysis)

        else:
            logger.debug(f"Score {analysis.total_score} - no action")

        # Update daily PnL
        db.update_daily_pnl()

    except Exception as e:
        logger.exception("Cycle error")
        result["status"] = f"error: {e}"

    return result


def start_monitoring(connector, connect_once: bool = False):
    if connect_once:
        if not connector.connect():
            logger.error("Cannot connect to MT5")
            return
    try:
        cfg = get()
        db = Database()
        engine = TradingEngine(connector, db)
        notifier = Notifier()
        interval = cfg.trading.monitor_interval_seconds
        started_at = datetime.now().isoformat()

        _write_runtime_status({
            "is_running": True,
            "started_at": started_at,
            "last_cycle_at": None,
            "last_result": {
                "status": "starting",
                "decision": "WAIT",
                "action": "none",
                "score": 0,
                "price": 0,
            },
            "monitor_interval_seconds": interval,
            "symbol": cfg.symbol.name,
            "updated_at": datetime.now().isoformat(),
            "pid": os.getpid(),
        })

        logger.info(f"Starting monitoring loop (interval={interval}s)")
        logger.info(f"Auto-trade: {cfg.trading.auto_trade}")
        logger.info(f"Execute threshold: {cfg.trading.execute_score_threshold}")
        logger.info(f"Alert threshold: {cfg.trading.alert_score_threshold}")

        cycle_count = 0
        while True:
            cycle_count += 1
            now = datetime.now().strftime("%H:%M:%S")

            result = run_one_cycle(connector, engine, db, notifier, cfg)

            _write_runtime_status({
                "is_running": True,
                "started_at": started_at,
                "last_cycle_at": datetime.now().isoformat(),
                "last_result": {
                    "status": result.get("status", "ok"),
                    "decision": result.get("decision", "WAIT"),
                    "action": result.get("action", "none"),
                    "score": result.get("score", 0),
                    "price": result.get("price", 0),
                },
                "monitor_interval_seconds": interval,
                "symbol": cfg.symbol.name,
                "updated_at": datetime.now().isoformat(),
                "pid": os.getpid(),
            })

            action_icons = {"none": "-", "alert": "!", "skipped": "~"}
            icon = action_icons.get(result.get("action", "none"), "?")
            action_str = result.get("action", "none")[:20]
            score = result.get("score", 0)
            decision = result.get("decision", "WAIT")
            price = result.get("price", 0)

            status = f"[{now}] ${price:.2f} | {decision:4s} | Score:{score:2d} | {action_str}"
            sys.stdout.write("\r" + " " * 90 + "\r")
            sys.stdout.write(status)
            sys.stdout.flush()

            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    finally:
        _write_runtime_status({
            "is_running": False,
            "stopped_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        if connect_once:
            connector.disconnect()


class RiskManager:
    from src.risk import RiskManager as RM
    def can_open_trade(self, open_trades: int, daily_pnl: dict) -> tuple[bool, str]:
        return self.RM().can_open_trade(open_trades, daily_pnl)
