"""Mae Pla framework: market structure, S/R, grid, frame, price action."""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.config import get
from src.logger import get_logger

logger = get_logger()


# ---------- Market Structure ----------

@dataclass
class StructureResult:
    condition: str = "RANGE"
    preference: str = "WAIT"
    detail: str = ""
    score: int = 0

    @property
    def bullish(self):
        return self.condition == "BULLISH"

    @property
    def bearish(self):
        return self.condition == "BEARISH"


def detect_structure(df: pd.DataFrame) -> StructureResult:
    if df.empty or len(df) < 20:
        return StructureResult(detail="insufficient data")

    high = df["high"].values
    low = df["low"].values
    n = len(high)

    pivots_h, pivots_l = [], []
    for i in range(3, n - 3):
        if all(high[i] >= high[i-j] for j in (1,2,3)) and all(high[i] >= high[i+j] for j in (1,2,3)):
            pivots_h.append((i, high[i]))
        if all(low[i] <= low[i-j] for j in (1,2,3)) and all(low[i] <= low[i+j] for j in (1,2,3)):
            pivots_l.append((i, low[i]))

    r = StructureResult()

    if len(pivots_h) < 2 or len(pivots_l) < 2:
        r.detail = "insufficient pivots"
        return r

    rh = [p[1] for p in pivots_h[-4:]]
    rl = [p[1] for p in pivots_l[-4:]]

    hh = sum(1 for i in range(1, len(rh)) if rh[i] > rh[i-1])
    lh = len(rh) - 1 - hh
    hl = sum(1 for i in range(1, len(rl)) if rl[i] > rl[i-1])
    ll = len(rl) - 1 - hl

    if hh + hl >= 3 and hh + hl > lh + ll:
        r.condition = "BULLISH"
        r.preference = "BUY"
        r.detail = f"HH:{hh} HL:{hl}"
        r.score = 2
    elif lh + ll >= 3 and lh + ll > hh + hl:
        r.condition = "BEARISH"
        r.preference = "SELL"
        r.detail = f"LH:{lh} LL:{ll}"
        r.score = 2
    else:
        r.score = 0
        r.detail = "sideways"

    return r


# ---------- Support / Resistance ----------

@dataclass
class SRLevel:
    level: float
    kind: str  # SUPPORT | RESISTANCE
    strength: int


@dataclass
class SRResult:
    supports: list = field(default_factory=list)
    resistances: list = field(default_factory=list)
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None


def detect_sr(df: pd.DataFrame, cluster_dist: float = 5.0) -> SRResult:
    r = SRResult()
    if df.empty or len(df) < 30:
        return r

    high, low = df["high"].values, df["low"].values
    n = len(high)

    ph, pl = [], []
    for i in range(2, n - 2):
        if all(high[i] >= high[i-j] for j in (1,2)) and all(high[i] >= high[i+j] for j in (1,2)):
            ph.append(high[i])
        if all(low[i] <= low[i-j] for j in (1,2)) and all(low[i] <= low[i+j] for j in (1,2)):
            pl.append(low[i])

    def cluster(arr):
        if not arr:
            return []
        arr = sorted(arr)
        clusters = []
        cur = [arr[0]]
        for v in arr[1:]:
            if abs(v - np.mean(cur)) <= cluster_dist:
                cur.append(v)
            else:
                clusters.append(round(np.mean(cur), 2))
                cur = [v]
        if cur:
            clusters.append(round(np.mean(cur), 2))
        return clusters

    for lvl in cluster(ph):
        r.resistances.append(SRLevel(lvl, "RESISTANCE", min(ph.count(lvl) if lvl in ph else 1, 10)))
    for lvl in cluster(pl):
        r.supports.append(SRLevel(lvl, "SUPPORT", min(pl.count(lvl) if lvl in pl else 1, 10)))

    price = df["close"].iloc[-1]
    for s in sorted(r.supports, key=lambda x: x.level, reverse=True):
        if s.level < price:
            r.nearest_support = s.level
            break
    for res in sorted(r.resistances, key=lambda x: x.level):
        if res.level > price:
            r.nearest_resistance = res.level
            break

    return r


