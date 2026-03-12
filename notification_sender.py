"""
notification_sender.py
───────────────────────
Sends signal alerts to a Zapier webhook (POST JSON) with:
  • configurable retry / back-off
  • deduplication / cooldown window
  • CSV signal log
"""

import csv
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from signal_detector import Signal

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
COOLDOWN_MINUTES = 15          # minimum gap between repeated signals
MAX_RETRIES      = 3
RETRY_BASE_DELAY = 2           # seconds (doubles each retry)
REQUEST_TIMEOUT  = 10          # seconds
CSV_LOG_PATH     = Path("nifty_signals.csv")

CSV_FIELDS = [
    "timestamp", "ticker", "signal_type",
    "current_price", "rsi", "atr",
    "ema9", "ema21", "volume", "volume_ma",
    "stop_loss", "target", "risk_reward",
    "conditions_met",
]


# ─────────────────────────────────────────────
#  Cooldown tracker
# ─────────────────────────────────────────────

class CooldownTracker:
    """Prevents duplicate webhook calls within COOLDOWN_MINUTES."""

    def __init__(self, cooldown_minutes: int = COOLDOWN_MINUTES):
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._last_sent: Optional[datetime] = None

    def can_send(self) -> bool:
        if self._last_sent is None:
            return True
        return datetime.utcnow() - self._last_sent >= self._cooldown

    def mark_sent(self) -> None:
        self._last_sent = datetime.utcnow()

    def seconds_until_ready(self) -> float:
        if self._last_sent is None:
            return 0.0
        elapsed = (datetime.utcnow() - self._last_sent).total_seconds()
        return max(0.0, self._cooldown.total_seconds() - elapsed)


# ─────────────────────────────────────────────
#  Webhook sender
# ─────────────────────────────────────────────

def _build_payload(signal: Signal) -> dict:
    """Construct the JSON payload for the Zapier webhook."""
    return {
        "source":       "NIFTY Scanner (Production)",
        "signal_type":  signal.signal_type,
        "ticker":       signal.ticker,
        "timestamp":    signal.timestamp,
        "price": {
            "current":    signal.current_price,
            "stop_loss":  signal.stop_loss,
            "target":     signal.target,
        },
        "risk_reward": signal.risk_reward,
        "indicators": {
            "rsi":       signal.rsi,
            "atr":       signal.atr,
            "ema9":      signal.ema9,
            "ema21":     signal.ema21,
            "volume":    signal.volume,
            "volume_ma": signal.volume_ma,
        },
        "conditions_met": signal.conditions_met,
        "message": (
            f"🚀 NIFTY Bullish Signal | {signal.timestamp} | "
            f"Price: ₹{signal.current_price:,.2f} | "
            f"RSI: {signal.rsi} | ATR: {signal.atr} | "
            f"SL: ₹{signal.stop_loss:,.2f} | Target: ₹{signal.target:,.2f} | "
            f"R:R = {signal.risk_reward}"
        ),
    }


def send_webhook(
    signal: Signal,
    webhook_url: str,
    retries: int = MAX_RETRIES,
) -> bool:
    """
    POST signal data to the Zapier webhook with exponential back-off.
    Returns True on success, False on total failure.
    """
    if not webhook_url or "YOUR_HOOK" in webhook_url:
        logger.warning("Webhook URL not configured — skipping POST.")
        return False

    payload    = _build_payload(signal)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                webhook_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info("✅ Webhook delivered (HTTP %d, attempt %d)", resp.status_code, attempt)
            return True

        except requests.exceptions.RequestException as exc:
            last_error = exc
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Webhook attempt %d/%d failed: %s — retrying in %ds",
                attempt, retries, exc, wait,
            )
            if attempt < retries:
                time.sleep(wait)

    logger.error("All webhook attempts failed. Last error: %s", last_error)
    return False


# ─────────────────────────────────────────────
#  CSV logger
# ─────────────────────────────────────────────

def log_signal_csv(signal: Signal, path: Path = CSV_LOG_PATH) -> None:
    """Append the signal as a row in the CSV log."""
    write_header = not path.exists()
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerow(signal.to_dict())
        logger.info("Signal appended to %s", path)
    except OSError as exc:
        logger.error("CSV write error: %s", exc)


# ─────────────────────────────────────────────
#  High-level dispatch (webhook + CSV in one call)
# ─────────────────────────────────────────────

def dispatch_signal(
    signal: Signal,
    webhook_url: str,
    cooldown: CooldownTracker,
) -> bool:
    """
    Send webhook + log CSV, respecting the cooldown window.
    Returns True if the signal was actually dispatched.
    """
    if not cooldown.can_send():
        wait = cooldown.seconds_until_ready()
        logger.info(
            "Signal suppressed by cooldown — next allowed in %.0f s", wait
        )
        return False

    # Always log to CSV (even if webhook fails)
    log_signal_csv(signal)

    success = send_webhook(signal, webhook_url)
    if success:
        cooldown.mark_sent()

    return success
