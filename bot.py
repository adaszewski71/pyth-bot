cat > ~/bot/bot.py << 'PYEOF'
# bot.py - PYTH BOT v9.4 FINAL - /raport NA ZADANIE
import pandas as pd
import requests, yaml, os, json, sys
from datetime import datetime
import numpy as np

SYMBOL = 'PYTHUSDT'
STATE_FILE = 'last_signal.json'
CONFIG_FILE = 'config.yml'
ALERT_FILE = 'last_alerts.json'
WALLET_FILE = 'wallet_state.json'
PYTH_MINT_SOL = "HZ1JovNiVvQKa4pC5wPy4xQsmveYSw8BRyCaGSnyDzT"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
ORACLE_BASKET = {"LINKUSDT":0.45,"PYTHUSDT":0.25,"REDUSDT":0.15,"API3USDT":0.07,"BANDUSDT":0.04,"TRBUSDT":0.04}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: return yaml.safe_load(f)
    return {}

def send_tg(msg):
    try:
        cfg=load_config(); token=cfg.get('telegram_token') or os.getenv("TELEGRAM_TOKEN"); chat_id=cfg.get('chat_id') or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id: return
        url=f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"}, timeout=10)
    except: pass

def check_telegram_command():
    try:
        cfg=load_config(); token=cfg.get('telegram_token') or os.getenv("TELEGRAM_TOKEN"); chat_id=str(cfg.get('chat_id') or os.getenv("TELEGRAM_CHAT_ID") or "")
        if not token or not chat_id: return False
        url=f"https://api.telegram.org/bot{token}/getUpdates"
        r=requests.get(url, params={"timeout":0}, timeout=8).json()
        for upd in r.get("result",[])[-5:]:
            m=upd.get("message",{})
            if str(m.get("chat",{}).get("id"))!=chat_id: continue
            txt=(m.get("text") or "").lower()
            if "/raport" in txt or "/report" in txt or "/full" in txt:
                try: requests.get(url, params={"offset":upd["update_id"]+1}, timeout=5)
                except: pass
                return True
    except: pass
    return False

