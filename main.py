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
    "PAIRS": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCAD=X", "GC=F"],
    "PAIR_NAMES": {
        "EURUSD=X": "EUR/USD",
        "GBPUSD=X": "GBP/USD",
        "USDJPY=X": "USD/JPY",
        "USDCAD=X": "USD/CAD",
        "GC=F": "Gold/USD"
    },
    "YF_PERIODS": {
        "EURUSD=X": "7d",
        "GBPUSD=X": "7d",
        "USDJPY=X": "7d",
        "USDCAD=X": "7d",
        "GC=F": "30d"
    },
    "YF_INTERVALS": {
        "EURUSD=X": "1m",
        "GBPUSD=X": "1m",
        "USDJPY=X": "1m",
        "USDCAD=X": "1m",
        "GC=F": "1m"
    },
    "HIGHER_INTERVALS": {
        "EURUSD=X": "5m",
        "GBPUSD=X": "5m",
        "USDJPY=X": "5m",
        "USDCAD=X": "5m",
        "GC=F": "5m"
    },
    "TRADE_SETTINGS": {
        "TP_MULT": [1.0, 2.0, 3.0],  # ATR multiples for TP1/2/3
        "SL_MULT": 1.0               # ATR multiple for SL
    },
    "PAPER_TRADING": True,
    "VERBOSE": True,
    "MONITOR_SLEEP": 10
}

PAIRS = config["PAIRS"]
PAIR_NAMES = config["PAIR_NAMES"]

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
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

# --- State ---
closed_pips = {pair:0 for pair in PAIRS}

# --- Bot Functions ---
def fetch_data(pair, interval=None):
    period = config["YF_PERIODS"].get(pair, "7d")
    interval = interval or config["YF_INTERVALS"].get(pair, "1m")
    try:
        df = yf.download(pair, period=period, interval=interval)
        if df.empty:
            if config["VERBOSE"]:
                print(f"[WARN] {pair} returned empty DataFrame")
            return None
        if config["VERBOSE"]:
            print(f"[DEBUG] {pair} ({PAIR_NAMES.get(pair,pair)}): {len(df)} rows fetched at {interval}")
        return df
    except Exception as e:
        print(f"[ERROR] Failed to download {pair}: {e}")
        return None

def compute_ATR(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr.iloc[-1]

def precision_signal(df, df_higher=None):
    close = df['Close']
    if len(close) < 26:
        return None, None
    ema5 = close.ewm(span=5, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    delta = close.diff().dropna()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))

    last_close = close.iloc[-1].item()
    prev_ema5 = ema5.iloc[-2].item()
    last_ema5 = ema5.iloc[-1].item()
    prev_ema12 = ema12.iloc[-2].item()
    last_ema12 = ema12.iloc[-1].item()
    last_ema26 = ema26.iloc[-1].item()
    last_rsi = rsi.iloc[-1].item()

    # higher timeframe EMA trend
    trend_ok = True
    if df_higher is not None and len(df_higher['Close'])>=26:
        h_close = df_higher['Close']
        h_ema26 = h_close.ewm(span=26, adjust=False).mean().iloc[-1]
        trend_ok = last_close > h_ema26 if last_ema5 > last_ema12 else last_close < h_ema26

    buy_signal = prev_ema5 < prev_ema12 and last_ema5 > last_ema12 and last_close > last_ema26 and last_rsi < 70 and trend_ok
    sell_signal = prev_ema5 > prev_ema12 and last_ema5 < last_ema12 and last_close < last_ema26 and last_rsi > 30 and trend_ok

    if buy_signal:
        return "BUY", last_close
    elif sell_signal:
        return "SELL", last_close
    return None, None

