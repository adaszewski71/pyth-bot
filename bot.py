import requests, os, sys
from datetime import datetime, timezone

# ============ TA BEZ PANDAS ============
def ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period
    for p in prices[period:]:
        ema_val = p * k + ema_val * (1 - k)
    return ema_val

def get_rsi(prices, period=14):
    if len(set(prices[-period:])) <= 1: return 55.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def get_macd(prices):
    e12 = ema(prices, 12); e26 = ema(prices, 26)
    macd_line = e12 - e26
    # signal 9 z macd history - uproszczenie: ema z ostatnich 30 macd
    # liczymy szybkie macd history
    macds = []
    for i in range(26, len(prices)):
        macds.append(ema(prices[:i+1], 12) - ema(prices[:i+1], 26))
    signal = ema(macds, 9) if len(macds) >= 9 else macds[-1] if macds else 0
    hist = macd_line - signal
    return macd_line, signal, hist

def get_bollinger(prices, period=20, std=2):
    if len(prices) < period: return prices[-1], prices[-1], prices[-1]
    sma = sum(prices[-period:]) / period
    var = sum((p - sma) ** 2 for p in prices[-period:]) / period
    sd = var ** 0.5
    return sma + sd*std, sma, sma - sd*std

def get_stoch(highs, lows, closes, k=14, d=3):
    if len(closes) < k: return 50, 50
    hh = max(highs[-k:]); ll = min(lows[-k:])
    if hh == ll: return 50, 50
    k_val = (closes[-1] - ll) / (hh - ll) * 100
    return k_val, k_val # uproszczone D=K dla 1 pkt

def get_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else sum(trs)/len(trs)

def get_klines(limit=100):
    for url in [f"https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}", f"https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}"]:
        try:
            resp = requests.get(url, timeout=10).json()
            if isinstance(resp, list) and len(resp) > 20:
                closes = [float(x[4]) for x in resp]; volumes = [float(x[5]) for x in resp]
                highs = [float(x[2]) for x in resp]; lows = [float(x[3]) for x in resp]
                return closes, volumes, highs, lows
        except: pass
    return [0.078]*100, [1]*100, [0.08]*100, [0.07]*100

def get_coingecko():
    try:
        md = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false", timeout=10).json()['market_data']
        return md['current_price']['usd'], md['price_change_percentage_24h'], md['market_cap']['usd']/1e9, md['total_volume']['usd']/1e6
    except: return 0.0769, -0.30, 0.607, 34.1

