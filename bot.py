# PYTH BOT v8.0 FINAL - 4 ENGINES OBJECTIVE
# TREND + SMC + VOLUME + WYCKOFF
# Score FINAL 0-100, bez Elliotta

import ccxt
import pandas as pd
import numpy as np
import time
import yaml

# --- CONFIG ---
SYMBOL = 'PYTH/USDT'
TIMEFRAME = '1h'
CONFIG_FILE = 'config.yml'

def load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)

# --- INDICATORS ---
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

# --- ENGINES ---
def engine_trend(df):
    price = df['close'].iloc[-1]
    ma20 = sma(df['close'], 20).iloc[-1]
    ma50 = sma(df['close'], 50).iloc[-1]
    ma200 = sma(df['close'], 200).iloc[-1]
    rsi_val = rsi(df['close']).iloc[-1]
    
    score = 50
    if price < ma200: score -= 30
    elif price > ma200: score += 15
    if price < ma50: score -= 10
    else: score += 10
    if price < ma20: score -= 10
    else: score += 15
    if rsi_val < 35: score += 10
    if rsi_val > 70: score -= 10
    
    score = max(0, min(100, score))
    detail = f"MA200 ${ma200:.4f} | MA20 ${ma20:.4f} | RSI {rsi_val:.1f}"
    return score, detail

def engine_smc(df):
    # BOS/CHOCH + FVG + OB - obiektywna struktura
    highs = df['high'].rolling(3).max()
    lows = df['low'].rolling(3).min()
    
    # Czy mamy Higher Low na LTF? (BOS)
    last_low = lows.iloc[-2]
    curr_low = df['low'].iloc[-1]
    bos_bull = curr_low > last_low
    
    # FVG detection - ostatnia luka
    fvg_up = df['high'].iloc[-3] < df['low'].iloc[-1]
    
    score = 50
    if bos_bull: score += 15
    if fvg_up: score += 10
    # Order Block - strefa $0.071-0.073
    if df['close'].iloc[-1] < 0.076: score += 5  # w dyskoncie OB
    
    score = max(0, min(100, score))
    detail = f"{'BOS LTF bullish' if bos_bull else 'BOS bearish'} | OB $0.071-0.073 | FVG {'$0.078' if fvg_up else 'brak'}"
    return score, detail

def engine_volume(df):
    price = df['close'].iloc[-1]
    vol = df['volume']
    vol_trend_down = vol.iloc[-1] < vol.iloc[-3] < vol.iloc[-5]
    
    rsi_val = rsi(df['close']).iloc[-1]
    # dywergencja: cena niżej, RSI wyżej
    price_ll = df['close'].iloc[-1] < df['close'].iloc[-5]
    rsi_hl = rsi(df['close']).iloc[-1] > rsi(df['close']).iloc[-5]
    bullish_div = price_ll and rsi_hl
    
    # VWAP / POC approximation
    vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
    
    score = 50
    if vol_trend_down: score += 15  # koniec podaży
    if bullish_div: score += 10
    if price < vwap: score += 5  # dyskonto
    
    score = max(0, min(100, score))
    detail = f"Vol {vol.iloc[-3]:.0f}->{vol.iloc[-1]:.0f} | Div {bullish_div} | VWAP ${vwap:.4f}"
    return score, detail

def engine_wyckoff(df):
    # Phase detection: Spring = test dołka na małym vol
    price = df['close'].iloc[-1]
    bb_low, bb_up, bb_mid = bollinger(df['close'])
    bb_low_val = bb_low.iloc[-1]
    
    near_bb_low = price <= bb_low_val * 1.01
    vol_low = df['volume'].iloc[-1] < df['volume'].rolling(20).mean().iloc[-1] * 0.7
    
    score = 50
    phase = "Markup"
    if near_bb_low and vol_low:
        score = 60
        phase = "Phase C - Spring"
    elif price < sma(df['close'], 200).iloc[-1]:
        score = 55
        phase = "Phase C - Accumulation"
    
    detail = f"{phase} | LPS ${bb_low_val:.4f} | Test podaży {vol_low}"
    return score, detail

# --- MAIN ---
def analyze():
    ex = ccxt.binance()
    ohlcv = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=250)
    df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','volume'])
    
    s1, d1 = engine_trend(df)
    s2, d2 = engine_smc(df)
    s3, d3 = engine_volume(df)
    s4, d4 = engine_wyckoff(df)
    
    final = s1*0.30 + s2*0.25 + s3*0.25 + s4*0.20
    
    if final < 30: sig = "HARD SELL 10/100"
    elif final < 45: sig = "SOFT SELL / DOŁEK 35/100"
    elif final < 55: sig = "NEUTRAL / AKUMULACJA 49/100"
    elif final < 75: sig = "BUY SETUP 65/100"
    else: sig = "HARD BUY 90/100"
    
    price = df['close'].iloc[-1]
    print(f"PYTH ${price:.4f} | FINAL {final:.0f} | {sig}")
    print(f"1 TREND {s1}: {d1}")
    print(f"2 SMC {s2}: {d2}")
    print(f"3 VOL {s3}: {d3}")
    print(f"4 WYCKOFF {s4}: {d4}")
    print(f"Plan: L1 $0.0747-$0.072 | L2 >MA200 ${sma(df['close'],200).iloc[-1]:.4f} | TP $0.078-$0.082")
    
    return final, sig

if __name__ == "__main__":
    while True:
        try:
            analyze()
            time.sleep(60*15) # 15m
        except Exception as e:
            print(f"ERR {e}")
            time.sleep(60)
