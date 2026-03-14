“””
╔══════════════════════════════════════════════════════════════╗
║           CLAUDE AI TRADING BOT — by Joe                    ║
║  Scans stocks + options, uses Claude to decide, auto-trades ║
║                                                              ║
║  DEPLOY TO RAILWAY:                                          ║
║  1. Upload this file + requirements.txt                      ║
║  2. Add your keys in Railway → Variables tab                 ║
║  3. Set Start Command: python trading_bot.py                 ║
║  4. Deploy — runs 24/7 automatically                         ║
╚══════════════════════════════════════════════════════════════╝
“””

import os
import time
import json
import smtplib
import requests
import sys
from datetime import datetime, time as dtime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ================================================================

# KEYS — Read automatically from Railway Variables

# Add these in Railway → Your Service → Variables tab

# Never hardcoded, never exposed in the file

# ================================================================

CLAUDE_API_KEY    = os.environ.get(“CLAUDE_API_KEY”)
ALPACA_API_KEY    = os.environ.get(“ALPACA_API_KEY”)
ALPACA_SECRET_KEY = os.environ.get(“ALPACA_SECRET_KEY”)
POLYGON_API_KEY   = os.environ.get(“POLYGON_API_KEY”)
ALERT_EMAIL       = os.environ.get(“ALERT_EMAIL”)
ALERT_EMAIL_PASS  = os.environ.get(“ALERT_EMAIL_PASS”)

def check_keys():
“”“Verify all keys are present before starting.”””
required = {
“CLAUDE_API_KEY”:    CLAUDE_API_KEY,
“ALPACA_API_KEY”:    ALPACA_API_KEY,
“ALPACA_SECRET_KEY”: ALPACA_SECRET_KEY,
“POLYGON_API_KEY”:   POLYGON_API_KEY,
“ALERT_EMAIL”:       ALERT_EMAIL,
“ALERT_EMAIL_PASS”:  ALERT_EMAIL_PASS,
}
missing = [k for k, v in required.items() if not v]
if missing:
print(“╔══════════════════════════════════════════════╗”)
print(“║  ❌ MISSING API KEYS — Bot cannot start      ║”)
print(“╚══════════════════════════════════════════════╝”)
for key in missing:
print(f”  Missing: {key}”)
print(”\nFix: Railway → Your Service → Variables tab”)
print(“Add each missing key and redeploy.\n”)
sys.exit(1)
print(“✅ All API keys loaded successfully.”)

# ================================================================

# TRADING SETTINGS — Edit these anytime

# ================================================================

PAPER_TRADING     = True    # ← Set False when ready for real money
MAX_TRADE_SIZE    = 300     # Max dollars per trade
MIN_TRADE_SIZE    = 100     # Min dollars per trade
STOP_LOSS_PCT     = 0.03    # 3% stop loss
TAKE_PROFIT_PCT   = 0.08    # 8% take profit
SCAN_INTERVAL_SEC = 60      # Scan every 60 seconds

# ================================================================

# YOUR WATCHLIST

# ================================================================

WATCHLIST = [
“SPY”, “QQQ”,                          # Indexes
“NVDA”, “AAPL”, “TSLA”, “AMD”,         # Big Tech
“META”, “MSFT”, “GOOGL”, “AMZN”,       # More momentum
]

# ================================================================

# ALPACA ENDPOINTS

# ================================================================

BASE_URL = (
“https://paper-api.alpaca.markets”
if PAPER_TRADING else
“https://api.alpaca.markets”
)
DATA_URL = “https://data.alpaca.markets”

def alpaca_headers():
return {
“APCA-API-KEY-ID”:     ALPACA_API_KEY,
“APCA-API-SECRET-KEY”: ALPACA_SECRET_KEY,
“Content-Type”:        “application/json”
}

def claude_headers():
return {
“x-api-key”:         CLAUDE_API_KEY,
“anthropic-version”: “2023-06-01”,
“content-type”:      “application/json”
}

# ================================================================

# MARKET HOURS CHECK

# ================================================================

def market_is_open():
now = datetime.now()
if now.weekday() >= 5:
return False
return dtime(9, 30) <= now.time() <= dtime(16, 0)

# ================================================================

# STEP 1 — FETCH LIVE STOCK DATA

# ================================================================

def get_stock_snapshot(ticker):
try:
resp = requests.get(
f”{DATA_URL}/v2/stocks/{ticker}/snapshot”,
headers=alpaca_headers(),
timeout=10
)
data      = resp.json()
latest    = data.get(“latestTrade”, {})
daily_bar = data.get(“dailyBar”, {})
prev_bar  = data.get(“prevDailyBar”, {})

