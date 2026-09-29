import requests
from datetime import datetime, timezone
import urllib.parse

PHONE = "48668873755"
APIKEY = "1212249"
TELEGRAM_TOKEN = "8982367160:AAFCnbku93EC6JzNB9WBqofsNVUvDuOjjRQ"
TELEGRAM_CHAT_ID = "39760226"

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist", "breach", "fraud"]

def send_whatsapp(msg):
    try:
        text_enc = urllib.parse.quote(msg[:900])
        url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={text_enc}&apikey={APIKEY}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        requests.get(url, headers=headers, timeout=20)
        print(f"WA wyslano")
    except Exception as e:
        print(f"WA blad: {e}")

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, data=data, timeout=10)
        print(f"TG wyslano")
    except Exception as e:
        print(f"TG blad: {e}")

def send_both(msg):
    send_whatsapp(msg)
    send_telegram(msg)

def get_data():
    r = requests.get("https://api.exchange.coinbase.com/products/PYTH-USD/stats", timeout=10).json()
    price = float(r['last'])
    open_price = float(r.get('open', price))
    change = ((price - open_price) / open_price * 100) if open_price else 0
    return price, change, float(r.get('high', price)), float(r.get('low', price))

def get_news():
    try:
        resp = requests.get("https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,coindesk,cointelegraph&extraParams=pythbot", timeout=10).json()
        data = resp.get('Data', [])
        now = datetime.now(timezone.utc).timestamp()
        for n in data[:20]:
            title = n.get('title','')
            if 'PYTH' in title.upper() and now - n.get('published_on',0) < 10800:
                return title, title.lower()
        return None, None
    except:
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()
print(f"PYTH: {price:.5f}$ {change:+.2f}% | News: {news_title}")

if news_title and any(w in news_lower for w in NEGATIVE_WORDS):
    send_both(f"🚨 PYTH ZLE NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif news_title:
    send_both(f"📰 PYTH NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif abs(change) >= 4.0:
    direction = "POMPA 📈" if change > 0 else "ZJAZD 📉"
    send_both(f"⚠️ PYTH {direction}: {change:+.2f}%\nTeraz {price:.5f}$ H:{high:.5f} L:{low:.5f}")
else:
    print("Brak alertu - spokojnie")
