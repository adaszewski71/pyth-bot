# PYTH BOT v8.1 FINAL FIX - 4 ENGINES OBJECTIVE
# Fixed Binance WAF on GitHub Actions

import pandas as pd
import numpy as np
import requests
import time
import yaml
import os
from datetime import datetime

SYMBOL = 'PYTHUSDT'
TIMEFRAME = '1h'
CONFIG_FILE = 'config.yml'

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
        if not token or not chat_id: return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
    except: pass

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

    print(f"FETCH FAILED: {last_error}")
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
    detail = f"MA200 ${ma200:.4f} MA20 ${ma20:.4f} RSI {rsi_val:.1f}"
    bias = "SELL" if score < 35 else "BUY" if score > 65 else "NEUTRAL"
    return score, detail, bias, ma200, ma20

def engine_smc(df):
    lows = df['low'].rolling(3).min()
    bos_bull = df['low'].iloc[-1] > lows.iloc[-3]
    fvg_up = df['high'].iloc[-3] < df['low'].iloc[-1]

    score = 50
    if bos_bull: score += 15
    if fvg_up: score += 10
    if df['close'].iloc[-1] < 0.076: score += 5

    score = max(0, min(100, int(score)))
    detail = f"{'BOS bull' if bos_bull else 'BOS bear'} OB $0.071-0.073 FVG {'$0.078' if fvg_up else 'brak'}"
    bias = "BUY" if score > 60 else "SELL" if score < 40 else "NEUTRAL"
    return score, detail, bias

def engine_volume(df):
    vol = df['volume']
    vol_down = vol.iloc[-1] < vol.iloc[-3] < vol.iloc[-5]
    price_ll = df['close'].iloc[-1] < df['close'].iloc[-5]
    rsi_hl = rsi(df['close']).iloc[-1] > rsi(df['close']).iloc[-5]
    bullish_div = price_ll and rsi_hl
    vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()

    score = 50
    if vol_down: score += 15
    if bullish_div: score += 15
    if df['close'].iloc[-1] < vwap: score += 5

    score = max(0, min(100, int(score)))
    detail = f"Vol {vol.iloc[-3]:.0f}->{vol.iloc[-1]:.0f} Div {bullish_div} VWAP ${vwap:.4f}"
    bias = "BUY" if score > 60 else "SELL" if score < 40 else "NEUTRAL"
    return score, detail, bias

def engine_wyckoff(df):
    price = df['close'].iloc[-1]
    bb_low, _, _ = bollinger(df['close'])
    bb_low_val = bb_low.iloc[-1]
    near_low = price <= bb_low_val * 1.015
    vol_low = df['volume'].iloc[-1] < df['volume'].rolling(20).mean().iloc[-1] * 0.7

    score = 50
    phase = "Phase B-C"
    if near_low and vol_low:
        score = 60
        phase = "Phase C - Spring"
    elif price < sma(df['close'], 200).iloc[-1]:
        score = 55
        phase = "Accumulation"

    detail = f"{phase} LPS ${bb_low_val:.4f} VolLow {vol_low}"
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

    msg = f"""PYTH v8.1 ${price:.4f} - {sig}
FINAL: {final:.0f}/100

1 TREND 30% {s1}/100 {b1}
{d1}
2 SMC 25% {s2}/100 {b2}
{d2}
3 VOLUME 25% {s3}/100 {b3}
{d3}
4 WYCKOFF 20% {s4}/100 {b4}
{d4}

PLAN:
L1 $0.0747-$0.072 | L2 >MA200 ${ma200:.4f}
TP $0.0769 (MA20) -> $0.078 FVG -> $0.082
SL close 4h < $0.071
Time {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    print(msg)
    send_tg(msg)
    return final

if __name__ == "__main__":
    analyze()
