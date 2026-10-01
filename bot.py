# PYTH BOT v9.0 FINAL - 7 SILNIKOW - FEAR & GREED + PORTFELE - BEZ SKROTOW
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
    try:
        holders = 0
        top20_change = 0
        new_wallets_24h = 0
        whale_accumulating = False
        try:
            url = f"https://api.solscan.io/v2/token/holders?token={PYTH_MINT_SOL}&offset=0&size=20"
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            if r.status_code==200:
                j=r.json()
                if 'data' in j and 'total' in j['data']:
                    holders = j['data']['total']
                elif 'total' in j:
                    holders = j['total']
                if 'data' in j and isinstance(j['data'], dict) and 'items' in j['data']:
                    items=j['data']['items'][:20]
                    top20_sum=sum(float(x.get('amount',0)) for x in items)
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
                    with open(WALLET_FILE,'w') as f:
                        json.dump({"holders":holders,"top20_sum":top20_sum,"time":datetime.now().isoformat()},f)
                    whale_accumulating = top20_change > 0.5
        except Exception as e:
            print(f"Wallet API err {e}")
        if holders==0:
            if os.path.exists(WALLET_FILE):
                with open(WALLET_FILE) as f:
                    d=json.load(f)
                    holders=d.get('holders',182000)
            else:
                holders=182000
        score=50
        if new_wallets_24h > 50: score+=15
        elif new_wallets_24h < -50: score-=10
        if whale_accumulating: score+=20
        elif top20_change < -1: score-=15
        return max(0,min(100,score)), holders, new_wallets_24h, top20_change, whale_accumulating
    except Exception as e:
        return 50, 0, 0, 0, False

def engine_fear_greed(df, rets, price, ma200, ma20):
    try:
        details = {}
        global_fng = 50
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if r.status_code == 200:
                j = r.json()
                global_fng = int(j['data'][0]['value'])
                details['global'] = global_fng
                details['global_txt'] = j['data'][0]['value_classification']
        except:
            details['global'] = 50
            details['global_txt'] = "Neutral"
            global_fng = 50

        vol_30 = df['close'].pct_change().rolling(30).std().iloc[-1] * 100 if len(df)>31 else 2
        vol_score = 100 - min(100, vol_30*20)
        dist200 = (price - ma200)/ma200*100 if ma200 else 0
        momentum_score = max(0, min(100, 50 + dist200*5))
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        vol_ratio = df['volume'].iloc[-1]/vol_ma if vol_ma else 1
        volume_score = 30 if vol_ratio > 1.5 else 70 if vol_ratio < 0.6 else 50
        dist20 = (price - ma20)/ma20*100 if ma20 else 0
        rsi_score = max(0, min(100, 50 + dist20*10))
        idx_ret = sum(rets.get(s,0)*w for s,w in ORACLE_BASKET.items())
        pyth_vs_sector = rets.get('PYTHUSDT',0) - idx_ret
        dominance_score = max(0, min(100, 50 + pyth_vs_sector*10))

        pyth_fng = int((vol_score*0.25 + momentum_score*0.25 + volume_score*0.15 + rsi_score*0.20 + dominance_score*0.15))
        details['pyth'] = pyth_fng
        details['pyth_components'] = {
            'volatility': int(vol_score),
            'momentum': int(momentum_score),
            'volume': int(volume_score),
            'rsi_proxy': int(rsi_score),
            'dominance': int(dominance_score)
        }
        sector_vals = list(rets.values())
        avg_sector_24h = sum(sector_vals)/len(sector_vals) if sector_vals else 0
        sector_fng = max(0, min(100, int(50 + avg_sector_24h*10)))
        details['sector'] = sector_fng
        details['sector_ret'] = avg_sector_24h

        if pyth_fng < 20: score = 85
        elif pyth_fng < 35: score = 70
        elif pyth_fng < 55: score = 50
        elif pyth_fng < 75: score = 35
        else: score = 15
        if global_fng < 20 and pyth_fng < 50:
            score += 15

        return max(0,min(100,score)), details
    except Exception as e:
        print(f"F&G fail {e}")
        return 50, {'global':50,'pyth':50,'sector':50,'global_txt':'Unknown','sector_ret':0,'pyth_components':{'volatility':50,'momentum':50,'volume':50,'rsi_proxy':50,'dominance':50}}

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

