"""
indicator_engine.py
────────────────────
Pure-pandas calculation of:
  • EMA 9 / EMA 21
  • RSI 14
  • ATR 14
  • Volume MA 20
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Individual indicator functions
# ─────────────────────────────────────────────

def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average (Wilder-style, adjust=False)."""
    return series.ewm(span=span, adjust=False).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI using Wilder's smoothing (EWM with alpha = 1/period).
    Identical to TradingView's default RSI.
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range using Wilder smoothing."""
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def calc_volume_ma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average of volume."""
    return series.rolling(window=period, min_periods=period).mean()


# ─────────────────────────────────────────────
#  Master function — attach all indicators
# ─────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a raw OHLCV DataFrame, attaches all indicator columns,
    and returns a clean copy (rows with NaN dropped).
    """
    df = df.copy()

    df["EMA9"]     = calc_ema(df["Close"], 9)
    df["EMA21"]    = calc_ema(df["Close"], 21)
    df["RSI14"]    = calc_rsi(df["Close"], 14)
    df["ATR14"]    = calc_atr(df, 14)
    df["VolMA20"]  = calc_volume_ma(df["Volume"], 20)

    # ATR change — positive means expanding volatility
    df["ATR_prev"] = df["ATR14"].shift(1)

    before = len(df)
    df.dropna(inplace=True)
    after  = len(df)
    logger.debug("Indicators computed. Dropped %d NaN rows (%d → %d)", before - after, before, after)

    return df
