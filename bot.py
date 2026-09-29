import requests
from datetime import datetime, timezone

PHONE = "48668873755"
APIKEY = "1212249"

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist", "breach", "fraud"]

def send(msg):
    try:
        params = {"phone": PHONE, "text": msg[:900], "apikey": APIKEY}
        r = requests.get("https://api.callmebot.com/whatsapp.php", params=params, timeout=20)
        print(f"Wyslano: {msg} | Odp: {r.text[:200]}")
    except Exception as e:
        print(f"Blad: {e}")

def get_data():
    r = requests.get("https://api.exchange.coinbase.com/products/PYTH-USD/stats", timeout=10).json()
    price = float(r['last'])
    open_price = float(r.get('open', price))
    high = float(r.get('high', price))
    low = float(r.get('low', price))
    change = ((price - open_price) / open_price * 100) if open_price else 0
    return price, change, high, low

def get_news():
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,coindesk,cointelegraph,decrypt&extraParams=pythbot"
        data = requests.get(url, timeout=10).json().get('Data', [])
        now = datetime.now(timezone.utc).timestamp()
        for n in data[:20]:
            if 'PYTH' in n['title'].upper():
                if now - n.get('published_on', 0) < 10800: # news z ostatnich 3h
                    return n['title'], n['title'].lower()
        return None, None
    except Exception as e:
        print(f"News err: {e}")
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()

print(f"PYTH: {price:.5f} $ | {change:+.2f}% | H:{high:.5f} L:{low:.5f} | News: {news_title}")

# 1. ZLE NEWSY - ZAWSZE ALERT
if news_title and any(w in news_lower for w in NEGATIVE_WORDS):
    send(f"🚨 PYTH ZLE NEWS: {news_title} | Cena {price:.5f}$ ({change:+.2f}%) - SPRAWDZ!")

# 2. DOBRE NEWSY (PYTH ale nie zle)
elif news_title:
    send(f"📰 PYTH NEWS: {news_title} | Cena {price:.5f}$ ({change:+.2f}%)")

# 3. DUZY RUCH CENY bez newsa
elif abs(change) >= 4.0:
    direction = "POMPA 📈" if change > 0 else "ZJAZD 📉"
    send(f"⚠️ PYTH {direction}: {change:+.2f}% | Teraz {price:.5f}$ | H:{high:.5f} L:{low:.5f}")
