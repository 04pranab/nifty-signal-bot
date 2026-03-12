"""
data_fetcher.py
───────────────
Responsible for fetching NIFTY OHLCV data from Yahoo Finance.
Includes retry logic and basic validation.
"""

import logging
import time
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TICKER   = "^NSEI"
INTERVAL = "5m"
PERIOD   = "1d"

# Retry configuration
MAX_RETRIES   = 3
RETRY_DELAY_S = 5  # seconds between retries


def fetch_ohlcv(
    ticker: str = TICKER,
    interval: str = INTERVAL,
    period: str = PERIOD,
    retries: int = MAX_RETRIES,
) -> Optional[pd.DataFrame]:
    """
    Download OHLCV data from Yahoo Finance with exponential-backoff retry.

    Returns a clean DataFrame or None if all attempts fail.
    """
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            logger.debug("Fetching %s  interval=%s  period=%s  (attempt %d/%d)",
                         ticker, interval, period, attempt, retries)

            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )

            if df is None or df.empty:
                raise ValueError("yfinance returned empty DataFrame")

            # Flatten MultiIndex columns (yfinance ≥ 0.2 quirk)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.dropna(inplace=True)

            if len(df) < 30:
                raise ValueError(f"Too few rows ({len(df)}) — market may be closed")

            logger.info("Fetched %d candles for %s", len(df), ticker)
            return df

        except Exception as exc:
            last_exc = exc
            wait = RETRY_DELAY_S * (2 ** (attempt - 1))  # exponential back-off
            logger.warning("Fetch attempt %d failed: %s — retrying in %ds", attempt, exc, wait)
            time.sleep(wait)

    logger.error("All %d fetch attempts failed. Last error: %s", retries, last_exc)
    return None
