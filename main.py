import pandas as pd
import yfinance as yf
import time
import os
import warnings
from datetime import datetime

warnings.simplefilter(action='ignore', category=FutureWarning)

# --- Embedded configuration ---
config = {
    "UPDATE_PROTECT": True,
    "PAIRS": ["CAD=X", "JPY=X", "GBPUSD=X", "EURUSD=X", "GC=F"],
    "YF_PERIOD": "3d",
    "YF_INTERVAL": "1m",
    "TRADE_SETTINGS": {
        "TP1_PIPS": 40,
        "TP2_PIPS": 40,
        "TP3_PIPS": 40,
        "STOP_LOSS_PIPS": 50
    },
    "PAPER_TRADING": True,
    "VERBOSE": True,
    "MONITOR_SLEEP": 10
}

PAIRS = config["PAIRS"]
TP1 = config["TRADE_SETTINGS"]["TP1_PIPS"]
TP2 = config["TRADE_SETTINGS"]["TP2_PIPS"]
TP3 = config["TRADE_SETTINGS"]["TP3_PIPS"]
SL = config["TRADE_SETTINGS"]["STOP_LOSS_PIPS"]
SLEEP = config["MONITOR_SLEEP"]

LOG_FILE = "trade_log.csv"
if not os.path.exists(LOG_FILE):
    df_log = pd.DataFrame(columns=[
        "Timestamp", "Pair", "Signal", "Entry", "TP1_hit", "TP2_hit", "TP3_hit", "SL_hit"
    ])
    df_log.to_csv(LOG_FILE, index=False)

# --- ANSI color codes ---
class bcolors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

# --- Additional state for cumulative P/L ---
closed_pips = {pair:0 for pair in PAIRS}

# --- Bot Functions ---
def fetch_data(pair):
    try:
        df = yf.download(pair, period=config["YF_PERIOD"], interval=config["YF_INTERVAL"])
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"[ERROR] Failed to download {pair}: {e}")
        return None

def precision_signal(df):
    close = df['Close']
    if len(close) < 50:
        return None, None
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))

    last_close = close.iloc[-1].item()
    prev_ema9 = ema9.iloc[-2].item()
    last_ema9 = ema9.iloc[-1].item()
    prev_ema21 = ema21.iloc[-2].item()
    last_ema21 = ema21.iloc[-1].item()
    last_ema50 = ema50.iloc[-1].item()
    last_rsi = rsi.iloc[-1].item()

    buy_signal = prev_ema9 < prev_ema21 and last_ema9 > last_ema21 and last_close > last_ema50 and last_rsi < 70
    sell_signal = prev_ema9 > prev_ema21 and last_ema9 < last_ema21 and last_close < last_ema50 and last_rsi > 30

    if buy_signal:
        return "BUY", last_close
    elif sell_signal:
        return "SELL", last_close
    return None, None

def check_trade(pair, signal, entry):
    df = fetch_data(pair)
    if df is None:
        return None
    last = df['Close'].iloc[-1].item()
    hits = {"TP1_hit": False, "TP2_hit": False, "TP3_hit": False, "SL_hit": False}
    factor = 10000 if "USD" in pair else 1

    if signal == "BUY":
        if last >= entry + TP1*factor: hits["TP1_hit"] = True
        if last >= entry + TP2*factor: hits["TP2_hit"] = True
        if last >= entry + TP3*factor: hits["TP3_hit"] = True
        if last <= entry - SL*factor: hits["SL_hit"] = True
    elif signal == "SELL":
        if last <= entry - TP1*factor: hits["TP1_hit"] = True
        if last <= entry - TP2*factor: hits["TP2_hit"] = True
        if last <= entry - TP3*factor: hits["TP3_hit"] = True
        if last >= entry + SL*factor: hits["SL_hit"] = True

    return hits

def log_trade(pair, signal, entry, hits):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df = pd.read_csv(LOG_FILE)
    df = pd.concat([df, pd.DataFrame([{
        "Timestamp": timestamp,
        "Pair": pair,
        "Signal": signal,
        "Entry": entry,
        **hits
    }])], ignore_index=True)
    df.to_csv(LOG_FILE, index=False)

