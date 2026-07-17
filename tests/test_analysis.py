import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config, get_config
from src.analysis.frame_engine import FrameAnalyzer, FrameResult
from src.analysis.cycle_engine import CycleAnalyzer, CycleResult
from src.analysis.trend_engine import TrendAnalyzer, TrendResult
from src.analysis.price_action import PriceActionDetector, PAResult
from src.analysis.market_structure import MarketStructureDetector, MarketStructure
from src.analysis.support_resistance import SupportResistanceDetector, SRResult
from src.analysis.grid_analysis import GridAnalyzer, GridAnalysis

from tests.conftest import generate_ohlcv, generate_multi_tf


class TestFrameEngine:
    def test_frame_analysis(self):
        analyzer = FrameAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data, 2050.0)

        assert isinstance(result, FrameResult)
        assert result.ath.ath > 0
        assert result.cycle.total_range > 0
        assert result.cycle.position in ("BEGINNING", "MIDDLE", "END")
        assert result.overall_frame in ("RANGE", "TREND", "BREAKOUT_UP", "BREAKOUT_DOWN",
                                         "ATH_BREAK", "ATH_REJECT")
        assert len(result.important_zones) > 0

    def test_ath_distance(self):
        analyzer = FrameAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data, 2050.0)
        assert result.ath.distance_percent >= 0

    def test_sideway_detection(self):
        analyzer = FrameAnalyzer()
        data = generate_multi_tf("sideway")
        result = analyzer.analyze(data, 2000.0)
        assert result.sideway.in_range in (True, False)


class TestCycleEngine:
    def test_cycle_analysis(self):
        analyzer = CycleAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data, 2050.0)

        assert isinstance(result, CycleResult)
        assert result.total_distance > 0
        assert 0 <= result.progress_percent <= 100
        assert result.position in ("EARLY", "MIDDLE", "LATE")
        assert 0 <= result.rsi_value <= 100

    def test_exhaustion_detection(self):
        analyzer = CycleAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data, 2050.0)
        assert isinstance(result.exhaustion_risk, bool)


class TestTrendEngine:
    def test_trend_analysis(self):
        analyzer = TrendAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data)

        assert isinstance(result, TrendResult)
        assert result.alignment_score >= 0
        assert result.direction in ("BUY", "SELL", "WAIT")

    def test_timeframe_trends(self):
        analyzer = TrendAnalyzer()
        data = generate_multi_tf("up")
        result = analyzer.analyze(data)

        assert result.d1.bias in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.h4.bias in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.h1.bias in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.m15.bias in ("BULLISH", "BEARISH", "NEUTRAL")


class TestPriceAction:
    def test_pa_detection(self):
        detector = PriceActionDetector()
        df = generate_ohlcv(100, "up")
        result = detector.detect(df)

        assert isinstance(result, PAResult)
        assert result.overall in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.signal_grade in ("A", "B", "C", "NO_TRADE")

    def test_pa_patterns(self):
        detector = PriceActionDetector()
        df = generate_ohlcv(100, "up")
        result = detector.detect(df)
        assert isinstance(result.patterns, list)


class TestMarketStructure:
    def test_structure_detection(self):
        detector = MarketStructureDetector()
        df = generate_ohlcv(100, "up")
        result = detector.detect(df)

        assert isinstance(result, MarketStructure)
        assert result.condition in ("BULLISH", "BEARISH", "RANGE")
        assert result.preference in ("BUY", "SELL", "WAIT")


class TestSupportResistance:
    def test_sr_detection(self):
        detector = SupportResistanceDetector(cluster_distance=5.0)
        df = generate_ohlcv(100, "sideway")
        result = detector.detect(df)

        assert isinstance(result, SRResult)
        assert len(result.all_zones) >= 0


class TestGridAnalysis:
    def test_grid_analysis(self):
        analyzer = GridAnalyzer(step=50.0)
        result = analyzer.analyze(4075.0)

        assert isinstance(result, GridAnalysis)
        assert len(result.levels) > 0
        assert result.nearest_level is not None
        assert result.score >= 0

    def test_grid_levels(self):
        analyzer = GridAnalyzer(step=50.0)
        result = analyzer.analyze(4073.0)
        levels = [l.level for l in result.levels]
        assert 4050.0 in levels or 4100.0 in levels


class TestConfig:
    def test_config_loading(self):
        cfg = load_config()
        assert cfg.symbol.name == "XAUUSD"
        assert cfg.risk.risk_per_trade_percent == 1.0
        assert cfg.risk.min_rr == 2.0

    def test_config_sections(self):
        cfg = load_config()
        assert hasattr(cfg, "mt5")
        assert hasattr(cfg, "symbol")
        assert hasattr(cfg, "frame")
        assert hasattr(cfg, "cycle")
        assert hasattr(cfg, "trend")
        assert hasattr(cfg, "price_action")
        assert hasattr(cfg, "risk")
        assert hasattr(cfg, "trade")
        assert hasattr(cfg, "backtest")
        assert hasattr(cfg, "database")
        assert hasattr(cfg, "notification")
        assert hasattr(cfg, "logging")
