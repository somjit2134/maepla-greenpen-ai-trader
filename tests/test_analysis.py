"""Tests for analysis engine components."""

import pytest
import pandas as pd
import numpy as np

from src.analysis.market_structure import MarketStructureDetector
from src.analysis.support_resistance import SupportResistanceDetector
from src.analysis.grid_analysis import GridAnalyzer
from src.analysis.frame_analysis import FrameAnalyzer
from src.analysis.price_action import PriceActionDetector
from src.analysis.setup_scorer import SetupScorer
from src.config_loader import load_config


@pytest.fixture
def sample_data():
    np.random.seed(42)
    n = 100
    prices = 4000 + np.cumsum(np.random.randn(n) * 5)
    return pd.DataFrame({
        "time": pd.date_range("2026-07-01", periods=n, freq="h"),
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 8 + 3,
        "low": prices - np.abs(np.random.randn(n)) * 8 - 3,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
        "spread": np.random.randint(10, 50, n),
        "real_volume": np.random.randint(1000, 50000, n),
    })


@pytest.fixture
def bullish_data():
    np.random.seed(42)
    n = 100
    base = 4000
    prices = base + np.linspace(0, 200, n) + np.random.randn(n) * 5
    return pd.DataFrame({
        "time": pd.date_range("2026-07-01", periods=n, freq="h"),
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 8 + 5,
        "low": prices - np.abs(np.random.randn(n)) * 8 - 5,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
        "spread": np.random.randint(10, 50, n),
        "real_volume": np.random.randint(1000, 50000, n),
    })


def test_market_structure_detection(sample_data):
    detector = MarketStructureDetector()
    structure = detector.detect(sample_data)
    assert structure.condition in ("BULLISH", "BEARISH", "RANGE")
    assert structure.preference in ("BUY", "SELL", "WAIT")
    assert structure.detail != ""


def test_bullish_structure(bullish_data):
    detector = MarketStructureDetector()
    structure = detector.detect(bullish_data)
    assert structure.condition == "BULLISH"


def test_support_resistance(sample_data):
    detector = SupportResistanceDetector(cluster_distance=5.0)
    result = detector.detect(sample_data)
    assert len(result.all_zones) > 0
    assert len(result.supports) + len(result.resistances) > 0


def test_grid_analysis():
    analyzer = GridAnalyzer(step=50.0)
    result = analyzer.analyze(4075.0)
    assert len(result.levels) > 0
    assert result.nearest_level is not None
    assert result.score >= 0


def test_grid_levels():
    analyzer = GridAnalyzer(step=50.0)
    result = analyzer.analyze(4073.0)
    levels = [l.level for l in result.levels]
    assert 4050.0 in levels or 4100.0 in levels


def test_ath_frame():
    analyzer = FrameAnalyzer(ath=5603.0)
    result = analyzer.analyze_ath(4073.0)
    assert result.ath == 5603.0
    assert result.distance_percent > 0
    assert not result.is_near_ath


def test_ath_frame_near():
    analyzer = FrameAnalyzer(ath=5603.0)
    result = analyzer.analyze_ath(5500.0)
    assert result.is_near_ath
    assert result.caution


def test_thousand_point_frame():
    analyzer = FrameAnalyzer(ath=5603.0)
    result = analyzer.analyze_thousand_point(current_price=4073.0)
    assert result.position in ("BEGINNING", "MIDDLE", "END")


def test_price_action(sample_data):
    detector = PriceActionDetector()
    result = detector.detect(sample_data)
    assert result.overall in ("BULLISH", "BEARISH", "NEUTRAL")
    assert result.patterns is not None


def test_price_action_patterns(bullish_data):
    detector = PriceActionDetector()
    result = detector.detect(bullish_data)
    assert result.bullish_confirmed or result.overall == "NEUTRAL"


def test_setup_scorer():
    scorer = SetupScorer()

    class MockGridResult:
        score = 3

    class MockFrameResult:
        class ATH:
            distance_percent = 27.0
            caution = False

        class TP:
            position = "MIDDLE"

        ath = ATH()
        thousand_point = TP()

    class MockPAResult:
        bullish_confirmed = False
        bearish_confirmed = True
        overall = "BEARISH"
        patterns = []

    score = scorer.score(
        direction="SELL",
        current_price=4073.0,
        range_high=4200.0,
        range_low=3960.0,
        monthly_bias="BEARISH",
        h4_structure="BEARISH",
        h1_direction="BEARISH",
        grid_result=MockGridResult(),
        frame_result=MockFrameResult(),
        pa_result=MockPAResult(),
        sr_support=4000.0,
        sr_resistance=4100.0,
    )

    assert 0 <= score.total <= 10
    assert score.grade != ""


def test_setup_scorer_buy():
    scorer = SetupScorer()

    class MockGridResult:
        score = 3

    class MockFrameResult:
        class ATH:
            distance_percent = 27.0
            caution = False

        class TP:
            position = "BEGINNING"

        ath = ATH()
        thousand_point = TP()

    class MockPAResult:
        bullish_confirmed = True
        bearish_confirmed = False
        overall = "BULLISH"
        patterns = []

    score = scorer.score(
        direction="BUY",
        current_price=3980.0,
        range_high=4200.0,
        range_low=3960.0,
        monthly_bias="BULLISH",
        h4_structure="BULLISH",
        h1_direction="BULLISH",
        grid_result=MockGridResult(),
        frame_result=MockFrameResult(),
        pa_result=MockPAResult(),
        sr_support=3960.0,
        sr_resistance=4100.0,
    )

    assert score.total >= 7
    assert "A+" in score.grade or "Good" in score.grade


def test_config_loading():
    cfg = load_config()
    assert cfg.symbol.name == "XAUUSD"
    assert cfg.symbol.at == 5603.0
    assert cfg.risk.min_rr == 2.0
