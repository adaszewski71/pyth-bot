# PYTH BOT v8.8 CLEAR - bez skrótów, wszystko po polsku jasno
import pandas as pd
import requests, yaml, os, json
from datetime import datetime
import numpy as np

SYMBOL = 'PYTHUSDT'
STATE_FILE = 'last_signal.json'
CONFIG_FILE = 'config.yml'
ALERT_FILE = 'last_alerts.json'

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

def load_last_alerts():
    if os.path.exists(ALERT_FILE):
        try:
            with open(ALERT_FILE) as f:
                return json.load(f)
        except: pass
    return {}

def save_alerts(alerts):
    with open(ALERT_FILE,'w') as f:
        json.dump(alerts,f)

def check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec):
    last = load_last_alerts()
    alerts = []
    red_ret = rets.get('REDUSDT',0)

    if corr < 0.55 and 'rozjazd' not in last:
        msg = f"""⚠️ OSTRZEŻENIE ROZJAZD - KORELACJA {corr:.2f} NISKA
Chainlink ${link_price:.2f} {rets.get('LINKUSDT',0):+.1f}% vs Pyth ${price:.4f} {rets.get('PYTHUSDT',0):+.1f}%
Pyth {pyth_dec:+.2f}% słabszy od całego sektora wyroczni {idx_ret:+.2f}%
Co to znaczy: będzie duży ruch w jedną stronę. Kup tylko 50% pierwszej strefy zakupowej teraz $0.0747-$0.072, czekaj aż korelacja wróci >0.7 żeby dokupić"""
        alerts.append(('rozjazd', msg))

    if price > ma200 and final > 55:
        if last.get('poziom_drugi_blisko')!= True:
            msg = f"""🚀 DRUGI POZIOM BLISKO / AKTYWNY
Pyth ${price:.4f} przebił średnią 200h ${ma200:.4f} Ocena {final:.0f}/100
Chainlink ${link_price:.2f} wolumen {link_vol:.1f}x {'Wybicie!' if link_break else 'trzyma się nad średnią'} Korelacja {corr:.2f}
Co robić: Drugi poziom aktywny - możesz dokupić resztę, przestaw Stop Loss na cenę wejścia ${price:.4f} żeby nie stracić
Cel 1 ${ma20:.4f} -> Cel 2 $0.078 -> Cel 3 $0.082"""
            alerts.append(('poziom_drugi_blisko', msg))

    if price <= 0.072 and price >= 0.069:
        if last.get('pierwszy_poziom_druga_czesc')!= round(price,4):
            msg = f"""📥 PIERWSZY POZIOM - DRUGA CZĘŚĆ WYPEŁNIONA
Pyth ${price:.4f} w dolnej części strefy zakupowej $0.071-0.073
Ocena {final:.0f} - maksymalne wyprzedanie, dokupiłeś dołek
Co robić: trzymaj, Stop Loss jak zamknie 4h poniżej $0.071 i Chainlink poniżej średniej 200h ${link_ma200:.2f}"""
            alerts.append(('pierwszy_poziom_druga_czesc', msg))

    if red_ret > 8 or (link_break and rets.get('LINKUSDT',0) > 5):
        if last.get('pump_sektora')!= round(red_ret,1):
            msg = f"""🔥 PUMP CAŁEGO SEKTORA WYROCZNI
Red +{red_ret:.1f}% vs Pyth {rets.get('PYTHUSDT',0):+.1f}% | Chainlink +{rets.get('LINKUSDT',0):+.1f}% wolumen {link_vol:.1f}x Wybicie
Pyth zostaje w tyle, nadrobi +5-7% w 24h
Ocena {final:.0f} SYGNAŁ KUPNA - ładuj pierwszy i drugi poziom"""
            alerts.append(('pump_sektora', msg))

    if price < 0.071 and link_price < link_ma200:
        if last.get('stop_loss')!= True:
            msg = f"""🛑 STOP LOSS - WYJDŹ Z POZYCJI - UTNIJ STRATĘ
Pyth ${price:.4f} poniżej $0.071 + Chainlink ${link_price:.2f} poniżej średniej 200h ${link_ma200:.2f}
Co to znaczy: cały sektor wyroczni się sypie, to nie jest dołek tylko dalszy spadek. Wyjdź z pierwszego poziomu, przyjmij małą stratę -4.5%, czekaj na nowy niższy poziom $0.069
Ocena {final:.0f} MOCNA SPRZEDAŻ"""
            alerts.append(('stop_loss', msg))

    if corr > 0.75 and last.get('rozjazd') is not None:
        if last.get('powrot_korelacji')!= True:
            msg = f"""✅ POWRÓT KORELACJI {corr:.2f} WYSOKA - SPÓJNOŚĆ WRÓCIŁA
Rozjazd zamknięty, sektor idzie razem
Można dokupić drugą połowę pierwszego poziomu, ryzyko mniejsze
Pyth {pyth_dec:+.2f}% vs sektor"""
            alerts.append(('powrot_korelacji', msg))

    for key, msg in alerts:
        send_tg(msg)
        print(f"ALERT {key}")
        last[key] = True if key in ['poziom_drugi_blisko','stop_loss','powrot_korelacji'] else round(price,4)

    if alerts:
        save_alerts(last)

