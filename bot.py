# PYTH BOT v8.6 HUMAN - 5 ENGINES + LUDZKI KOMUNIKAT
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
    return max(0,min(100,score)), ma200, ma20

def engine_smc(df):
    bos_bull=df['low'].iloc[-1] > df['low'].rolling(3).min().iloc[-3]
    ob_low=df['low'].rolling(20).min().iloc[-1]
    score=50 + (15 if bos_bull else -5) + (5 if df['close'].iloc[-1]<0.076 else 0)
    return max(0,min(100,score)), ob_low

def engine_volume(df):
    vol_ma=df['volume'].rolling(20).mean().iloc[-1]
    ratio=df['volume'].iloc[-1]/vol_ma if vol_ma else 1
    score=50
    if ratio<0.5: score+=15
    elif ratio>1.5: score-=5
    vwap=(df['close']*df['volume']).sum()/df['volume'].sum()
    return max(0,min(100,score)), ratio, vwap

def engine_wyckoff(df):
    bb_low,bb_high,bb_mid=bollinger(df['close'])
    near=df['close'].iloc[-1] <= bb_low.iloc[-1]*1.015
    score=60 if near else 55
    width=(bb_high.iloc[-1]-bb_low.iloc[-1])/bb_mid.iloc[-1]*100 if bb_mid.iloc[-1] else 0
    return score, bb_low.iloc[-1], width, near

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
        idx_ret=sum(rets.get(s,0)*w for s,w in ORACLE_BASKET.items())
        pyth_dec=rets.get('PYTHUSDT',0)-idx_ret
        score=50
        if link_breakout: score+=20
        if red_ret>8: score+=10
        if pyth_dec>2: score+=10
        elif pyth_dec<-2: score-=10
        return max(0,min(100,int(score))), idx_ret, pyth_dec, rets, corr_link, link_price, link_ma200, link_vol_ratio, link_breakout
    except Exception as e:
        return 50, 0, 0, {}, 0.8, 0, 0, 1.0, False

def analyze():
    df=fetch_ohlcv(SYMBOL)
    price=df['close'].iloc[-1]
    s1,ma200,ma20=engine_trend(df)
    s2,ob_low=engine_smc(df)
    s3,ratio,vwap=engine_volume(df)
    s4,bb_low,bb_width,near=engine_wyckoff(df)
    s5,idx_ret,pyth_dec,rets,corr,link_price,link_ma200,link_vol,link_break=engine_competitor()
    final=s1*0.25 + s2*0.20 + s3*0.20 + s4*0.15 + s5*0.20

    if final<30: sig="HARD SELL 10/100 - uciekaj"
    elif final<45: sig="SOFT SELL / DOLEK 35/100 - dno, ale jeszcze nie kupuj wszystkiego"
    elif final<55: sig="NEUTRAL / AKUMULACJA 49/100 - zbieraj powoli"
    elif final<75: sig="BUY SETUP 65/100 - można ładować"
    else: sig="HARD BUY 90/100"

    dist200=(price-ma200)/ma200*100 if ma200 else 0
    dist20=(price-ma20)/ma20*100 if ma20 else 0

    vol_txt="wysycha, nikt nie chce sprzedawać na dołku - to dobrze dla L1" if ratio<0.6 else "podwyższony, ktoś jeszcze sprzedaje - uważaj na L1" if ratio>1.3 else "neutralny"
    sector_txt=f"LINK {rets.get('LINKUSDT',0):+.1f}% vs PYTH {rets.get('PYTHUSDT',0):+.1f}% | PYTH {pyth_dec:+.2f}% {'słabszy od sektora = ktoś dumpuje PYTH' if pyth_dec<-1 else 'silniejszy = przejmuje narrację' if pyth_dec>1 else 'zgodny z sektorem'}"
    corr_txt="ROZJAZD - duża vola idzie, będzie strzał w jedną stronę, dlatego tylko 50% L1" if corr<0.6 else "spójny - sektor idzie razem, bezpieczniej" if corr>0.8 else "normalny"

    # HUMAN MESSAGE
    msg=f"""PYTH ${price:.4f} | FINAL {final:.0f}/100 - {sig}

ANALIZA DLACZEGO {final:.0f}?

Trend {s1}/100 SELL bo jesteśmy {dist200:+.2f}% pod MA200 (${ma200:.4f}). To jest główny opór. Dopóki nie wrócimy nad MA200, nie ma L2. Cena też {dist20:+.2f}% pod MA20 (${ma20:.4f}).

Ale: Wyckoff {s4}/100 BUY - jesteśmy na dolnej Bandzie ${bb_low:.4f} (szerokość {bb_width:.2f}%). {'Dotykamy dolnej wstęgi = wyprzedanie, Spring możliwy' if near else 'Jeszcze nad wstęgą'}. Volume {s3}/100 - {ratio:.2f}x avg 20H = {vol_txt}. VWAP ${vwap:.4f}, jesteśmy {((price-vwap)/vwap*100):+.2f}% nad VWAP.

Sektor Oracle {idx_ret:+.2f}%: {sector_txt}. Korelacja PYTH/LINK {corr:.2f} = {corr_txt}. LINK ${link_price:.2f} {'BREAKOUT' if link_break else f'nad MA200 {((link_price-link_ma200)/link_ma200*100):+.2f}% vol {link_vol:.1f}x - trzyma sektor, baza dla PYTH' if link_price>link_ma200 else f'pod MA200 - sektor słaby'}.

CO TO JEST L1 i L2? (dla Ciebie)

L1 = STREFA ZAKUPU NA DOŁKU ($0.0747-$0.072, OB low ${ob_low:.4f}). Tu akumulujesz bo FINAL 40 to dołek 35/100. Dzielisz: 50% teraz po ${price:.4f}, drugie 50% jak zejdzie do $0.072 LUB jak korelacja wróci >0.7 i PYTH przestanie być weaker. Dlaczego 50%? Bo corr LOW + PYTH weaker = może jeszcze zjechać, nie ładuj wszystkiego.

L2 = POTWIERDZENIE ŻE DOŁEK KONIEC (>${ma200:.4f}). Jak zamkniemy 4h nad MA200 ${ma200:.4f} + LINK zrobi breakout vol>1.5x (teraz {link_vol:.1f}x), to znaczy że Spring zadziałał, duzi gracze weszli i idziemy na TP. Dopiero na L2 dokładasz resztę pozycji i przestawiasz SL na breakeven. TERAZ L2 NIEAKTYWNE - jesteśmy pod MA200.

PLAN 3 TURY:
L1 50% teraz, 50% $0.072
L2 >${ma200:.4f} + LINK breakout
TP1 ${ma20:.4f} (MA20) -> TP2 $0.078 FVG -> TP3 $0.082 (i $0.089 jeśli RED pump)
SL 4h close <$0.071 + LINK traci MA200

Skład: T25% {s1} + SMC20% {s2} + VOL20% {s3} + WYK15% {s4} + COMP20% {s5} = {final:.0f}
Time {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last=json.load(f).get('final',0)
        except: pass
    if abs(final-last)>=7 or final<35 or final>60 or abs(idx_ret)>3 or abs(pyth_dec)>2.5 or corr<0.55:
        send_tg(msg)
        with open(STATE_FILE,'w') as f:
            json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret)},f)
    else:
        print(f"SKIP {last}->{final:.0f}")
    return final

if __name__=="__main__":
    analyze()
