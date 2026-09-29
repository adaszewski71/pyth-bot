import os, requests, feedparser
from datetime import datetime, timedelta, timezone

PHONE = os.getenv("PHONE")
APIKEY = os.getenv("APIKEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IS_SUMMARY = os.getenv("SUMMARY") == "1"

COINGECKO_ID = "pyth-network"
BINANCE_SYMBOL = "PYTHUSDT"
PRICE_ALERT_PCT = 4.0
VOL_SPIKE_MULT = 3.0
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
    cg = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_ID}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true", timeout=15).json()[COINGECKO_ID]
    price, chg, vol, mcap = cg['usd'], cg.get('usd_24h_change',0), cg.get('usd_24h_vol',0), cg.get('usd_market_cap',0)
    vol_mult = 1.0
    try:
        k = requests.get(f"https://api.binance.com/api/v3/klines?symbol={BINANCE_SYMBOL}&interval=1h&limit=26", timeout=10).json()
        last=float(k[-1][5]); avg=sum(float(x[5]) for x in k[:-1])/25
        vol_mult=last/avg if avg>0 else 1.0
    except: pass
    return price, chg, vol, mcap, vol_mult

def get_coinglass():
    funding, oi_chg, liq24 = None, None, None
    hdr={"User-Agent":"Mozilla/5.0"}
    try:
        r=requests.get("https://fapi.coinglass.com/api/futures/fundingRate/list?symbol=PYTH", timeout=10, headers=hdr).json()
        rates=[float(x['fundingRate']*100) for x in r.get('data',[]) if 'fundingRate' in x][:10]
        if rates: funding=sum(rates)/len(rates)
    except: pass
    try:
        r=requests.get("https://fapi.coinglass.com/api/futures/openInterest/chart?symbol=PYTH&interval=1h", timeout=10, headers=hdr).json()
        d=r.get('data',[])
        if len(d)>=24:
            oi_chg=(float(d[-1]['openInterest'])-float(d[-24]['openInterest']))/float(d[-24]['openInterest'])*100
    except: pass
    try:
        r=requests.get("https://fapi.coinglass.com/api/futures/liquidation/history?symbol=PYTH&interval=1h", timeout=10, headers=hdr).json()
        d=r.get('data',[])[-24:]
        if d: liq24=sum(float(x.get('buyVol',0)+x.get('sellVol',0)) for x in d)
    except: pass
    return funding, oi_chg, liq24

def get_defillama():
    try:
        tvs=requests.get("https://api.llama.fi/tvl/pyth", timeout=10).json()
        r2=requests.get("https://api.llama.fi/protocol/pyth", timeout=10).json()
        return tvs, r2.get('change_1d',0), r2.get('change_7d',0)
    except:
        return None, None, None

def get_hermes():
    try:
        r=requests.get("https://hermes.pyth.network/v2/price_feeds", timeout=10).json()
        return len(r)
    except:
        return None

def get_github():
    try:
        since=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        r=requests.get(f"https://api.github.com/repos/pyth-network/pyth-client/commits?since={since}", timeout=10, headers={"User-Agent":"bot"}).json()
        if isinstance(r,list): return len(r)
    except: pass
    return None

def get_news():
    feeds=[
        "https://cointelegraph.com/tags/pyth/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://news.google.com/rss/search?q=Pyth+Network&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=PYTH+oracle&hl=en-US&gl=US&ceid=US:en",
        "https://forum.pyth.network/latest.rss"
    ]
    pos=["listing","partnership","rwa","equities","cboe","reserve","buyback","tvs","lazer","integrat"]
    neg=["hack","lawsuit","unlock","exploit"]
    found=[]; now=datetime.now(timezone.utc)
    for url in feeds:
        try:
            f=feedparser.parse(url)
            for e in f.entries[:20]:
                pub=e.get('published_parsed')
                if not pub: continue
                dt=datetime(*pub[:6], tzinfo=timezone.utc)
                if now-dt>timedelta(hours=36): continue
                text=(e.title+" "+e.get('summary','')).lower()
                if "pyth" not in text: continue
                sent="NEUTRAL"
                if any(k in text for k in pos): sent="BULLISH 🚀"
                if any(k in text for k in neg): sent="BEARISH 💩"
                if any(t[1]==e.title for t in found): continue
                found.append((sent,e.title,e.link,dt))
        except: pass
    found.sort(key=lambda x: x[3], reverse=True)
    return found[:5]

