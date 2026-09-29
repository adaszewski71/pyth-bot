import requests, statistics, os, json, time

PHONE = "48668873755"
APIKEY = "1212249"
STATE_FILE = "last_alert.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f: return json.load(f)
        except: pass
    return {"time":0, "price":0}

def save_state(price):
    with open(STATE_FILE,'w') as f: json.dump({"time":time.time(),"price":price}, f)

def run():
    state = load_state()
    # anti-spam 1h
    if time.time() - state["time"] < 3600:
        print("Anti-spam, czekam")
        return

    url = "https://api.exchange.coinbase.com/products/PYTH-USD/candles?granularity=3600"
    candles = sorted(requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15).json())[-50:]
    closes = [c[4] for c in candles]
    vols = [c[5] for c in candles]
    price = closes[-1]
    avg_vol = statistics.mean(vols[-20:])

    is_breakout = price > 0.082 and vols[-1] > avg_vol * 1.3
    is_pump = price > state["price"] * 1.03 and price > 0.078 # 3% w górę

    if is_breakout or is_pump:
        msg = f"PYTH_MAX_ALERT_{price:.5f}_VOL_{vols[-1]/avg_vol:.1f}x"
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text={msg}&apikey={APIKEY}", timeout=10)
        save_state(price)
        print(f"ALERT {msg}")

    # NEWS - ruch 24h
    cg = requests.get("https://api.coingecko.com/api/v3/coins/pyth-network", headers={"User-Agent":"Mozilla/5.0"}, timeout=15).json()
    change = cg['market_data']['price_change_percentage_24h']
    if abs(change) > 6:
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={PHONE}&text=PYTH_NEWS_{change:.1f}pct&apikey={APIKEY}", timeout=10)
        save_state(price)

if __name__ == "__main__":
    run()
