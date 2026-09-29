import requests
from datetime import datetime, timezone

PHONE = "48668873755"
APIKEY = "1212249"

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist"]

def send(msg):
    safe = requests.utils.quote(msg[:900])
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={safe}&apikey={APIKEY}"
    try:
        r = requests.get(url, timeout=15)
        print(f"Wyslano: {msg} | Status: {r.text[:200]}")
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
        for n in data[:15]:
            if 'PYTH' in n['title'].upper():
                if now - n.get('published_on', 0) < 10800:
                    return n['title'], n['title'].lower()
        return None, None
    except:
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()

print(f"PYTH: {price:.5f} | {change:+.2f}% | H:{high:.5f} L:{low:.5f} | News: {news_title}")

# === TEST - ZAWSZE WYSLA ===
send(f"✅ TEST BOT DZIALA: PYTH {price:.5f}$ ({change:+.2f}%) News: {news_title or 'brak'}")
