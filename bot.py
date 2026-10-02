import requests, os, sys, time
from datetime import datetime, timezone

def ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]: e = p*k + e*(1-k)
    return e

def get_rsi(prices, p=14):
    if len(set(prices[-p:])) <= 1: return 55.0
    deltas = [prices[i]-prices[i-1] for i in range(1,len(prices))]
    gains = [d if d>0 else 0 for d in deltas[-p:]]
    losses = [-d if d<0 else 0 for d in deltas[-p:]]
    ag = sum(gains)/p; al = sum(losses)/p
    return 100.0 if al==0 else 100 - (100/(1+ag/al))

def get_macd(prices):
    e12 = ema(prices,12); e26 = ema(prices,26); ml = e12-e26
    macds = [ema(prices[:i+1],12)-ema(prices[:i+1],26) for i in range(26,len(prices))]
    sig = ema(macds,9) if len(macds)>=9 else macds[-1] if macds else 0
    return ml, sig, ml-sig

def get_bollinger(prices, p=20, s=2):
    if len(prices)<p: return prices[-1],prices[-1],prices[-1]
    sma = sum(prices[-p:])/p; var = sum((x-sma)**2 for x in prices[-p:])/p
    return sma+(var**0.5)*s, sma, sma-(var**0.5)*s

def get_stoch(h,l,c,k=14):
    if len(c)<k: return 50
    hh = max(h[-k:]); ll = min(l[-k:])
    return 50 if hh==ll else (c[-1]-ll)/(hh-ll)*100

def get_klines(limit=100):
    for url in [f"https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}", f"https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}"]:
        try:
            r = requests.get(url,timeout=10).json()
            if isinstance(r,list) and len(r)>20:
                return [float(x[4]) for x in r], [float(x[5]) for x in r], [float(x[2]) for x in r], [float(x[3]) for x in r]
        except: pass
    return [0.078]*100,[1]*100,[0.08]*100,[0.07]*100

def get_coingecko_full():
    try:
        ids = "pyth-network,chainlink,redstone"
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&price_change_percentage=24h", timeout=10).json()
        d = {x['id']: x for x in r}
        pyth = d['pyth-network']; link = d['chainlink']
        red = d.get('redstone', {'current_price':0.35,'price_change_percentage_24h':-3.2,'market_cap':350000000,'fully_diluted_valuation':1000000000,'total_volume':20000000})
        return pyth, link, red
    except:
        return {'current_price':0.0766,'price_change_percentage_24h':-2.94,'market_cap':603482000,'fully_diluted_valuation':766330000,'total_volume':21500000}, {'current_price':14.43,'price_change_percentage_24h':-0.01,'market_cap':10800000000,'fully_diluted_valuation':14500000000,'total_volume':300000000}, {'current_price':0.35,'price_change_percentage_24h':-3.2,'market_cap':350000000,'fully_diluted_valuation':1000000000,'total_volume':20000000}