def check_trade(pair, signal, entry, atr):
    df = fetch_data(pair)
    if df is None:
        return None
    last = df['Close'].iloc[-1].item()
    hits = {"TP1_hit": False, "TP2_hit": False, "TP3_hit": False, "SL_hit": False}

    tp_vals = [atr*mult for mult in config["TRADE_SETTINGS"]["TP_MULT"]]
    sl_val = atr * config["TRADE_SETTINGS"]["SL_MULT"]

    if signal == "BUY":
        for i, tp in enumerate(tp_vals,1):
            if last >= entry + tp: hits[f"TP{i}_hit"]=True
        if last <= entry - sl_val: hits["SL_hit"]=True
    elif signal == "SELL":
        for i, tp in enumerate(tp_vals,1):
            if last <= entry - tp: hits[f"TP{i}_hit"]=True
        if last >= entry + sl_val: hits["SL_hit"]=True

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
        tp1 = bcolors.GREEN+"TP1✔"+bcolors.RESET if hits["TP1_hit"] else "TP1…"
        tp2 = bcolors.CYAN+"TP2✔"+bcolors.RESET if hits["TP2_hit"] else "TP2…"
        tp3 = bcolors.MAGENTA+"TP3✔"+bcolors.RESET if hits["TP3_hit"] else "TP3…"
        sl  = bcolors.RED+"SL✖"+bcolors.RESET if hits["SL_hit"] else "SL…"
        df = fetch_data(pair)
        last_price = df['Close'].iloc[-1].item() if df is not None else entry
        live_pips = calculate_pips(signal, entry, last_price, pair)
        color = bcolors.GREEN if live_pips >=0 else bcolors.RED
        name = PAIR_NAMES.get(pair, pair)
        print(f"  {name}: {signal} @ {entry:.5f} | {tp1} {tp2} {tp3} {sl} | Live P/L: {color}{live_pips:.1f} pips{bcolors.RESET}")

    print("\nClosed Trades Stats:")
    total = closed_stats['total']
    wins = closed_stats['wins']
    losses = closed_stats['losses']
    win_rate = (wins / total * 100) if total>0 else 0
    print(f"  Wins: {bcolors.GREEN}{wins}{bcolors.RESET} | Losses: {bcolors.RED}{losses}{bcolors.RESET} | Total: {total} | Win Rate: {bcolors.GREEN if win_rate>=50 else bcolors.RED}{win_rate:.2f}%{bcolors.RESET}")
    
    print("\nCumulative P/L per Pair (Closed Trades):")
    for pair, pips in closed_pips.items():
        color = bcolors.GREEN if pips >=0 else bcolors.RED
        name = PAIR_NAMES.get(pair, pair)
        print(f"  {name}: {color}{pips:.1f} pips{bcolors.RESET}")
    
    print("========================================")

# --- Always-on Bot Loop ---
def run_bot():
    active_trades = {}
    closed_stats = {"wins": 0, "losses": 0, "total": 0}
    while True:
        for pair in PAIRS:
            atr = compute_ATR(fetch_data(pair)) or 50
            df_higher = fetch_data(pair, interval=config["HIGHER_INTERVALS"].get(pair))
            if pair not in active_trades:
                df = fetch_data(pair)
                if df is None or len(df) < 26:
                    continue
                signal, entry = precision_signal(df, df_higher)
                if signal:
                    active_trades[pair] = (signal, entry, {"TP1_hit":False,"TP2_hit":False,"TP3_hit":False,"SL_hit":False})
            else:
                signal, entry, hits = active_trades[pair]
                new_hits = check_trade(pair, signal, entry, atr)
                if new_hits is None:
                    continue
                hits.update(new_hits)
                log_trade(pair, signal, entry, hits)

                if hits["TP3_hit"] or hits["SL_hit"]:
                    df = fetch_data(pair)
                    last_price = df['Close'].iloc[-1].item() if df is not None else entry
                    pips = calculate_pips(signal, entry, last_price, pair)
                    closed_pips[pair] += pips
                    closed_stats["total"] += 1
                    if pips >= 0:
                        closed_stats["wins"] += 1
                    else:
                        closed_stats["losses"] += 1
                    del active_trades[pair]

                    # Generate new signal after trade closes
                    df_new = fetch_data(pair)
                    df_higher_new = fetch_data(pair, interval=config["HIGHER_INTERVALS"].get(pair))
                    if df_new is not None and len(df_new) >= 26:
                        new_signal, new_entry = precision_signal(df_new, df_higher_new)
                        if new_signal:
                            active_trades[pair] = (new_signal, new_entry, {"TP1_hit":False,"TP2_hit":False,"TP3_hit":False,"SL_hit":False})

        dashboard(active_trades, closed_stats, closed_pips)
        time.sleep(SLEEP)

if __name__=="__main__":
    if config["UPDATE_PROTECT"]:
        print("[INFO] Auto-update blocked by protection (will still run).")
    print(f"[INFO] Precision Bot (enhanced, precise + TP sequence dashboard) starting. Pairs: {PAIRS}")
    run_bot()
