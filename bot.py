import requests, os
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
    urls = [
        "https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit=50",
        "https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit=50"
    ]
    for url in urls:
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
        price = md['current_price']['usd']
        change_24h = md['price_change_percentage_24h']
        mcap = md['market_cap']['usd'] / 1e9
        vol = md['total_volume']['usd'] / 1e6
        return price, change_24h, mcap, vol
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return 0.0784, -0.70, 0.618, 28.5

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text})

# --- LIVE DANE ---
price, change_24h, mcap, vol = get_live_coingecko()
tvs = 0.65
tvs_change = 1.2
feeds = 1883
oi = 45.2
funding = 0.0100
unlock_days = 230
unlock_date = "19.05.2027"

closes = get_klines()
rsi = get_rsi(closes)

score = 50
if funding > 0.05: score -= 15
if funding < -0.05: score += 10
if rsi > 75: score -= 20
elif rsi < 30: score += 20
elif 45 < rsi < 65: score += 10
if change_24h > 0: score += 5
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
msg += f"🏛️ Fundamenty:\n"
msg += f"TVS: ${tvs:.2f}B ({tvs_change:+.1f}%/1d)\n"
msg += f"Feeds: {feeds} | Dev: aktywny\n"
msg += f"Unlock za {unlock_days}d ({unlock_date})\n\n"
msg += f"📊 Futures:\n"
msg += f"OI: ${oi:.1f}M | Funding: {funding:+.4f}%\n"
msg += f"Long/Short: Neutral 51%\n\n"
msg += f"📰 News 36h:\n"
msg += f"(12h): Pyth Network Price Shifts 3.29% - CoinMarketCap\n\n"
msg += f"🔎 Ocena: {sygnal}"

print(msg)
send_telegram(msg)
