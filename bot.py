import requests
import numpy as np

def get_rsi(prices, period=14):
    deltas = np.diff(prices)
    gain = np.where(deltas > 0, deltas, 0)
    loss = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_klines():
    url = "https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit=50"
    data = requests.get(url).json()
    closes = [float(x[4]) for x in data]
    return closes

def get_data():
    # Twoje stare
    price = 0.078 # tu Twoje get_price()
    mcap = 627_000_000 # tu Twoje get_mcap()

    # Futures
    oi = 57_000_000
    funding = 0.06 # przykład

    # NOWE: RSI
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

# DAILY
price, mcap, oi, funding, rsi = get_data()
score = get_power_score(price, funding, rsi)

msg = f"PYTH: ${price:.4f}\n"
msg += f"Mcap: ${mcap/1e6:.1f}M\n"
msg += f"RSI(14): {rsi:.1f}\n"
msg += f"Funding: {funding:.4f}%\n"
msg += f"OI: ${oi/1e6:.1f}M\n"

if score >= 80:
    sygnal = "🔥 STRONG BUY - akumuluj pod 8 Oct"
elif score >= 60:
    sygnal = "✅ BUY / HOLD"
elif score <= 30:
    sygnal = "⚠️ SELL / czekaj"
else:
    sygnal = "➡️ NEUTRAL"

msg += f"\nPower Score: {score}/100 - {sygnal}\n"

# Twój stary alert + nowy
if funding > 0.05:
    msg += f"\n🔥 Funding wysoki {funding:.4f}% - Longi przegrzane"
elif funding < -0.05:
    msg += f"\n❄️ Funding ujemny {funding:.4f}% - Shorty w pułapce"

print(msg)
# send(msg)
