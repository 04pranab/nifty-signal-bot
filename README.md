# NIFTY Production Trading Signal Scanner

A production-grade Python scanner that monitors the NIFTY 50 index in real-time,
detects bullish call option setups using multiple technical confirmations,
and delivers rich alerts to a Zapier webhook.

---

## Architecture

```
scanner.py          ← orchestrator / main loop
  ├── data_fetcher.py       ← yfinance download + retry logic
  ├── indicator_engine.py   ← EMA 9/21, RSI 14, ATR 14, Volume MA 20
  ├── signal_detector.py    ← 5-condition bullish filter + risk estimation
  └── notification_sender.py ← Zapier POST + cooldown + CSV log
```

---

## Signal Logic

A **BULLISH_CALL_OPPORTUNITY** fires only when **ALL FIVE** conditions hold
on the last fully-completed 5-minute candle:

| # | Condition | Detail |
|---|-----------|--------|
| 1 | **EMA Crossover** | EMA 9 crosses above EMA 21 |
| 2 | **RSI Zone** | RSI 14 between 50 and 65 |
| 3 | **Price Breakout** | Close > previous candle High |
| 4 | **Volume Surge** | Volume > 20-period Volume MA |
| 5 | **ATR Expansion** | ATR 14 higher than previous ATR |

### Risk Estimation

| Field | Formula |
|-------|---------|
| Stop Loss | `price − ATR × 1.5` |
| Target | `price + ATR × 3.0` |
| Risk:Reward | `(target − price) / (price − stop_loss)` |

---

## Installation (local)

### Prerequisites
- Python 3.11+

### Steps

```bash
# 1. Clone / copy project files
git clone <your-repo>
cd nifty_scanner

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your Zapier webhook URL
export ZAPIER_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/ABC123/XYZ789/"

# 5. Run
python scanner.py
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZAPIER_WEBHOOK_URL` | placeholder | Your Zapier catch-hook URL (**required**) |
| `NIFTY_TICKER` | `^NSEI` | Yahoo Finance symbol |
| `POLL_INTERVAL` | `60` | Seconds between scans |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

---

## Zapier Webhook Setup

### Step 1 — Create the Zap
1. Go to [zapier.com](https://zapier.com) → **Create Zap**
2. **Trigger**: Search for **"Webhooks by Zapier"** → choose **Catch Hook**
3. Click **Continue** → copy the generated webhook URL

### Step 2 — Paste URL into scanner
```bash
export ZAPIER_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/1234567/abcdefg/"
```

### Step 3 — Choose your Action
After testing the trigger, connect any action:
- **Gmail / Outlook** → send an alert email
- **Slack** → post to a channel
- **Google Sheets** → log to spreadsheet
- **SMS** → Twilio / ClickSend
- **Telegram** → via Telegram Bot action

### Step 4 — Map the payload fields
The scanner sends these fields; map them to your action:

```
message          → full human-readable alert
price.current    → current NIFTY price
price.stop_loss  → suggested stop-loss
price.target     → suggested profit target
risk_reward      → risk:reward ratio
indicators.rsi   → RSI 14 value
indicators.atr   → ATR 14 value
timestamp        → candle timestamp
signal_type      → BULLISH_CALL_OPPORTUNITY
```

---

## Deploy on Railway

Railway gives you a free cloud server that runs the scanner 24/7.

### Step 1 — Push code to GitHub
```bash
git init
git add .
git commit -m "NIFTY scanner"
git remote add origin https://github.com/<you>/nifty-scanner.git
git push -u origin main
```

### Step 2 — Create Railway project
1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo** → select your repo
3. Railway auto-detects Python via `requirements.txt`

### Step 3 — Add environment variable
In your Railway project:
1. Click **Variables** tab
2. Add: `ZAPIER_WEBHOOK_URL` = your Zapier URL
3. Optionally add `LOG_LEVEL=DEBUG` while testing

### Step 4 — Verify deployment
- Railway will use `Procfile` → `worker: python scanner.py`
- Open the **Logs** tab to confirm the scanner is running
- You should see: `── Cycle start ──` every 60 seconds

### Railway pricing
- **Hobby plan** (free tier): 500 hours/month — enough for market-hours-only running
- **Pro plan** ($5/mo): unlimited always-on if you want 24/7

---

## Output Files

| File | Description |
|------|-------------|
| `nifty_signals.csv` | Every signal that fired (never overwritten) |
| `scanner.log` | Full structured runtime log |

### CSV columns
```
timestamp, ticker, signal_type, current_price, rsi, atr,
ema9, ema21, volume, volume_ma, stop_loss, target,
risk_reward, conditions_met
```

---

## Reliability Features

| Feature | Implementation |
|---------|---------------|
| Network retry | Exponential back-off, 3 attempts on fetch + 3 on webhook POST |
| Never crashes | Top-level `except Exception` in main loop catches everything |
| Signal cooldown | 15-minute window — duplicate alerts suppressed |
| Market hours guard | Skips cycles outside 09:15–15:30 IST Mon–Fri |
| Structured logging | `timestamp \| level \| module \| message` format to stdout + file |
| CSV logging | Signals always written to CSV even if webhook fails |

---

## Customization

Edit the constant blocks at the top of each module:

```python
# signal_detector.py
RSI_LOW               = 50.0   # RSI lower bound
RSI_HIGH              = 65.0   # RSI upper bound
ATR_STOP_MULTIPLIER   = 1.5    # stop = price - ATR * this
ATR_TARGET_MULTIPLIER = 3.0    # target = price + ATR * this

# notification_sender.py
COOLDOWN_MINUTES = 15   # minimum gap between repeated alerts

# scanner.py
POLL_INTERVAL = 60      # seconds between cycles
```

---

## Disclaimer

This tool is for **educational and informational purposes only**.
It does not constitute financial or investment advice.
Always do your own research before trading options.
