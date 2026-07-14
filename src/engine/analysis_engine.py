import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import pandas as pd

from src.config_loader import get_config
from src.data.mt5_connector import MT5Connector
from src.data.database import Database
from src.analysis.multi_timeframe import MultiTimeframeAnalyzer
from src.analysis.market_structure import MarketStructureDetector
from src.analysis.support_resistance import SupportResistanceDetector
from src.analysis.grid_analysis import GridAnalyzer
from src.analysis.frame_analysis import FrameAnalyzer
from src.analysis.price_action import PriceActionDetector
from src.analysis.setup_scorer import SetupScorer, SetupScore
from src.log_setup import get_logger

logger = get_logger()


@dataclass
class AnalysisResult:
    timestamp: str = ""
    symbol: str = "XAUUSD"
    current_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0

    monthly_bias: str = "RANGE"
    weekly_bias: str = "RANGE"
    daily_zone: str = ""
    h4_bias: str = "WAIT"
    h4_structure: str = "RANGE"
    h1_direction: str = "NEUTRAL"

    support_zones: list = field(default_factory=list)
    resistance_zones: list = field(default_factory=list)

    range_high: float = 0.0
    range_low: float = 0.0
    mid_range: float = 0.0
    current_position: str = "MIDDLE RANGE"

    grid_levels: list = field(default_factory=list)
    grid_score: int = 0

    ath_distance_percent: float = 0.0
    thousand_point_position: str = ""
    frame_score: int = 0

    price_action_patterns: list = field(default_factory=list)
    price_action_bullish: bool = False
    price_action_bearish: bool = False

    buy_score: Optional[SetupScore] = None
    sell_score: Optional[SetupScore] = None
    final_decision: str = "WAIT"
    trade_plan: Optional[dict] = None

    news_risk: bool = False
    news_detail: str = ""