```
    price      = latest.get("p", 0)
    volume     = daily_bar.get("v", 0)
    prev_close = prev_bar.get("c", price)
    pct_change = ((price - prev_close) / prev_close * 100) if prev_close else 0
    avg_volume = prev_bar.get("v", volume)
    vol_ratio  = (volume / avg_volume) if avg_volume else 1

    return {
        "ticker":     ticker,
        "price":      round(price, 2),
        "pct_change": round(pct_change, 2),
        "volume":     int(volume),
        "vol_ratio":  round(vol_ratio, 2),
    }
except Exception as e:
    print(f"  [Data Error] {ticker}: {e}")
    return None
```

# ================================================================

# STEP 2 — FETCH OPTIONS CHAIN

# ================================================================

def get_options_snapshot(ticker):
try:
resp    = requests.get(
f”https://api.polygon.io/v3/snapshot/options/{ticker}”
f”?limit=10&apiKey={POLYGON_API_KEY}”,
timeout=10
)
results = resp.json().get(“results”, [])
summary = []
for opt in results[:5]:
details = opt.get(“details”, {})
greeks  = opt.get(“greeks”, {})
day     = opt.get(“day”, {})
summary.append({
“type”:          details.get(“contract_type”, “”),
“strike”:        details.get(“strike_price”, 0),
“expiry”:        details.get(“expiration_date”, “”),
“volume”:        day.get(“volume”, 0),
“open_interest”: opt.get(“open_interest”, 0),
“iv”:            round(opt.get(“implied_volatility”, 0) * 100, 1),
“delta”:         round(greeks.get(“delta”, 0), 3),
})
return summary
except Exception as e:
print(f”  [Options Error] {ticker}: {e}”)
return []

# ================================================================

# STEP 3 — ASK CLAUDE TO ANALYZE

# ================================================================

def ask_claude(market_data, options_data):
stock_report = “”
for s in market_data:
if s:
stock_report += (
f”  {s[‘ticker’]:<6} Price: ${s[‘price’]:<9} “
f”Change: {s[‘pct_change’]:+.1f}%  “
f”Volume: {s[‘vol_ratio’]}x avg\n”
)

```
options_report = ""
for ticker, opts in options_data.items():
    if opts:
        options_report += f"\n  {ticker} options:\n"
        for o in opts:
            options_report += (
                f"    {o['type'].upper()} ${o['strike']} "
                f"exp {o['expiry']} "
                f"Vol:{o['volume']} OI:{o['open_interest']} "
                f"IV:{o['iv']}% Delta:{o['delta']}\n"
            )

prompt = f"""You are an expert stock and options trader analyzing real-time market data.
```

Current time: {datetime.now().strftime(’%Y-%m-%d %H:%M:%S ET’)}

LIVE STOCK DATA:
{stock_report}

OPTIONS CHAIN DATA:
{options_report if options_report else “  No unusual options activity detected.”}

TRADING RULES:

- BUY_STOCK: price up 1.5%+, volume 1.5x+ average, strong momentum
- BUY_CALL: IV spike, unusual call sweep vs open interest, bullish price
- BUY_PUT: price down 1.5%+, high volume, bearish momentum
- WATCH: mixed signals, wait for confirmation
- SKIP: no clear signal, flat price, low volume
- Max position: $300 — only HIGH confidence trades execute automatically

## RESPOND IN THIS EXACT FORMAT for every ticker — no extra text:

TICKER: [symbol]
ACTION: [BUY_STOCK / BUY_CALL / BUY_PUT / WATCH / SKIP]
SHARES_OR_CONTRACTS: [number or 0]
REASON: [one sentence]
CONFIDENCE: [HIGH / MEDIUM / LOW]
—”””

```
try:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=claude_headers(),
        json={
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages":   [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    return resp.json()["content"][0]["text"]
except Exception as e:
    print(f"  [Claude Error]: {e}")
    return None
```

# ================================================================

# STEP 4 — PARSE CLAUDE’S DECISIONS

# ================================================================

def parse_decisions(text):
decisions = []
if not text:
return decisions
for block in text.strip().split(”—”):
block = block.strip()
if not block or “TICKER:” not in block:
continue
try:
lines = {}
for line in block.split(”\n”):
if “:” in line:
k, v = line.split(”:”, 1)
lines[k.strip()] = v.strip()
d = {
“ticker”:     lines.get(“TICKER”, “”),
“action”:     lines.get(“ACTION”, “SKIP”),
“quantity”:   int(lines.get(“SHARES_OR_CONTRACTS”, “0”)),
“reason”:     lines.get(“REASON”, “”),
“confidence”: lines.get(“CONFIDENCE”, “LOW”),
}
if d[“ticker”]:
decisions.append(d)
except Exception:
continue
return decisions

# ================================================================

# STEP 5 — PLACE ORDER ON ALPACA

# ================================================================

