import requests
import os

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

def get_data():
    price = 0.078
    mcap = 627_000_000
    oi = 57_000_000
    funding = 0.06
    closes = get_klines()
    rsi = get_rsi(closes)
    return price, mcap, oi, funding, rsi

def get_power_score(price, funding, rsi):
    score = 50
    if funding > 0.05: score -= 15
    if funding < -0.05: score += 10
    if rsi > 75: score -= 20
    elif rsi < 30: score += 20
    elif 50 < rsi < 70: score += 10
    if price > 0.085: score += 10
    if price < 0.075: score -= 10
    return max(0, min(100, score))

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Brak tokena")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

price, mcap, oi, funding, rsi = get_data()
score = get_power_score(price, funding, rsi)

msg = f"PYTH: ${price:.4f}\n"
msg += f"Mcap: ${mcap/1e6:.1f}M\n"
msg += f"RSI(14): {rsi:.1f}\n"
msg += f"Funding: {funding:.4f}%\n"
msg += f"OI: ${oi/1e6:.1f}M\n"
if score >= 80: sygnal = "🔥 STRONG BUY - akumuluj pod 8 Oct"
elif score >= 60: sygnal = "✅ BUY / HOLD"
elif score <= 30: sygnal = "⚠️ SELL / czekaj"
else: sygnal = "➡️ NEUTRAL"
msg += f"\nPower Score: {score}/100 - {sygnal}\n"
if funding > 0.05: msg += f"\n🔥 Funding wysoki {funding:.4f}% - Longi przegrzane"
elif funding < -0.05: msg += f"\n❄️ Funding ujemny {funding:.4f}% - Shorty w pułapce"

print(msg)
send_telegram(msg)
