import requests, os, sys, math
from datetime import datetime

def ema(prices, period):
    k = 2/(period+1); e = prices[0]
    for p in prices[1:]: e = p*k + e*(1-k)
    return e
def sma(prices, period):
    return sum(prices[-period:])/period if len(prices)>=period else prices[-1]
def rsi(prices, period=14):
    if len(prices)<period+1: return 55.0
    if len(set(prices[-period-1:]))<=1: return 55.0
    deltas=[prices[i]-prices[i-1] for i in range(1,len(prices))]
    gains=[d if d>0 else 0 for d in deltas[-period:]]
    losses=[-d if d<0 else 0 for d in deltas[-period:]]
    avg_g=sum(gains)/period or 0.00001; avg_l=sum(losses)/period or 0.00001
    return 100-(100/(1+avg_g/avg_l))
def macd_calc(prices):
    if len(prices)<26: return 0,0,0
    e12=ema(prices[-26:],12); e26=ema(prices[-26:],26); ml=e12-e26
    sig_list=[]
    for i in range(9):
        sp=prices[-(26+9-i):-(9-i) or None]
        if len(sp)>=12: sig_list.append(ema(sp[-26:],12)-ema(sp[-26:],26))
    sig=ema(sig_list,9) if sig_list else 0
    return ml,sig,ml-sig
def bollinger(prices, period=20):
    if len(prices)<period: return prices[-1],prices[-1],prices[-1]
    m=sma(prices,period); std=math.sqrt(sum((x-m)**2 for x in prices[-period:])/period)
    return m-2*std,m,m+2*std
def atr_calc(klines, period=14):
    trs=[]
    for i in range(1,len(klines)):
        h=float(klines[i][2]); l=float(klines[i][3]); pc=float(klines[i-1][4])
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-period:])/period if trs else 0
def get_klines(limit=200):
    for url in [f"https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}", f"https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}"]:
        try:
            r=requests.get(url,timeout=10).json()
            if isinstance(r,list) and len(r)>=50: return r
        except: pass
    return None
def get_coingecko():
    try:
        url="https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
        r=requests.get(url,timeout=10).json(); md=r['market_data']
        return md['current_price']['usd'], md['price_change_percentage_24h'], md['market_cap']['usd']/1e9, md['total_volume']['usd']/1e6
    except: return 0.0769,-0.3,0.607,34.1
def get_futures_live(price):
    funding=0.01; oi=45.2; ls_ratio=1.0; ls_accounts=1.0
    try:
        prem=requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=PYTHUSDT",timeout=10).json()
        funding=float(prem.get('lastFundingRate',0.0001))*100
    except: pass
    try:
        oi_r=requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=PYTHUSDT",timeout=10).json()
        oi=float(oi_r.get('openInterest',0))*price/1e6
        if oi<1: oi=45.2
    except: pass
    try:
        ls=requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=PYTHUSDT&period=5m&limit=1",timeout=10).json()
        if isinstance(ls,list) and len(ls)>0:
            ls_accounts=float(ls[0].get('longShortRatio',1.0))
    except: pass
    try:
        ls2=requests.get("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=PYTHUSDT&period=5m&limit=1",timeout=10).json()
        if isinstance(ls2,list) and len(ls2)>0:
            ls_ratio=float(ls2[0].get('longShortRatio',1.0))
    except: pass
    return funding, oi, ls_accounts, ls_ratio
def get_tvs():
    try:
        r=requests.get("https://api.llama.fi/protocol/pyth-network",timeout=10).json()
        tvs=float(r.get('tvl',3.589e9))/1e9
        if tvs<0.1:
            r2=requests.get("https://api.llama.fi/oracles",timeout=10).json()
            for o in r2:
                if 'pyth' in o['name'].lower(): tvs=float(o['tvl'])/1e9; break
        return tvs if tvs>0.1 else 3.589
    except: return 3.589
def send_telegram(text):
    token=os.getenv("TELEGRAM_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":text})
        except: pass

kl=get_klines(); closes=[float(x[4]) for x in kl]; vols=[float(x[5]) for x in kl]
price_cg, change_24h, mcap, vol_cg = get_coingecko()
price = closes[-1] if closes else price_cg
funding, oi_live, ls_acc, ls_pos = get_futures_live(price)
tvs = get_tvs()

r=rsi(closes); ma20=sma(closes,20); ma50=sma(closes,50); ma200=sma(closes,200)
ml,sig,hist=macd_calc(closes); bb_low,bb_mid,bb_high=bollinger(closes)
atr_v=atr_calc(kl); vol_avg=sma(vols,20); vol_now=vols[-1]; atr_pct=atr_v/price*100 if price else 0

score=50; reasons=[]; level1=[]; level2=[]

if tvs>4.0: score+=10
elif tvs<2.5: score-=10
if change_24h>3: score+=5
elif change_24h<-5: score-=5

if price>ma20>ma50>ma200: score+=20; reasons.append("Golden Stack MA20>MA50>MA200")
elif price>ma50 and ma50>ma200: score+=10; reasons.append("Trend bullish >MA50>MA200")
elif price<ma20: score-=15; reasons.append("Cena <MA20 - krotka korekta"); level1.append("ponizej MA20")
if price<ma200: score-=15; reasons.append("Ponizej MA200 - dlugi trend pekl"); level2.append("ponizej MA200 = HARD")