def get_funding():
    try: return float(requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=PYTHUSDT", timeout=10).json().get('lastFundingRate', 0.0001))*100
    except: return 0.01

def get_tvs():
    try: return float(requests.get("https://api.llama.fi/protocol/pyth-network", timeout=10).json().get('tvl', 3.589e9))/1e9
    except: return 3.589

def get_fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()['data'][0]
        return int(d['value']), d['value_classification']
    except: return 50, "Neutral"

def get_oracle_competition():
    try:
        r = requests.get("https://api.llama.fi/oracles", timeout=10).json()
        data = {o['name'].lower(): float(o['tvl'])/1e9 for o in r}
        chainlink, pyth, red = data.get('chainlink', 39.3), data.get('pyth', 2.79), data.get('redstone', 4.1)
        total = sum([v for v in data.values() if v > 0.1])
        share = (pyth/total*100) if total else 5.9
        return chainlink, pyth, red, share
    except: return 39.3, 2.79, 4.1, 5.9

def detect_wyckoff(closes, volumes, rsi):
    vol_avg = sum(volumes[-20:]) / 20
    if closes[-1] < closes[-20] and volumes[-1] > vol_avg*1.5 and rsi < 40: return "Akumulacja 🌸", +20
    if closes[-1] > closes[-20] and volumes[-1] > vol_avg*1.5 and rsi > 60: return "Dystrybucja 🌩️", -20
    if rsi < 35: return "Wyprzedany", +10
    if rsi > 70: return "Przegrzany", -15
    return "Konsolidacja", 0

def detect_elliot(closes):
    change = (closes[-1] - closes[-20]) / closes[-20] * 100
    if change > 5: return f"Impuls +{change:.1f}% 📈", +15
    if change < -5: return f"Korekta {change:.1f}% 📉", -15
    return "Boczniak", 0

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN"); chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: print(text); return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)

def analyze(force_report=False):
    price, chg, mcap, vol = get_coingecko(); funding = get_funding(); tvs = get_tvs()
    closes, volumes, highs, lows = get_klines()
    rsi = get_rsi(closes); fg_val, fg_class = get_fear_greed()
    link_tvs, pyth_tvs, red_tvs, share = get_oracle_competition()
    wyckoff_txt, wyckoff_score = detect_wyckoff(closes, volumes, rsi)
    elliot_txt, elliot_score = detect_elliot(closes)

    # --- NOWE TA ---
    ema9 = ema(closes, 9); ema21 = ema(closes, 21); ema50 = ema(closes, 50); ema200 = ema(closes, 200)
    macd_line, macd_signal, macd_hist = get_macd(closes)
    bb_up, bb_mid, bb_low = get_bollinger(closes)
    stoch_k, stoch_d = get_stoch(highs, lows, closes)
    atr = get_atr(highs, lows, closes)
    vol_sma = sum(volumes[-20:])/20

    score = 50
    # EMA trend
    if price > ema9 > ema21: score += 10
    elif price < ema9 < ema21: score -= 10
    if price > ema200: score += 10
    else: score -= 10
    # MACD
    if macd_hist > 0 and macd_line > macd_signal: score += 10
    elif macd_hist < 0: score -= 10
    # RSI + BB
    if rsi < 30 and price < bb_low: score += 15
    elif rsi > 70 and price > bb_up: score -= 15
    elif 40 <= rsi <= 65: score += 5
    # Stochastic
    if stoch_k < 20: score += 10
    elif stoch_k > 80: score -= 10
    # Volume
    if volumes[-1] > vol_sma*1.5: score += 5

    if funding > 0.05: score -= 20
    if funding < -0.02: score += 15
    if fg_val < 25: score += 15
    elif fg_val > 75: score -= 10
    score += wyckoff_score + elliot_score
    score = max(0, min(100, score))

    if score >= 80: decyzja = "KUPUJ 🔥"
    elif score >= 60: decyzja = "Można kupować ✅"
    elif score <= 30: decyzja = "SPRZEDAJ ⚠️"
    else: decyzja = "CZEKAJ ➡️"

    now_str = datetime.now().strftime("%d.%m %H:%M")
    utc_hour = datetime.now(timezone.utc).hour
    report_slots = {5: "☀️ Poranny 7:00", 13: "🌤️ Popołudniowy 15:00", 19: "🌙 Wieczorny 21:00"}
    slot_header = report_slots.get(utc_hour)

    if not (force_report or slot_header or score >=80 or score <=25 or fg_val <20 or fg_val >85):
        print(f"[{now_str}] cicho {score}"); sys.exit(0)

    header = f"🔥 *TEST v9.4 TA*" if force_report else (slot_header or f"🚨 *ALERT {score}/100*") + f" - {now_str}"
    unlock_days = (datetime(2027,5,19,tzinfo=timezone.utc)-datetime.now(timezone.utc)).days

    # Support/Resist
    support = min(lows[-50:]); resist = max(highs[-50:])

    msg = f"{header}\n\n"
    msg += f"PYTH ${price:.4f} ({chg:+.2f}%) Vol ${vol:.1f}M\n"
    msg += f"Mcap ${mcap:.2f}B | TVS ${tvs:.2f}B\n\n"

    msg += f"*TA:*\n"
    msg += f"EMA: 9=${ema9:.4f} 21=${ema21:.4f} 50=${ema50:.4f} 200=${ema200:.4f}\n"
    msg += f"{'🟢' if price>ema200 else '🔴'} Cena {'nad' if price>ema200 else 'pod'} EMA200\n"
    msg += f"MACD: {macd_line:.5f}/{macd_signal:.5f} Hist {macd_hist:+.5f} {'🟢' if macd_hist>0 else '🔴'}\n"
    msg += f"BB: Gora ${bb_up:.4f} Dol ${bb_low:.4f} {'🔵 przy dolnej - odbicie?' if price<bb_low*1.01 else '🔴 przy gornej' if price>bb_up*0.99 else ''}\n"
    msg += f"RSI {rsi:.1f} | Stoch {stoch_k:.0f} | ATR {atr:.5f}\n"
    msg += f"Sup ${support:.4f} Res ${resist:.4f}\n"
    msg += f"Vol {'🔥' if volumes[-1]>vol_sma*1.5 else '😴'} {volumes[-1]/vol_sma:.1f}x SMA20\n\n"

    msg += f"F&G {fg_val}/100 {fg_class}\n"
    msg += f"Oracle: LINK ${link_tvs:.0f}B | PYTH ${pyth_tvs:.1f}B ({share:.1f}%) | RED ${red_tvs:.1f}B\n"
    msg += f"Wyckoff: {wyckoff_txt} | Elliot: {elliot_txt}\n"
    msg += f"Funding {funding:+.4f}% | Siła {score}/100\n\n"
    msg += f"Wniosek: *{decyzja}* | Unlock za {unlock_days}d"

    print(msg); send_telegram(msg)

if __name__ == "__main__":
    analyze(force_report=True)
