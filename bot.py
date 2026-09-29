import os, requests, feedparser
from datetime import datetime, timedelta, timezone

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IS_SUMMARY = os.getenv("SUMMARY") == "1"

PRICE_ALERT_PCT = 4.0
CIRC_SUPPLY = 5_750_000_000 # PYTH circulating ~5.75B
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
    H = {"User-Agent":"Mozilla/5.0"}

    # 1. Gate.io - główne źródło (działa w US)
    try:
        r = requests.get("https://api.gateio.ws/api/v4/spot/tickers?currency_pair=PYTH_USDT", timeout=10, headers=H)
        j = r.json()
        d = j[0] if isinstance(j, list) else j
        price = float(d['last'])
        chg = float(d['change_percentage'])
        vol = float(d['quote_volume'])
        print(f"Gate OK price={price} vol={vol} chg={chg}")
    except Exception as e:
        print(f"Gate err {e}")

    # 2. OKX jako backup ceny
    if price is None:
        try:
            r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=PYTH-USDT", timeout=10, headers=H).json()
            d = r.get('data',[{}])[0]
            price = float(d['last'])
            chg = ((float(d['last'])-float(d['open24h']))/float(d['open24h'])*100) if float(d.get('open24h',0))>0 else 0
            vol = float(d.get('volCcy24h',0))
            print(f"OKX OK {price} vol {vol}")
        except Exception as e:
            print(f"OKX err {e}")

    # 3. CoinGecko tylko do mcap (jeśli nie zbanowany)
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false", timeout=15, headers=H)
        if r.status_code == 200:
            md = r.json().get('market_data',{})
            if price is None:
                price = md.get('current_price',{}).get('usd')
                chg = md.get('price_change_percentage_24h',0)
            mcap = md.get('market_cap',{}).get('usd',0)
            if vol==0:
                vol = md.get('total_volume',{}).get('usd',0)
            print(f"CG mcap {mcap}")
    except Exception as e:
        print(f"CG err {e}")

    # Mcap fallback = price * circulating
    if (not mcap or mcap==0) and price:
        mcap = price * CIRC_SUPPLY

    # vol spike z Gate klines
    try:
        r = requests.get("https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=PYTH_USDT&interval=1h&limit=26", timeout=10, headers=H).json()
        if isinstance(r, list) and len(r)>=2:
            last = float(r[-1][5])
            avg = sum(float(x[5]) for x in r[:-1])/len(r[:-1])
            vol_mult = last/avg if avg>0 else 1.0
    except: pass

    return price, chg, vol, mcap, vol_mult

def get_defillama():
    try:
        r = requests.get("https://api.llama.fi/protocol/pyth", timeout=10).json()
        tvl_list = r.get('tvl',[])
        tvs = tvl_list[-1]['totalLiquidityUSD'] if isinstance(tvl_list, list) and tvl_list else 0
        return tvs, r.get('change_1d',0), r.get('change_7d',0)
    except Exception as e:
        print(f"Llama err {e}")
        return None, None, None

def get_hermes():
    try:
        return len(requests.get("https://hermes.pyth.network/v2/price_feeds", timeout=10).json())
    except:
        return 1883

def get_github():
    try:
        since=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        r=requests.get(f"https://api.github.com/repos/pyth-network/pyth-client/commits?since={since}", timeout=10, headers={"User-Agent":"bot"}).json()
        return len(r) if isinstance(r,list) else 3
    except:
        return 3

def get_news():
    feeds=["https://cointelegraph.com/tags/pyth/rss","https://www.coindesk.com/arc/outboundfeeds/rss/","https://news.google.com/rss/search?q=Pyth+Network&hl=en-US&gl=US&ceid=US:en","https://forum.pyth.network/latest.rss"]
    pos=["listing","partnership","rwa","equities","cboe","reserve","buyback","tvs","lazer","integrat"]; neg=["hack","unlock","exploit","delist"]
    found=[]; now=datetime.now(timezone.utc)
    for url in feeds:
        try:
            f=feedparser.parse(url)
            for e in f.entries[:20]:
                pub=e.get('published_parsed')
                if not pub: continue
                dt=datetime(*pub[:6], tzinfo=timezone.utc)
                if now-dt>timedelta(hours=36): continue
                if "pyth" not in (e.title+" "+e.get('summary','')).lower(): continue
                s="NEUTRAL"
                txt=(e.title+e.get('summary','')).lower()
                if any(k in txt for k in pos): s="BULLISH 🚀"
                if any(k in txt for k in neg): s="BEARISH 💩"
                found.append((s,e.title,e.link,dt))
        except: pass
    found.sort(key=lambda x:x[3], reverse=True)
    return found[:4]

price, chg_24, vol, mcap, vol_mult = get_market()
if price is None:
    print("No market"); exit(0)

tvs, tvs_1d, tvs_7d = get_defillama()
feeds_cnt = get_hermes()
gh = get_github()
news = get_news()
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days

print(f"DEBUG price={price:.4f} chg={chg_24:.2f}% vol={vol/1e6:.1f}M mcap={mcap/1e9:.2f}B volx={vol_mult:.1f} tvs={tvs}")

if IS_SUMMARY:
    vol_m = f"${vol/1e6:.1f}M" if vol>0 else "n/a"
    mcap_b = f"${mcap/1e9:.2f}B"
    tvs_s = f"${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d)" if tvs else "n/a"
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\nMcap: {mcap_b} | Vol {vol_m} x{vol_mult:.1f}\n\n"
    msg += f"🏛️ *Fundamenty:*\nTVS: {tvs_s}\nFeeds: {feeds_cnt} | Dev: {gh} comm/7d\nUnlock za {days_unlock}d\n\n"
    if news:
        msg += "📰 *News 36h:*\n"
        for s,t,l,d in news[:3]:
            h=int((datetime.now(timezone.utc)-d).total_seconds()/3600)
            msg+=f"{s} ({h}h): {t}\n"
    else:
        msg+="📰 Brak newsów 36h - konsolidacja\n"
    msg+=f"\n🔎 Ocena: {'Fundamentalny wzrost TVS' if tvs_1d and tvs_1d>3 else 'Spekulacja' if abs(chg_24)>4 else 'Konsolidacja'}"
    send(msg)
    exit(0)

if abs(chg_24) >= PRICE_ALERT_PCT:
    send(f"⚠️ *PYTH CENA {chg_24:+.1f}%* {price:.4f}$ Vol ${vol/1e6:.1f}M")
