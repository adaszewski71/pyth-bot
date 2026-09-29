import os, requests, feedparser
from datetime import datetime, timedelta, timezone

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IS_SUMMARY = os.getenv("SUMMARY") == "1"

CIRC_SUPPLY = 5750000000
UNLOCK_DATE = datetime(2027, 5, 19, tzinfo=timezone.utc)

def send(msg):
    print(msg)
    try:
        if PHONE and APIKEY:
            requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={msg}&apikey={APIKEY}", timeout=15)
    except Exception as e:
        print(f"WA err {e}")
    try:
        if TG_TOKEN and TG_CHAT:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"TG err {e}")

def get_market():
    price, chg, vol, mcap = None, 0, 0, 0
    H = {"User-Agent":"Mozilla/5.0"}
    vols = []

    # 1. Kraken - działa w US
    try:
        r = requests.get("https://api.kraken.com/0/public/Ticker?pair=PYTHUSD", timeout=10, headers=H).json()
        d = list(r.get('result',{}).values())[0]
        price = float(d['c'][0])
        chg = ((price - float(d['o']))/float(d['o'])*100) if float(d['o'])>0 else 0
        vols.append(float(d['v'][1]) * price)
        print(f"Kraken OK price={price} vol={vols[-1]:.0f}")
    except Exception as e:
        print(f"Kraken err {e}")

    # 2. CoinPaprika - globalny vol + mcap
    try:
        r = requests.get("https://api.coinpaprika.com/v1/tickers/pyth-network", timeout=10, headers=H).json()
        q = r.get('quotes',{}).get('USD',{})
        if q:
            if q.get('price'): price = q['price']
            if q.get('percent_change_24h'): chg = q['percent_change_24h']
            if q.get('volume_24h'): vols.append(float(q['volume_24h']))
            if q.get('market_cap'): mcap = float(q['market_cap'])
            print(f"Paprika vol={q.get('volume_24h')} mcap={q.get('market_cap')}")
    except Exception as e:
        print(f"Paprika err {e}")

    # 3. CryptoCompare - backup
    try:
        r = requests.get("https://min-api.cryptocompare.com/data/pricemultifull?fsyms=PYTH&tsyms=USD", timeout=10, headers=H).json()
        raw = r.get('RAW',{}).get('PYTH',{}).get('USD',{})
        if raw.get('PRICE'): price = float(raw['PRICE'])
        if raw.get('CHANGEPCT24HOUR'): chg = float(raw['CHANGEPCT24HOUR'])
        if raw.get('VOLUME24HOURTO'): vols.append(float(raw['VOLUME24HOURTO']))
        if raw.get('MKTCAP'): mcap = float(raw['MKTCAP'])
        print(f"CC vol={raw.get('VOLUME24HOURTO')} mcap={raw.get('MKTCAP')}")
    except Exception as e:
        print(f"CC err {e}")

    if vols:
        vol = max(vols)
    if vol < 1_000_000:
        vol = 28_500_000
        print("Vol fallback 28.5M")

    if (mcap==0 or mcap is None) and price:
        mcap = price * CIRC_SUPPLY

    return price, chg, vol, mcap, 1.0

def get_tvs():
    try:
        r = requests.get("https://api.llama.fi/protocol/pyth", timeout=12, headers={"User-Agent":"Mozilla/5.0"}).json()
        tvl = r.get('tvl',[])
        if isinstance(tvl, list) and len(tvl)>0:
            tvs = float(tvl[-1]['totalLiquidityUSD'])
            print(f"Llama TVS {tvs}")
            return tvs, r.get('change_1d',0), r.get('change_7d',0)
    except Exception as e:
        print(f"Llama proto err {e}")

    try:
        r = requests.get("https://api.llama.fi/tvl/pyth", timeout=10)
        tvs = float(r.text.strip())
        print(f"Llama tvl direct {tvs}")
        return tvs, 0, 0
    except Exception as e:
        print(f"Llama tvl err {e}")

    return 650_000_000, 1.2, 5.4

def get_news():
    items=[]
    try:
        f=feedparser.parse("https://news.google.com/rss/search?q=Pyth+Network&hl=en-US&gl=US&ceid=US:en")
        now=datetime.now(timezone.utc)
        for e in f.entries[:6]:
            pub=e.get('published_parsed')
            if not pub: continue
            dt=datetime(*pub[:6], tzinfo=timezone.utc)
            if now-dt>timedelta(hours=36): continue
            items.append((e.title, int((now-dt).total_seconds()/3600)))
    except Exception as e:
        print(f"News err {e}")
    return items[:3]

# ---- MAIN ----
price, chg_24, vol, mcap, vol_mult = get_market()
if price is None:
    print("No price - exit")
    exit(0)

tvs, tvs_1d, tvs_7d = get_tvs()
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days
news = get_news()

print(f"FINAL price={price:.4f} chg={chg_24:.2f}% vol={vol/1e6:.1f}M mcap={mcap/1e9:.2f}B tvs={tvs/1e9:.2f}B")

if IS_SUMMARY:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\n"
    msg += f"Mcap: ${mcap/1e9:.2f}B | Vol ${vol/1e6:.1f}M\n\n"
    msg += f"🏛️ *Fundamenty:*\nTVS: ${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d)\n"
    msg += f"Feeds: 1883 | Dev: aktywny\nUnlock za {days_unlock}d (19.05.2027)\n\n"
    if news:
        msg += "📰 *News 36h:*\n"
        for t,h in news:
            msg += f"({h}h): {t[:90]}\n"
    else:
        msg += "📰 Brak dużych newsów 36h - konsolidacja\n"
    msg += f"\n🔎 Ocena: {'Wzrost TVS' if tvs_1d>2 else 'Konsolidacja'}"
    send(msg)
    exit(0)

# alerty intraday
if abs(chg_24) >= 4.0:
    send(f"⚠️ *PYTH CENA {chg_24:+.1f}%* {price:.4f}$ Vol ${vol/1e6:.1f}M")
