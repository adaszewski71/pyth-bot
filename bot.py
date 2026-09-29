import os, requests, feedparser
from datetime import datetime, timedelta, timezone

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IS_SUMMARY = os.getenv("SUMMARY") == "1"

COINGECKO_ID = "pyth-network"
PRICE_ALERT_PCT = 4.0
UNLOCK_DATE = datetime(2027, 5, 19, tzinfo=timezone.utc)

def send(msg):
    print(msg)
    try:
        if PHONE and APIKEY:
            requests.post(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={msg}&apikey={APIKEY}", timeout=12)
    except: pass
    try:
        if TG_TOKEN and TG_CHAT:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=12)
    except: pass

def get_market():
    price, chg, vol, mcap, vol_mult = None, 0, 0, 0, 1.0
    headers = {"User-Agent":"Mozilla/5.0"}

    # 1. CoinGecko
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_ID}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true",
            timeout=15, headers=headers
        )
        if r.status_code == 200 and r.text:
            j = r.json()
            if COINGECKO_ID in j:
                cg = j[COINGECKO_ID]
                price = cg.get('usd')
                chg = cg.get('usd_24h_change', 0)
                vol = cg.get('usd_24h_vol', 0)
                mcap = cg.get('usd_market_cap', 0)
                print(f"CG OK {price}")
    except Exception as e:
        print(f"CG err {e}")

    # 2. Bybit (działa w US) - zamiennik Binance
    if price is None:
        try:
            r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=PYTHUSDT", timeout=10, headers=headers)
            print(f"Bybit status {r.status_code}")
            j = r.json()
            t = j.get('result',{}).get('list',[{}])[0]
            if t:
                price = float(t['lastPrice'])
                chg = float(t['price24hPcnt'])*100
                vol = float(t['turnover24h'])
                print(f"Bybit OK {price}")
        except Exception as e:
            print(f"Bybit err {e}")

    # 3. OKX fallback
    if price is None:
        try:
            r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=PYTH-USDT", timeout=10, headers=headers)
            j = r.json()
            d = j.get('data',[{}])[0]
            price = float(d['last'])
            chg = ((float(d['last'])-float(d['open24h']))/float(d['open24h'])*100) if float(d['open24h'])>0 else 0
            vol = float(d['volCcy24h'])*price
            print(f"OKX OK {price}")
        except Exception as e:
            print(f"OKX err {e}")
            return None, 0, 0, 0, 1.0

    # Vol spike z Bybit klines
    try:
        r = requests.get("https://api.bybit.com/v5/market/kline?category=spot&symbol=PYTHUSDT&interval=60&limit=26", timeout=10, headers=headers).json()
        kl = r.get('result',{}).get('list',[])[::-1]
        if len(kl)>=26:
            last = float(kl[-1][5])
            avg = sum(float(x[5]) for x in kl[:-1])/25
            vol_mult = last/avg if avg>0 else 1.0
    except: pass

    return price, chg, vol, mcap, vol_mult

def get_coinglass():
    funding, oi_chg, liq24 = None, None, None
    hdr = {"User-Agent":"Mozilla/5.0"}
    try:
        r = requests.get("https://fapi.coinglass.com/api/futures/fundingRate/list?symbol=PYTH", timeout=10, headers=hdr).json()
        rates = [float(x['fundingRate']*100) for x in r.get('data',[]) if 'fundingRate' in x][:10]
        if rates: funding = sum(rates)/len(rates)
    except: pass
    try:
        r = requests.get("https://fapi.coinglass.com/api/futures/openInterest/chart?symbol=PYTH&interval=1h", timeout=10, headers=hdr).json()
        d = r.get('data',[])
        if len(d) >= 24:
            oi_chg = (float(d[-1]['openInterest'])-float(d[-24]['openInterest']))/float(d[-24]['openInterest'])*100
    except: pass
    try:
        r = requests.get("https://fapi.coinglass.com/api/futures/liquidation/history?symbol=PYTH&interval=1h", timeout=10, headers=hdr).json()
        d = r.get('data',[])[-24:]
        if d: liq24 = sum(float(x.get('buyVol',0)+x.get('sellVol',0)) for x in d)
    except: pass
    return funding, oi_chg, liq24

def get_defillama():
    try:
        tvs = requests.get("https://api.llama.fi/tvl/pyth", timeout=10).json()
        r2 = requests.get("https://api.llama.fi/protocol/pyth", timeout=10).json()
        return tvs, r2.get('change_1d',0), r2.get('change_7d',0)
    except:
        return None, None, None

def get_hermes():
    try:
        r = requests.get("https://hermes.pyth.network/v2/price_feeds", timeout=10).json()
        return len(r)
    except:
        return None

