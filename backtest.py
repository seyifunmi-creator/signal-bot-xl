# backtest.py
# Backtest 1 year of hourly data using the precision confluence logic.
# Usage: python backtest.py
#
# Requires: pip install yfinance pandas numpy

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------- CONFIG ----------
PAIRS = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]
INTERVAL = "1h"
END_DATE = "2025-09-06"
START_DATE = "2024-09-06"
HORIZON_BARS = 10   # lookahead bars to check TP/SL
MIN_BARS_REQUIRED = 50

# Strategy params (match your main bot's params.json defaults)
PARAMS = {
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
    "tp_atr_mult": 1.0,
    "sl_atr_mult": 0.67
}

# ---------- INDICATORS ----------
def compute_indicators(df):
    df = df.copy()
    close = df["Close"]
    df["SMA_fast"] = close.rolling(PARAMS["sma_fast"]).mean()
    df["SMA_slow"] = close.rolling(PARAMS["sma_slow"]).mean()
    ema_fast = close.ewm(span=PARAMS["macd_fast"], adjust=False).mean()
    ema_slow = close.ewm(span=PARAMS["macd_slow"], adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=PARAMS["macd_signal"], adjust=False).mean()
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/PARAMS["rsi_period"], adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/PARAMS["rsi_period"], adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    # ATR
    prev_close = close.shift(1)
    tr = pd.concat([(df["High"] - df["Low"]),
                    (df["High"] - prev_close).abs(),
                    (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()
    return df

# ---------- SIGNAL RULE ----------
def signal_on_bar(row, prev_row):
    # row and prev_row are Series with indicators already computed
    # ensure NaNs are handled
    keys = ["SMA_fast", "SMA_slow", "MACD", "MACD_SIGNAL", "RSI", "ATR"]
    if any(pd.isna(row.get(k, np.nan)) for k in keys):
        return "HOLD"
    sma_f = float(row["SMA_fast"]); sma_s = float(row["SMA_slow"])
    macd = float(row["MACD"]); macd_signal = float(row["MACD_SIGNAL"])
    rsi = float(row["RSI"])
    trend_up = sma_f > sma_s
    trend_down = sma_f < sma_s
    macd_cross_up = macd > macd_signal
    macd_cross_down = macd < macd_signal
    rsi_ok_long = PARAMS["rsi_ok_long_min"] <= rsi <= PARAMS["rsi_ok_long_max"]
    rsi_ok_short = PARAMS["rsi_ok_short_min"] <= rsi <= PARAMS["rsi_ok_short_max"]
    if trend_up and macd_cross_up and rsi_ok_long:
        return "BUY"
    if trend_down and macd_cross_down and rsi_ok_short:
        return "SELL"
    return "HOLD"

# ---------- SIMULATE TRADES ----------
def backtest_pair(pair):
    print(f"\nBacktesting {pair} from {START_DATE} to {END_DATE} ({INTERVAL})")
    df = yf.download(pair, start=START_DATE, end=END_DATE, interval=INTERVAL, auto_adjust=True, progress=False)
    if df is None or df.empty or len(df) < MIN_BARS_REQUIRED:
        print("Insufficient historical data for", pair)
        return None
    df = compute_indicators(df)
    trades = []
    # iterate bars (we enter at next bar open)
    for i in range(1, len(df) - HORIZON_BARS):
        row = df.iloc[i]       # this bar's indicators determine signal
        prev_row = df.iloc[i-1]
        sig = signal_on_bar(row, prev_row)
        if sig == "HOLD":
            continue
        entry_idx = i + 1
        if entry_idx >= len(df):
            break
        entry_price = df["Open"].iloc[entry_idx]
        atr = row["ATR"] if not pd.isna(row["ATR"]) else None
        if atr is None or atr <= 0:
            # skip if no volatility measure
            continue
        tp = entry_price + PARAMS["tp_atr_mult"] * atr if sig == "BUY" else entry_price - PARAMS["tp_atr_mult"] * atr
        sl = entry_price - PARAMS["sl_atr_mult"] * atr if sig == "BUY" else entry_price + PARAMS["sl_atr_mult"] * atr
        result = "no_hit"
        win = 0.0
        # check next HORIZON_BARS bars for hit
        for j in range(entry_idx, min(len(df), entry_idx + HORIZON_BARS)):
            high = df["High"].iloc[j]; low = df["Low"].iloc[j]
            if sig == "BUY":
                if high >= tp and not (low <= sl and df.index.get_loc(df.index[df.index.get_loc(df.index[j])] ) < df.index.get_loc(df.index[df.index[df.index.get_loc(df.index[j])]])):  # simple
                    result = "win"; win = tp - entry_price; break
                if low <= sl:
                    result = "loss"; win = sl - entry_price; break
            else:
                if low <= tp:
                    result = "win"; win = entry_price - tp; break
                if high >= sl:
                    result = "loss"; win = entry_price - sl; break
        trades.append({
            "pair": pair,
            "entry_time": df.index[entry_idx],
            "signal_time": df.index[i],
            "signal": sig,
            "entry_price": float(entry_price),
            "tp": float(tp),
            "sl": float(sl),
            "result": result,
            "pnl": float(win) if result in ("win","loss") else 0.0,
            "return_pct": (float(win) / float(entry_price)) if result in ("win","loss") else 0.0
        })
    # compute metrics
    total = len([t for t in trades if t["result"] in ("win","loss")])
    wins = len([t for t in trades if t["result"] == "win"])
    losses = len([t for t in trades if t["result"] == "loss"])
    win_rate = (wins/total*100) if total>0 else 0.0
    gross_win = sum(t["pnl"] for t in trades if t["result"]=="win")
    gross_loss = sum(-t["pnl"] for t in trades if t["result"]=="loss")
    profit_factor = (gross_win / gross_loss) if gross_loss>0 else float("inf")
    avg_return = (sum(t["return_pct"] for t in trades if t["result"] in ("win","loss")) / total*100) if total>0 else 0.0
    print(f"Trades={total}, Wins={wins}, Losses={losses}, WinRate={win_rate:.1f}%, ProfitFactor={profit_factor:.3f}, AvgReturn%={avg_return:.4f}")
    # save detailed trades CSV
    if trades:
        outdf = pd.DataFrame(trades)
        outdf.to_csv(f"backtest_{pair.replace('=','_')}.csv", index=False)
    return {
        "pair": pair,
        "trades": total, "wins": wins, "losses": losses,
        "win_rate": win_rate, "profit_factor": profit_factor, "avg_return_pct": avg_return
    }

if _name_ == "_main_":
    results = []
    for p in PAIRS:
        res = backtest_pair(p)
        if res:
            results.append(res)
    if results:
        summary = pd.DataFrame(results)
        print("\nSUMMARY:")
        print(summary.to_string(index=False))
