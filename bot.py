import requests, os, sys
from datetime import datetime, timezone

def get_rsi(prices, period=14):
    if len(set(prices)) <= 1: return 55.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_klines(limit=100):
    for url in [f"https://data-api.binance.vision/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}", f"https://api.binance.com/api/v3/klines?symbol=PYTHUSDT&interval=1h&limit={limit}"]:
        try:
            resp = requests.get(url, timeout=10).json()
            if isinstance(resp, list) and len(resp) > 20:
                return [float(x[4]) for x in resp], [float(x[5]) for x in resp], [float(x[2]) for x in resp], [float(x[3]) for x in resp]
        except: pass
    return [0.078]*100, [1]*100, [0.08]*100, [0.07]*100

def get_coingecko():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false", timeout=10).json()
        md = r['market_data']
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
    if closes[-1] < closes[-20] and volumes[-1] > vol_avg*1.5 and rsi < 40: return "Duzi gracze po cichu skupują (akumulacja) 🌸", +20
    if closes[-1] > closes[-20] and volumes[-1] > vol_avg*1.5 and rsi > 60: return "Duzi gracze rozładowują torby (dystrybucja) 🌩️", -20
    if rsi < 35: return "Rynek wyprzedany, ludzie panikują", +10
    if rsi > 70: return "Rynek przegrzany", -15
    return "Konsolidacja", 0

def detect_elliot(closes, highs, lows):
    change = (closes[-1] - closes[-20]) / closes[-20] * 100
    if change > 5: return f"Mocny impuls w górę (+{change:.1f}%) 📈", +15
    if change < -5: return f"Korekta w dół ({change:.1f}%) 📉", -15
    return "Boczniak, czeka na sygnał", 0

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN"); chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: print(text); return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)

def analyze(force_report=False):
    price, chg, mcap, vol = get_coingecko()
    funding = get_funding(); tvs = get_tvs()
    closes, volumes, highs, lows = get_klines()
    rsi = get_rsi(closes); fg_val, fg_class = get_fear_greed()
    link_tvs, pyth_tvs, red_tvs, share = get_oracle_competition()
    wyckoff_txt, wyckoff_score = detect_wyckoff(closes, volumes, rsi)
    elliot_txt, elliot_score = detect_elliot(closes, highs, lows)

    score = 50
    if funding > 0.05: score -= 20
    elif funding > 0.02: score -= 10
    if funding < -0.02: score += 15
    if rsi > 75: score -= 20
    elif rsi < 30: score += 20
    elif 40 <= rsi <= 65: score += 15
    if fg_val < 25: score += 15
    elif fg_val > 75: score -= 15
    if share > 6.5: score += 10
    elif share < 5.0: score -= 10
    score += wyckoff_score + elliot_score
    score = max(0, min(100, score))

    if score >= 80: decyzja = "KUPUJ - mocny sygnał 🔥"
    elif score >= 60: decyzja = "Można kupować, ale ostrożnie ✅"
    elif score <= 30: decyzja = "UWAŻAJ - sygnał sprzedaży ⚠️"
    else: decyzja = "CZEKAJ ➡️"

    now_str = datetime.now().strftime("%d.%m %H:%M")
    utc_hour = datetime.now(timezone.utc).hour
    report_slots = {5: "☀️ Dzień dobry! Poranny 7:00", 13: "🌤️ Popołudniowy 15:00", 19: "🌙 Wieczorny 21:00"}
    slot_header = report_slots.get(utc_hour)

    if not (force_report or slot_header or score >=80 or score <=25 or fg_val <20 or fg_val >85):
        print(f"[{now_str}] cicho {score}"); sys.exit(0)

    header = f"🔥 *TEST v9.3.2 FULL*" if force_report else (slot_header or f"🚨 *ALERT {score}/100*") + f" - {now_str}"
    unlock_days = (datetime(2027,5,19,tzinfo=timezone.utc)-datetime.now(timezone.utc)).days

    msg = f"{header}\n\n"
    msg += f"Cześć! PYTH teraz ${price:.4f} ({chg:+.2f}% 24h).\n"
    msg += f"Wolumen ${vol:.1f}M | Mcap ${mcap:.2f}B | TVS ${tvs:.2f}B\n\n"

    if fg_val < 25: msg += f"Nastroje: Strach {fg_val}/100 {fg_class} - panika, często okazja do kupna.\n\n"
    elif fg_val > 75: msg += f"Nastroje: Chciwość {fg_val}/100 {fg_class} - euforia, ryzyko korekty.\n\n"
    else: msg += f"Nastroje: {fg_val}/100 {fg_class} - neutralnie.\n\n"

    msg += f"Konkurencja: LINK ${link_tvs:.0f}B | PYTH ${pyth_tvs:.1f}B ({share:.1f}%) | RED ${red_tvs:.1f}B\n"
    if share > 6.5: msg += "→ Zyskujemy udziały 🚀\n\n"
    elif share < 5.0: msg += "→ Tracimy vs RedStone ⚠️\n\n"
    else: msg += "→ Stabilnie\n\n"

    msg += f"Duzi gracze: {wyckoff_txt}\n"
    msg += f"Trend: {elliot_txt}\n"
    msg += f"RSI {rsi:.1f} | Funding {funding:+.4f}% | Siła {score}/100\n\n"
    msg += f"Wniosek: *{decyzja}*\n"
    msg += f"Unlock 2.13B PYTH za {unlock_days} dni"

    print(msg); send_telegram(msg)

if __name__ == "__main__":
    analyze(force_report=True)
