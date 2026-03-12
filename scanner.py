"""
scanner.py
───────────
Production-grade NIFTY bullish call option scanner.

Orchestrates: data_fetcher → indicator_engine → signal_detector → notification_sender

Usage:
    python scanner.py

Environment variables:
    ZAPIER_WEBHOOK_URL   — Zapier catch-hook URL (required for alerts)
    NIFTY_TICKER         — override ticker symbol (default: ^NSEI)
    POLL_INTERVAL        — seconds between cycles (default: 60)
    LOG_LEVEL            — DEBUG / INFO / WARNING (default: INFO)
"""

import logging
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from data_fetcher       import fetch_ohlcv
from indicator_engine   import add_indicators
from signal_detector    import detect_signal
from notification_sender import CooldownTracker, dispatch_signal

# ─────────────────────────────────────────────
#  Configuration from environment
# ─────────────────────────────────────────────
ZAPIER_WEBHOOK_URL = os.getenv(
    "ZAPIER_WEBHOOK_URL",
    "https://hooks.zapier.com/hooks/catch/YOUR_HOOK_ID/YOUR_HOOK_KEY/",
)
TICKER         = os.getenv("NIFTY_TICKER",   "^NSEI")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "60"))
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO").upper()
IST            = ZoneInfo("Asia/Kolkata")

# ─────────────────────────────────────────────
#  Structured logging setup
# ─────────────────────────────────────────────
def configure_logging(level: str) -> None:
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
    )
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scanner.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level   = getattr(logging, level, logging.INFO),
        format  = fmt,
        datefmt = "%Y-%m-%d %H:%M:%S",
        handlers= handlers,
    )

logger = logging.getLogger("scanner.main")


# ─────────────────────────────────────────────
#  Market-hours guard (optional — remove to run 24 h)
# ─────────────────────────────────────────────
def is_market_hours() -> bool:
    """Return True during NIFTY regular hours: 09:15 – 15:30 IST, Mon–Fri."""
    now = datetime.now(IST)
    if now.weekday() >= 5:          # Saturday / Sunday
        return False
    open_h,  open_m  = 9,  15
    close_h, close_m = 15, 30
    minutes_now   = now.hour * 60 + now.minute
    minutes_open  = open_h  * 60 + open_m
    minutes_close = close_h * 60 + close_m
    return minutes_open <= minutes_now <= minutes_close


# ─────────────────────────────────────────────
#  One scanner cycle
# ─────────────────────────────────────────────
def run_cycle(cooldown: CooldownTracker) -> None:
    """Fetch → compute → detect → notify (one full pass)."""

    logger.info("── Cycle start ── %s", datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"))

    # 1. Fetch data
    df_raw = fetch_ohlcv(ticker=TICKER)
    if df_raw is None:
        logger.warning("Skipping cycle — data fetch returned None")
        return

    # 2. Compute indicators
    df = add_indicators(df_raw)
    if df.empty:
        logger.warning("Skipping cycle — DataFrame empty after indicator calculation")
        return

    # 3. Detect signal
    signal = detect_signal(df, ticker=TICKER)

    # 4. Dispatch if found
    if signal:
        dispatched = dispatch_signal(signal, ZAPIER_WEBHOOK_URL, cooldown)
        if dispatched:
            logger.info("Signal dispatched: %s", signal.to_dict())
        else:
            logger.info("Signal detected but suppressed (cooldown or webhook config)")
    else:
        logger.info("No signal this cycle.")

    logger.info("── Cycle end ──")


# ─────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────
def main() -> None:
    configure_logging(LOG_LEVEL)

    logger.info("=" * 65)
    logger.info("  NIFTY Production Scanner  v2.0")
    logger.info("  Ticker       : %s", TICKER)
    logger.info("  Poll interval: %d s", POLL_INTERVAL)
    logger.info("  Webhook URL  : %s…", ZAPIER_WEBHOOK_URL[:55])
    logger.info("=" * 65)

    cooldown = CooldownTracker(cooldown_minutes=15)
    cycle    = 0

    while True:
        cycle += 1
        cycle_start = time.monotonic()

        try:
            if not is_market_hours():
                logger.info("Market closed — sleeping until next poll.")
            else:
                run_cycle(cooldown)

        except KeyboardInterrupt:
            logger.info("Scanner stopped by user (KeyboardInterrupt).")
            sys.exit(0)

        except Exception as exc:          # absolute safety net — loop never dies
            logger.exception("Unhandled exception in cycle %d: %s", cycle, exc)

        elapsed   = time.monotonic() - cycle_start
        sleep_for = max(0.0, POLL_INTERVAL - elapsed)
        logger.debug("Cycle %d took %.2f s — sleeping %.2f s", cycle, elapsed, sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
