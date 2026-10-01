import requests, os, sys, math
from datetime import datetime

def ema(prices, period):
    k = 2/(period+1)
    e = prices[0]
    for p in prices[1:]:
        e = p*k + e*(1-k)
    return e

def sma(prices, period):
    return sum(prices[-period:])/period if len(prices)>=period else prices[-1]

def rsi(prices, period=14):
    if len(prices)<period+1: return 55.0
    if len(set(prices[-period-1:]))<=1: return 55.0
    deltas=[prices[i]-prices[i-1] for i in range(1,len(prices))]
    gains=[d if d>0 else 0 for d in deltas[-period:]]
    losses=[-d if d<0 else 0 for d in deltas[-period:]]
    avg_g=sum(gains)/period or 0.00001
    avg_l=sum(losses)/period or 0.00001
    rs=avg_g/avg_l
    return 100-(100/(1+rs))

def macd_calc(prices):
    if len(prices)<26: return 0,0,0
    e12=ema(prices[-26:],12)
    e26=ema(prices[-26:],26)
    ml=e12-e26
    sig_list=[]
    for i in range(9):
        slice_p=prices[-(26+9-i):-(9-i) or None]
        if len(slice_p)>=12:
            sig_list.append(ema(slice_p[-26:],12)-ema(slice_p[-26:],26))
    sig=ema(sig_list,9) if sig_list else 0
    return ml,sig,ml-sig

def bollinger(prices, period=20):
    if len(prices)<period: return prices[-1],prices[-1],prices[-1]
    m=sma(prices,period)
    std=math.sqrt(sum((x-m)**2 for x in prices[-period:])/period)
    return m-2*std,m,m+2*std

def atr_calc(klines, period=14):
    trs=[]
    for i in range(1,len(klines)):
        h=float(klines[i][2]); l=float(klines[i][3]); pc=float(klines[i-1][4])
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-period:])/period if trs else 0

def get_klines(limit=200):
    for url in [
        f"https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}",
        f"https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}"
    ]:
        try:
            r=requests.get(url,timeout=10).json()
            if isinstance(r,list) and len(r)>=50:
                return r
        except: pass
    return None

def get_coingecko():
    try:
        url="https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
        r=requests.get(url,timeout=10).json()
        md=r['market_data']
        return md['current_price']['usd'], md['price_change_percentage_24h'], md['market_cap']['usd']/1e9, md['total_volume']['usd']/1e6
    except:
        return 0.0769,-0.3,0.607,34.1

def get_funding():
    try:
        f=requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=PYTHUSDT",timeout=10).json()
        return float(f.get('lastFundingRate',0.0001))*100, 45.2
    except:
        return 0.01,45.2

def get_tvs():
    try:
        r=requests.get("https://api.llama.fi/protocol/pyth-network",timeout=10).json()
        tvs=float(r.get('tvl',3.589e9))/1e9
        if tvs<0.1:
            r2=requests.get("https://api.llama.fi/oracles",timeout=10).json()
            for o in r2:
                if 'pyth' in o['name'].lower():
                    tvs=float(o['tvl'])/1e9; break
        return tvs if tvs>0.1 else 3.589
    except:
        return 3.589

def send_telegram(text):
    token=os.getenv("TELEGRAM_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":text,"parse_mode":"Markdown"})
        except: pass

kl=get_klines()
closes=[float(x[4]) for x in kl]
vols=[float(x[5]) for x in kl]
price_cg, change_24h, mcap, vol_cg = get_coingecko()
price = closes[-1] if closes else price_cg
funding, oi = get_funding()
tvs = get_tvs()

r=rsi(closes)
ma20=sma(closes,20); ma50=sma(closes,50); ma200=sma(closes,200)
ml,sig,hist=macd_calc(closes)
bb_low,bb_mid,bb_high=bollinger(closes)
atr_v=atr_calc(kl)
vol_avg=sma(vols,20); vol_now=vols[-1]
atr_pct=atr_v/price*100 if price else 0

score=50
reasons=[]