def analyze():
    df=fetch_ohlcv(SYMBOL)
    price=df['close'].iloc[-1]
    s1,ma200,ma20=engine_trend(df)
    s2,ob_low=engine_smc(df)
    s3,ratio,vwap=engine_volume(df)
    s4,bb_low,bb_width,near=engine_wyckoff(df)
    s5,idx_ret,pyth_dec,rets,corr,link_price,link_ma200,link_vol,link_break=engine_competitor()
    final=s1*0.25 + s2*0.20 + s3*0.20 + s4*0.15 + s5*0.20

    if final<30: sig="MOCNA SPRZEDAŻ 10/100 - uciekaj"
    elif final<45: sig="SŁABA SPRZEDAŻ / DOŁEK 35/100 - dno, ale nie kupuj wszystkiego"
    elif final<55: sig="NEUTRALNIE / ZBIERANIE 49/100 - zbieraj powoli"
    elif final<75: sig="SYGNAŁ KUPNA 65/100 - można ładować"
    else: sig="MOCNE KUPNO 90/100"

    dist200=(price-ma200)/ma200*100 if ma200 else 0
    dist20=(price-ma20)/ma20*100 if ma20 else 0
    vol_txt="wysycha, nikt nie chce sprzedawać na dołku - dobrze dla pierwszego poziomu" if ratio<0.6 else "podwyższony, ktoś jeszcze sprzedaje - uważaj na pierwszy poziom" if ratio>1.3 else "neutralny"

    msg=f"""PYTH ${price:.4f} | OCENA KOŃCOWA {final:.0f}/100 - {sig}

DLACZEGO OCENA {final:.0f}?

Trend {s1}/100 SPRZEDAŻ bo jesteśmy {dist200:+.2f}% pod średnią 200-godzinną (${ma200:.4f}). To jest główny opór. Dopóki nie wrócimy nad średnią 200h, nie ma drugiego poziomu. Cena też {dist20:+.2f}% pod średnią 20h (${ma20:.4f}).

Wyckoff {s4}/100 KUPNO - dolna wstęga Bollingera ${bb_low:.4f} (szerokość {bb_width:.2f}%). {'Dotykamy dolnej wstęgi = wyprzedanie, możliwe odbicie Spring' if near else 'Nad wstęgą'}. Wolumen {s3}/100 {ratio:.2f}x średniej 20h = {vol_txt}. Średnia ważona wolumenem VWAP ${vwap:.4f}, jesteśmy {((price-vwap)/vwap*100):+.2f}% nad nią.

Sektor wyroczni {idx_ret:+.2f}%: Chainlink {rets.get('LINKUSDT',0):+.1f}% vs Pyth {rets.get('PYTHUSDT',0):+.1f}% | Pyth {pyth_dec:+.2f}% {'słabszy od sektora = ktoś wyprzedaje Pyth' if pyth_dec<-1 else 'silniejszy od sektora = przejmuje narrację' if pyth_dec>1 else 'zgodny z sektorem'}. Korelacja Pyth/Chainlink {corr:.2f} = {'NISKA rozjazd = duży ruch idzie, dlatego tylko 50% pierwszego poziomu' if corr<0.6 else 'WYSOKA sektor spójny, bezpieczniej' if corr>0.8 else 'ŚREDNIA normalna zależność'}. Chainlink ${link_price:.2f} {'Wybicie!' if link_break else f'{((link_price-link_ma200)/link_ma200*100):+.2f}% vs średnia 200h'} wolumen {link_vol:.1f}x średniej

CO TO JEST PIERWSZY I DRUGI POZIOM?

Pierwszy poziom = STREFA ZAKUPU NA DOŁKU ($0.0747-$0.072, najniższy punkt z 20h ${ob_low:.4f}). Tu zbierasz na dołku bo ocena 38 to dołek 35/100. Dzielisz: 50% teraz po ${price:.4f}, drugie 50% jak zejdzie do $0.072 LUB jak korelacja wróci powyżej 0.7 i Pyth przestanie być słabszy. Dlaczego 50%? Bo niska korelacja + słabszy Pyth = może jeszcze zjechać, nie ładuj wszystkiego.

Drugi poziom = POTWIERDZENIE ŻE DOŁEK KONIEC (powyżej ${ma200:.4f}). Jak zamkniemy 4 godziny nad średnią 200h ${ma200:.4f} + Chainlink zrobi wybicie wolumen >1.5x (teraz {link_vol:.1f}x), to znaczy że duzi gracze weszli i idziemy w górę. Dopiero na drugim poziomie dokładasz resztę i przestawiasz Stop Loss na cenę wejścia żeby nie stracić. TERAZ DRUGI POZIOM NIEAKTYWNY - jesteśmy pod średnią 200h.

PLAN 3 TURY:
Pierwszy poziom 50% teraz, 50% $0.072
Drugi poziom dopiero powyżej ${ma200:.4f} + wybicie Chainlink
Cel zysku 1 ${ma20:.4f} (średnia 20h) -> Cel 2 $0.078 luka cenowa -> Cel 3 $0.082 (i $0.089 jeśli Red pump)
Stop Loss = Ucięcie straty: 4h zamknięcie poniżej $0.071 i Chainlink poniżej średniej 200h
Wyjaśnienie skrótów: FVG=luka cenowa gdzie nie było handlu, OB=blok zleceń gdzie duzi kupowali, BOS=przełamanie struktury, VWAP=średnia cena ważona wolumenem

Skład oceny: Trend 25% {s1} + Struktura rynku 20% {s2} + Wolumen 20% {s3} + Wyckoff 15% {s4} + Konkurencja 20% {s5} = {final:.0f}
Czas {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec)

    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last=json.load(f).get('final',0)
        except: pass
    if abs(final-last)>=7 or final<35 or final>60:
        send_tg(msg)
        with open(STATE_FILE,'w') as f:
            json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret)},f)
    else:
        print(f"SKIP {last}->{final:.0f}")
    return final

if __name__=="__main__":
    analyze()