# ---------- Grid 0/5 ----------

@dataclass
class GridResult:
    levels: list = field(default_factory=list)
    nearest: Optional[float] = None
    distance: float = 999
    score: int = 0


def analyze_grid(price: float, step: float = 50.0) -> GridResult:
    base = round(price / step) * step
    r = GridResult()
    best_dist = step

    for off in range(-5, 6):
        lvl = base + off * step
        dist = abs(price - lvl)
        r.levels.append(round(lvl, 2))
        if dist < best_dist:
            best_dist = dist
            r.nearest = lvl
            r.distance = dist

    if best_dist <= step * 0.3:
        r.score = 2
    elif best_dist <= step * 0.8:
        r.score = 1
    else:
        r.score = 0

    return r


# ---------- ATH Frame ----------

@dataclass
class ATHResult:
    distance_pct: float = 0.0
    is_near: bool = False
    score: int = 0


def analyze_ath(price: float) -> ATHResult:
    ath = get().symbol.at
    pct = (ath - price) / ath * 100 if ath > 0 else 0
    r = ATHResult(distance_pct=round(pct, 2), is_near=pct <= 5)
    r.score = 0 if r.is_near else 1
    return r


# ---------- 1000 Point Frame ----------

@dataclass
class FrameResult:
    position: str = "MIDDLE"
    progress: float = 50.0
    score: int = 0


def analyze_frame(df: pd.DataFrame | None, price: float | None = None) -> FrameResult:
    if df is not None and not df.empty:
        close = df["close"].values[-100:]
        swing_h = close.max()
        swing_l = close.min()
    elif price:
        swing_h, swing_l = price * 1.03, price * 0.97
    else:
        return FrameResult()

    rng = swing_h - swing_l
    pos = price or swing_l
    progress = ((pos - swing_l) / rng * 100) if rng > 0 else 50

    r = FrameResult(progress=round(progress, 1))
    if rng >= 1000:
        if progress < 20:
            r.position = "BEGINNING"
            r.score = 1
        elif progress > 80:
            r.position = "END"
            r.score = 0
        else:
            r.position = "MIDDLE"
            r.score = 1
    else:
        r.score = 1

    return r


# ---------- Price Action ----------

@dataclass
class Pattern:
    name: str = ""
    direction: str = ""
    strength: int = 0
    idx: int = -1


@dataclass
class PAResult:
    patterns: list = field(default_factory=list)
    bullish: bool = False
    bearish: bool = False
    overall: str = "NEUTRAL"
    score: int = 0


def analyze_pa(df: pd.DataFrame) -> PAResult:
    r = PAResult()
    if df.empty or len(df) < 5:
        return r

    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    last = len(c) - 1
    bullish_score = bearish_score = 0

    # Engulfing
    if last > 0:
        if c[last] > o[last] and c[last-1] < o[last-1] and c[last] > o[last-1] and o[last] < c[last-1]:
            r.patterns.append(Pattern("Bullish Engulfing", "BULLISH", 3, last))
            bullish_score += 3
        if c[last] < o[last] and c[last-1] > o[last-1] and c[last] < o[last-1] and o[last] > c[last-1]:
            r.patterns.append(Pattern("Bearish Engulfing", "BEARISH", 3, last))
            bearish_score += 3

    # Pin bars
    for i in range(max(0, last-5), last+1):
        body = abs(c[i] - o[i])
        total = h[i] - l[i]
        if total == 0:
            continue
        lw = min(o[i], c[i]) - l[i]
        uw = h[i] - max(o[i], c[i])
        if lw / total >= 0.5 and lw > uw * 2:
            r.patterns.append(Pattern("Bullish Pin", "BULLISH", 2, i))
            bullish_score += 2
        elif uw / total >= 0.5 and uw > lw * 2:
            r.patterns.append(Pattern("Bearish Pin", "BEARISH", 2, i))
            bearish_score += 2

    # Rejection wicks
    if h[last] - l[last] > 0:
        lw = min(o[last], c[last]) - l[last]
        uw = h[last] - max(o[last], c[last])
        if lw > abs(c[last]-o[last]) * 2 and lw > uw and c[last] > o[last]:
            bullish_score += 2
        if uw > abs(c[last]-o[last]) * 2 and uw > lw and c[last] < o[last]:
            bearish_score += 2

    # Consecutive closes
    if last > 1:
        if c[last] > o[last] and c[last-1] > o[last-1] and c[last] > c[last-1]:
            bullish_score += 1
        if c[last] < o[last] and c[last-1] < o[last-1] and c[last] < c[last-1]:
            bearish_score += 1

    r.bullish = bullish_score >= 3
    r.bearish = bearish_score >= 3

    if r.bullish and not r.bearish:
        r.overall = "BULLISH"
        r.score = 2
    elif r.bearish and not r.bullish:
        r.overall = "BEARISH"
        r.score = 2
    elif r.bullish and r.bearish:
        r.score = 1
        r.overall = "BULLISH" if bullish_score > bearish_score else "BEARISH"
    else:
        r.score = 0

    return r


