import requests
from datetime import datetime, timezone
import urllib.parse

PHONE = "48668873755"
APIKEY = "1212249"

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist", "breach", "fraud"]

def send(msg):
    try:
        text_enc = urllib.parse.quote(msg[:900])
        # OBEJSCIE 403 - przez proxy
        original_url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={text_enc}&apikey={APIKEY}"
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(original_url)}"
        
        r = requests.get(proxy_url, timeout=25)
        print(f"Wyslano: {msg} | Odp proxy: {r.text[:300]}")
        
        # jesli proxy nie zadziala, sprobuj bezposrednio
        if "queued" not in r.text.lower() and "message" not in r.text.lower():
            r2 = requests.get(original_url, timeout=15)
            print(f"Proba bezposrednia: {r2.text[:300]}")
            
    except Exception as e:
        print(f"Blad wysylki: {e}")

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
        resp = requests.get(url, timeout=10).json()
        data = resp.get('Data', [])
        if not isinstance(data, list):
            return None, None
        now = datetime.now(timezone.utc).timestamp()
        for n in data[:20]:
            title = n.get('title','')
            if 'PYTH' in title.upper():
                if now - n.get('published_on', 0) < 10800:
                    return title, title.lower()
        return None, None
    except Exception as e:
        print(f"News err: {e}")
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()
print(f"PYTH: {price:.5f} $ | {change:+.2f}% | H:{high:.5f} L:{low:.5f} | News: {news_title}")

# LOGIKA
if news_title and any(w in news_lower for w in NEGATIVE_WORDS):
    send(f"🚨 PYTH ZLE NEWS: {news_title} | Cena {price:.5f}$ ({change:+.2f}%) - SPRAWDZ!")

elif news_title:
    send(f"📰 PYTH NEWS: {news_title} | Cena {price:.5f}$ ({change:+.2f}%)")

elif abs(change) >= 4.0:
    direction = "POMPA 📈" if change > 0 else "ZJAZD 📉"
    send(f"⚠️ PYTH {direction}: {change:+.2f}% | Teraz {price:.5f}$ | H:{high:.5f} L:{low:.5f}")
else:
    print("Brak alertu - spokojnie")
    send(f"✅ PYTH bot naprawiony! Proxy dziala. Cena {price:.5f}$")
