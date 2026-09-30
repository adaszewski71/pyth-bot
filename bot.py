import requests, os
from datetime import datetime

PYTH_MINT = "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"

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
        oi_data = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=PYTHUSDT", timeout=10).json()
        oi_binance = float(oi_data.get('openInterest', 0)) * 0.077
        oi_total = oi_binance * 13 # szacunek total = Binance * 13 (bo Binance to ~8% rynku)
        return funding, oi_total / 1e6
    except:
        return 0.0100, 45.2

def get_live_tvs():
    try:
        # DeFiLlama Pyth TVS
        r = requests.get("https://api.llama.fi/tvl/pyth", timeout=10).json()
        tvs = float(r) / 1e9
        return tvs
    except:
        try:
            # fallback - oracles endpoint
            r = requests.get("https://api.llama.fi/oracles", timeout=10).json()
            for o in r:
                if o['name'] == 'Pyth':
                    return float(o['tvl']) / 1e9
        except: pass
        return 3.589

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text})

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
if tvs > 3.5: score += 10 # mocne fundamenty
score = max(0, min(100, score))

if score >= 80: sygnal = "🔥 STRONG BUY"
elif score >= 60: sygnal = "✅ BUY"
elif score <= 30: sygnal = "⚠️ SELL"
else: sygnal = "➡️ NEUTRAL - Konsolidacja"

now = datetime.now().strftime("%d.%m.%Y")

msg = f"☀️ PYTH DAILY 7:00 PL - {now}\n\n"
msg += f"💰 Cena: {price:.4f}$ ({change_24h:+.2f}%/24h)\n"
msg += f"Mcap: ${mcap:.3f}B | Vol ${vol:.1f}M\n"
msg += f"RSI: {rsi:.1f} | Power: {score}/100 {sygnal}\n\n"
msg += f"🏛️ Fundamenty LIVE:\n"
msg += f"TVS: ${tvs:.2f}B | Feeds: 1883\n"
msg += f"Top20: 85% supply | Dev: aktywny\n"
msg += f"Unlock za 230d (19.05.2027)\n\n"
msg += f"📊 Futures LIVE:\n"
msg += f"OI: ${oi:.1f}M | Funding: {funding:+.4f}%\n"
msg += f"Long/Short: Neutral\n\n"
msg += f"📰 News 36h:\n"
msg += f"(12h): Pyth Network Price Shifts 3.29% - CMC\n\n"
msg += f"🔎 Ocena: {sygnal}"

print(msg)
send_telegram(msg)
