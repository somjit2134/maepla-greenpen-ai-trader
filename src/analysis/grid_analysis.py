from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class GridLevel:
    level: float = 0.0
    distance: float = 0.0
    has_reaction: bool = False
    reaction_type: str = ""  # "SUPPORT" or "RESISTANCE"
    score: int = 0


@dataclass
class GridAnalysis:
    levels: list = field(default_factory=list)
    nearest_level: Optional[GridLevel] = None
    score: int = 0
    detail: str = ""


class GridAnalyzer:
    """Grid 0/5 Analysis - psychological price levels at 50-point intervals."""

    def __init__(self, step: float = 50.0):
        self.step = step

    def analyze(self, current_price: float, df: Optional[pd.DataFrame] = None) -> GridAnalysis:
        base = round(current_price / self.step) * self.step
        levels = []

        for offset in range(-5, 6):
            lvl = base + (offset * self.step)
            grid = GridLevel(level=lvl, distance=abs(current_price - lvl))

            if df is not None and not df.empty:
                high = df["high"].values
                low = df["low"].values
                close = df["close"].values
                touch_buffer = self.step * 0.3

                for i in range(len(close)):
                    if low[i] <= lvl <= high[i]:
                        grid.has_reaction = True
                        if i == len(close) - 1 or i == len(close) - 2:
                            if close[i] > lvl:
                                grid.reaction_type = "SUPPORT"
                            else:
                                grid.reaction_type = "RESISTANCE"
                        break

            distance_score = 0
            if grid.distance <= self.step * 0.3:
                distance_score = 2
            elif grid.distance <= self.step * 0.8:
                distance_score = 1

            reaction_score = 0
            if grid.has_reaction:
                reaction_score = 2
                if grid.reaction_type:
                    reaction_score = 1

            grid.score = distance_score + reaction_score
            levels.append(grid)

        levels.sort(key=lambda x: x.distance)
        nearest = levels[0] if levels else None

        total_score = sum(min(l.score, 2) for l in levels[:3])

        result = GridAnalysis(
            levels=levels,
            nearest_level=nearest,
            score=total_score,
            detail=f"Nearest grid: {nearest.level if nearest else 'N/A'} (dist: {nearest.distance:.2f})" if nearest else "No grid levels",
        )

        return result
