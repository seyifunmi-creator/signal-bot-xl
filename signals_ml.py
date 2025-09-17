# signals_ml.py
import pandas as pd
import pickle

# -----------------------------
# Load your trained ML model
# -----------------------------
with open("ml_model.pkl", "rb") as f:
    model = pickle.load(f)

# -----------------------------
# Prepare features for ML
# -----------------------------
def prepare_features(pair_data):
    """
    Convert live MT5 price data into features for your trained model.
    - Ensure columns match what your model expects (e.g., Open, High, Low, Close, volume, indicators).
    - This example assumes your model was trained on OHLC data.
    """
    if pair_data is None or pair_data.empty:
        return pd.DataFrame()  # return empty DataFrame if no data

    # Example: create features directly from OHLC
    # Replace this section with your actual feature engineering
    features = pair_data[['Open', 'High', 'Low', 'Close']].copy()
    return features

# -----------------------------
# Generate ML signal
# -----------------------------
def generate_signal(pair, pair_data=None):
    """
    Returns 'BUY', 'SELL', or None for a trading pair based on ML prediction.
    """
    try:
        X = prepare_features(pair_data)
        if X.empty:
            return None

        # Predict the last row
        prediction = model.predict(X.tail(1))
        if prediction[0] == 1:
            return "BUY"
        elif prediction[0] == -1:
            return "SELL"
        else:
            return None

    except Exception as e:
        print(f"[ERROR] Failed to generate signal for {pair}: {e}")
        return None

# -----------------------------
# Optional: log signals (for testing)
# -----------------------------
def log_ml_signals(pairs, live_data_func):
    """
    pairs: list of trading pairs
    live_data_func: function to fetch live MT5 data per pair
    """
    print("[INFO] Fetching ML signals for all pairs...\n")
    for pair in pairs:
        pair_data = live_data_func(pair)
        signal = generate_signal(pair, pair_data)
        print(f"{pair} → Signal={signal}")
