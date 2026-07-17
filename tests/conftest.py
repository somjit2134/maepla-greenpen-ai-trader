import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_ohlcv(n=200, trend="up", base_price=2000.0):
    np.random.seed(42)
    times = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1h")
    noise = np.random.randn(n) * 5

    if trend == "up":
        prices = base_price + np.linspace(0, 100, n) + noise.cumsum()
    elif trend == "down":
        prices = base_price + np.linspace(0, -100, n) + noise.cumsum()
    else:
        prices = base_price + noise.cumsum() * 0.5

    df = pd.DataFrame({
        "time": times,
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 5 + 3,
        "low": prices - np.abs(np.random.randn(n)) * 5 - 3,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
    })
    return df


def generate_multi_tf(trend="up"):
    return {
        "D1": generate_ohlcv(100, trend, 2000),
        "H4": generate_ohlcv(200, trend, 2000),
        "H1": generate_ohlcv(300, trend, 2000),
        "M15": generate_ohlcv(400, trend, 2000),
    }
