from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SetupScore:
    location: int = 0
    trend: int = 0
    grid: int = 0
    frame: int = 0
    price_action: int = 0
    total: int = 0
    max_score: int = 10
    grade: str = "NO TRADE"
    detail: str = ""


class SetupScorer:
    """
    Score each component 0-2, total /10.
    9-10: A+ Setup (High probability)
    7-8:  Good Setup
    5-6:  Watchlist
    <5:   NO TRADE
    """

    def score_location(
        self,
        current_price: float,
        range_high: float,
        range_low: float,
        direction: str,
        sr_support: Optional[float] = None,
        sr_resistance: Optional[float] = None,
    ) -> tuple[int, str]:
        """
        Upper range (near resistance) -> SELL area: 2 if confirming sell, 1 if near
        Lower range (near support) -> BUY area: 2 if confirming buy, 1 if near
        Middle range -> 0
        """
        if range_high == range_low:
            return 0, "Range too narrow"

        range_pct = (current_price - range_low) / (range_high - range_low)

        if sr_support and current_price <= sr_support * 1.01:
            if direction == "BUY":
                return 2, f"At support zone ${sr_support:.2f}"
            return 1, f"At support but direction is {direction}"

        if sr_resistance and current_price >= sr_resistance * 0.99:
            if direction == "SELL":
                return 2, f"At resistance zone ${sr_resistance:.2f}"
            return 1, f"At resistance but direction is {direction}"

        if range_pct < 0.25:
            if direction == "BUY":
                return 2, "Lower range (BUY zone)"
            return 0, "Lower range but bearish"
        elif range_pct > 0.75:
            if direction == "SELL":
                return 2, "Upper range (SELL zone)"
            return 0, "Upper range but bullish"
        else:
            return 0, "Middle range - avoid"

    def score_trend(self, monthly_bias: str, h4_structure: str, h1_direction: str, direction: str) -> tuple[int, str]:
        score = 0
        reasons = []

        if direction == "BUY":
            if monthly_bias == "BULLISH":
                score += 1
                reasons.append("Monthly bullish")
            if h4_structure == "BULLISH":
                score += 1
                reasons.append("H4 bullish")
            if h1_direction == "BULLISH":
                score += 1
                reasons.append("H1 bullish")
            if h4_structure == "BEARISH":
                score -= 1
                reasons.append("H4 bearish (conflict)")

        elif direction == "SELL":
            if monthly_bias == "BEARISH":
                score += 1
                reasons.append("Monthly bearish")
            if h4_structure == "BEARISH":
                score += 1
                reasons.append("H4 bearish")
            if h1_direction == "BEARISH":
                score += 1
                reasons.append("H1 bearish")
            if h4_structure == "BULLISH":
                score -= 1
                reasons.append("H4 bullish (conflict)")

        score = max(0, min(2, score))
        return score, ", ".join(reasons) if reasons else "No clear trend"

    def score_grid(self, grid_score: int) -> tuple[int, str]:
        g = min(grid_score, 4)
        if g >= 3:
            return 2, "Strong grid alignment"
        elif g >= 1:
            return 1, "Partial grid alignment"
        return 0, "No grid support"

    def score_frame(self, frame_result) -> tuple[int, str]:
        score = 2

        if frame_result.ath.caution:
            score -= 1

        if frame_result.thousand_point.position == "END":
            score -= 0
        elif frame_result.thousand_point.position == "BEGINNING":
            score += 0

        score = max(0, min(2, score))
        return score, f"ATH dist: {frame_result.ath.distance_percent:.1f}%, 1000pt: {frame_result.thousand_point.position}"

    def score_price_action(self, pa_result, expected_direction: str) -> tuple[int, str]:
        score = 0
        reasons = []

        if expected_direction == "BUY":
            if pa_result.bullish_confirmed:
                score += 2
                reasons.append("Bullish PA confirmed")
            elif pa_result.overall == "BULLISH":
                score += 1
                reasons.append("Mild bullish PA")
            else:
                reasons.append("No bullish confirmation")

        elif expected_direction == "SELL":
            if pa_result.bearish_confirmed:
                score += 2
                reasons.append("Bearish PA confirmed")
            elif pa_result.overall == "BEARISH":
                score += 1
                reasons.append("Mild bearish PA")
            else:
                reasons.append("No bearish confirmation")

        return min(score, 2), ", ".join(reasons)

    def score(
        self,
        direction: str,
        current_price: float,
        range_high: float,
        range_low: float,
        monthly_bias: str,
        h4_structure: str,
        h1_direction: str,
        grid_result,
        frame_result,
        pa_result,
        sr_support: Optional[float] = None,
        sr_resistance: Optional[float] = None,
    ) -> SetupScore:
        loc_score, loc_reason = self.score_location(
            current_price, range_high, range_low, direction, sr_support, sr_resistance
        )
        trend_score, trend_reason = self.score_trend(
            monthly_bias, h4_structure, h1_direction, direction
        )
        grid_score, grid_reason = self.score_grid(grid_result.score if hasattr(grid_result, 'score') else 0)

        if hasattr(frame_result, 'ath'):
            frame_score, frame_reason = self.score_frame(frame_result)
        else:
            frame_score, frame_reason = 0, "No frame data"

        pa_score, pa_reason = self.score_price_action(pa_result, direction)

        total = loc_score + trend_score + grid_score + frame_score + pa_score

        if total >= 9:
            grade = "A+ Setup (High probability)"
        elif total >= 7:
            grade = "Good Setup"
        elif total >= 5:
            grade = "Watchlist"
        else:
            grade = "NO TRADE"

        detail = (
            f"Location({loc_score}/2): {loc_reason} | "
            f"Trend({trend_score}/2): {trend_reason} | "
            f"Grid({grid_score}/2): {grid_reason} | "
            f"Frame({frame_score}/2): {frame_reason} | "
            f"PA({pa_score}/2): {pa_reason}"
        )

        return SetupScore(
            location=loc_score,
            trend=trend_score,
            grid=grid_score,
            frame=frame_score,
            price_action=pa_score,
            total=total,
            max_score=10,
            grade=grade,
            detail=detail,
        )