def get_funding():
    try: return float(requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=PYTHUSDT",timeout=10).json().get('lastFundingRate',0.0001))*100
    except: return 0.01

def get_funding_history():
    # 1. próba Binance fapi (3 hosty)
    headers = {"User-Agent":"Mozilla/5.0"}
    for base in ["https://fapi.binance.com/fapi/v1/fundingRate","https://fapi1.binance.com/fapi/v1/fundingRate","https://fapi2.binance.com/fapi/v1/fundingRate"]:
        try:
            r = requests.get(f"{base}?symbol=PYTHUSDT&limit=90", headers=headers, timeout=8).json()
            if isinstance(r,list) and len(r)>=3:
                rates = [float(x['fundingRate'])*100 for x in r]
                return rates[-1], sum(rates[-3:])/3, sum(rates[-21:])/21 if len(rates)>=21 else sum(rates)/len(rates), sum(rates)/len(rates)
        except: pass
    # 2. fallback Coinglass public - bez klucza
    try:
        # Coinglass open API v4
        url = "https://open-api-v4.coinglass.com/api/futures/fundingRate/history?exchange=Binance&symbol=PYTHUSDT&interval=8h&limit=90"
        r = requests.get(url, headers={"coinglassSecret":"public"}, timeout=8).json()
        data = r.get('data') or r.get('result') or []
        if data and len(data)>=3:
            rates = [float(x.get('fundingRate',x.get('rate',0)))*100 for x in data]
            if rates:
                return rates[-1], sum(rates[-3:])/3, sum(rates[-21:])/21 if len(rates)>=21 else sum(rates)/len(rates), sum(rates)/len(rates)
    except: pass
    return None

def get_price_dynamics():
    # v9.5.6 - poprawione timestampy, działa dla hourly i daily
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network/market_chart?vs_currency=usd&days=90", timeout=10).json()
        prices = r['prices'] # [[ts, price],...]
        if len(prices)<10: return None
        cur_ts, cur_price = prices[-1]
        def pct(days):
            target = cur_ts - days*24*3600*1000
            # znajdź najbliższy punkt
            closest = min(prices, key=lambda x: abs(x[0]-target))
            prev = closest[1]
            return (cur_price-prev)/prev*100 if prev else 0
        return pct(1), pct(7), pct(30), pct(90)
    except Exception as e:
        return None

def get_tvs():
    try: return float(requests.get("https://api.llama.fi/protocol/pyth-network",timeout=10).json().get('tvl',3.589e9))/1e9
    except: return 3.589

def get_fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1",timeout=10).json()['data'][0]
        return int(d['value']), d['value_classification']
    except: return 50, "Neutral"

def get_oracle_tvs():
    try:
        r = requests.get("https://api.llama.fi/oracles",timeout=10).json()
        data = {o['name'].lower(): float(o['tvl'])/1e9 for o in r}
        link, pyth, red = data.get('chainlink',39.3), data.get('pyth',2.79), data.get('redstone',4.1)
        total = sum([v for v in data.values() if v>0.1])
        share = (pyth/total*100) if total else 5.9
        return link, pyth, red, share
    except: return 39.3,2.79,4.1,5.9

def get_oi():
    try: return float(requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=PYTHUSDT",timeout=10).json()['openInterest'])
    except: return 961000000

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN"); chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: print(text); return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)

def analyze(force_report=False):
    pyth, link, red = get_coingecko_full()
    price = pyth['current_price']; chg = pyth['price_change_percentage_24h']
    mcap = pyth['market_cap']; fdv = pyth['fully_diluted_valuation']; vol = pyth['total_volume']

    funding = get_funding(); fh = get_funding_history(); pd = get_price_dynamics()
    tvs = get_tvs(); closes, volumes, highs, lows = get_klines()
    rsi = get_rsi(closes); fg_val, fg_class = get_fear_greed()
    link_tvs, pyth_tvs, red_tvs, share = get_oracle_tvs()

    ema9 = ema(closes,9); ema21 = ema(closes,21); ema200 = ema(closes,200)
    ml, ms, mh = get_macd(closes); bb_up, _, bb_low = get_bollinger(closes); stoch = get_stoch(highs,lows,closes)

    reasons = []; score = 50
    if price > ema9 > ema21: score+=10; reasons.append(f"Trend +10: cena > EMA9 ${ema9:.4f} > EMA21")
    elif price < ema9 < ema21: score-=10; reasons.append(f"Trend -10: cena < EMA9 < EMA21")
    else: reasons.append(f"Trend 0: EMA9 ${ema9:.4f} vs EMA21 ${ema21:.4f}")

    if price > ema200*1.002: score+=8; reasons.append(f"Trend +8: nad EMA200 ${ema200:.4f}")
    elif price < ema200*0.998: score-=8; reasons.append(f"Trend -8: pod EMA200 ${ema200:.4f}")
    else: reasons.append(f"Trend 0: przy EMA200 ${ema200:.4f}")

    if mh>0 and ml>ms: score+=10; reasons.append(f"MACD +10: {mh:+.5f} bycze")
    elif mh<0: score-=10; reasons.append(f"MACD -10: {mh:+.5f} niedźwiedzie")

    if rsi<30 and price<bb_low: score+=15; reasons.append(f"Wyckoff +15: RSI {rsi:.0f} + dolna BB")
    elif rsi>70 and price>bb_up*0.99: score-=15; reasons.append(f"Wyckoff -15: RSI {rsi:.0f} + górna BB")

    if stoch>85: score-=15; reasons.append(f"Stoch -15: {stoch:.0f} max wykupienie")
    elif stoch>80: score-=8; reasons.append(f"Stoch -8: {stoch:.0f} wykupienie")
    elif stoch<20: score+=10; reasons.append(f"Stoch +10: {stoch:.0f} wyprzedanie")

    if price>bb_up*0.99: score-=10; reasons.append(f"BB -10: cena przy górnej {bb_up:.4f}")
    if price<bb_low*1.01: score+=10; reasons.append(f"BB +10: cena przy dolnej {bb_low:.4f}")

    if funding>0.05: score-=20; reasons.append(f"Funding -20: {funding:.4f}% przegrzany")
    elif funding<-0.02: score+=15; reasons.append(f"Funding +15: {funding:.4f}% shorty")

    if fg_val<25: score+=15; reasons.append(f"F&G +15: {fg_val} strach")
    elif fg_val>75: score-=10; reasons.append(f"F&G -10: {fg_val} chciwość")

    score = max(0,min(100,score))
    if score>=80: decyzja="KUPUJ 🔥"
    elif score>=60: decyzja="Można kupować ✅"
    elif score<=30: decyzja="SPRZEDAJ ⚠️"
    else: decyzja="CZEKAJ ➡️"

    now_str = datetime.now().strftime("%d.%m %H:%M")
    utc_hour = datetime.now(timezone.utc).hour
    slots = {5:"☀️ Poranny 7:00",13:"🌤️ Popołudniowy 15:00",19:"🌙 Wieczorny 21:00"}
    slot_header = slots.get(utc_hour)
    if not (force_report or slot_header or score>=80 or score<=25 or fg_val<20 or fg_val>85):
        print(f"[{now_str}] cicho {score}"); sys.exit(0)

    header = f"🔥 *TEST v9.5.6 FINAL*" if force_report else (slot_header or f"🚨 *ALERT {score}/100*") + f" - {now_str}"
    unlock_days = (datetime(2027,5,19,tzinfo=timezone.utc)-datetime.now(timezone.utc)).days
    oi = get_oi(); oi_usd = oi * price
    diff_red = pyth['price_change_percentage_24h'] - red['price_change_percentage_24h']
    diff_link = pyth['price_change_percentage_24h'] - link['price_change_percentage_24h']

    if chg < -2 and diff_link < -2: dol_typ = f"BRUDNY DÓŁ ({diff_link:+.1f}% vs LINK)"
    elif chg < -2 and abs(diff_link) < 1: dol_typ = f"CZYSTY DÓŁ"
    elif score <= 35 and rsi > 65: dol_typ = f"FAŁSZYWA SPRZEDAŻ RSI {rsi:.0f}"
    else: dol_typ = "Neutralny"

    if fh:
        now_f, f24, f7, f30 = fh
        def arrow(a,b):
            d=a-b
            if abs(d)<0.001: return "→"
            return "↓" if d<0 else "↑"
        def arrow2(a,b):
            d=a-b
            if abs(d)<0.001: return "→"
            return "↓↓" if d<-0.008 else "↑↑" if d>0.008 else ("↓" if d<0 else "↑")
        funding_line = f"Funding {now_f:+.4f}% (24h {f24:+.4f}% {arrow(now_f,f24)} | 7d {f7:+.4f}% {arrow2(now_f,f7)} | 30d {f30:+.4f}% {arrow2(now_f,f30)})"
    else:
        funding_line = f"Funding {funding:+.4f}%"

    if pd:
        p1,p7,p30,p90 = pd
        price_dyn = f"PYTH dyn: 24h {p1:+.1f}% | 7d {p7:+.1f}% | 30d {p30:+.1f}% | 90d {p90:+.1f}%"
    else:
        price_dyn = ""

    msg = f"{header}\n\n"
    msg += f"PYTH ${price:.4f} ({chg:+.2f}%) Mcap ${mcap/1e6:.0f}M FDV ${fdv/1e6:.0f}M\n"
    msg += f"Supply 7.875B/10B | Vol ${vol/1e6:.1f}M OI ${oi_usd/1e6:.1f}M | TVS ${tvs:.2f}B\n\n"
    msg += f"*Oracle 24h:*\nLINK ${link['current_price']:.2f} ({link['price_change_percentage_24h']:+.2f}%)\nPYTH ${pyth['current_price']:.4f} ({pyth['price_change_percentage_24h']:+.2f}%)\nRED ${red['current_price']:.4f} ({red['price_change_percentage_24h']:+.2f}%)\n"
    msg += f"PYTH vs RED {diff_red:+.2f}% vs LINK {diff_link:+.2f}% - {dol_typ}\n\n"
    msg += f"*TA:* EMA9 ${ema9:.4f} EMA200 ${ema200:.4f}\nMACD {mh:+.5f} RSI {rsi:.0f} Stoch {stoch:.0f} BB [{bb_low:.4f}-{bb_up:.4f}]\n"
    msg += f"F&G {fg_val} {fg_class} | {funding_line} | Siła {score}/100\n"
    if price_dyn: msg += f"{price_dyn}\n"
    msg += f"TVS: LINK ${link_tvs:.0f}B | PYTH ${pyth_tvs:.1f}B ({share:.1f}%) | RED ${red_tvs:.1f}B\n\n"
    msg += f"*DLACZEGO {score}/100?*\n"
    for r in reasons: msg += f"- {r}\n"
    msg += f"\nWniosek: *{decyzja}* | Unlock {unlock_days}d"
    print(msg); send_telegram(msg)

if __name__ == "__main__":
    analyze(force_report=False)
