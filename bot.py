import requests
from datetime import datetime, timezone

PHONE = "48668873755"
APIKEY = "1212249"

def send(msg):
    safe = requests.utils.quote(msg[:900])
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={safe}&apikey={APIKEY}"
    try:
        requests.get(url, timeout=15)
        print(f"Wyslano: {msg}")
    except Exception as e:
        print(f"Blad wysylki: {e}")

def get_data():
    # Coinbase daje price + volume
    r = requests.get("https://api.exchange.coinbase.com/products/PYTH-USD/stats", timeout=10).json()
    price = float(r['last'])
    vol = float(r.get('volume_30day', 0))
    open_price = float(r.get('open', price))
    change = ((price - open_price) / open_price * 100) if open_price else 0
    return price, vol, change

def get_news():
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,coindesk,cointelegraph,decrypt&extraParams=pythbot"
        data = requests.get(url, timeout=10).json().get('Data', [])
        now = datetime.now(timezone.utc).timestamp()
        for n in data[:10]:
            title = n['title']
            if 'PYTH' in title.upper():
                if now - n.get('published_on', 0) < 10800: # 3h
                    return title
        return None
    except:
        return None

price, vol, change = get_data()
news = get_news()

print(f"PYTH: {price:.5f} | {change:+.2f}% | Vol: {vol:.0f} | News: {news}")

# === OPTYMALNA LOGIKA ===
# Nie spamuje, wysyla tylko wazne momenty

msg = None

if price > 0.082 and change > 3 and news:
    msg = f"🚀 PYTH MAX: {price:.5f}$ ({change:+.2f}%) NEWS: {news}"
elif price > 0.082 and change > 3:
    msg = f"🚀 PYTH BREAKOUT: {price:.5f}$ ({change:+.2f}%) VOL: {vol/1e6:.1f}M"
elif price > 0.082:
    msg = f"⚠️ PYTH ALERT: {price:.5f}$ ({change:+.2f}%) wybicie 0.082"
elif news and abs(change) > 2:
    msg = f"📰 PYTH NEWS: {news} | Cena: {price:.5f}$ ({change:+.2f}%)"
elif change > 5 or change < -5:
    msg = f"📊 PYTH RUCH: {price:.5f}$ ({change:+.2f}%)"

if msg:
    send(msg)
else:
    print("OK - brak sygnalu, nie wysylam")
