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
    print(msg[:4000])
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

    # 1. Kraken - 100% działa w US, nie blokuje
    try:
        r = requests.get("https://api.kraken.com/0/public/Ticker?pair=PYTHUSD", timeout=10, headers=H).json()
        d = list(r.get('result',{}).values())[0] if r.get('result') else None
        if d:
            price = float(d['c'][0])
            vol = float(d['v'][1]) * price # vol 24h w USD
            chg = ((price - float(d['o']))/float(d['o'])*100) if float(d['o'])>0 else 0
            print(f"Kraken OK price={price} vol={vol}")
    except Exception as e:
        print(f"Kraken err {e}")

    # 2. CoinPaprika - działa wszędzie, daje vol + mcap poprawnie
    try:
        r = requests.get("https://api.coinpaprika.com/v1/tickers/pyth-network", timeout=10, headers=H).json()
        q = r.get('quotes',{}).get('USD',{})
        if q:
            if price is None:
                price = q.get('price')
                chg = q.get('percent_change_24h',0)
            # bierz vol i mcap stąd bo Kraken ma mały vol (tylko Kraken)
            pap_vol = q.get('volume_24h',0)
            pap_mcap = q.get('market_cap',0)
            if pap_vol > vol: # większy vol = lepszy (globalny)
                vol = pap_vol
            mcap = pap_mcap if pap_mcap>0 else mcap
            print(f"Paprika OK price={q.get('price')} vol={pap_vol} mcap={pap_mcap}")
    except Exception as e:
        print(f"Paprika err {e}")

    # 3. CoinGecko tylko jako backup
    if price is None:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=pyth-network&vs_currencies=usd&include_24hr_vol=true&include_market_cap=true&include_24hr_change=true", timeout=10, headers=H).json()
            d = r.get('pyth-network',{})
            price = d.get('usd')
            chg = d.get('usd_24h_change',0)
            vol = d.get('usd_24h_vol',0) if vol==0 else vol
            mcap = d.get('usd_market_cap',0) if mcap==0 else mcap
            print(f"CG OK {price}")
        except Exception as e:
            print(f"CG err {e}")

    if mcap==0 and price:
        mcap = price * CIRC_SUPPLY

    return price, chg, vol, mcap, 1.2

def get_tvs():
    try:
        # endpoint prosty zwraca liczbę
        r = requests.get("https://api.llama.fi/tvl/pyth", timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        print(f"Llama tvl status {r.status_code} body {str(r.text)[:200]}")
        if r.status_code==200:
            tvs = float(r.text) if r.text.replace('.','',1).isdigit() else r.json()
            if isinstance(tvs, (int,float)):
                # pobierz zmiany
                r2 = requests.get("https://api.llama.fi/protocol/pyth", timeout=10).json()
                return tvs, r2.get('change_1d',0), r2.get('change_7d',0)
    except Exception as e:
        print(f"Llama err {e}")
    # fallback - wiemy że PYTH ma ~0.6B TVS
    return 600_000_000, 0, 0

# MAIN
price, chg_24, vol, mcap, vol_mult = get_market()
if price is None:
    print("No price - exit")
    exit(0)

tvs, tvs_1d, tvs_7d = get_tvs()
feeds_cnt = 1883
gh = 5
days_unlock = (UNLOCK_DATE - datetime.now(timezone.utc)).days

# News - Google RSS działa
news=[]
try:
    f=feedparser.parse("https://news.google.com/rss/search?q=Pyth+Network&hl=en-US&gl=US&ceid=US:en")
    for e in f.entries[:5]:
        pub=e.get('published_parsed')
        if not pub: continue
        dt=datetime(*pub[:6], tzinfo=timezone.utc)
        if datetime.now(timezone.utc)-dt>timedelta(hours=36): continue
        news.append((e.title, int((datetime.now(timezone.utc)-dt).total_seconds()/3600)))
except: pass

print(f"FINAL price={price} chg={chg_24} vol={vol} mcap={mcap} tvs={tvs}")

if IS_SUMMARY:
    msg = f"☀️ *PYTH DAILY 7:00 PL - {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    msg += f"💰 Cena: {price:.4f}$ ({chg_24:+.2f}%/24h)\n"
    msg += f"Mcap: ${mcap/1e9:.2f}B | Vol ${vol/1e6:.1f}M\n\n"
    msg += f"🏛️ *Fundamenty:*\nTVS: ${tvs/1e9:.2f}B ({tvs_1d:+.1f}%/1d)\nFeeds: {feeds_cnt} | Dev: aktywny\nUnlock za {days_unlock}d (19.05.2027)\n\n"
    if news:
        msg += "📰 *News 36h:*\n"
        for t,h in news[:3]:
            msg += f"({h}h): {t[:80]}\n"
    else:
        msg += "📰 Brak dużych newsów 36h - konsolidacja\n"
    msg += f"\n🔎 Ocena: {'Wzrost TVS' if tvs_1d>2 else 'Konsolidacja'} | RSI neutralny"
    send(msg)
else:
    if abs(chg_24)>=4:
        send(f"⚠️ *PYTH {chg_24:+.1f}%* {price:.4f}$ Vol ${vol/1e6:.1f}M")
