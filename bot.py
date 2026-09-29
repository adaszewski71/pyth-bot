import requests, os, feedparser, time
from datetime import datetime, timedelta

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NEGATIVE_WORDS = ["hack","exploit","scam","crash","lawsuit","sec","ban","downgrade","vulnerability","attack","breach","fraud"]

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=PYTH+Network+crypto&hl=en-US&gl=US&ceid=US:en",
    "https://cointelegraph.com/rss/tag/pyth",
    "https://www.coindesk.com/tag/pyth-network/rss/",
    "https://cryptonews.com/news/feed/",
    "https://decrypt.co/feed",
    "https://www.coinspeaker.com/tag/pyth-network/feed/"
]

def send_both(msg):
    try:
        # WhatsApp
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={requests.utils.quote(msg)}&apikey={APIKEY}", timeout=10)
    except Exception as e:
        print(f"WA error {e}")
    try:
        # Telegram
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={requests.utils.quote(msg)}", timeout=10)
    except Exception as e:
        print(f"TG error {e}")

def get_data():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network?localization=false", timeout=15).json()
        price = r['market_data']['current_price']['usd']
        change = r['market_data']['price_change_percentage_24h']
        high = r['market_data']['high_24h']['usd']
        low = r['market_data']['low_24h']['usd']
        return price, change, high, low
    except:
        # fallback binance
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=PYTHUSDT", timeout=10).json()
        return float(r['lastPrice']), float(r['priceChangePercent']), float(r['highPrice']), float(r['lowPrice'])

def get_news():
    all_news = []
    for rss_url in RSS_SOURCES:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.title
                lower = title.lower()
                # tylko newsy o PYTH w ostatnich 24h i zawierające pyth
                if "pyth" in lower or "pyth" in entry.get('description','').lower():
                    published = entry.get('published_parsed')
                    if published:
                        dt = datetime(*published[:6])
                        if datetime.utcnow() - dt > timedelta(hours=24):
                            continue
                    all_news.append((title, lower, rss_url))
        except Exception as e:
            print(f"RSS fail {rss_url}: {e}")
            continue

    if not all_news:
        return None, ""
    # najnowszy
    return all_news[0][0], all_news[0][1]

# MAIN
price, change, high, low = get_data()
news_title, news_lower = get_news()

if news_title and any(w in news_lower for w in NEGATIVE_WORDS):
    send_both(f"🚨 PYTH ZLE NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif news_title:
    send_both(f"📰 PYTH NEWS: {news_title}\nCena {price:.5f}$ ({change:+.2f}%)")
elif abs(change) >= 4.0:
    d = "POMPA 📈" if change > 0 else "ZJAZD 📉"
    send_both(f"⚠️ PYTH {d}: {change:+.2f}%\nTeraz {price:.5f}$ H:{high:.5f} L:{low:.5f}")
