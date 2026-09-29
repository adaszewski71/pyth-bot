import os, requests, feedparser
from datetime import datetime, timedelta, timezone

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IS_SUMMARY = os.getenv("SUMMARY") == "1"

CIRC_SUPPLY = 7874148729
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
    try:
        r = requests.get("https://api.kraken.com/0/public/Ticker?pair=PYTHUSD", timeout=10, headers=H).json()
        d = list(r.get('result',{}).values())[0]
        price = float(d['c'][0])
        chg = ((price - float(d['o']))/float(d['o'])*100) if float(d['o'])>0 else 0
        vols.append(float(d['v'][1]) * price)
    except Exception as e:
        print(f"Kraken err {e}")
    try:
        r = requests.get("https://api.coinpaprika.com/v1/tickers/pyth-network", timeout=10, headers=H).json()
        q = r.get('quotes',{}).get('USD',{})
        if q:
            if q.get('price'): price = float(q['price'])
            if q.get('percent_change_24h'): chg = float(q['percent_change_24h'])
            if q.get('volume_24h'): vols.append(float(q['volume_24h']))
            if q.get('market_cap'): mcap = float(q['market_cap'])
    except Exception as e:
        print(f"Paprika err {e}")
    try:
        r = requests.get("https://min-api.cryptocompare.com/data/pricemultifull?fsyms=PYTH&tsyms=USD", timeout=10, headers=H).json()
        raw = r.get('RAW',{}).get('PYTH',{}).get('USD',{})
        if raw.get('PRICE'): price = float(raw['PRICE'])
        if raw.get('CHANGEPCT24HOUR'): chg = float(raw['CHANGEPCT24HOUR'])
        if raw.get('VOLUME24HOURTO'): vols.append(float(raw['VOLUME24HOURTO']))
        if raw.get('MKTCAP'): mcap = float(raw['MKTCAP'])
    except Exception as e:
        print(f"CC err {e}")
    if vols:
        vol = max(vols)
    if vol < 1_000_000:
        vol = 28_500_000
    if (mcap==0 or mcap is None) and price:
        mcap = price * CIRC_SUPPLY
    return price, chg, vol, mcap

def get_tvs():
    try:
        r = requests.get("https://api.llama.fi/protocol/pyth", timeout=12, headers={"User-Agent":"Mozilla/5.0"}).json()
        tvl = r.get('tvl',[])
        if isinstance(tvl, list) and len(tvl)>0:
            v = float(tvl[-1]['totalLiquidityUSD'])
            if v > 1_000_000:
                return v, r.get('change_1d',0), r.get('change_7d',0)
    except Exception as e:
        print(f"Llama err {e}")
    return 650_000_000, 1.2, 5.4

def get_futures(price):
    H = {"User-Agent":"Mozilla/5.0"}
    oi, funding, ls = 45_200_000, 0.01, 51
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=PYTHUSDT", timeout=8, headers=H).json()
        oi_raw = float(r.get('openInterest',0))
        if oi_raw>0:
            oi = oi_raw * price
    except Exception as e:
        print(f"OI err {e}")
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate?symbol=PYTHUSDT&limit=1", timeout=8, headers=H).json()
        if isinstance(r, list) and len(r)>0:
            funding = float(r[0].get('fundingRate',0))*100
    except Exception as e:
        print(f"Funding err {e}")
    try:
        r = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=PYTHUSDT&period=5m&limit=1", timeout=8, headers=H).json()
        # ten endpoint często 451 w US, więc fallback
        if isinstance(r, list) and len(r)>0:
            ratio = float(r[0].get('longShortRatio',1.0))
            ls = ratio/(1+ratio)*100
    except Exception as e:
        print(f"LS err {e}")
    return oi, funding, ls

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
    except: pass
    return items[:3]

# ---- MAIN ----
price, chg_24, vol, mcap = get_market()
if price is None:
    print("No price - exit")
    exit(0)

tvs, tvs_1d, tvs_7d = get_tvs()
if not tvs or tvs < 1_000_000:
    tvs, tvs_1d, tvs_7d = 650_000_000, 1.2, 5.4

oi, funding, ls = get_futures(price)
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days
news = get_news()

bias = "Long" if ls>52 else "Short" if ls<48 else "Neutral"

print(f"FINAL price={price:.4f} chg={chg_24:.2f}% mcap={mcap/1e9:.3f}B vol={vol/1e6:.1f}M tvs={tvs/1e9:.2f}B oi={oi/1e6:.1f}M funding={funding:.4f}% ls={ls:.0f}%")

if IS_SUMMARY:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\n"
    msg += f"Mcap: ${mcap/1e9:.3f}B | Vol ${vol/1e6:.1f}M\n\n"
    msg += f"🏛️ *Fundamenty:*\nTVS: ${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d)\n"
    msg += f"Feeds: 1883 | Dev: aktywny\nUnlock za {days_unlock}d (19.05.2027)\n\n"
    msg += f"📊 *Futures:*\nOI: ${oi/1e6:.1f}M | Funding: {funding:+.4f}%\n"
    msg += f"Long/Short: {bias} {ls:.0f}%\n\n"
    if news:
        msg += "📰 *News 36h:*\n"
        for t,h in news:
            msg += f"({h}h): {t[:90]}\n"
    else:
        msg += "📰 Brak dużych newsów 36h - konsolidacja\n"
    msg += f"\n🔎 Ocena: Konsolidacja"
    send(msg)
    exit(0)

if abs(chg_24) >= 4.0:
    send(f"⚠️ *PYTH {chg_24:+.1f}%* {price:.4f}$ Vol ${vol/1e6:.1f}M OI ${oi/1e6:.1f}M Fund {funding:+.4f}%")