if 50<r<70: score+=15; reasons.append(f"RSI {r:.1f} momentum OK")
elif r<30: score+=20; reasons.append(f"RSI {r:.1f} OVERSOLD DIP"); level1.append("RSI oversold")
elif r>78: score-=20; reasons.append(f"RSI {r:.1f} OVERBOUGHT TP"); level2.append("RSI overbought")
elif r>70: score-=10; level1.append("RSI wysoki")

if hist>0 and ml>sig: score+=15; reasons.append("MACD bullish")
elif hist<0 and ml<sig: score-=10; reasons.append("MACD bearish"); level1.append("MACD bearish")

if bb_low<=price<=bb_mid: score+=5; reasons.append("Dolna BB - akumulacja")
elif bb_mid<price<bb_high: score+=10; reasons.append("Gorna BB - zdrowy")
elif price>=bb_high: score-=10; reasons.append("Gorna BB - cofka"); level1.append("gorna BB")
elif price<=bb_low: score+=15; reasons.append("Dolna BB - odbicie"); level1.append("dolna BB")

if vol_now>vol_avg*1.8: score+=10; reasons.append("Volume spike")
elif vol_now<vol_avg*0.5: score-=5; reasons.append("Niski vol"); level1.append("niski vol")

# FUTURES LIVE SCORING
if funding>0.05: score-=20; reasons.append(f"Funding {funding:.4f}% EXTREME LONG"); level2.append(f"Funding {funding:.3f}% HARD")
elif funding>0.02: score-=10; reasons.append(f"Funding {funding:.4f}% wysoki"); level1.append(f"Funding {funding:.3f}%")
elif funding<-0.02: score+=15; reasons.append(f"Funding {funding:.4f}% SHORT SQUEEZE"); level1.append(f"Funding {funding:.3f}% squeeze")
else: reasons.append(f"Funding {funding:.4f}% neutralny")

if oi_live>80: reasons.append(f"OI ${oi_live:.1f}M bardzo wysokie - duza dzwignia"); level2.append(f"OI ${oi_live:.0f}M HIGH")
elif oi_live<20: level1.append(f"OI ${oi_live:.0f}M niskie")

if ls_acc>2.0: score-=15; reasons.append(f"L/S Accounts {ls_acc:.2f} tlum LONG"); level2.append(f"L/S {ls_acc:.2f} crowd LONG")
elif ls_acc<0.8: score+=10; reasons.append(f"L/S Accounts {ls_acc:.2f} tlum SHORT - squeeze?"); level1.append(f"L/S {ls_acc:.2f} crowd SHORT")
else: reasons.append(f"L/S {ls_acc:.2f} balanced")

if ls_pos>2.5: score-=10; level1.append(f"Top Pos L/S {ls_pos:.2f} LONG heavy")
elif ls_pos<0.7: score+=10; level1.append(f"Top Pos L/S {ls_pos:.2f} SHORT heavy")

score=max(0,min(100,score))

if score>=80: lvl="HARD BUY"; action="Mocny KUPNA - squeeze + potwierdzony"
elif score>=60: lvl="SOFT BUY"; action="Nie panikuj - akumulacja"
elif score<=20: lvl="HARD SELL"; action="Krytyczny - rozwaz TP / nie kupuj"
elif score<=40: lvl="SOFT SELL"; action="Nie panikuj - tylko korekta"
else: lvl="NEUTRAL"; action="Trzymaj"

now = datetime.now(); hour_utc = now.hour
is_daily = hour_utc in [5, 10, 17]
is_hard = score >= 80 or score <= 20

if is_daily:
    if hour_utc == 5: daily_name = "PORANNY 7:00"
    elif hour_utc == 10: daily_name = "POLUDNIOWY 12:00"
    else: daily_name = "WIECZORNY 19:00"
    should = True
elif is_hard:
    daily_name = f"ALERT HARD {lvl}"
    should = True
else:
    print(f"[{now.strftime('%d.%m.%Y %H:%M')}] {price:.4f}$ | {score}/100 {lvl} SKIP")
    sys.exit(0)

msg=f"PYTH {daily_name} {score}/100 - {now.strftime('%d.%m.%Y %H:%M')}\n\n"
msg+=f"Cena: {price:.4f}$ ({change_24h:+.2f}%) RSI {r:.1f}\n"
msg+=f"MA20 {ma20:.4f} | MA200 {ma200:.4f} | BB {bb_low:.4f}-{bb_high:.4f}\n"
msg+=f"FUTURES LIVE: Funding {funding:+.4f}% | OI ${oi_live:.1f}M\n"
msg+=f"L/S Acc {ls_acc:.2f} | Top Pos {ls_pos:.2f} | TVS ${tvs:.2f}B\n\n"
msg+=f"POZIOM: {lvl}\nCo to znaczy: {action}\n\n"
if level1: msg+=f"SOFT: {', '.join(level1)}\n"
if level2: msg+=f"HARD: {', '.join(level2)}\n"
msg+=f"\n" + "\n".join([f"- {x}" for x in reasons])

print(msg)
send_telegram(msg)
