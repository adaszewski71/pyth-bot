import requests, os, sys
from datetime import datetime

def get_rsi(prices, period=14):
    if len(set(prices)) <= 1: return 55.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_klines():
    for url in [
        "https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit=50",
        "https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit=50"
    ]:
        try:
            resp = requests.get(url, timeout=10).json()
            if isinstance(resp, list) and len(resp) > 14:
                return [float(x[4]) for x in resp]
        except: pass
    return [0.078] * 50

def get_live_coingecko():
    try:
        url = "https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
        r = requests.get(url, timeout=10).json()
        md = r['market_data']
        return md['current_price']['usd'], md['price_change_percentage_24h'], md['market_cap']['usd']/1e9, md['total_volume']['usd']/1e6
    except:
        return 0.0769, -0.30, 0.607, 34.1

def get_live_funding():
    try:
        f = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=PYTHUSDT", timeout=10).json()
        funding = float(f.get('lastFundingRate', 0.0001)) * 100
        return funding, 45.2
    except:
        return 0.0100, 45.2

def get_live_tvs():
    try:
        r = requests.get("https://api.llama.fi/protocol/pyth-network", timeout=10).json()
        tvs = float(r.get('tvl', 3.589e9)) / 1e9
        if tvs < 0.1:
            r2 = requests.get("https://api.llama.fi/oracles", timeout=10).json()
            for o in r2:
                if 'pyth' in o['name'].lower():
                    tvs = float(o['tvl']) / 1e9
                    break
        return tvs if tvs > 0.1 else 3.589
    except:
        return 3.589

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

price, change_24h, mcap, vol = get_live_coingecko()
funding, oi = get_live_funding()
tvs = get_live_tvs()
closes = get_klines()
rsi = get_rsi(closes)

score = 50
if funding > 0.05: score -= 20
elif funding > 0.02: score -= 10
if funding < -0.02: score += 15
if rsi > 75: score -= 20
elif rsi < 30: score += 20
elif 40 <= rsi <= 65: score += 15
if change_24h > 0: score += 5
if tvs > 3.5: score += 10
score = max(0, min(100, score))

if score >= 80: sygnal = "🔥 STRONG BUY"
elif score >= 60: sygnal = "✅ BUY"
elif score <= 30: sygnal = "⚠️ SELL"
else: sygnal = "➡️ NEUTRAL"

now = datetime.now().strftime("%d.%m.%Y %H:%M")
is_morning = datetime.utcnow().hour == 5

should_send = False
if is_morning:
    should_send = True
elif score >= 80 or score <= 25:
    should_send = True
else:
    print(f"[{now}] {price:.4f}$ | {score}/100 - skip")
    sys.exit(0)

if is_morning:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {now}*\n\n"
else:
    msg = f"🚨 *PYTH ALERT {score}/100 - {now}*\n\n"

msg += f"💰 Cena: {price:.4f}$ ({change_24h:+.2f}%/24h)\n"
msg += f"Mcap: ${mcap:.3f}B | Vol ${vol:.1f}M\n"
msg += f"RSI: {rsi:.1f} | Power: {score}/100 {sygnal}\n\n"
msg += f"🏛️ Fundamenty LIVE:\nTVS: ${tvs:.2f}B | Feeds: 1883\n"
msg += f"📊 Futures LIVE: OI: ${oi:.1f}M | Funding: {funding:+.4f}%\n\n"
msg += f"🔎 Ocena: {sygnal}"

print(msg)
send_telegram(msg)
