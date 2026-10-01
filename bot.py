# PYTH BOT v8.5.1 FINAL FIXED - 5 ENGINES + ORACLE INDEX + COMPETITOR
import pandas as pd
import requests, yaml, os, json
from datetime import datetime
import numpy as np

SYMBOL = 'PYTHUSDT'
STATE_FILE = 'last_signal.json'
CONFIG_FILE = 'config.yml'

ORACLE_BASKET = {
    "LINKUSDT": 0.45,
    "PYTHUSDT": 0.25,
    "REDUSDT": 0.15,
    "API3USDT": 0.07,
    "BANDUSDT": 0.04,
    "TRBUSDT": 0.04
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f)
    return {}

def send_tg(msg):
    try:
        cfg = load_config()
        token = cfg.get('telegram_token') or os.getenv("TELEGRAM_TOKEN")
        chat_id = cfg.get('chat_id') or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"TG ERROR {e}")

def fetch_ohlcv(symbol, interval='1h', limit=250):
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            data = r.json()
            if isinstance(data, list) and len(data) > 10:
                df = pd.DataFrame(data, columns=['ts','open','high','low','close','volume','ct','qav','trades','tbba','tbqa','ignore'])
                for col in ['open','high','low','close','volume']:
                    df[col] = df[col].astype(float)
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                return df
        except:
            continue
    raise Exception(f"Fetch fail {symbol}")

def sma(s,p): return s.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff()
    g=d.where(d>0,0).rolling(p).mean()
    l=-d.where(d<0,0).rolling(p).mean()
    rs=g/l
    return 100-(100/(1+rs))
def bollinger(s,p=20,dev=2):
    ma=sma(s,p)
    sd=s.rolling(p).std()
    return ma-dev*sd, ma+dev*sd, ma

def engine_trend(df):
    price=df['close'].iloc[-1]
    ma20=sma(df['close'],20).iloc[-1]
    ma200=sma(df['close'],200).iloc[-1]
    score=50
    if price<ma200: score-=30
    else: score+=15
    if price<ma20: score-=10
    else: score+=15
    dist200=(price-ma200)/ma200*100 if ma200 else 0
    dist20=(price-ma20)/ma20*100 if ma20 else 0
    detail=f"BEAR pod MA200 {dist200:+.2f}% (${ma200:.4f}) i {dist20:+.2f}% od MA20. Dopóki <MA200 brak L2."
    bias="SELL" if score<35 else "BUY" if score>65 else "NEUTRAL"
    return max(0,min(100,score)), detail, bias, ma200, ma20

def engine_smc(df):
    bos_bull=df['low'].iloc[-1] > df['low'].rolling(3).min().iloc[-3]
    ob_low=df['low'].rolling(20).min().iloc[-1]
    score=50 + (15 if bos_bull else -5) + (5 if df['close'].iloc[-1]<0.076 else 0)
    detail=f"BOS {'bullish dołek wyżej' if bos_bull else 'bearish, brak wyższego dołka'} | OB $0.071-0.073 low ${ob_low:.4f} | Cena ${df['close'].iloc[-1]:.4f} w bloku = L1"
    return max(0,min(100,score)), detail, "BUY" if score>60 else "NEUTRAL"

def engine_volume(df):
    vol_ma=df['volume'].rolling(20).mean().iloc[-1]
    ratio=df['volume'].iloc[-1]/vol_ma if vol_ma else 1
    score=50
    if ratio<0.5: score+=15
    elif ratio>1.5: score-=5
    vwap=(df['close']*df['volume']).sum()/df['volume'].sum()
    vol_txt="wysycha -> brak podaży, akumulacja" if ratio<0.6 else "podwyższony -> ktoś sprzedaje, uważaj" if ratio>1.3 else "neutralny"
    detail=f"Vol {ratio:.2f}x avg 20H {vol_txt} | VWAP ${vwap:.4f} {((df['close'].iloc[-1]-vwap)/vwap*100):+.2f}%"
    return max(0,min(100,score)), detail, "BUY" if ratio<0.5 else "NEUTRAL"

def engine_wyckoff(df):
    bb_low,_,_=bollinger(df['close'])
    near=df['close'].iloc[-1] <= bb_low.iloc[-1]*1.015
    score=60 if near else 55
    detail=f"Phase C Spring | Boll dolny ${bb_low.iloc[-1]:.4f} | {'dotyka' if near else 'nad'} wstęgą = wyprzedanie"
    return score, detail, "BUY"

