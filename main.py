# main.py
# Precision-focused signal bot with local auto-tuning (no GitHub).
# Requires: pip install yfinance pandas numpy

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import time
from datetime import timedelta

# ---------- Config / params persistence ----------
PARAMS_FILE = "params.json"
LOG_FILE = "performance_log.csv"
ACCURACY_WINDOW = 50          # evaluate last 50 resolved trades
ACCURACY_THRESHOLD = 0.75     # 75% required
HORIZON_BARS = 3              # how many bars ahead to evaluate outcome
INTERVAL = "1h"

DEFAULT_PARAMS = {
    "periods_to_try": ["1mo", "3mo"],
    "sma_fast": 10,
    "sma_slow": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "rsi_period": 14,
    "rsi_ok_long_min": 45,
    "rsi_ok_long_max": 65,
    "rsi_ok_short_min": 35,
    "rsi_ok_short_max": 55,
    "tp_atr_mults": [1.0, 1.5, 2.0],
    "sl_atr_mult": 0.67,
    "min_bars_required": 50
}

def load_params():
    if os.path.exists(PARAMS_FILE):
        try:
            with open(PARAMS_FILE, "r") as f:
                params = json.load(f)
            # ensure any missing defaults are filled
            for k, v in DEFAULT_PARAMS.items():
                if k not in params:
                    params[k] = v
            return params
        except Exception:
            pass
    # write defaults
    with open(PARAMS_FILE, "w") as f:
        json.dump(DEFAULT_PARAMS, f, indent=2)
    return DEFAULT_PARAMS.copy()

def save_params(params):
    with open(PARAMS_FILE, "w") as f:
        json.dump(params, f, indent=2)

# ---------- Utilities / indicators ----------
def safe_fetch(pair, periods, interval=INTERVAL):
    last_err = None
    for p in periods:
        try:
            df = yf.download(pair, period=p, interval=interval, auto_adjust=True, progress=False)
        except Exception as e:
            last_err = e
            df = None
        if df is not None and not df.empty and {"Open","High","Low","Close"}.issubset(df.columns):
            return df, p
    return None, None if last_err is None else (None, str(last_err))