# --- DATA ---
price, chg_24, vol, mcap, vol_mult = get_market()
funding, oi_chg, liq24 = get_coinglass()
tvs, tvs_1d, tvs_7d = get_defillama()
feeds_cnt = get_hermes()
gh = get_github()
news = get_news()
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days

# --- TRYB PODSUMOWANIA 7:00 PL ---
if IS_SUMMARY:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\nMcap: ${mcap/1e9:.2f}B | Vol ${vol/1e6:.1f}M x{vol_mult:.1f}\n\n"
    msg += f"📊 *Coinglass:*\nFunding: {funding:.4f}% | OI {oi_chg:+.1f}%/24h\nLiq 24h: ${liq24/1e6:.2f}M\n\n" if funding is not None else ""
    msg += f"🏛️ *Fundamenty:*\nTVS: ${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d, {tvs_7d:+.1f}%/7d)\nFeeds: {feeds_cnt} | Dev: {gh} commity/7d\nUnlock {UNLOCK_DATE.date()} ({days_unlock} dni) {2.12:.2f}B PYTH\n\n" if tvs else f"🏛️ Feeds: {feeds_cnt} | Dev: {gh}/7d | Unlock za {days_unlock}d\n\n"
    if news:
        msg += f"📰 *News 36h:*\n"
        for s,t,l,d in news[:3]:
            h=int((datetime.now(timezone.utc)-d).total_seconds()/3600)
            msg += f"{s} ({h}h): {t}\n"
    else:
        msg += f"📰 Brak newsów 36h - ruch czysto spekulacyjny\n"
    msg += f"\n🔎 Ocena: {'FUNDAMENTALNY wzrost TVS' if tvs_1d and tvs_1d>3 else 'Spekulacyjny' if abs(chg_24)>4 and not news else 'Konsolidacja'}"
    send(msg)
    print("SUMMARY sent")
    exit(0)

# --- TRYB NORMALNY (co 5 min) ---
if abs(chg_24) >= PRICE_ALERT_PCT:
    send(f"⚠️ *PYTH CENA {chg_24:+.1f}%*\n{price:.4f}$ Vol x{vol_mult:.1f} | TVS ${tvs/1e9:.2f}B" if tvs else f"⚠️ *PYTH CENA {chg_24:+.1f}%* {price:.4f}$")

if funding and abs(funding)>0.05:
    send(f"🔥 *PYTH FUNDING {funding:.4f}%* OI {oi_chg:+.1f}% | Cena {chg_24:+.1f}%")
if oi_chg and oi_chg>15 and abs(chg_24)<3:
    send(f"👀 *PYTH OI +{oi_chg:.1f}%* Cena {chg_24:+.1f}% - lewary wchodzą")
if liq24 and liq24>1_000_000:
    send(f"💥 *PYTH LIQ ${liq24/1e6:.2f}M/24h*")

if tvs_1d and tvs_1d>5:
    send(f"🏛️ *PYTH TVS +{tvs_1d:.1f}%* ${tvs/1e9:.2f}B vs cena {chg_24:+.1f}%")

for s,t,l,d in news:
    if s!="NEUTRAL":
        h=int((datetime.now(timezone.utc)-d).total_seconds()/3600)
        send(f"📰 *PYTH {s} ({h}h)*\n{t}\n{l}")

print(f"OK chg={chg_24:.2f}% volx={vol_mult:.1f} fund={funding} oi={oi_chg} tvs={tvs}")