def get_github():
    try:
        since = (datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        r = requests.get(f"https://api.github.com/repos/pyth-network/pyth-client/commits?since={since}", timeout=10, headers={"User-Agent":"bot"}).json()
        if isinstance(r, list): return len(r)
    except: pass
    return None

def get_news():
    feeds = [
        "https://cointelegraph.com/tags/pyth/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://decrypt.co/feed",
        "https://news.google.com/rss/search?q=Pyth+Network&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=PYTH+oracle&hl=en-US&gl=US&ceid=US:en",
        "https://forum.pyth.network/latest.rss"
    ]
    pos = ["listing","partnership","rwa","equities","cboe","reserve","buyback","tvs","lazer","integrat","pyth pro"]
    neg = ["hack","lawsuit","unlock","exploit","delist"]
    found = []
    now = datetime.now(timezone.utc)
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:25]:
                pub = e.get('published_parsed')
                if not pub: continue
                dt = datetime(*pub[:6], tzinfo=timezone.utc)
                if now - dt > timedelta(hours=36): continue
                text = (e.title + " " + e.get('summary','')).lower()
                if "pyth" not in text: continue
                sent = "NEUTRAL"
                if any(k in text for k in pos): sent = "BULLISH 🚀"
                if any(k in text for k in neg): sent = "BEARISH 💩"
                if any(t[1]==e.title for t in found): continue
                found.append((sent, e.title, e.link, dt))
        except: pass
    found.sort(key=lambda x: x[3], reverse=True)
    return found[:5]

# --- MAIN ---
market = get_market()
if market[0] is None:
    print("No market - exit")
    exit(0)

price, chg_24, vol, mcap, vol_mult = market
funding, oi_chg, liq24 = get_coinglass()
tvs, tvs_1d, tvs_7d = get_defillama()
feeds_cnt = get_hermes()
gh = get_github()
news = get_news()
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days

print(f"DEBUG price={price:.4f} chg={chg_24:.2f}% volx={vol_mult:.1f} fund={funding} oi={oi_chg} tvs={tvs} feeds={feeds_cnt} gh={gh} news={len(news)}")

if IS_SUMMARY:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\nMcap: ${mcap/1e9:.2f}B | Vol ${vol/1e6:.1f}M x{vol_mult:.1f}\n\n"
    if funding is not None:
        liq_str = f"${liq24/1e6:.2f}M" if liq24 else "n/a"
        oi_str = f"{oi_chg:+.1f}%" if oi_chg is not None else "n/a"
        msg += f"📊 *Coinglass:*\nFunding: {funding:.4f}% | OI {oi_str}/24h\nLiq 24h: {liq_str}\n\n"
    if tvs:
        msg += f"🏛️ *Fundamenty:*\nTVS: ${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d, {tvs_7d:+.1f}%/7d)\nFeeds: {feeds_cnt} | Dev: {gh} comm/7d\nUnlock za {days_unlock}d\n\n"
    else:
        msg += f"🏛️ Feeds: {feeds_cnt} | Dev: {gh}/7d | Unlock {days_unlock}d\n\n"
    if news:
        msg += f"📰 *News 36h:*\n"
        for s,t,l,d in news[:3]:
            h = int((datetime.now(timezone.utc)-d).total_seconds()/3600)
            msg += f"{s} ({h}h): {t}\n"
    else:
        msg += f"📰 Brak newsów 36h\n"
    msg += f"\n🔎 Ocena: {'FUNDAMENTALNY wzrost TVS' if tvs_1d and tvs_1d>3 else 'Spekulacyjny' if abs(chg_24)>4 and not news else 'Konsolidacja'}"
    send(msg)
    exit(0)

if abs(chg_24) >= PRICE_ALERT_PCT:
    send(f"⚠️ *PYTH CENA {chg_24:+.1f}%*\n{price:.4f}$ Vol x{vol_mult:.1f} | TVS ${tvs/1e9:.2f}B" if tvs else f"⚠️ *PYTH CENA {chg_24:+.1f}%* {price:.4f}$")

if funding is not None and abs(funding) > 0.05:
    send(f"🔥 *PYTH FUNDING {funding:.4f}%* {'LONG przegrzany' if funding>0 else 'SHORT przegrzany'} | OI {oi_chg:+.1f if oi_chg else 0:.1f}%")

if oi_chg is not None and oi_chg > 15 and abs(chg_24) < 3:
    send(f"👀 *PYTH OI BUILDUP +{oi_chg:.1f}%/24h* Cena {chg_24:+.1f}% - lewary wchodzą")

if liq24 and liq24 > 1000000:
    send(f"💥 *PYTH LIKWIDACJE ${liq24/1e6:.2f}M/24h*")

if tvs_1d and tvs_1d > 5:
    send(f"🏛️ *PYTH TVS +{tvs_1d:.1f}%* ${tvs/1e9:.2f}B vs cena {chg_24:+.1f}%")

for s,t,l,d in news:
    if s!= "NEUTRAL":
        h = int((datetime.now(timezone.utc)-d).total_seconds()/3600)
        send(f"📰 *PYTH {s} ({h}h)*\n{t}\n{l}")