if tvs>4.0: score+=10; reasons.append(f"TVS ${tvs:.2f}B mocny")
elif tvs<2.5: score-=10; reasons.append(f"TVS ${tvs:.2f}B slaby")
if change_24h>3: score+=5; reasons.append(f"+{change_24h:.1f}% 24h")
elif change_24h<-5: score-=5

if price>ma20>ma50>ma200:
    score+=20; reasons.append("Golden Stack MA20>MA50>MA200")
elif price>ma50 and ma50>ma200:
    score+=10; reasons.append("Trend bullish >MA50>MA200")
elif price<ma20:
    score-=15; reasons.append("Cena <MA20 - korekta")
if price<ma200:
    score-=15; reasons.append("Ponizej MA200 - bear")

if 50<r<70:
    score+=15; reasons.append(f"RSI {r:.1f} momentum")
elif r<30:
    score+=20; reasons.append(f"RSI {r:.1f} OVERSOLD DIP")
elif r>78:
    score-=20; reasons.append(f"RSI {r:.1f} OVERBOUGHT TP")
elif r>70:
    score-=10; reasons.append(f"RSI {r:.1f} wysoki")

if hist>0 and ml>sig:
    score+=15; reasons.append("MACD bullish")
elif hist<0 and ml<sig:
    score-=10; reasons.append("MACD bearish")

if bb_low<=price<=bb_mid:
    score+=5; reasons.append("Dolna polowa BB - akumulacja")
elif bb_mid<price<bb_high:
    score+=10; reasons.append("Gorna polowa BB - zdrowy trend")
elif price>=bb_high:
    score-=10; reasons.append("Gorna BB - mozliwa cofka")
elif price<=bb_low:
    score+=15; reasons.append("Dolna BB - potencjalne odbicie")

if vol_now>vol_avg*1.8:
    score+=10; reasons.append("Volume spike x1.8 - potwierdzenie")
elif vol_now<vol_avg*0.5:
    score-=5; reasons.append("Niski vol - falszywy ruch")

if funding>0.05:
    score-=20; reasons.append(f"Funding {funding:.4f}% chciwosc LONG")
elif funding>0.02:
    score-=10; reasons.append(f"Funding {funding:.4f}% wysoki")
elif funding<-0.02:
    score+=15; reasons.append(f"Funding {funding:.4f}% SQUEEZE")

if atr_pct>3: reasons.append(f"High vol {atr_pct:.1f}%")
else: reasons.append(f"Low vol {atr_pct:.1f}%")

score=max(0,min(100,score))

if score>=85: sygnal="STRONG BUY - WEJSCIE IDEALNE"
elif score>=70: sygnal="BUY"
elif score>=60: sygnal="BUY / HOLD"
elif score<=20: sygnal="STRONG SELL - UCIEKAJ"
elif score<=35: sygnal="SELL / TAKE PROFIT"
else: sygnal="NEUTRAL - CZEKAJ"

now=datetime.now().strftime("%d.%m.%Y %H:%M")
is_morning=datetime.utcnow().hour==5

should=is_morning or score>=80 or score<=25
if not should:
    print(f"[{now}] {price:.4f}$ | {score}/100 SKIP")
    sys.exit(0)

if is_morning:
    header=f"PYTH DAILY v7 MAX - {now}\n\n"
else:
    header=f"PYTH ALERT v7 MAX {score}/100 - {now}\n\n"

msg=header
msg+=f"Cena: {price:.4f}$ ({change_24h:+.2f}% 24h)\n"
msg+=f"Mcap: ${mcap:.3f}B | Vol CG ${vol_cg:.1f}M\n"
msg+=f"RSI: {r:.1f} | Power: {score}/100 {sygnal}\n\n"
msg+=f"TA: MA20 {ma20:.4f} | MA50 {ma50:.4f} | MA200 {ma200:.4f}\n"
msg+=f"MACD hist {hist:+.5f} | BB {bb_low:.4f}-{bb_high:.4f}\n"
msg+=f"ATR {atr_pct:.2f}%\n\n"
msg+=f"Fundamenty: TVS ${tvs:.2f}B | Funding {funding:+.4f}%\n\n"
msg+=f"Analiza:\n" + "\n".join([f"- {x}" for x in reasons]) + f"\n\n{sygnal}"

print(msg)
send_telegram(msg)
