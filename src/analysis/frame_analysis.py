from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class ATHFrame:
    ath: float = 0.0
    current_price: float = 0.0
    distance_percent: float = 0.0
    is_near_ath: bool = False
    caution: bool = False
    detail: str = ""


@dataclass
class ThousandPointFrame:
    cycle_start: float = 0.0
    cycle_end: float = 0.0
    cycle_progress: float = 0.0
    position: str = ""  # "BEGINNING", "MIDDLE", "END"
    detail: str = ""


@dataclass
class FrameResult:
    ath: ATHFrame
    thousand_point: ThousandPointFrame
    score: int = 0


class FrameAnalyzer:
    """ATH Frame and 1000 Point Frame analysis."""

    def __init__(self, ath: float):
        self.ath = ath

    def analyze_ath(self, current_price: float) -> ATHFrame:
        distance = self.ath - current_price
        distance_percent = (distance / self.ath) * 100 if self.ath > 0 else 0

        is_near = distance_percent <= 5.0
        caution = is_near and distance > 0

        return ATHFrame(
            ath=self.ath,
            current_price=current_price,
            distance_percent=round(distance_percent, 2),
            is_near_ath=is_near,
            caution=caution,
            detail=(
                f"ATH: ${self.ath:.2f}, Current: ${current_price:.2f}, "
                f"Distance: {distance_percent:.2f}% {'NEAR ATH - CAUTION' if caution else ''}"
            ),
        )

    def analyze_thousand_point(self, df: Optional[pd.DataFrame] = None, current_price: Optional[float] = None) -> ThousandPointFrame:
        if df is not None and not df.empty:
            close = df["close"].values
            swing_high = np.max(close[-100:])
            swing_low = np.min(close[-100:])
        elif current_price is not None:
            swing_high = max(current_price * 1.02, current_price + 20)
            swing_low = min(current_price * 0.98, current_price - 20)
        else:
            return ThousandPointFrame(detail="Insufficient data")

        total_range = swing_high - swing_low
        current_pos = current_price or swing_low

        if total_range >= 1000:
            progress = ((current_pos - swing_low) / total_range) * 100

            if progress < 20:
                position = "BEGINNING"
                detail = f"Early in 1000pt cycle ({progress:.0f}%)"
            elif progress < 70:
                position = "MIDDLE"
                detail = f"Middle of 1000pt cycle ({progress:.0f}%)"
            else:
                position = "END"
                detail = f"Late in 1000pt cycle ({progress:.0f}%) - expect pullback/reversal"
        else:
            position = "MIDDLE"
            progress = 50
            detail = f"Range {total_range:.0f}pts - below 1000pt threshold"

        return ThousandPointFrame(
            cycle_start=swing_low,
            cycle_end=swing_high,
            cycle_progress=round(progress, 1),
            position=position,
            detail=detail,
        )

    def analyze(self, current_price: float, df: Optional[pd.DataFrame] = None) -> FrameResult:
        ath_frame = self.analyze_ath(current_price)
        thousand = self.analyze_thousand_point(df, current_price)

        score = 2
        if ath_frame.caution:
            score -= 1
        if thousand.position == "END":
            score -= 1
        score = max(0, score)

        return FrameResult(ath=ath_frame, thousand_point=thousand, score=score)