class AnalysisEngine:
    def __init__(self, connector: Optional[MT5Connector] = None, db: Optional[Database] = None):
        self.cfg = get_config()
        self.connector = connector
        self.db = db or Database()

        self.mtf_analyzer = MultiTimeframeAnalyzer()
        self.structure_detector = MarketStructureDetector()
        self.sr_detector = SupportResistanceDetector()
        self.grid_analyzer = GridAnalyzer()
        self.frame_analyzer = FrameAnalyzer(ath=self.cfg.symbol.at)
        self.pa_detector = PriceActionDetector()
        self.scorer = SetupScorer()

    def set_connector(self, connector: MT5Connector):
        self.connector = connector

    def _detect_news_risk(self) -> tuple[bool, str]:
        today = datetime.now()
        day = today.day
        month = today.month
        year = today.year

        high_impact = []

        from datetime import timedelta
        next_friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)

        if day in [12, 13, 14] or (next_friday.day - day <= 2 and month == today.month):
            high_impact.append("CPI / FOMC week")

        if day in [1, 2, 3, 4, 5, 6, 7]:
            high_impact.append("NFP week")

        if high_impact:
            return True, f"Near high-impact news: {', '.join(high_impact)}"
        return False, "No major news event near"

    def run_full_analysis(self) -> AnalysisResult:
        if not self.connector or not self.connector.is_connected():
            logger.error("MT5 not connected")
            return AnalysisResult()

        data = self.connector.get_all_timeframes(count=300)
        bid, ask = self.connector.get_current_price()
        current_price = (bid + ask) / 2

        return self._analyze(data, current_price, bid, ask)

    def run_analysis_with_data(self, data: dict[str, pd.DataFrame], current_price: float, bid: float, ask: float) -> AnalysisResult:
        return self._analyze(data, current_price, bid, ask)

    def _analyze(self, data: dict[str, pd.DataFrame], current_price: float, bid: float, ask: float) -> AnalysisResult:
        result = AnalysisResult(
            timestamp=datetime.now().isoformat(),
            current_price=round(current_price, 2),
            bid=round(bid, 2),
            ask=round(ask, 2),
        )

        mtf_result = self.mtf_analyzer.analyze(data)
        result.monthly_bias = mtf_result.monthly_bias or "RANGE"
        result.weekly_bias = mtf_result.weekly_bias or "RANGE"
        result.daily_zone = mtf_result.daily_zone or ""
        result.h4_structure = mtf_result.h4_structure
        result.h4_bias = mtf_result.h4_bias
        result.h1_direction = mtf_result.h1_direction
        result.support_zones = mtf_result.support_zones
        result.resistance_zones = mtf_result.resistance_zones

        if "D1" in data:
            d1 = data["D1"]
            result.range_high = round(d1["high"].max(), 2)
            result.range_low = round(d1["low"].min(), 2)
        elif "H4" in data:
            h4 = data["H4"]
            result.range_high = round(h4["high"].max(), 2)
            result.range_low = round(h4["low"].min(), 2)
        else:
            result.range_high = round(current_price * 1.02, 2)
            result.range_low = round(current_price * 0.98, 2)

        result.mid_range = round((result.range_high + result.range_low) / 2, 2)

        range_pct = (current_price - result.range_low) / (result.range_high - result.range_low) if result.range_high != result.range_low else 0.5
        if range_pct < 0.33:
            result.current_position = "LOWER RANGE"
        elif range_pct > 0.67:
            result.current_position = "UPPER RANGE"
        else:
            result.current_position = "MIDDLE RANGE"

        d1 = data.get("D1")
        daily_df = d1 if d1 is not None and not d1.empty else data.get("H4")
        grid_result = self.grid_analyzer.analyze(current_price, daily_df)
        result.grid_levels = [
            {"level": round(l.level, 2), "distance": round(l.distance, 2), "score": l.score}
            for l in grid_result.levels[:5]
        ]
        result.grid_score = grid_result.score

        h4_for_frame = data.get("H4")
        frame_result = self.frame_analyzer.analyze(current_price, h4_for_frame)
        result.ath_distance_percent = frame_result.ath.distance_percent
        result.thousand_point_position = frame_result.thousand_point.position
        result.frame_score = frame_result.score

        h1 = data.get("H1")
        pa_df = h1 if h1 is not None and not h1.empty else data.get("M15")
        pa_result = self.pa_detector.detect(pa_df)
        result.price_action_patterns = [
            {"pattern": p.pattern_name, "direction": p.direction, "strength": p.strength}
            for p in (pa_result.patterns or [])
        ]
        result.price_action_bullish = pa_result.bullish_confirmed
        result.price_action_bearish = pa_result.bearish_confirmed

        nearest_support = None
        nearest_resistance = None
        if mtf_result.daily and mtf_result.daily.sr:
            sr = mtf_result.daily.sr
            for s in sr.supports:
                if s.mid < current_price:
                    nearest_support = s.mid
                    break
            for r in sr.resistances:
                if r.mid > current_price:
                    nearest_resistance = r.mid
                    break

        result.news_risk, result.news_detail = self._detect_news_risk()

        buy_score_obj = self.scorer.score(
            direction="BUY",
            current_price=current_price,
            range_high=result.range_high,
            range_low=result.range_low,
            monthly_bias=result.monthly_bias,
            h4_structure=result.h4_structure,
            h1_direction=result.h1_direction,
            grid_result=grid_result,
            frame_result=frame_result,
            pa_result=pa_result,
            sr_support=nearest_support,
            sr_resistance=nearest_resistance,
        )
        result.buy_score = buy_score_obj

        sell_score_obj = self.scorer.score(
            direction="SELL",
            current_price=current_price,
            range_high=result.range_high,
            range_low=result.range_low,
            monthly_bias=result.monthly_bias,
            h4_structure=result.h4_structure,
            h1_direction=result.h1_direction,
            grid_result=grid_result,
            frame_result=frame_result,
            pa_result=pa_result,
            sr_support=nearest_support,
            sr_resistance=nearest_resistance,
        )
        result.sell_score = sell_score_obj

        use_buy = result.buy_score.total >= 5
        use_sell = result.sell_score.total >= 5

        decision_score = 0
        use_direction = "WAIT"

        if use_buy and use_sell:
            if result.buy_score.total > result.sell_score.total:
                use_direction = "BUY"
                decision_score = result.buy_score.total
            else:
                use_direction = "SELL"
                decision_score = result.sell_score.total
        elif use_buy:
            if result.buy_score.total >= 7:
                use_direction = "BUY"
                decision_score = result.buy_score.total
        elif use_sell:
            if result.sell_score.total >= 7:
                use_direction = "SELL"
                decision_score = result.sell_score.total

        if result.news_risk and use_direction != "WAIT":
            logger.info(f"News risk detected: {result.news_detail}")
            if use_direction == "BUY" and result.buy_score.total < 7:
                use_direction = "WAIT"
            elif use_direction == "SELL" and result.sell_score.total < 7:
                use_direction = "WAIT"

        result.final_decision = use_direction

        if use_direction != "WAIT":
            result.trade_plan = self._generate_trade_plan(
                use_direction, current_price, result, nearest_support, nearest_resistance
            )

        signal_data = {
            "timestamp": result.timestamp,
            "symbol": result.symbol,
            "price": result.current_price,
            "decision": result.final_decision,
            "score": decision_score,
            "score_breakdown": {
                "buy": asdict(result.buy_score) if result.buy_score else {},
                "sell": asdict(result.sell_score) if result.sell_score else {},
            },
            "monthly_bias": result.monthly_bias,
            "weekly_bias": result.weekly_bias,
            "daily_zone": result.daily_zone,
            "h4_structure": result.h4_structure,
            "h1_direction": result.h1_direction,
            "support_zones": result.support_zones,
            "resistance_zones": result.resistance_zones,
            "frame_analysis": {
                "ath_distance": result.ath_distance_percent,
                "thousand_point": result.thousand_point_position,
            },
            "grid_levels": result.grid_levels,
            "price_action": result.price_action_patterns,
            "trade_plan": result.trade_plan,
        }
        self.db.save_signal(signal_data)

        return result

    def _generate_trade_plan(
        self,
        direction: str,
        price: float,
        result: AnalysisResult,
        nearest_support: Optional[float],
        nearest_resistance: Optional[float],
    ) -> dict:
        plan = {}

        if direction == "BUY":
            entry = round(price, 2)
            sl_buffer = (result.range_high - result.range_low) * 0.02
            sl = round(entry - sl_buffer, 2)
            if nearest_support:
                sl = min(sl, round(nearest_support - 1, 2))

            tp1_target = entry + (entry - sl) * 2
            tp2_target = entry + (entry - sl) * 3
            tp1 = round(min(tp1_target, nearest_resistance if nearest_resistance else tp1_target), 2)
            tp2 = round(min(tp2_target, result.range_high), 2)
            rr = round((tp1 - entry) / (entry - sl), 2) if (entry - sl) > 0 else 0

            plan = {
                "direction": "BUY",
                "entry": entry,
                "stop_loss": sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "risk_reward": rr,
                "reason": f"Bullish setup at support zone. "
                          f"H4: {result.h4_structure}, Monthly: {result.monthly_bias}",
            }
        elif direction == "SELL":
            entry = round(price, 2)
            sl_buffer = (result.range_high - result.range_low) * 0.02
            sl = round(entry + sl_buffer, 2)
            if nearest_resistance:
                sl = max(sl, round(nearest_resistance + 1, 2))

            tp1_target = entry - (sl - entry) * 2
            tp2_target = entry - (sl - entry) * 3
            tp1 = round(max(tp1_target, nearest_support if nearest_support else tp1_target), 2)
            tp2 = round(max(tp2_target, result.range_low), 2)
            rr = round((entry - tp1) / (sl - entry), 2) if (sl - entry) > 0 else 0

            plan = {
                "direction": "SELL",
                "entry": entry,
                "stop_loss": sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "risk_reward": rr,
                "reason": f"Bearish setup at resistance zone. "
                          f"H4: {result.h4_structure}, Monthly: {result.monthly_bias}",
            }

        return plan

    def scan_all_setups(self) -> list[AnalysisResult]:
        result = self.run_full_analysis()
        setups = []
        if result.final_decision != "WAIT":
            setups.append(result)
        return setups

    def scan_buy(self) -> list[AnalysisResult]:
        result = self.run_full_analysis()
        if result.final_decision == "BUY":
            return [result]
        return []

    def scan_sell(self) -> list[AnalysisResult]:
        result = self.run_full_analysis()
        if result.final_decision == "SELL":
            return [result]
        return []