# ---------- Full Market Analysis ----------

@dataclass
class MarketResult:
    time: str = ""
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0

    monthly: str = "RANGE"
    weekly: str = "RANGE"
    daily_zone: str = ""
    h4: str = ""
    h1: str = ""

    supports: list = field(default_factory=list)
    resistances: list = field(default_factory=list)

    grid_score: int = 0
    grid_nearest: Optional[float] = None

    ath_pct: float = 0.0
    thousand_pt: str = ""

    pa_bullish: bool = False
    pa_bearish: bool = False
    pa_overall: str = "NEUTRAL"
    pa_patterns: list = field(default_factory=list)

    range_high: float = 0.0
    range_low: float = 0.0
    range_position: str = "MIDDLE RANGE"

    # Scoring breakdown
    framework_score: int = 0
    trend_score: int = 0
    grid_score_val: int = 0
    ath_score: int = 0
    pa_score: int = 0
    rr_score: int = 0
    total_score: int = 0
    grade: str = "NO TRADE"
    decision: str = "WAIT"

    trade_plan: dict = field(default_factory=dict)


def run_analysis(data: dict[str, pd.DataFrame], bid: float, ask: float, spread: float) -> MarketResult:
    cfg = get()
    price = (bid + ask) / 2
    r = MarketResult(time=pd.Timestamp.now().isoformat(), price=round(price, 2),
                     bid=round(bid, 2), ask=round(ask, 2), spread=round(spread, 2))

    # Multi-timeframe
    if "MN1" in data:
        s = detect_structure(data["MN1"])
        r.monthly = s.condition
    if "W1" in data:
        s = detect_structure(data["W1"])
        r.weekly = s.condition
    if "D1" in data:
        s = detect_structure(data["D1"])
        sr = detect_sr(data["D1"])
        r.supports = [f"${s.level:.2f}" for s in sr.supports[:3]]
        r.resistances = [f"${r.level:.2f}" for r in sr.resistances[:3]]
        rh = data["D1"]["high"].max()
        rl = data["D1"]["low"].min()
        r.range_high = round(rh, 2)
        r.range_low = round(rl, 2)
        r.daily_zone = f"S: {', '.join(r.supports[:2])} R: {', '.join(r.resistances[:2])}"
    if "H4" in data:
        s = detect_structure(data["H4"])
        r.h4 = s.condition
    if "H1" in data:
        s = detect_structure(data["H1"])
        r.h1 = s.condition

    # Range position
    if r.range_high > r.range_low:
        pct = (price - r.range_low) / (r.range_high - r.range_low)
        if pct < 0.33:
            r.range_position = "LOWER RANGE"
        elif pct > 0.67:
            r.range_position = "UPPER RANGE"
        else:
            r.range_position = "MIDDLE RANGE"

    # Grid
    g = analyze_grid(price)
    r.grid_score = g.score
    r.grid_nearest = g.nearest

    # ATH
    a = analyze_ath(price)
    r.ath_pct = a.distance_pct

    # 1000-pt frame
    f = analyze_frame(data.get("H4"), price)
    r.thousand_pt = f.position

    # Price action
    h1_df = data.get("H1")
    m15_df = data.get("M15")
    h4_df = data.get("H4")
    pa_df = h1_df if h1_df is not None and not h1_df.empty else (
        m15_df if m15_df is not None and not m15_df.empty else h4_df
    )
    pa = analyze_pa(pa_df)
    r.pa_bullish = pa.bullish
    r.pa_bearish = pa.bearish
    r.pa_overall = pa.overall
    r.pa_patterns = [{"name": p.name, "dir": p.direction} for p in pa.patterns[:3]]

    # ---------- SCORING (10-pt Mae Pla) ----------

    # Framework (2pt): multi-timeframe alignment
    fw = 0
    bearish_tfs = sum(1 for x in [r.monthly, r.weekly, r.h4, r.h1] if x == "BEARISH")
    bullish_tfs = sum(1 for x in [r.monthly, r.weekly, r.h4, r.h1] if x == "BULLISH")
    if bearish_tfs >= 3:
        fw = 2
        r.decision = "SELL"
    elif bullish_tfs >= 3:
        fw = 2
        r.decision = "BUY"
    elif bearish_tfs == 2:
        fw = 1
        r.decision = "SELL"
    elif bullish_tfs == 2:
        fw = 1
        r.decision = "BUY"
    r.framework_score = fw

    # Trend (2pt): market structure alignment
    tr = 0
    h4_s = s.condition if "H4" in data else "RANGE"
    if r.decision == "BUY" and h4_s == "BULLISH":
        tr = 2
    elif r.decision == "BUY" and h4_s != "BEARISH":
        tr = 1
    elif r.decision == "SELL" and h4_s == "BEARISH":
        tr = 2
    elif r.decision == "SELL" and h4_s != "BULLISH":
        tr = 1
    r.trend_score = tr

    # Grid (2pt)
    r.grid_score_val = g.score

    # ATH (1pt)
    r.ath_score = a.score

    # Price Action (2pt)
    r.pa_score = pa.score

    # Risk Reward (1pt) — evaluated in trade plan, give 1 if decision is clear
    r.rr_score = 1 if r.decision != "WAIT" else 0

    total = fw + tr + r.grid_score_val + a.score + pa.score + r.rr_score
    r.total_score = min(total, 10)

    if r.total_score >= 9:
        r.grade = "A+ (EXECUTE)"
    elif r.total_score >= 7:
        r.grade = "B (ALERT)"
    elif r.total_score >= 5:
        r.grade = "C (WATCH)"
    else:
        r.grade = "D (TEST)"
        if r.decision == "WAIT":
            r.decision = "SELL" if price > (r.range_high + r.range_low) / 2 else "BUY"

    # Trade plan
    if r.decision in ("BUY", "SELL"):
        nearest_s = sr.nearest_support if "D1" in data and hasattr(sr := detect_sr(data["D1"]), "nearest_support") else None
        nearest_r = sr.nearest_resistance if "D1" in data else None

        if r.decision == "BUY":
            entry = round(price, 2)
            sl_dist = max((r.range_high - r.range_low) * 0.015, 10)
            sl = round(entry - sl_dist, 2)
            tp1 = round(entry + sl_dist * 2, 2)
            tp2 = round(entry + sl_dist * 3, 2)
            rr_val = round((tp1 - entry) / (entry - sl), 2)
            r.trade_plan = {"direction": "BUY", "entry": entry, "sl": sl,
                            "tp1": tp1, "tp2": tp2, "rr": rr_val,
                            "reason": f"Bullish: M={r.monthly} H4={r.h4} PA={r.pa_overall}"}
        else:
            entry = round(price, 2)
            sl_dist = max((r.range_high - r.range_low) * 0.015, 10)
            sl = round(entry + sl_dist, 2)
            tp1 = round(entry - sl_dist * 2, 2)
            tp2 = round(entry - sl_dist * 3, 2)
            rr_val = round((entry - tp1) / (sl - entry), 2)
            r.trade_plan = {"direction": "SELL", "entry": entry, "sl": sl,
                            "tp1": tp1, "tp2": tp2, "rr": rr_val,
                            "reason": f"Bearish: M={r.monthly} H4={r.h4} PA={r.pa_overall}"}

    return r
