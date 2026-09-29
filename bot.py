import requests, os, urllib.parse
from datetime import datetime, timezone

PHONE = os.environ.get("PHONE")
APIKEY = os.environ.get("APIKEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist", "breach", "fraud"]

def send_whatsapp(msg):
    try:
        text_enc = urllib.parse.quote(msg[:900])
        url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={text_enc}&apikey={APIKEY}"
        headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"}
        requests.get(url, headers=headers, timeout=20)
    except Exception as e:
        print(f"WA blad: {e}")

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"TG blad: {e}")

def send_both(m):
    send_whatsapp(m)
    send_telegram(m)

def get_data():
    r = requests.get("https://api.exchange.coinbase.com/products/PYTH-USD/stats", timeout=10).json()
    price = float(r['last'])
    open_p = float(r.get('open', price))
    ch = ((price - open_p) / open_p * 100) if open_p else 0
    return price, ch, float(r.get('high', price)), float(r.get('low', price))

def get_news():
    try:
        resp = requests.get("https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,coindesk,cointelegraph&extraParams=pythbot", timeout=10).json()
        now = datetime.now(timezone.utc).timestamp()
        for n in resp.get('Data', [])[:20]:
            t = n.get('title','')
            if 'PYTH' in t.upper() and now - n.get('published_on',0) < 10800:
                return t, t.lower()
        return None, None
    except:
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()

if news_title and any(w in news_lower for w in NEGATIVE_WORDS):
    send_both(f"🚨 PYTH ZLE NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif news_title:
    send_both(f"📰 PYTH NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif abs(change) >= 4.0:
    d = "POMPA 📈" if change > 0 else "ZJAZD 📉"
    send_both(f"⚠️ PYTH {d}: {change:+.2f}%\nTeraz {price:.5f}$ H:{high:.5f} L:{low:.5f}")
