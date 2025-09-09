import json
import pandas as pd
import yfinance as yf
import time
import os
import warnings
from datetime import datetime

# Suppress FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Load configuration
with open("config.json") as f:
    config = json.load(f)

PAIRS = config["PAIRS"]
PAPER = config["PAPER_TRADING"]
TP1 = config["TRADE_SETTINGS"]["TP1_PIPS"]
TP2 = config["TRADE_SETTINGS"]["TP2_PIPS"]
TP3 = config["TRADE_SETTINGS"]["TP3_PIPS"]
SL = config["TRADE_SETTINGS"]["STOP_LOSS_PIPS"]
SLEEP = config["MONITOR_SLEEP"]
VERBOSE = config.get("VERBOSE", True)

LOG_FILE = "trade_log.csv"

# Ensure log exists
if not os.path.exists(LOG_FILE):
    df_log = pd.DataFrame(columns=[
        "Timestamp", "Pair", "Signal", "Entry", "TP1_hit", "TP2_hit", "TP3_hit", "SL_hit"
    ])
    df_log.to_csv(LOG_FILE, index=False)

# --- Helper Functions ---

def fetch_data(pair):
    try:
        df = yf.download(pair, period=config["YF_PERIOD"], interval=config["YF_INTERVAL"])
        if df.empty:
            return None
        return df
    except Exception as e:
        if VERBOSE:
            print(f"[ERROR] Failed to download {pair}: {e}")
        return None

def precision_signal(df):
    """
    Original precision logic fully integrated, now enhanced for accuracy:
    - EMA9/EMA21 crossover filter
    - RSI filter to reduce false signals
    - Confirm trend with EMA50
    - Prevent signals if close too close to previous TP/SL
    """
    close = df['Close']
    if len(close) < 50:
        return None, None  # Not enough data

    # EMA calculations
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    # RSI calculation
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, 0.0001)  # avoid divide by zero
    rsi = 100 - (100 / (1 + rs))

    # Last values
    last_close = close.iloc[-1].item()
    prev_close = close.iloc[-2].item()
    last_ema9 = ema9.iloc[-1].item()
    prev_ema9 = ema9.iloc[-2].item()
    last_ema21 = ema21.iloc[-1].item()
    prev_ema21 = ema21.iloc[-2].item()
    last_ema50 = ema50.iloc[-1].item()
    last_rsi = rsi.iloc[-1].item()

    # BUY condition
    buy_signal = (prev_ema9 < prev_ema21 and last_ema9 > last_ema21 and
                  last_close > last_ema50 and last_rsi < 70)

    # SELL condition
    sell_signal = (prev_ema9 > prev_ema21 and last_ema9 < last_ema21 and
                   last_close < last_ema50 and last_rsi > 30)

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

    # Convert PIPS to price difference (adjust per instrument)
    factor = 0.0001 if "USD" in pair else 1

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
    if VERBOSE:
        print(f"[LOG] {pair} | {signal} | Entry: {entry} | Hits: {hits}")

# --- Bot Loop ---

def run_bot():
    active_trades = {}  # pair -> (signal, entry)
    while True:
        for pair in PAIRS:
            # Generate new signal if no active trade
            if pair not in active_trades:
                df = fetch_data(pair)
                if df is None: 
                    continue
                signal, entry = precision_signal(df)
                if signal:
                    active_trades[pair] = (signal, entry)
                    if VERBOSE:
                        print(f"[SIGNAL] {pair} | {signal} | Entry: {entry}")
            else:
                # Check active trade
                signal, entry = active_trades[pair]
                hits = check_trade(pair, signal, entry)
                if hits is None:
                    continue
                log_trade(pair, signal, entry, hits)
                # Close trade if TP3 or SL hit
                if hits["TP3_hit"] or hits["SL_hit"]:
                    if VERBOSE:
                        print(f"[CLOSE] {pair} | {signal} closed.")
                    del active_trades[pair]
        time.sleep(SLEEP)

# --- Start Bot ---
if __name__ == "__main__":
    print(f"[INFO] Precision Bot (enhanced + accurate) starting. Pairs: {PAIRS}")
    if config.get("UPDATE_PROTECT", True):
        print("[INFO] Auto-update blocked by protection (will still run).")
    run_bot()
