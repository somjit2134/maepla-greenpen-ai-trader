from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

from src.analysis.market_structure import MarketStructureDetector
from src.log_setup import get_logger

logger = get_logger()


@dataclass
class SRTier:
    zone_type: str = ""  # "SUPPORT" or "RESISTANCE"
    zone_high: float = 0.0
    zone_low: float = 0.0
    mid: float = 0.0
    strength: int = 0
    touches: int = 0


@dataclass
class SRResult:
    supports: list = field(default_factory=list)
    resistances: list = field(default_factory=list)
    all_zones: list = field(default_factory=list)
    current_support: Optional[SRTier] = None
    current_resistance: Optional[SRTier] = None


class SupportResistanceDetector:
    def __init__(self, cluster_distance: float = 5.0, min_touches: int = 2):
        self.cluster_distance = cluster_distance
        self.min_touches = min_touches
        self.structure_detector = MarketStructureDetector()

    def _cluster_levels(self, levels: list[float]) -> list[tuple[float, int]]:
        if not levels:
            return []

        sorted_levels = sorted(levels)
        clusters = []
        current_cluster = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            if abs(level - np.mean(current_cluster)) <= self.cluster_distance:
                current_cluster.append(level)
            else:
                avg = np.mean(current_cluster)
                clusters.append((round(avg, 2), len(current_cluster)))
                current_cluster = [level]

        if current_cluster:
            avg = np.mean(current_cluster)
            clusters.append((round(avg, 2), len(current_cluster)))

        return clusters

    def detect(self, df: pd.DataFrame) -> SRResult:
        if df.empty or len(df) < 30:
            return SRResult()

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        current_price = close[-1]

        result = SRResult()

        pivot_highs, pivot_lows = self.structure_detector._find_pivots(
            high, low, left=2, right=2
        )

        resistances_raw = [p[1] for p in pivot_highs]
        supports_raw = [p[1] for p in pivot_lows]

        resistance_clusters = self._cluster_levels(resistances_raw)
        support_clusters = self._cluster_levels(supports_raw)

        for level, touches in resistance_clusters:
            zone_width = self.cluster_distance * 1.5
            tier = SRTier(
                zone_type="RESISTANCE",
                zone_high=level + zone_width / 2,
                zone_low=level - zone_width / 2,
                mid=level,
                strength=min(touches, 10),
                touches=touches,
            )
            result.resistances.append(tier)
            result.all_zones.append(tier)

        for level, touches in support_clusters:
            zone_width = self.cluster_distance * 1.5
            tier = SRTier(
                zone_type="SUPPORT",
                zone_high=level + zone_width / 2,
                zone_low=level - zone_width / 2,
                mid=level,
                strength=min(touches, 10),
                touches=touches,
            )
            result.supports.append(tier)
            result.all_zones.append(tier)

        result.resistances.sort(key=lambda x: x.mid)
        result.supports.sort(key=lambda x: x.mid, reverse=True)

        for r in result.resistances:
            if r.mid > current_price:
                result.current_resistance = r
                break

        for s in result.supports:
            if s.mid < current_price:
                result.current_support = s
                break

        logger.debug(
            f"S/R: {len(result.supports)} supports, {len(result.resistances)} resistances"
        )
        return result