def place_order(ticker, qty, side=“buy”):
if qty <= 0:
return None
try:
resp = requests.post(
f”{BASE_URL}/v2/orders”,
headers=alpaca_headers(),
json={
“symbol”:        ticker,
“qty”:           str(qty),
“side”:          side,
“type”:          “market”,
“time_in_force”: “day”
},
timeout=10
)
return resp.json()
except Exception as e:
print(f”  [Order Error] {ticker}: {e}”)
return None

# ================================================================

# STEP 6 — SEND EMAIL ALERT

# ================================================================

def send_email(subject, body):
try:
msg            = MIMEMultipart()
msg[“From”]    = ALERT_EMAIL
msg[“To”]      = ALERT_EMAIL
msg[“Subject”] = subject
msg.attach(MIMEText(body, “plain”))
with smtplib.SMTP_SSL(“smtp.gmail.com”, 465) as server:
server.login(ALERT_EMAIL, ALERT_EMAIL_PASS)
server.send_message(msg)
print(f”  [Email ✅] Sent: {subject}”)
except Exception as e:
print(f”  [Email Error]: {e}”)

# ================================================================

# MAIN LOOP — Runs forever

# ================================================================

def run_bot():
check_keys()

```
mode = "PAPER 📄" if PAPER_TRADING else "LIVE 💰"
print(f"""
```

╔══════════════════════════════════════════════╗
║       CLAUDE TRADING BOT STARTED ✅          ║
║       Mode:     {mode:<28}║
║       Tickers:  {len(WATCHLIST)} stocks being watched          ║
║       Interval: every {SCAN_INTERVAL_SEC}s                     ║
╚══════════════════════════════════════════════╝
“””)

```
trades_today = []

while True:
    now = datetime.now().strftime("%H:%M:%S")

    # Wait if market is closed
    if not market_is_open():
        print(f"[{now}] Market closed — checking again in 5 min...")
        time.sleep(300)
        continue

    print(f"\n[{now}] ── SCANNING ─────────────────────────────────")

    # 1. Get stock data
    market_data = []
    for ticker in WATCHLIST:
        snap = get_stock_snapshot(ticker)
        if snap:
            market_data.append(snap)
            print(
                f"  {snap['ticker']:<6} "
                f"${snap['price']:<9} "
                f"{snap['pct_change']:+.1f}%  "
                f"vol:{snap['vol_ratio']}x"
            )

    # 2. Get options for hot tickers
    hot = [
        s["ticker"] for s in market_data
        if abs(s["pct_change"]) >= 1.5 or s["vol_ratio"] >= 1.5
    ]
    print(f"\n  🔥 Hot tickers: {hot if hot else 'none yet'}")
    options_data = {}
    for ticker in hot[:3]:
        options_data[ticker] = get_options_snapshot(ticker)

    # 3. Ask Claude
    print("\n  🧠 Sending to Claude for analysis...")
    response = ask_claude(market_data, options_data)
    if not response:
        print("  No response. Retrying next cycle.")
        time.sleep(SCAN_INTERVAL_SEC)
        continue

    print(f"\n  Claude says:\n{response}")

    # 4. Execute HIGH confidence trades
    for d in parse_decisions(response):
        action     = d["action"]
        ticker     = d["ticker"]
        qty        = d["quantity"]
        confidence = d["confidence"]
        reason     = d["reason"]

        if action in ("BUY_STOCK", "BUY_CALL", "BUY_PUT") \
           and confidence == "HIGH" \
           and qty > 0:

            print(f"\n  ✅ TRADE: {action} {qty}x {ticker}")
            result = place_order(ticker, qty)
            trades_today.append(d)

            send_email(
                subject=f"✅ {action}: {ticker} x{qty}  |  {'PAPER' if PAPER_TRADING else 'LIVE'}",
                body=f"""CLAUDE TRADING BOT ALERT
```

{’=’*45}
Time:        {datetime.now().strftime(’%Y-%m-%d %H:%M:%S ET’)}
Mode:        {‘📄 PAPER TRADE (fake money)’ if PAPER_TRADING else ‘💰 LIVE TRADE (real money)’}
Ticker:      {ticker}
Action:      {action}
Quantity:    {qty}
Confidence:  {confidence}

Claude’s Reasoning:
{reason}

Alpaca Order Result:
{json.dumps(result, indent=2) if result else ‘Order failed — check logs’}

Trades executed today: {len(trades_today)}
{’=’*45}
Bot running on Railway 24/7
“””
)

```
        elif action == "WATCH":
            print(f"  👀 WATCH: {ticker} — {reason}")
        else:
            print(f"  ⏭  SKIP: {ticker}")

    print(f"\n  ⏱  Next scan in {SCAN_INTERVAL_SEC}s...")
    time.sleep(SCAN_INTERVAL_SEC)
```

# ================================================================

if **name** == “**main**”:
run_bot()
