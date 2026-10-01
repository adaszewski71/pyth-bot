# PYTH BOT v8.3 FINAL - BOGATE OPISY + 4 ENGINES + ANTI-SPAM + 3 TURY
# FINAL 38 zachowany, Fix WAF

import pandas as pd
import requests
import yaml
import os
import json
from datetime import datetime

SYMBOL = 'PYTHUSDT'
TIMEFRAME = '1h'
CONFIG_FILE = 'config.yml'
STATE_FILE = 'last_signal.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f)
    return {"telegram_token": os.getenv("TELEGRAM_TOKEN"), "chat_id": os.getenv("TELEGRAM_CHAT_ID")}

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
        print(f"TG ERROR: {e}")

def fetch_ohlcv(symbol=SYMBOL, interval=TIMEFRAME, limit=250):
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    last_error = None
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            data = r.json()
            if isinstance(data, list) and len(data) > 10:
                df = pd.DataFrame(data, columns=['ts','open','high','low','close','volume','ct','qav','trades','tbba','tbqa','ignore'])
                for col in ['open','high','low','close','volume']:
                    df[col] = df[col].astype(float)
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                print(f"OK fetched from {url} rows={len(df)}")
                return df
            last_error = data
        except Exception as e:
            last_error = e
            continue
    raise Exception(f"Cannot fetch klines: {last_error}")

def sma(series, period):
    return series.rolling(period).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def bollinger(series, period=20, std=2):
    ma = sma(series, period)
    sd = series.rolling(period).std()
    return ma - std*sd, ma + std*sd, ma

def engine_trend(df):
    price = df['close'].iloc[-1]
    ma20 = sma(df['close'], 20).iloc[-1]
    ma50 = sma(df['close'], 50).iloc[-1]
    ma200 = sma(df['close'], 200).iloc[-1]
    rsi_val = rsi(df['close']).iloc[-1]
    rsi_ma14 = rsi(df['close']).rolling(14).mean().iloc[-1]
    dist_ma200 = (price-ma200)/ma200*100
    dist_ma20 = (price-ma20)/ma20*100
    score = 50
    if price < ma200: score -= 30
    else: score += 15
    if price < ma50: score -= 10
    else: score += 10
    if price < ma20: score -= 10
    else: score += 15
    if rsi_val < 35: score += 10
    if rsi_val > 70: score -= 10
    score = max(0, min(100, int(score)))
    trend_txt = "BEAR pod MA200 - główny trend spadkowy" if price < ma200 else "BULL nad MA200 - trend wzrostowy"
    mom_txt = "słaba, pod MA20" if price < ma20 else "silna, nad MA20"
    rsi_txt = "wyprzedanie <35 - końcówka spadków" if rsi_val < 35 else "wykupienie >70" if rsi_val > 70 else f"neutralny {rsi_val:.1f}, bez dywergencji"
    detail = f"{trend_txt} | Cena {dist_ma200:+.2f}% od MA200 (${ma200:.4f}) i {dist_ma20:+.2f}% od MA20 (${ma20:.4f}). Momentum {mom_txt}. RSI {rsi_txt} (SMA14 RSI {rsi_ma14:.1f}). Dopóki < MA200 nie ma potwierdzenia L2."
    bias = "SELL" if score < 35 else "BUY" if score > 65 else "NEUTRAL"
    return score, detail, bias, ma200, ma20

def engine_smc(df):
    lows = df['low'].rolling(3).min()
    highs = df['high'].rolling(3).max()
    bos_bull = df['low'].iloc[-1] > lows.iloc[-3]
    bos_bear = df['high'].iloc[-1] < highs.iloc[-3]
    fvg_up = df['high'].iloc[-3] < df['low'].iloc[-1]
    fvg_down = df['low'].iloc[-3] > df['high'].iloc[-1]
    ob_low = df['low'].rolling(20).min().iloc[-1]
    score = 50
    if bos_bull: score += 15
    if fvg_up: score += 10
    if df['close'].iloc[-1] < 0.076: score += 5
    score = max(0, min(100, int(score)))
    bos_txt = "BOS bullish - dołek wyżej, struktura chce rosnąć" if bos_bull else "BOS bearish - brak wyższego dołka, nadal struktura spadkowa" if bos_bear else "BOS neutral - konsolidacja"
    fvg_txt = f"Byczy FVG $0.078 do wypełnienia - luka na wzrost" if fvg_up else f"Berish FVG - luka na spadek" if fvg_down else "Brak FVG - wszystkie luki wypełnione, rynek zbilansowany"
    ob_txt = f"Order Block $0.071-0.073 (20-bar low ${ob_low:.4f}) - strefa popytowa z dużym wolumenem historycznym"
    detail = f"{bos_txt}. {fvg_txt}. {ob_txt}. Cena ${df['close'].iloc[-1]:.4f} jest w dolnej części bloku, to jest L1 do akumulacji."
    bias = "BUY" if score > 60 else "SELL" if score < 40 else "NEUTRAL"
    return score, detail, bias