def calculate_pips(signal, entry, last, pair):
    factor = 10000 if "USD" in pair else 1
    if signal == "BUY":
        return (last - entry) * factor
    elif signal == "SELL":
        return (entry - last) * factor
    return 0

def dashboard(active_trades, closed_stats, closed_pips):
    os.system('cls' if os.name=='nt' else 'clear')
    print("====== Precision Bot Live Dashboard ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print("Active Trades:")
    if not active_trades:
        print("  None")
    for pair, (signal, entry, hits) in active_trades.items():
        tp1 = bcolors.GREEN+"✔"+bcolors.RESET if hits["TP1_hit"] else bcolors.YELLOW+"…"+bcolors.RESET
        tp2 = bcolors.GREEN+"✔"+bcolors.RESET if hits["TP2_hit"] else bcolors.YELLOW+"…"+bcolors.RESET
        tp3 = bcolors.GREEN+"✔"+bcolors.RESET if hits["TP3_hit"] else bcolors.YELLOW+"…"+bcolors.RESET
        sl  = bcolors.RED+"✖"+bcolors.RESET if hits["SL_hit"] else bcolors.YELLOW+"…"+bcolors.RESET
        df = fetch_data(pair)
        last_price = df['Close'].iloc[-1].item() if df is not None else entry
        live_pips = calculate_pips(signal, entry, last_price, pair)
        color = bcolors.GREEN if live_pips >=0 else bcolors.RED
        print(f"  {pair}: {signal} @ {entry:.5f} | TP1:{tp1} TP2:{tp2} TP3:{tp3} SL:{sl} | Live P/L: {color}{live_pips:.1f} pips{bcolors.RESET}")

    print("\nClosed Trades Stats:")
    total = closed_stats['total']
    wins = closed_stats['wins']
    losses = closed_stats['losses']
    win_rate = (wins / total * 100) if total>0 else 0
    print(f"  Wins: {bcolors.GREEN}{wins}{bcolors.RESET} | Losses: {bcolors.RED}{losses}{bcolors.RESET} | Total: {total} | Win Rate: {bcolors.GREEN if win_rate>=50 else bcolors.RED}{win_rate:.2f}%{bcolors.RESET}")
    
    print("\nCumulative P/L per Pair (Closed Trades):")
    for pair, pips in closed_pips.items():
        color = bcolors.GREEN if pips >=0 else bcolors.RED
        print(f"  {pair}: {color}{pips:.1f} pips{bcolors.RESET}")
    
    print("========================================")

def run_bot():
    active_trades = {}
    closed_stats = {"wins": 0, "losses": 0, "total": 0}
    while True:
        for pair in PAIRS:
            if pair not in active_trades:
                df = fetch_data(pair)
                if df is None:
                    continue
                signal, entry = precision_signal(df)
                if signal:
                    active_trades[pair] = (signal, entry, {"TP1_hit":False,"TP2_hit":False,"TP3_hit":False,"SL_hit":False})
            else:
                signal, entry, hits = active_trades[pair]
                new_hits = check_trade(pair, signal, entry)
                if new_hits is None:
                    continue
                hits.update(new_hits)
                log_trade(pair, signal, entry, hits)
                if hits["TP3_hit"] or hits["SL_hit"]:
                    df = fetch_data(pair)
                    last_price = df['Close'].iloc[-1].item() if df is not None else entry
                    trade_pips = calculate_pips(signal, entry, last_price, pair)
                    closed_pips[pair] += trade_pips
                    active_trades.pop(pair)
                    closed_stats["total"] +=1
                    if hits["TP3_hit"]:
                        closed_stats["wins"] +=1
                    if hits["SL_hit"]:
                        closed_stats["losses"] +=1
        dashboard(active_trades, closed_stats, closed_pips)
        time.sleep(SLEEP)

if __name__ == "__main__":
    print(f"[INFO] Precision Bot (full integrated) starting. Pairs: {PAIRS}")
    if config.get("UPDATE_PROTECT", True):
        print("[INFO] Auto-update blocked by protection (will still run).")
    run_bot()