def fetch_ohlcv(symbol, interval='1h', limit=250):
    headers={"User-Agent":"Mozilla/5.0"}
    urls=[f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"]
    for url in urls:
        try:
            r=requests.get(url, headers=headers, timeout=15); data=r.json()
            if isinstance(data,list) and len(data)>10:
                df=pd.DataFrame(data, columns=['ts','open','high','low','close','volume','ct','qav','trades','tbba','tbqa','ignore'])
                for col in ['open','high','low','close','volume']: df[col]=df[col].astype(float)
                df['ts']=pd.to_datetime(df['ts'], unit='ms'); return df
        except: continue
    raise Exception(f"Fetch fail {symbol}")

def sma(s,p): return s.rolling(p).mean()
def bollinger(s,p=20,dev=2):
    ma=sma(s,p); sd=s.rolling(p).std(); return ma-dev*sd, ma+dev*sd, ma

def engine_trend(df):
    price=df['close'].iloc[-1]; ma20=sma(df['close'],20).iloc[-1]; ma200=sma(df['close'],200).iloc[-1]
    score=50
    if price<ma200: score-=30
    else: score+=15
    if price<ma20: score-=10
    else: score+=15
    return max(0,min(100,score)), ma200, ma20

def engine_smc(df):
    bos_bull=df['low'].iloc[-1] > df['low'].rolling(3).min().iloc[-3]; ob_low=df['low'].rolling(20).min().iloc[-1]
    score=50 + (15 if bos_bull else -5) + (5 if df['close'].iloc[-1]<0.076 else 0)
    return max(0,min(100,score)), ob_low

def engine_volume(df):
    vol_ma=df['volume'].rolling(20).mean().iloc[-1]; ratio=df['volume'].iloc[-1]/vol_ma if vol_ma else 1
    score=50
    if ratio<0.5: score+=15
    elif ratio>1.5: score-=5
    vwap=(df['close']*df['volume']).sum()/df['volume'].sum()
    return max(0,min(100,score)), ratio, vwap

def engine_wyckoff(df):
    bb_low,bb_high,bb_mid=bollinger(df['close']); near=df['close'].iloc[-1] <= bb_low.iloc[-1]*1.015
    score=60 if near else 55; width=(bb_high.iloc[-1]-bb_low.iloc[-1])/bb_mid.iloc[-1]*100 if bb_mid.iloc[-1] else 0
    return score, bb_low.iloc[-1], width, near

def engine_competitor():
    try:
        data={}
        for sym in ORACLE_BASKET: data[sym]=fetch_ohlcv(sym,'1h',250)
        rets={}
        for sym,df in data.items(): rets[sym]=(df['close'].iloc[-1]/df['close'].iloc[-24]-1)*100 if len(df)>=25 else 0
        pyth_close=data['PYTHUSDT']['close'].tail(24).values; link_close=data['LINKUSDT']['close'].tail(24).values
        corr_link=float(np.corrcoef(pyth_close, link_close)[0,1]) if len(pyth_close)==24 else 0.8
        if np.isnan(corr_link): corr_link=0.8
        link_price=data['LINKUSDT']['close'].iloc[-1]; link_ma200=sma(data['LINKUSDT']['close'],200).iloc[-1]
        if pd.isna(link_ma200): link_ma200=link_price
        link_ma20=sma(data['LINKUSDT']['close'],20).iloc[-1]
        link_vol_ratio=data['LINKUSDT']['volume'].iloc[-1]/data['LINKUSDT']['volume'].rolling(20).mean().iloc[-1]
        if pd.isna(link_vol_ratio): link_vol_ratio=1.0
        link_breakout = link_price > link_ma200 and link_price > link_ma20 and link_vol_ratio > 1.5
        idx_ret=sum(rets.get(s,0)*w for s,w in ORACLE_BASKET.items()); pyth_dec=rets.get('PYTHUSDT',0)-idx_ret
        score=50
        if link_breakout: score+=20
        if rets.get('REDUSDT',0)>8: score+=10
        if pyth_dec>2: score+=10
        elif pyth_dec<-2: score-=10
        return max(0,min(100,int(score))), idx_ret, pyth_dec, rets, corr_link, link_price, link_ma200, link_vol_ratio, link_breakout
    except: return 50, 0, 0, {}, 0.8, 0, 0, 1.0, False

def engine_wallets():
    holders=182000; top20_change=0; new_wallets_24h=0; whale_accumulating=False; top20_sum=3215000000
    try:
        payload={"jsonrpc":"2.0","id":1,"method":"getTokenLargestAccounts","params":[PYTH_MINT_SOL]}
        r=requests.post(SOLANA_RPC, json=payload, timeout=12, headers={"Content-Type":"application/json"})
        if r.status_code==200:
            j=r.json()
            if 'result' in j and 'value' in j['result']:
                vals=j['result']['value'][:20]; s=0
                for v in vals:
                    try:
                        amt=v.get('uiAmount')
                        if amt is None: amt=float(v.get('amount','0'))/(10**v.get('decimals',6))
                        s+=float(amt)
                    except: continue
                if s>1000000: top20_sum=s
                if os.path.exists(WALLET_FILE):
                    with open(WALLET_FILE) as f:
                        prev=json.load(f); prev_top20=prev.get('top20_sum', top20_sum)
                        if prev_top20>1000000 and top20_sum>1000000: top20_change=((top20_sum-prev_top20)/prev_top20*100)
                        holders=prev.get('holders',182000)
                with open(WALLET_FILE,'w') as f: json.dump({"holders":holders,"top20_sum":top20_sum,"time":datetime.now().isoformat()},f)
                whale_accumulating=top20_change>0.3
    except: pass
    score=50
    if whale_accumulating: score+=20
    elif top20_change<-1: score-=15
    return max(0,min(100,score)), holders, new_wallets_24h, top20_change, whale_accumulating, top20_sum

def engine_fear_greed(df, rets, price, ma200, ma20):
    try:
        details={}; global_fng=74
        try:
            r=requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if r.status_code==200:
                j=r.json(); global_fng=int(j['data'][0]['value']); details['global']=global_fng; details['global_txt']=j['data'][0]['value_classification']
        except: details['global']=74; details['global_txt']="Greed"; global_fng=74
        vol_30=df['close'].pct_change().rolling(30).std().iloc[-1]*100 if len(df)>31 else 2
        vol_score=100-min(100, vol_30*20); dist200=(price-ma200)/ma200*100 if ma200 else 0
        momentum_score=max(0,min(100,50+dist200*5)); vol_ma=df['volume'].rolling(20).mean().iloc[-1]
        vol_ratio=df['volume'].iloc[-1]/vol_ma if vol_ma else 1; volume_score=30 if vol_ratio>1.5 else 70 if vol_ratio<0.6 else 50
        dist20=(price-ma20)/ma20*100 if ma20 else 0; rsi_score=max(0,min(100,50+dist20*10))
        idx_ret=sum(rets.get(s,0)*w for s,w in ORACLE_BASKET.items()); pyth_vs_sector=rets.get('PYTHUSDT',0)-idx_ret
        dominance_score=max(0,min(100,50+pyth_vs_sector*10)); pyth_fng=int((vol_score*0.25+momentum_score*0.25+volume_score*0.15+rsi_score*0.20+dominance_score*0.15))
        details['pyth']=pyth_fng; details['pyth_components']={'volatility':int(vol_score),'momentum':int(momentum_score),'volume':int(volume_score),'rsi_proxy':int(rsi_score),'dominance':int(dominance_score)}
        sector_vals=list(rets.values()); avg_sector_24h=sum(sector_vals)/len(sector_vals) if sector_vals else 0
        sector_fng=max(0,min(100,int(50+avg_sector_24h*10))); details['sector']=sector_fng; details['sector_ret']=avg_sector_24h
        if pyth_fng<20: score=85
        elif pyth_fng<35: score=70
        elif pyth_fng<55: score=50
        elif pyth_fng<75: score=35
        else: score=15
        if global_fng<20 and pyth_fng<50: score+=15
        return max(0,min(100,score)), details
    except: return 50, {'global':74,'pyth':50,'sector':50,'global_txt':'Greed','sector_ret':0,'pyth_components':{'volatility':50,'momentum':50,'volume':50,'rsi_proxy':50,'dominance':50}}

def load_last_alerts():
    if os.path.exists(ALERT_FILE):
        try:
            with open(ALERT_FILE) as f: return json.load(f)
        except: pass
    return {}
def save_alerts(a):
    with open(ALERT_FILE,'w') as f: json.dump(a,f)

def check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, w_score, holders, new_wallets, top20_change, whale_acc, fng_score, fng_details):
    last=load_last_alerts(); alerts=[]
    if fng_details['pyth']<20 and 'fng_extreme_fear' not in last: alerts.append(('fng_extreme_fear', f"😱 EXTREME FEAR PYTH {fng_details['pyth']}/100"))
    if whale_acc and price<0.076:
        if last.get('whale_acc')!= round(top20_change,2): alerts.append(('whale_acc', f"🐋 WIELORYBY +{top20_change:.2f}%"))
    if corr<0.55 and 'rozjazd' not in last: alerts.append(('rozjazd', f"⚠️ ROZJAZD CORR {corr:.2f}"))
    if price>ma200 and final>55 and last.get('poziom_drugi_blisko')!=True: alerts.append(('poziom_drugi_blisko', f"🚀 P2 AKTYWNY ${price:.4f}"))
    for key,msg in alerts: send_tg(msg); last[key]=True if key!='whale_acc' else round(top20_change,2)
    if alerts: save_alerts(last)