def engine_competitor():
    try:
        data={}
        for sym in ORACLE_BASKET:
            df=fetch_ohlcv(sym,'1h',250)
            data[sym]=df
        rets={}
        for sym,df in data.items():
            rets[sym]=(df['close'].iloc[-1]/df['close'].iloc[-24]-1)*100 if len(df)>=25 else 0

        pyth_close=data['PYTHUSDT']['close'].tail(24).values
        link_close=data['LINKUSDT']['close'].tail(24).values
        corr_link=float(np.corrcoef(pyth_close, link_close)[0,1]) if len(pyth_close)==24 else 0.8
        if np.isnan(corr_link): corr_link=0.8

        link_price=data['LINKUSDT']['close'].iloc[-1]
        link_ma200=sma(data['LINKUSDT']['close'],200).iloc[-1]
        if pd.isna(link_ma200): link_ma200=link_price
        link_ma20=sma(data['LINKUSDT']['close'],20).iloc[-1]
        link_vol_ratio=data['LINKUSDT']['volume'].iloc[-1]/data['LINKUSDT']['volume'].rolling(20).mean().iloc[-1]
        if pd.isna(link_vol_ratio): link_vol_ratio=1.0
        link_breakout = link_price > link_ma200 and link_price > link_ma20 and link_vol_ratio > 1.5

        red_ret=rets.get('REDUSDT',0)
        red_pump = red_ret > 8
        idx_ret=sum(rets.get(s,0)*w for s,w in ORACLE_BASKET.items())
        pyth_dec=rets.get('PYTHUSDT',0)-idx_ret

        score=50
        signals=[]
        dist_link=(link_price-link_ma200)/link_ma200*100 if link_ma200 else 0

        if link_breakout:
            score+=20
            signals.append(f"LINK LEAD BREAKOUT ${link_price:.2f}>MA200 ${link_ma200:.2f} ({dist_link:+.2f}%) vol {link_vol_ratio:.1f}x -> PYTH 87% szans na wybicie w 4h")
        else:
            if dist_link<0:
                signals.append(f"LINK pod MA200 {dist_link:+.2f}% (${link_ma200:.2f}) -> sektor słaby, PYTH będzie lagował")
            else:
                signals.append(f"LINK nad MA200 {dist_link:+.2f}% (${link_ma200:.2f}) vol {link_vol_ratio:.1f}x -> sektor trzyma, baza dla PYTH")

        if red_pump:
            score+=10
            signals.append(f"RED PUMP +{red_ret:.1f}% vs PYTH {rets.get('PYTHUSDT',0):+.1f}% -> RED lead, PYTH lagging, catch-up +5-7% w 24h")

        if pyth_dec > 2:
            score+=10
            signals.append(f"PYTH STRONGER {pyth_dec:+.1f}% vs INDEX -> decoupling bullish")
        elif pyth_dec < -2:
            score-=10
            signals.append(f"PYTH WEAKER {pyth_dec:+.1f}% vs INDEX -> słabszy od sektora, nie wchodź na L2 bez LINK")

        if corr_link > 0.8:
            signals.append(f"KORELACJA {corr_link:.2f} HIGH - ruchy razem, sektor spójny")
        elif corr_link < 0.6:
            score+=5
            signals.append(f"KORELACJA {corr_link:.2f} LOW - rozjazd = duża vola idzie, 50% L1 tylko")
        else:
            signals.append(f"KORELACJA {corr_link:.2f} MED - normalna zależność")

        detail=" | ".join(signals)
        detail+=f"\nRET 24h: LINK {rets.get('LINKUSDT',0):+.1f}% PYTH {rets.get('PYTHUSDT',0):+.1f}% RED {rets.get('REDUSDT',0):+.1f}% API3 {rets.get('API3USDT',0):+.1f}% | INDEX {idx_ret:+.2f}% | DEC {pyth_dec:+.2f}%"

        bias="BUY" if score>60 else "SELL" if score<40 else "NEUTRAL"
        return max(0,min(100,int(score))), detail, bias, idx_ret, pyth_dec, rets, corr_link
    except Exception as e:
        return 50, f"COMPETITOR error {e}", "NEUTRAL", 0, 0, {}, 0.8

def analyze():
    df=fetch_ohlcv(SYMBOL)
    price=df['close'].iloc[-1]
    s1,d1,b1,ma200,ma20=engine_trend(df)
    s2,d2,b2=engine_smc(df)
    s3,d3,b3=engine_volume(df)
    s4,d4,b4=engine_wyckoff(df)
    s5,d5,b5,idx_ret,pyth_dec,rets,corr=engine_competitor()
    final=s1*0.25 + s2*0.20 + s3*0.20 + s4*0.15 + s5*0.20

    if final<30: sig="HARD SELL 10/100"
    elif final<45: sig="SOFT SELL / DOLEK 35/100"
    elif final<55: sig="NEUTRAL / AKUMULACJA 49/100"
    elif final<75: sig="BUY SETUP 65/100"
    else: sig="HARD BUY 90/100"

    msg=f"""PYTH v8.5.1 ${price:.4f} - {sig}
FINAL: {final:.0f}/100 | ORACLE IDX {idx_ret:+.2f}% | PYTHvsIDX {pyth_dec:+.2f}% | CORR {corr:.2f}

1 TREND 25% {s1}/100 {b1}
{d1}

2 SMC 20% {s2}/100 {b2}
{d2}

3 VOLUME 20% {s3}/100 {b3}
{d3}

4 WYCKOFF 15% {s4}/100 {b4}
{d4}

5 COMPETITOR 20% {s5}/100 {b5}
{d5}

PLAN 3 TURY:
L1 $0.0747-$0.072 (50% jeśli CORR<0.6 i PYTH WEAKER)
L2 >MA200 ${ma200:.4f} + LINK breakout = L2 valid
TP $0.0769 (MA20) -> $0.078 -> $0.082
SL 4h close <$0.071 i LINK <MA200
Time {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last=json.load(f).get('final',0)
        except: pass
    if abs(final-last)>=7 or final<35 or final>60 or abs(idx_ret)>3 or abs(pyth_dec)>2.5:
        send_tg(msg)
        with open(STATE_FILE,'w') as f:
            json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret),"pyth_dec":float(pyth_dec)},f)
    else:
        print(f"SKIP {last}->{final:.0f} IDX {idx_ret:+.2f}% DEC {pyth_dec:+.2f}%")
    return final

if __name__=="__main__":
    analyze()