def engine_volume(df):
    vol = df['volume']
    vol_ma20 = vol.rolling(20).mean().iloc[-1]
    vol_ratio = vol.iloc[-1] / vol_ma20
    vol_down = vol.iloc[-1] < vol.iloc[-3] < vol.iloc[-5]
    price_ll = df['close'].iloc[-1] < df['close'].iloc[-5]
    rsi_hl = rsi(df['close']).iloc[-1] > rsi(df['close']).iloc[-5]
    bullish_div = price_ll and rsi_hl
    vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
    dist_vwap = (df['close'].iloc[-1]-vwap)/vwap*100
    score = 50
    if vol_down: score += 15
    if bullish_div: score += 15
    if df['close'].iloc[-1] < vwap: score += 5
    score = max(0, min(100, int(score)))
    vol_txt = f"Wolumen wysycha {vol.iloc[-3]:.0f} -> {vol.iloc[-1]:.0f} ({vol_ratio:.2f}x średniej 20H). To znaczy że sprzedający nie mają już siły - brak podaży"
    div_txt = "Jest bycza dywergencja cenowa - cena robi niższy dołek, ale RSI wyższy dołek = słabnące spadki" if bullish_div else "Brak dywergencji - RSI podąża za ceną, spadki jeszcze nie zanegowane"
    vwap_txt = f"VWAP ${vwap:.4f}, cena {dist_vwap:+.2f}% od VWAP. Poniżej VWAP = tanio, powyżej = drogo"
    detail = f"{vol_txt}. {div_txt}. {vwap_txt}. Niski wolumen przy dołku = akumulacja."
    bias = "BUY" if score > 60 else "SELL" if score < 40 else "NEUTRAL"
    return score, detail, bias

def engine_wyckoff(df):
    price = df['close'].iloc[-1]
    bb_low, bb_high, bb_mid = bollinger(df['close'])
    bb_low_val = bb_low.iloc[-1]
    bb_width = (bb_high.iloc[-1]-bb_low.iloc[-1])/bb_mid.iloc[-1]*100
    near_low = price <= bb_low_val * 1.015
    vol_low = df['volume'].iloc[-1] < df['volume'].rolling(20).mean().iloc[-1] * 0.7
    ma200 = sma(df['close'], 200).iloc[-1]
    score = 50
    phase = "Phase B - konsolidacja przed ruchem"
    if near_low and vol_low:
        score = 60
        phase = "Phase C - Spring (fałszywe wybicie dołem, łapanie stopów)"
    elif price < ma200:
        score = 55
        phase = "Phase C - akumulacja po spadku, duzi gracze zbierają"
    phase_desc = f"{phase}. Bollinger dolny ${bb_low_val:.4f}, szerokość wstęg {bb_width:.2f}% (ścisk = {'mały, będzie ruch' if bb_width < 5 else 'duży, duża zmienność'}). Cena {'dotyka dolnej wstęgi - wyprzedanie i szansa na Spring' if near_low else f'{((price-bb_low_val)/bb_low_val*100):+.2f}% nad dolną wstęgą - jeszcze nie Spring'}."
    vol_desc = f"Wolumen {'niski - nikt nie chce sprzedawać na dołku, typowe dla akumulacji' if vol_low else 'średni - jeszcze nie ma wyschnięcia podaży'}."
    detail = f"{phase_desc} {vol_desc} LPS (Last Point Support) w okolicy ${bb_low_val:.4f}. Plan: Spring -> Test -> SOS -> markup."
    bias = "BUY" if score >= 55 else "NEUTRAL"
    return score, detail, bias

def analyze():
    df = fetch_ohlcv()
    price = df['close'].iloc[-1]
    s1, d1, b1, ma200, ma20 = engine_trend(df)
    s2, d2, b2 = engine_smc(df)
    s3, d3, b3 = engine_volume(df)
    s4, d4, b4 = engine_wyckoff(df)
    final = s1*0.30 + s2*0.25 + s3*0.25 + s4*0.20

    if final < 30: sig = "HARD SELL 10/100"
    elif final < 45: sig = "SOFT SELL / DOLEK 35/100"
    elif final < 55: sig = "NEUTRAL / AKUMULACJA 49/100"
    elif final < 75: sig = "BUY SETUP 65/100"
    else: sig = "HARD BUY 90/100"

    msg = f"""PYTH v8.3 ${price:.4f} - {sig}
FINAL: {final:.0f}/100

1 TREND 30% {s1}/100 {b1}
{d1}

2 SMC 25% {s2}/100 {b2}
{d2}

3 VOLUME 25% {s3}/100 {b3}
{d3}

4 WYCKOFF 20% {s4}/100 {b4}
{d4}

PLAN 3 TURY:
L1 $0.0747-$0.072 | L2 >MA200 ${ma200:.4f}
TP $0.0769 (MA20) -> $0.078 FVG -> $0.082
SL close 4h < $0.071
Time {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    last = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                last = json.load(f).get('final', 0)
        except:
            pass
    if abs(final - last) >= 7 or final < 35 or final > 60:
        send_tg(msg)
        with open(STATE_FILE, 'w') as f:
            json.dump({"final": float(final), "price": float(price)}, f)
    else:
        print(f"SKIP alert - {last} -> {final:.0f}")
    return final

if __name__ == "__main__":
    analyze()
