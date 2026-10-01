# PYTH BOT v8.9 WALLETS - 6 SILNIKOW + 6 ALERTOW - BEZ SKROTOW
import pandas as pd
import requests, yaml, os, json
from datetime import datetime
import numpy as np

SYMBOL = 'PYTHUSDT'
STATE_FILE = 'last_signal.json'
CONFIG_FILE = 'config.yml'
ALERT_FILE = 'last_alerts.json'
WALLET_FILE = 'wallet_state.json'

PYTH_MINT_SOL = "HZ1JovNiVvQKa4pC5wPy4xQsmveYSw8BRyCaGSnyDzT"

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

def engine_wallets():
    """6 silnik - ilość portfeli darmowy Solscan + Helius public"""
    try:
        # 1 - Solscan public holder count
        holders = 0
        top20_change = 0
        new_wallets_24h = 0
        whale_accumulating = False

        # Darmowe API Solscan v2 - holderzy
        try:
            url = f"https://api.solscan.io/v2/token/holders?token={PYTH_MINT_SOL}&offset=0&size=20"
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            if r.status_code==200:
                j=r.json()
                if 'data' in j and 'total' in j['data']:
                    holders = j['data']['total']
                elif 'total' in j:
                    holders = j['total']
                # top 20 suma
                if 'data' in j and isinstance(j['data'], dict) and 'items' in j['data']:
                    items=j['data']['items'][:20]
                    top20_sum=sum(float(x.get('amount',0)) for x in items)
                    # porównaj z poprzednim stanem
                    prev=0
                    if os.path.exists(WALLET_FILE):
                        try:
                            with open(WALLET_FILE) as f:
                                prev_data=json.load(f)
                                prev=prev_data.get('top20_sum', top20_sum)
                                prev_holders=prev_data.get('holders', holders)
                                new_wallets_24h = holders - prev_holders if holders and prev_holders else 0
                                top20_change = ((top20_sum - prev)/prev*100) if prev else 0
                        except: pass
                    # zapisz nowy stan
                    with open(WALLET_FILE,'w') as f:
                        json.dump({"holders":holders,"top20_sum":top20_sum,"time":datetime.now().isoformat()},f)
                    whale_accumulating = top20_change > 0.5
        except Exception as e:
            print(f"Wallet API err {e}")

        # Fallback jeśli API nie działa - estymacja z wolumenu i ceny
        if holders==0:
            # użyj ostatniego zapisanego
            if os.path.exists(WALLET_FILE):
                with open(WALLET_FILE) as f:
                    d=json.load(f)
                    holders=d.get('holders',182000)
            else:
                holders=182000

        score=50
        if new_wallets_24h > 50: score+=15 # nowe wchodzą na dołku = dobrze
        elif new_wallets_24h < -50: score-=10 # uciekają = źle

        if whale_accumulating: score+=20
        elif top20_change < -1: score-=15

        if holders>0 and holders<180000: score-=5 # mało holderów

        return max(0,min(100,score)), holders, new_wallets_24h, top20_change, whale_accumulating

    except Exception as e:
        print(f"Wallets engine fail {e}")
        return 50, 0, 0, 0, False

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

