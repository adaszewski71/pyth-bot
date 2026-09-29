import requests
from datetime import datetime, timezone

PHONE = "48668873755"
APIKEY = "1212249"

NEGATIVE_WORDS = ["hack", "exploit", "lawsuit", "sec", "crash", "down", "fall", "dump", "scam", "vulnerability", "attack", "delist"]

def send(msg):
    safe = requests.utils.quote(msg[:900])
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={safe}&apikey={APIKEY}"
    try:
        requests.get(url, timeout=15)
        print(f"Wyslano: {msg}")
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
                if now - n.get('published_on', 0) < 10800: # 3h
                    return n['title'], n['title'].lower()
        return None, None
    except:
        return None, None

price, change, high, low = get_data()
news_title, news_lower = get_news()

print(f"PYTH: {price:.5f} | {change:+.2f}% | H:{high:.5f} L:{low:.5f} | News: {news_title}")

msg = None
is_bad_news = False
if news_lower:
    is_bad_news = any(w in news_lower for w in NEGATIVE_WORDS)

# === LOGIKA OPTYMALNA + OSTRZEŻENIA ===

# 1. ZAGROŻENIE - NAJWAŻNIEJSZE
if is_bad_news:
    msg = f"🚨 PYTH ZAGROZENIE: {news_title} | Cena: {price:.5f}$ ({change:+.2f}%) - SPRAWDZ!"
elif change < -7:
    msg = f"⚠️ PYTH CRASH: {price:.5f}$ ({change:+.2f}%) - SILNY SPADEK! L:{low:.5f}$"
elif change < -4:
    msg = f"📉 PYTH OSTRZEZENIE: {price:.5f}$ ({change:+.2f}%) - ZJAZD"
elif price < 0.06:
    msg = f"🆘 PYTH NISKO: {price:.5f}$ ({change:+.2f}%) - Poziom alarmowy <0.06!"

# 2. OKAZJA - DOBRE
elif price > 0.082 and change > 3 and news_title:
    msg = f"🚀 PYTH MAX: {price:.5f}$ ({change:+.2f}%) NEWS: {news_title}"
elif price > 0.082 and change > 3:
    msg = f"🚀 PYTH BREAKOUT: {price:.5f}$ ({change:+.2f}%) H:{high:.5f}$"
elif price > 0.082:
    msg = f"⚠️ PYTH ALERT: {price:.5f}$ ({change:+.2f}%) wybicie 0.082"
elif news_title and change > 2:
    msg = f"📰 PYTH NEWS+: {news_title} | {price:.5f}$ ({change:+.2f}%)"
elif change > 5:
    msg = f"📈 PYTH POMPA: {price:.5f}$ (+{change:.2f}%)"

if msg:
    send(msg)
else:
    print("OK - stabilnie, nie wysylam")