def analyze(force_report=False):
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE) as f:
                d=json.load(f)
                if d.get('top20_sum',0)<1000: os.remove(WALLET_FILE)
        except:
            try: os.remove(WALLET_FILE)
            except: pass
    df=fetch_ohlcv(SYMBOL); price=df['close'].iloc[-1]
    s1,ma200,ma20=engine_trend(df); s2,ob_low=engine_smc(df); s3,ratio,vwap=engine_volume(df)
    s4,bb_low,bb_width,near=engine_wyckoff(df); s5,idx_ret,pyth_dec,rets,corr,link_price,link_ma200,link_vol,link_break=engine_competitor()
    s6,holders,new_wallets,top20_change,whale_acc,top20_sum=engine_wallets(); s7,fng_details=engine_fear_greed(df, rets, price, ma200, ma20)
    final=s1*0.20 + s2*0.10 + s3*0.10 + s4*0.10 + s5*0.15 + s6*0.15 + s7*0.20
    if final<30: sig="MOCNA SPRZEDAZ 10/100 - uciekaj"
    elif final<45: sig="SLABA SPRZEDAZ / DOLEK 35/100 - dno"
    elif final<55: sig="NEUTRALNIE / ZBIERANIE 49/100 - zbieraj powoli"
    elif final<75: sig="SYGNAL KUPNA 65/100 - mozna ladowac"
    else: sig="MOCNE KUPNO 90/100"
    dist200=(price-ma200)/ma200*100 if ma200 else 0; dist20=(price-ma20)/ma20*100 if ma20 else 0
    vol_txt="wysycha - nikt nie sprzedaje" if ratio<0.6 else "podwyzszony" if ratio>1.3 else "neutralny"
    wallet_txt=f"WIELORYBY ZBIERAJA +{top20_change:.2f}%" if whale_acc else f"Wieloryby wyrzucaja {top20_change:.2f}%" if top20_change<-0.5 else f"Wieloryby neutralne {top20_change:+.2f}%"
    holders_txt=f"Nowe portfele {new_wallets:+.0f}" if abs(new_wallets)>50 else f"Holderzy stabilni {new_wallets:+.0f}"
    msg=f"PYTH ${price:.4f} | OCENA KONCOWA {final:.0f}/100 - {sig}\n\nTrend {s1}/100 {dist200:+.2f}% vs 200h ${ma200:.4f} | {dist20:+.2f}% vs 20h ${ma20:.4f}\nStruktura {s2}/100 OB ${ob_low:.4f} | Wyckoff {s4}/100 wstega ${bb_low:.4f} szer {bb_width:.2f}%\nWolumen {s3}/100 {ratio:.2f}x {vol_txt} VWAP ${vwap:.4f}\nKonkurencja {s5}/100 Sektor {idx_ret:+.2f}% LINK {rets.get('LINKUSDT',0):+.1f}% vs PYTH {rets.get('PYTHUSDT',0):+.1f}% PYTH {pyth_dec:+.2f}% CORR {corr:.2f} LINK ${link_price:.2f} vol {link_vol:.1f}x\n\nPORTFELE {s6}/100 {holders} holderow {holders_txt} | {wallet_txt} | Top20 {top20_sum:,.0f} PYTH {top20_change:+.3f}%\n\nFEAR & GREED {s7}/100: Global {fng_details['global']}/100 {fng_details['global_txt']} | Pyth {fng_details['pyth']}/100 | Sektor {fng_details['sector']}/100 {fng_details['sector_ret']:+.2f}%\n\nP1 = $0.0747-$0.072 OB ${ob_low:.4f} 50% teraz ${price:.4f} | P2 >${ma200:.4f}\nPLAN: P1 50% | P2 >${ma200:.4f} | Cel ${ma20:.4f} -> $0.078 -> $0.082 | Stop <$0.071\nSklad: T{s1}*20% S{s2}*10% V{s3}*10% W{s4}*10% K{s5}*15% P{s6}*15% F{s7}*20% = {final:.0f}\nCzas {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    print(msg); check_alerts(price, final, ma200, ma20, rets, corr, link_price, link_ma200, link_vol, link_break, idx_ret, pyth_dec, s6, holders, new_wallets, top20_change, whale_acc, s7, fng_details)
    last=0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f: last=json.load(f).get('final',0)
        except: pass
    if force_report or abs(final-last)>=7 or final<35 or final>60 or fng_details['pyth']<20:
        if force_report: msg="📊 RAPORT NA ZADANIE /raport\n\n"+msg
        send_tg(msg)
        with open(STATE_FILE,'w') as f: json.dump({"final":float(final),"price":float(price),"oracle_idx":float(idx_ret),"wallets":holders,"fng_pyth":fng_details['pyth'],"top20":float(top20_sum)},f)
    else: print(f"SKIP {last}->{final:.0f}")
    return final

if __name__=="__main__":
    force=False
    if check_telegram_command(): print("TELEGRAM /raport -> wymuszam"); force=True
    if "--force" in sys.argv: force=True
    analyze(force_report=force)
PYEOF
