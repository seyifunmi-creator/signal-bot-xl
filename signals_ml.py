# signals_ml.py
import os
import sys
import pickle
import pandas as pd
from datetime import datetime

# -----------------------------
# Determine base path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    # Running as PyInstaller .exe
    base_path = sys._MEIPASS
else:
    # Running as script
    base_path = os.path.dirname(__file__)

# Paths
model_path = os.path.join(base_path, "ml_model.pkl")
log_path = os.path.join(base_path, "ml_signals_log.csv")

# -----------------------------
# Load ML model safely
# -----------------------------
try:
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    print("✅ ML model loaded successfully!")
except FileNotFoundError:
    print(f"❌ ML model not found at {model_path}")
    model = None
except pickle.UnpicklingError:
    print("❌ Failed to load ML model (protocol issue).")
    model = None

# -----------------------------
# Example function: generate signal
# -----------------------------
def generate_signal(df: pd.DataFrame) -> str:
    """
    df: DataFrame with columns ['Open','High','Low','Close']
    Returns: 'BUY', 'SELL', or None
    """
    if model is None or df.empty:
        return None
    try:
        # Replace this with your real features
        features = df[['Open','High','Low','Close']].values[-1].reshape(1, -1)
        pred = model.predict(features)[0]
        return "BUY" if pred == 1 else "SELL"
    except Exception as e:
        print(f"❌ Error generating signal: {e}")
        return None

# -----------------------------
# Log ML signals
# -----------------------------
def log_ml_signals(pairs: list):
    """
    pairs: list of string symbols, e.g. ['EURUSD','GBPUSD']
    Logs signals to ml_signals_log.csv
    """
    if model is None:
        print("❌ Cannot log signals: ML model not loaded")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs = []

    for pair in pairs:
        # Example: generate signal using dummy price data
        df = pd.DataFrame([[1,1,0,0]], columns=['Open','High','Low','Close'])  # Replace with real data fetch
        signal = generate_signal(df)
        logs.append({'Datetime': now, 'Pair': pair, 'Signal': signal})

        print(f"{pair} → Signal={signal}")

    df_log = pd.DataFrame(logs)
    if not os.path.exists(log_path):
        df_log.to_csv(log_path, index=False)
    else:
        df_log.to_csv(log_path, mode='a', header=False, index=False)
