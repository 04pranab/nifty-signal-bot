"""
signal_detector.py
───────────────────
Evaluates the last two completed candles against the bullish-call criteria
and computes stop-loss / target / risk-reward when a signal fires.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Tunable signal parameters
# ─────────────────────────────────────────────
RSI_LOW  = 50.0
RSI_HIGH = 65.0
ATR_STOP_MULTIPLIER   = 1.5   # stop-loss = price - ATR * multiplier
ATR_TARGET_MULTIPLIER = 3.0   # target    = price + ATR * multiplier


# ─────────────────────────────────────────────
#  Signal data container
# ─────────────────────────────────────────────

@dataclass
class Signal:
    timestamp:      str
    ticker:         str
    signal_type:    str
    current_price:  float
    rsi:            float
    atr:            float
    ema9:           float
    ema21:          float
    volume:         float
    volume_ma:      float
    stop_loss:      float
    target:         float
    risk_reward:    float

    # human-readable breakdown of why the signal fired
    conditions_met: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────
#  Detection logic
# ─────────────────────────────────────────────

def detect_signal(df: pd.DataFrame, ticker: str) -> Optional[Signal]:
    """
    Evaluate the last two *completed* candles (df[-3] and df[-2];
    df[-1] is still forming).

    Bullish conditions (ALL must be true):
      1. EMA9 crosses above EMA21
      2. RSI between RSI_LOW and RSI_HIGH
      3. Current close > previous candle high   (price breakout)
      4. Current volume > VolMA20               (volume confirmation)
      5. ATR14 increasing                        (expanding volatility)

    Returns a Signal or None.
    """
    MIN_ROWS = 3
    if len(df) < MIN_ROWS:
        logger.debug("Not enough rows for detection (%d < %d)", len(df), MIN_ROWS)
        return None

    prev = df.iloc[-3]   # two candles ago (for EMA cross detection)
    curr = df.iloc[-2]   # last *completed* candle

    # ── individual condition checks ──────────────────────────────────────

    # 1. EMA crossover
    ema_cross = bool(
        (prev["EMA9"] < prev["EMA21"]) and
        (curr["EMA9"] >= curr["EMA21"])
    )

    # 2. RSI in zone
    rsi_val = float(curr["RSI14"])
    rsi_ok  = RSI_LOW <= rsi_val <= RSI_HIGH

    # 3. Price breakout
    price_break = bool(curr["Close"] > prev["High"])

    # 4. Volume surge
    vol     = float(curr["Volume"])
    vol_ma  = float(curr["VolMA20"])
    vol_ok  = bool(vol > vol_ma)

    # 5. ATR expanding
    atr_now  = float(curr["ATR14"])
    atr_prev = float(curr["ATR_prev"]) if not pd.isna(curr["ATR_prev"]) else atr_now
    atr_up   = bool(atr_now > atr_prev)

    # ── log individual results ────────────────────────────────────────────
    logger.debug(
        "Conditions | EMA_cross=%s | RSI=%.2f(%s) | PriceBreak=%s | "
        "Vol=%s | ATR_up=%s",
        ema_cross, rsi_val, rsi_ok, price_break, vol_ok, atr_up,
    )

    all_conditions = ema_cross and rsi_ok and price_break and vol_ok and atr_up

    if not all_conditions:
        return None

    # ── risk estimation ───────────────────────────────────────────────────
    price      = round(float(curr["Close"]), 2)
    stop_loss  = round(price - ATR_STOP_MULTIPLIER   * atr_now, 2)
    target     = round(price + ATR_TARGET_MULTIPLIER * atr_now, 2)
    risk       = price - stop_loss
    reward     = target - price
    rr_ratio   = round(reward / risk, 2) if risk > 0 else 0.0

    # ── candle timestamp ──────────────────────────────────────────────────
    ts = curr.name
    if hasattr(ts, "strftime"):
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    else:
        ts_str = str(ts)

    conditions_str = (
        f"EMA_cross=True | RSI={rsi_val:.2f} | "
        f"PriceBreak=True | VolSurge=True | ATR_expanding=True"
    )

    signal = Signal(
        timestamp      = ts_str,
        ticker         = ticker,
        signal_type    = "BULLISH_CALL_OPPORTUNITY",
        current_price  = price,
        rsi            = round(rsi_val, 2),
        atr            = round(atr_now, 2),
        ema9           = round(float(curr["EMA9"]),  2),
        ema21          = round(float(curr["EMA21"]), 2),
        volume         = round(vol,    0),
        volume_ma      = round(vol_ma, 0),
        stop_loss      = stop_loss,
        target         = target,
        risk_reward    = rr_ratio,
        conditions_met = conditions_str,
    )

    logger.info(
        "🔔 SIGNAL DETECTED | Price=%.2f | SL=%.2f | Target=%.2f | R:R=%.2f",
        price, stop_loss, target, rr_ratio,
    )
    return signal