def check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, w_score, holders, new_wallets, top20_change, whale_acc):
    last = load_last_alerts()
    alerts = []
    red_ret = rets.get('REDUSDT',0)

    if corr < 0.55 and 'rozjazd' not in last:
        msg = f"""⚠️ OSTRZEŻENIE ROZJAZD - KORELACJA {corr:.2f} NISKA
Chainlink ${link_price:.2f} {rets.get('LINKUSDT',0):+.1f}% vs Pyth ${price:.4f} {rets.get('PYTHUSDT',0):+.1f}%
Pyth {pyth_dec:+.2f}% słabszy od całego sektora wyroczni {idx_ret:+.2f}%
Kup tylko 50% pierwszej strefy zakupowej teraz $0.0747-$0.072, czekaj aż korelacja wróci >0.7"""
        alerts.append(('rozjazd', msg))

    if whale_acc and price<0.076:
        if last.get('whale_acc')!= round(top20_change,2):
            msg = f"""🐋 WIELORYBY ZBIERAJĄ NA DOŁKU
Top 20 portfeli +{top20_change:.2f}% stanów w 24h, holderów {holders} ({new_wallets:+.0f} w 24h)
Pyth ${price:.4f} - duzi dokupują gdy mali sprzedają (wolumen {link_vol:.1f}x)
Potwierdza dołek - można zwiększyć pierwszy poziom z 50% na 75%"""
            alerts.append(('whale_acc', msg))

    if new_wallets < -100:
        if last.get('wallets_drop')!= new_wallets:
            msg = f"""⚠️ PORTFELE UCIEKAJĄ {new_wallets:+.0f} w 24h holderów {holders}
Słabe ręce wyrzucają Pyth ${price:.4f}, ale wieloryby {top20_change:+.2f}%
Uważaj, dołek może pogłębić się do $0.069"""
            alerts.append(('wallets_drop', msg))

    if price > ma200 and final > 55:
        if last.get('poziom_drugi_blisko')!= True:
            msg = f"""🚀 DRUGI POZIOM BLISKO / AKTYWNY
Pyth ${price:.4f} przebił średnią 200h ${ma200:.4f} Ocena {final:.0f}/100
Chainlink ${link_price:.2f} wolumen {link_vol:.1f}x {'Wybicie!' if link_break else 'trzyma'} Korelacja {corr:.2f}
Portfele {holders} ({new_wallets:+.0f}) wieloryby {top20_change:+.2f}%
Drugi poziom aktywny - możesz dokupić resztę, przestaw Stop Loss na cenę wejścia"""
            alerts.append(('poziom_drugi_blisko', msg))

    if price <= 0.072 and price >= 0.069:
        if last.get('pierwszy_poziom_druga_czesc')!= round(price,4):
            msg = f"""📥 PIERWSZY POZIOM - DRUGA CZĘŚĆ WYPEŁNIONA
Pyth ${price:.4f} w dolnej części strefy zakupowej $0.071-0.073
Ocena {final:.0f} - maksymalne wyprzedanie
Portfele potwierdzają: {holders} holderów wieloryby {top20_change:+.2f}%"""
            alerts.append(('pierwszy_poziom_druga_czesc', msg))

    if red_ret > 8 or (link_break and rets.get('LINKUSDT',0) > 5):
        if last.get('pump_sektora')!= round(red_ret,1):
            msg = f"""🔥 PUMP CAŁEGO SEKTORA WYROCZNI Red +{red_ret:.1f}%
Pyth {rets.get('PYTHUSDT',0):+.1f}% | Chainlink +{rets.get('LINKUSDT',0):+.1f}% wolumen {link_vol:.1f}x"""
            alerts.append(('pump_sektora', msg))

    if price < 0.071 and link_price < link_ma200:
        if last.get('stop_loss')!= True:
            msg = f"""🛑 STOP LOSS - WYJDŹ Z POZYCJI - UTNIJ STRATĘ
Pyth ${price:.4f} poniżej $0.071 + Chainlink ${link_price:.2f} poniżej średniej 200h ${link_ma200:.2f}
Portfele {holders} wieloryby {top20_change:+.2f}%"""
            alerts.append(('stop_loss', msg))

    if corr > 0.75 and last.get('rozjazd') is not None:
        if last.get('powrot_korelacji')!= True:
            msg = f"""✅ POWRÓT KORELACJI {corr:.2f} WYSOKA"""
            alerts.append(('powrot_korelacji', msg))

    for key, msg in alerts:
        send_tg(msg)
        print(f"ALERT {key}")
        last[key] = True if key in ['poziom_drugi_blisko','stop_loss','powrot_korelacji'] else round(price,4) if 'poziom' in key else round(top20_change,2)

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
    s6,holders,new_wallets,top20_change,whale_acc=engine_wallets()

    # NOWE WAGI: 6 silników
    final=s1*0.20 + s2*0.15 + s3*0.15 + s4*0.15 + s5*0.20 + s6*0.15

    if final<30: sig="MOCNA SPRZEDAŻ 10/100 - uciekaj"
    elif final<45: sig="SŁABA SPRZEDAŻ / DOŁEK 35/100 - dno, ale nie kupuj wszystkiego"
    elif final<55: sig="NEUTRALNIE / ZBIERANIE 49/100 - zbieraj powoli"
    elif final<75: sig="SYGNAŁ KUPNA 65/100 - można ładować"
    else: sig="MOCNE KUPNO 90/100"

    dist200=(price-ma200)/ma200*100 if ma200 else 0
    dist20=(price-ma20)/ma20*100 if ma20 else 0
    vol_txt="wysycha, nikt nie chce sprzedawać na dołku" if ratio<0.6 else "podwyższony, ktoś jeszcze sprzedaje" if ratio>1.3 else "neutralny"

    wallet_txt = f"WIELORYBY ZBIERAJĄ +{top20_change:.2f}% - potwierdzają dołek" if whale_acc else f"Wieloryby wyrzucają {top20_change:.2f}% - uważaj" if top20_change<-1 else f"Wieloryby neutralne {top20_change:+.2f}%"
    holders_txt = f"Nowe portfele wchodzą {new_wallets:+.0f} = dołek skupowany" if new_wallets>50 else f"Portfele uciekają {new_wallets:+.0f} = strach" if new_wallets<-50 else f"Portfele stabilne {new_wallets:+.0f}"

    msg=f"""PYTH ${price:.4f} | OCENA KOŃCOWA {final:.0f}/100 - {sig}

DLACZEGO OCENA {final:.0f}?

Trend {s1}/100 SPRZEDAŻ bo jesteśmy {dist200:+.2f}% pod średnią 200-godzinną (${ma200:.4f}). Dopóki nie wrócimy nad średnią 200h, nie ma drugiego poziomu.

Wyckoff {s4}/100 KUPNO - dolna wstęga ${bb_low:.4f} (szer {bb_width:.2f}%). {'Dotykamy dolnej wstęgi = wyprzedanie' if near else 'Nad wstęgą'}. Wolumen {s3}/100 {ratio:.2f}x = {vol_txt}. Średnia ważona wolumenem ${vwap:.4f} {((price-vwap)/vwap*100):+.2f}%

Sektor wyroczni {idx_ret:+.2f}%: Chainlink {rets.get('LINKUSDT',0):+.1f}% vs Pyth {rets.get('PYTHUSDT',0):+.1f}% | Pyth {pyth_dec:+.2f}% {'słabszy = ktoś wyprzedaje Pyth' if pyth_dec<-1 else 'silniejszy' if pyth_dec>1 else 'zgodny'}. Korelacja {corr:.2f} = {'NISKA rozjazd = 50% pierwszego poziomu' if corr<0.6 else 'WYSOKA spójny' if corr>0.8 else 'ŚREDNIA'}. Chainlink ${link_price:.2f} {'Wybicie!' if link_break else f'{((link_price-link_ma200)/link_ma200*100):+.2f}% vs średnia 200h'} wolumen {link_vol:.1f}x

PORTFELE - NOWY SILNIK {s6}/100:
Ilość portfeli trzymających Pyth: {holders} sztuk. Zmiana w 24h: {holders_txt}
Top 20 największych portfeli: {wallet_txt}
Co to znaczy: {'Wieloryby zbierają na dołku gdy mali sprzedają - to potwierdza że dołek jest prawdziwy, możesz dać 75% pierwszego poziomu zamiast 50%' if whale_acc and new_wallets>-50 else 'Wieloryby też sprzedają - to nie jest jeszcze dołek, czekaj z pierwszym poziomem' if top20_change<-1 and new_wallets<-50 else 'Portfele neutralne - czekaj na sygnał od wielorybów'}

CO TO JEST PIERWSZY I DRUGI POZIOM?

Pierwszy poziom = STREFA ZAKUPU NA DOŁKU ($0.0747-$0.072, najniższy punkt ${ob_low:.4f}). 50% teraz ${price:.4f}, 50% $0.072 LUB korelacja >0.7 + wieloryby zbierają
Drugi poziom = POTWIERDZENIE ŻE DOŁEK KONIEC (powyżej ${ma200:.4f}). Dopiero jak zamkniemy 4h nad średnią 200h + Chainlink wybicie + wieloryby +2% - wtedy dokładasz i Stop Loss na cenę wejścia

PLAN:
Pierwszy poziom 50% teraz{' 75% bo wieloryby zbierają' if whale_acc else ''}, 50% $0.072
Drugi poziom >${ma200:.4f}
Cel zysku 1 ${ma20:.4f} -> Cel 2 $0.078 -> Cel 3 $0.082
Stop Loss: 4h poniżej $0.071 i Chainlink poniżej średniej 200h i wieloryby -1%
Skład: Trend {s1} (20%) + Struktura {s2} (15%) + Wolumen {s3} (15%) + Wyckoff {s4} (15%) + Konkurencja {s5} (20%) + Portfele {s6} (15%) = {final:.0f}
Czas {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, s6, holders, new_wallets, top20_change, whale_acc)

    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last=json.load(f).get('final',0)
        except: pass
    if abs(final-last)>=7 or final<35 or final>60:
        send_tg(msg)
        with open(STATE_FILE,'w') as f:
            json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret),"wallets":holders},f)
    else:
        print(f"SKIP {last}->{final:.0f}")
    return final

if __name__=="__main__":
    analyze()