def compute_indicators(df, params):
    df = df.copy()
    df["SMA_fast"] = df["Close"].rolling(params["sma_fast"]).mean()
    df["SMA_slow"] = df["Close"].rolling(params["sma_slow"]).mean()
    ema_fast = df["Close"].ewm(span=params["macd_fast"], adjust=False).mean()
    ema_slow = df["Close"].ewm(span=params["macd_slow"], adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=params["macd_signal"], adjust=False).mean()
    # RSI (standard)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/params["rsi_period"], adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/params["rsi_period"], adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    # ATR
    prev_close = df["Close"].shift(1)
    tr = pd.concat([(df["High"] - df["Low"]),
                    (df["High"] - prev_close).abs(),
                    (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()
    return df

def last_valid_row(df, cols):
    mask = df[cols].notna().all(axis=1)
    if not mask.any():
        return None
    return df.loc[mask].iloc[-1]

# ---------- Logging / evaluation ----------
def init_log():
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(columns=[
            "timestamp", "pair", "signal", "price", "tp1", "tp2", "tp3", "sl",
            "reason", "data_period", "resolved", "result", "evaluated_at"
        ])
        df.to_csv(LOG_FILE, index=False)

def append_log(entry: dict):
    df = pd.DataFrame([entry])
    df.to_csv(LOG_FILE, mode="a", header=not os.path.exists(LOG_FILE), index=False)

def load_log():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=[
            "timestamp", "pair", "signal", "price", "tp1", "tp2", "tp3", "sl",
            "reason", "data_period", "resolved", "result", "evaluated_at"
        ])
    return pd.read_csv(LOG_FILE, parse_dates=["timestamp", "evaluated_at"])

def evaluate_pending_entries(params):
    """
    For each unresolved log entry, attempt to fetch price bars from the entry time
    for HORIZON_BARS ahead and determine whether TP or SL was hit first.
    """
    log = load_log()
    pending = log[log["resolved"] != True]
    if pending.empty:
        return
    for _, row in pending.iterrows():
        pair = row["pair"]
        entry_time = pd.to_datetime(row["timestamp"])
        # fetch data from entry_time to entry_time + horizon bars
        end_time = entry_time + pd.Timedelta(hours=HORIZON_BARS + 1)
        try:
            # period param doesn't accept custom ranges easily; fetch larger window and slice
            df, used = safe_fetch(pair, params["periods_to_try"])
            if df is None:
                continue
            # ensure the timeframe covers entry_time -> end_time
            # yfinance index is tz-aware; convert to UTC naive for comparison carefulness
            df_idx = df.index.tz_convert(None) if hasattr(df.index, "tz") else df.index
            # find rows after entry_time
            future = df[df_idx > entry_time]
            future = future.head(HORIZON_BARS)
            if future.empty:
                continue
            # evaluate hits
            tp1 = float(row["tp1"])
            sl = float(row["sl"])
            hit_tp = (future["High"] >= tp1).any()
            hit_sl = (future["Low"] <= sl).any()
            result = None
            if hit_tp and not hit_sl:
                result = "win"
            elif hit_sl and not hit_tp:
                result = "loss"
            elif hit_tp and hit_sl:
                # whichever hit first by bar order
                highs = future["High"] >= tp1
                lows = future["Low"] <= sl
                first_tp_idx = highs.idxmax() if highs.any() else None
                first_sl_idx = lows.idxmax() if lows.any() else None
                if first_tp_idx is not None and first_sl_idx is not None:
                    result = "win" if future.index.get_loc(first_tp_idx) < future.index.get_loc(first_sl_idx) else "loss"
                elif first_tp_idx is not None:
                    result = "win"
                elif first_sl_idx is not None:
                    result = "loss"
            else:
                result = "no_hit"
            # update log
            log.loc[log["timestamp"] == row["timestamp"], ["resolved","result","evaluated_at"]] = [True, result, pd.Timestamp.utcnow()]
            log.to_csv(LOG_FILE, index=False)
        except Exception:
            continue

def compute_recent_accuracy(n=ACCURACY_WINDOW):
    log = load_log()
    resolved = log[log["resolved"] == True].tail(n)
    if resolved.empty:
        return None, 0, 0
    wins = (resolved["result"] == "win").sum()
    losses = (resolved["result"] == "loss").sum()
    total = wins + losses
    acc = (wins / total) if total > 0 else None
    return acc, int(wins), int(losses)

# ---------- Auto-tune ----------
def autotune_if_needed(params):
    acc, wins, losses = compute_recent_accuracy(ACCURACY_WINDOW)
    if acc is None:
        return params, False
    if acc < ACCURACY_THRESHOLD:
        # Simple auto-tune heuristic: small random tweak to sma and macd
        old = params.copy()
        # tighten SMA lengths slightly (try both directions)
        import random
        delta = random.choice([-2, -1, 1, 2])
        params["sma_fast"] = max(3, params["sma_fast"] + delta)
        params["sma_slow"] = max(params["sma_fast"]+1, params["sma_slow"] + delta)
        # nudge macd params a bit
        params["macd_fast"] = max(5, params["macd_fast"] + random.choice([-1, 1]))
        params["macd_slow"] = max(params["macd_fast"]+1, params["macd_slow"] + random.choice([-1, 1]))
        # tighten RSI bands if too many false positives (narrow range)
        params["rsi_ok_long_min"] = min(55, params["rsi_ok_long_min"] + 1)
        params["rsi_ok_long_max"] = max(50, params["rsi_ok_long_max"] - 1)
        # update saved params
        save_params(params)
        # write a backup copy of main.py (snapshot) for traceability
        try:
            with open("main.py", "r", encoding="utf-8") as f:
                code = f.read()
            ts = int(time.time())
            with open(f"main_backup_{ts}.py", "w", encoding="utf-8") as f:
                f.write(code)
        except Exception:
            pass
        return params, True
    return params, False

# ---------- Signal generation (precision confluence) ----------
def generate_signal_for_pair(pair, params):
    df, used_period = safe_fetch(pair, params["periods_to_try"])
    if df is None or df.empty:
        return {"pair": pair, "status": "no_data"}

    if len(df) < params["min_bars_required"]:
        return {"pair": pair, "status": "insufficient_bars", "data_period": used_period}

    df = compute_indicators(df, params)
    cols_needed = ["SMA_fast", "SMA_slow", "MACD", "MACD_SIGNAL", "RSI", "ATR", "Close", "High", "Low"]
    latest = last_valid_row(df, cols_needed)
    if latest is None:
        return {"pair": pair, "status": "indicators_not_ready"}

    # convert scalars
    try:
        sma_fast = float(latest["SMA_fast"])
        sma_slow = float(latest["SMA_slow"])
        macd = float(latest["MACD"])
        macd_signal = float(latest["MACD_SIGNAL"])
        rsi = float(latest["RSI"])
        atr = float(latest["ATR"]) if not pd.isna(latest["ATR"]) else None
        price = float(latest["Close"])
    except Exception:
        return {"pair": pair, "status": "bad_latest_row"}

    trend_up = sma_fast > sma_slow
    trend_down = sma_fast < sma_slow
    macd_cross_up = macd > macd_signal
    macd_cross_down = macd < macd_signal
    rsi_ok_long = params["rsi_ok_long_min"] <= rsi <= params["rsi_ok_long_max"]
    rsi_ok_short = params["rsi_ok_short_min"] <= rsi <= params["rsi_ok_short_max"]

    action = "HOLD"
    reasons = []

    if trend_up and macd_cross_up and rsi_ok_long:
        action = "BUY"
        reasons.append("Strong Long: trend_up+MACD_up+RSI_ok")
    elif trend_down and macd_cross_down and rsi_ok_short:
        action = "SELL"
        reasons.append("Strong Short: trend_down+MACD_down+RSI_ok")
    else:
        reasons.append("No high-confidence confluence")

    # compute TP/SL using ATR if available, else percent fallback
    if atr is not None and atr > 0:
        tp1 = price + params["tp_atr_mults"][0] * atr if action == "BUY" else price - params["tp_atr_mults"][0] * atr
        tp2 = price + params["tp_atr_mults"][1] * atr if action == "BUY" else price - params["tp_atr_mults"][1] * atr
        tp3 = price + params["tp_atr_mults"][2] * atr if action == "BUY" else price - params["tp_atr_mults"][2] * atr
        sl = price - params["sl_atr_mult"] * atr if action == "BUY" else price + params["sl_atr_mult"] * atr
    else:
        # fallback percentages (tight)
        pct_tp = 0.002
        pct_sl = 0.0013
        tp1 = price * (1 + pct_tp) if action == "BUY" else price * (1 - pct_tp)
        tp2 = price * (1 + pct_tp*1.5) if action == "BUY" else price * (1 - pct_tp*1.5)
        tp3 = price * (1 + pct_tp*2.0) if action == "BUY" else price * (1 - pct_tp*2.0)
        sl = price * (1 - pct_sl) if action == "BUY" else price * (1 + pct_sl)

    # formatting clean numeric outputs (rounded appropriately)
    def fmt(x):
        # choose decimals based on magnitude
        if x >= 1000:
            return f"{x:.3f}"
        elif x >= 1:
            return f"{x:.5f}"
        else:
            return f"{x:.6f}"

    out = {
        "pair": pair,
        "action": action,
        "price": fmt(price),
        "tp1": fmt(tp1),
        "tp2": fmt(tp2),
        "tp3": fmt(tp3),
        "sl": fmt(sl),
        "reason": "; ".join(reasons),
        "data_period": used_period,
        "raw_price": price,
        "raw_tp1": tp1,
        "raw_sl": sl,
        "timestamp": pd.Timestamp.utcnow()
    }
    return out

# ---------- Main run loop ----------
def main():
    params = load_params()
    init_log()
    # evaluate unresolved entries first (if any)
    try:
        evaluate_pending_entries(params)
    except Exception:
        pass

    pairs = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]
    results = []
    for pair in pairs:
        try:
            r = generate_signal_for_pair(pair, params)
        except Exception as e:
            r = {"pair": pair, "status": "error", "error": str(e)}
        # show clean output depending on result
        if r.get("status") == "no_data":
            print(f"\n{pair} Signals:\nNo sufficient data available")
            continue
        if r.get("status") == "insufficient_bars":
            print(f"\n{pair} Signals:\nNo sufficient data available (period used: {r.get('data_period')})")
            continue
        if r.get("status") == "indicators_not_ready":
            print(f"\n{pair} Signals:\nIndicators not ready")
            continue
        if r.get("status") == "bad_latest_row":
            print(f"\n{pair} Signals:\nFailed to parse latest indicators")
            continue
        if r.get("status") == "error":
            print(f"\n{pair} Signals:\nError: {r.get('error')}")
            continue

        action = r["action"]
        # Print clean numeric output
        if action == "HOLD":
            print(f"\n{pair} Signals:\nHOLD @ {r['price']}\nReason: {r['reason']}\nData period: {r['data_period']}")
        else:
            print(f"\n{pair} Signals:\n{action} @ {r['price']}")
            print(f"TP1: {r['tp1']}, TP2: {r['tp2']}, TP3: {r['tp3']}")
            print(f"SL: {r['sl']}")
            print(f"Reason: {r['reason']}")
            print(f"Data period: {r['data_period']}")

        # log signals (only BUY/SELL)
        entry = {
            "timestamp": r["timestamp"],
            "pair": pair,
            "signal": action,
            "price": r["price"],
            "tp1": r["tp1"],
            "tp2": r["tp2"],
            "tp3": r["tp3"],
            "sl": r["sl"],
            "reason": r["reason"],
            "data_period": r["data_period"],
            "resolved": False,
            "result": "",
            "evaluated_at": ""
        }
        if action in ("BUY", "SELL"):
            append_log(entry)

    # after running through pairs, evaluate pending again
    try:
        evaluate_pending_entries(params)
    except Exception:
        pass

    # check accuracy and autotune if needed
    try:
        params, tuned = autotune_if_needed(params)
        if tuned:
            # inform user (console message only)
            print("\nAuto-tune: Parameters adjusted due to low recent accuracy. New parameters saved to params.json")
    except Exception:
        pass

    print("\nRun complete. Signals logged to", LOG_FILE)
    # pause before exit so you can see output when run from double-click
    try:
        input("\nPress Enter to close the program...")
    except Exception:
        pass

if __name__ == "__main__":
    main()