def check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, w_score, holders, new_wallets, top20_change, whale_acc, fng_score, fng_details):
    last = load_last_alerts()
    alerts = []
    red_ret = rets.get('REDUSDT',0)

    if fng_details['pyth'] < 20 and 'fng_extreme_fear' not in last:
        msg = f"""😱 EXTREME FEAR PYTH {fng_details['pyth']}/100 - KAPITULACJA
Global {fng_details['global']}/100 {fng_details['global_txt']} | Sektor {fng_details['sector']}/100
Pyth ${price:.4f} wszyscy sprzedają w panice - to najlepszy moment na pierwszy poziom 100%
Historycznie takie poziomy = +15-25% w 7 dni"""
        alerts.append(('fng_extreme_fear', msg))

    if corr < 0.55 and 'rozjazd' not in last:
        msg = f"""⚠️ OSTRZEŻENIE ROZJAZD - KORELACJA {corr:.2f} NISKA
Chainlink ${link_price:.2f} {rets.get('LINKUSDT',0):+.1f}% vs Pyth ${price:.4f} {rets.get('PYTHUSDT',0):+.1f}%
Pyth {pyth_dec:+.2f}% słabszy od sektora {idx_ret:+.2f}%"""
        alerts.append(('rozjazd', msg))

    if whale_acc and price<0.076:
        if last.get('whale_acc')!= round(top20_change,2):
            msg = f"""🐋 WIELORYBY ZBIERAJĄ NA DOŁKU Top20 +{top20_change:.2f}% holderów {holders} ({new_wallets:+.0f})
Pyth ${price:.4f} - duzi dokupują gdy Fear {fng_details['pyth']}/100"""
            alerts.append(('whale_acc', msg))

    if fng_details['global'] < 20 and fng_details['pyth'] < 30 and 'global_fear' not in last:
        msg = f"""🌍 GLOBAL EXTREME FEAR {fng_details['global']}/100 - CAŁE KRYPT0 W PANICE
Pyth Fear {fng_details['pyth']}/100 Sektor {fng_details['sector']}/100
Dołki wszędzie - ładuj pierwszy poziom 100%, nie 50%"""
        alerts.append(('global_fear', msg))

    if price > ma200 and final > 55:
        if last.get('poziom_drugi_blisko')!= True:
            msg = f"""🚀 DRUGI POZIOM AKTYWNY Pyth ${price:.4f} > średnia 200h ${ma200:.4f} Ocena {final:.0f}
Chainlink vol {link_vol:.1f}x Korelacja {corr:.2f} Portfele {holders} Fear {fng_details['pyth']}/100"""
            alerts.append(('poziom_drugi_blisko', msg))

    if price < 0.071 and link_price < link_ma200:
        if last.get('stop_loss')!= True:
            msg = f"""🛑 STOP LOSS - UTNIJ STRATĘ Pyth ${price:.4f} <$0.071 + Chainlink ${link_price:.2f} < średnia 200h"""
            alerts.append(('stop_loss', msg))

    if corr > 0.75 and last.get('rozjazd') is not None:
        if last.get('powrot_korelacji')!= True:
            msg = f"""✅ POWRÓT KORELACJI {corr:.2f} WYSOKA"""
            alerts.append(('powrot_korelacji', msg))

    for key, msg in alerts:
        send_tg(msg)
        print(f"ALERT {key}")
        last[key] = True if key in ['poziom_drugi_blisko','stop_loss','powrot_korelacji','fng_extreme_fear','global_fear'] else round(top20_change,2)

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
    s7,fng_details=engine_fear_greed(df, rets, price, ma200, ma20)

    final=s1*0.20 + s2*0.10 + s3*0.10 + s4*0.10 + s5*0.15 + s6*0.15 + s7*0.20

    if final<30: sig="MOCNA SPRZEDAŻ 10/100 - uciekaj"
    elif final<45: sig="SŁABA SPRZEDAŻ / DOŁEK 35/100 - dno, ale nie kupuj wszystkiego"
    elif final<55: sig="NEUTRALNIE / ZBIERANIE 49/100 - zbieraj powoli"
    elif final<75: sig="SYGNAŁ KUPNA 65/100 - można ładować"
    else: sig="MOCNE KUPNO 90/100"

    dist200=(price-ma200)/ma200*100 if ma200 else 0
    dist20=(price-ma20)/ma20*100 if ma20 else 0
    vol_txt="wysycha" if ratio<0.6 else "podwyższony" if ratio>1.3 else "neutralny"

    wallet_txt = f"WIELORYBY ZBIERAJĄ +{top20_change:.2f}%" if whale_acc else f"Wieloryby wyrzucają {top20_change:.2f}%" if top20_change<-1 else f"Wieloryby neutralne {top20_change:+.2f}%"
    holders_txt = f"Nowe wchodzą {new_wallets:+.0f}" if new_wallets>50 else f"Uciekają {new_wallets:+.0f}" if new_wallets<-50 else f"Stabilne {new_wallets:+.0f}"

    msg=f"""PYTH ${price:.4f} | OCENA KOŃCOWA {final:.0f}/100 - {sig}

Trend {s1}/100 {'SPRZEDAŻ' if s1<45 else 'KUPNO'} {dist200:+.2f}% pod średnią 200h ${ma200:.4f} | {dist20:+.2f}% vs średnia 20h ${ma20:.4f}
Wyckoff {s4}/100 dolna wstęga ${bb_low:.4f} szer {bb_width:.2f}% {'Dotykamy = wyprzedanie' if near else 'Nad'} | Wolumen {s3}/100 {ratio:.2f}x {vol_txt} VWAP ${vwap:.4f}
Sektor {idx_ret:+.2f}% LINK {rets.get('LINKUSDT',0):+.1f}% vs PYTH {rets.get('PYTHUSDT',0):+.1f}% PYTH {pyth_dec:+.2f}% {'słabszy' if pyth_dec<-1 else 'silniejszy' if pyth_dec>1 else 'zgodny'} CORR {corr:.2f} LINK ${link_price:.2f} vol {link_vol:.1f}x {'Wybicie' if link_break else 'brak'}

PORTFELE {s6}/100: {holders} holderów {holders_txt} | {wallet_txt}

FEAR & GREED {s7}/100 - NOWY:
Global Krypto: {fng_details['global']}/100 {fng_details['global_txt']} - {'EXTREME FEAR = dołki wszędzie' if fng_details['global']<20 else 'Fear = okazje' if fng_details['global']<40 else 'Neutral' if fng_details['global']<60 else 'Greed' if fng_details['global']<80 else 'Extreme Greed = realizuj'}
Pyth Network: {fng_details['pyth']}/100 {'EXTREME FEAR = kapitulacja mocne kupno' if fng_details['pyth']<20 else 'Fear = dołek' if fng_details['pyth']<35 else 'Neutral' if fng_details['pyth']<55 else 'Greed' if fng_details['pyth']<75 else 'Extreme Greed = sprzedawaj'} | Skład: Zmienność {fng_details['pyth_components']['volatility']} Pęd {fng_details['pyth_components']['momentum']} Wolumen {fng_details['pyth_components']['volume']} Siła {fng_details['pyth_components']['rsi_proxy']} Dominacja {fng_details['pyth_components']['dominance']}
Sektor Wyroczni: {fng_details['sector']}/100 {fng_details['sector_ret']:+.2f}% średnio 24h - {'panika w sektorze, odbicie 5-7%' if fng_details['sector']<25 else 'strach' if fng_details['sector']<45 else 'neutralny' if fng_details['sector']<65 else 'chciwość'}

PIERWSZY POZIOM = STREFA ZAKUPU NA DOŁKU ($0.0747-$0.072 OB ${ob_low:.4f}) - 50% teraz ${price:.4f}{' 75% bo wieloryby zbierają' if whale_acc else ''}{' 100% bo Extreme Fear' if fng_details['pyth']<20 else ''}, 50% $0.072 lub korelacja>0.7
DRUGI POZIOM = POTWIERDZENIE >${ma200:.4f} + LINK vol>1.5x (teraz {link_vol:.1f}x) + Fear>40 - wtedy dokładasz Stop Loss na wejście

PLAN: P1 50%{' 75%' if whale_acc else ''}{' 100% Fear' if fng_details['pyth']<20 else ''} teraz, 50% $0.072 | P2 >${ma200:.4f} | Cel ${ma20:.4f} -> $0.078 -> $0.082 | Stop Loss 4h <$0.071 + LINK<średnia200h
Skład: Trend {s1}*20% + Struktura {s2}*10% + Wolumen {s3}*10% + Wyckoff {s4}*10% + Konkurencja {s5}*15% + Portfele {s6}*15% + FearGreed {s7}*20% = {final:.0f}
Czas {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, s6, holders, new_wallets, top20_change, whale_acc, s7, fng_details)

    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last=json.load(f).get('final',0)
        except: pass
    if abs(final-last)>=7 or final<35 or final>60 or fng_details['pyth']<20:
        send_tg(msg)
        with open(STATE_FILE,'w') as f:
            json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret),"wallets":holders,"fng_pyth":fng_details['pyth']},f)
    else:
        print(f"SKIP {last}->{final:.0f}")
    return final

if __name__=="__main__":
    analyze()
