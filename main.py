import yfinance as yf
import pandas as pd
import numpy as np

# --------------- Indicators ---------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd, macd_signal, macd - macd_signal

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def last_valid_row(df: pd.DataFrame, required_cols: list[str]) -> pd.Series | None:
    mask = df[required_cols].notna().all(axis=1)
    if not mask.any():
        return None
    return df.loc[mask].iloc[-1]

# --------------- Data fetch ---------------

def fetch_ohlc(pair: str, interval="1h"):
    periods_to_try = ["1d", "5d", "1mo", "3mo"]
    for period in periods_to_try:
        df = yf.download(pair, period=period, interval=interval, auto_adjust=True, progress=False)
        if df is not None and not df.empty and {"Open","High","Low","Close"}.issubset(df.columns):
            if len(df) >= 50:
                return df, period
    return None, None

# --------------- Precision Signal Generation ---------------

def generate_signals(pair: str) -> str:
    print(f"\nFetching data for {pair}...")
    df, used = fetch_ohlc(pair)
    if df is None:
        return "No sufficient data available"

    # Indicators
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["SMA_200"] = df["Close"].rolling(200).mean()
    df["RSI_14"] = compute_rsi(df["Close"])
    macd, macd_sig, macd_hist = compute_macd(df["Close"])
    df["MACD_HIST"] = macd_hist
    df["ATR_14"] = compute_atr(df)

    latest = last_valid_row(df, ["SMA_50","SMA_200","RSI_14","MACD_HIST","ATR_14","Close"])
    if latest is None:
        return "Indicators not ready"

    # Trend & momentum
    trend_up = latest["SMA_50"] > latest["SMA_200"]
    trend_down = latest["SMA_50"] < latest["SMA_200"]
    rsi = latest["RSI_14"]
    rsi_ok_long = 45 <= rsi <= 65
    rsi_ok_short = 35 <= rsi <= 55

    macd_prev = df["MACD_HIST"].iloc[-2] if len(df) > 1 else np.nan
    macd_now = latest["MACD_HIST"]
    macd_cross_up = macd_prev < 0 and macd_now > 0
    macd_cross_down = macd_prev > 0 and macd_now < 0

    # --- Precision-focused logic ---
    prob_threshold = 0.7
    gray_zone_low, gray_zone_high = 0.4, 0.6
    prob = 0.65  # Placeholder (future ML integration)
    pred = 1 if prob >= 0.5 else 0

    action = "HOLD"
    reasons = []

    if gray_zone_low < prob < gray_zone_high:
        reasons.append(f"Prob={prob:.2f} in gray zone ({gray_zone_low}-{gray_zone_high})")
    else:
        if pred == 1 and prob >= prob_threshold and trend_up and macd_cross_up and rsi_ok_long:
            action = "BUY"
            reasons.append(f"Strong Long: prob={prob:.2f}, trend_up, MACD_up, RSI_ok")
        elif pred == 0 and prob <= (1 - prob_threshold) and trend_down and macd_cross_down and rsi_ok_short:
            action = "SELL"
            reasons.append(f"Strong Short: prob={prob:.2f}, trend_down, MACD_down, RSI_ok")
        else:
            reasons.append("No high-confidence confluence")

    price = latest["Close"]
    atr = latest["ATR_14"]

    if action == "HOLD":
        return f"HOLD @ {price:.5f}\nReason: {', '.join(reasons)}\nData period: {used}"

    # ATR-based TP/SL
    r = atr if pd.notna(atr) and atr > 0 else price * 0.002
    if action == "BUY":
        tp1 = round(price + 1.0 * r, 5)
        tp2 = round(price + 1.5 * r, 5)
        tp3 = round(price + 2.0 * r, 5)
        sl = round(price - 0.67 * r, 5)
    else:  # SELL
        tp1 = round(price - 1.0 * r, 5)
        tp2 = round(price - 1.5 * r, 5)
        tp3 = round(price - 2.0 * r, 5)
        sl = round(price + 0.67 * r, 5)

    return (
        f"{action} @ {price:.5f}\n"
        f"TP1: {tp1}, TP2: {tp2}, TP3: {tp3}, SL: {sl}\n"
        f"Data period: {used}\n"
        f"Reason: {', '.join(reasons)}"
    )

# --------------- Main ---------------

def main():
    print("Signal Bot XL initialized — Precision Mode")
    pairs = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]

    for pair in pairs:
        print(f"\n{pair} Signals:\n{generate_signals(pair)}")

    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
