# signals_ml.py
import pandas as pd
import pickle
import sys
import os

# -----------------------------
# Determine correct path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

# Paths
model_path = os.path.join(base_path, "ml_model.pkl")
log_path = os.path.join(base_path, "ml_signals_log.csv")

# -----------------------------
# Load trained ML model
# -----------------------------
try:
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    print("✅ ML model loaded successfully!")
except Exception as e:
    print(f"❌ Failed to load ML model: {e}")
    model = None

# -----------------------------
# Generate signal for a pair
# -----------------------------
def generate_signal(pair, pair_data_dict, candles_per_tf_dict):
    if model is None:
        return None
    try:
        # Example: use last candle's OHLC as features (4-feature model)
        last_data = pair_data_dict['M1'].iloc[-1]
        X = [[last_data['Open'], last_data['High'], last_data['Low'], last_data['Close']]]
        signal = model.predict(X)[0]
        return "BUY" if signal == 1 else "SELL"
    except Exception as e:
        print(f"❌ Error generating signal: {e}")
        return None

# -----------------------------
# Log signal to CSV
# -----------------------------
def log_signal(pair, signal):
    try:
        df = pd.DataFrame([[pair, signal, pd.Timestamp.now()]],
                          columns=['Pair','Signal','Timestamp'])
        if not os.path.exists(log_path):
            df.to_csv(log_path, index=False)
        else:
            df.to_csv(log_path, mode='a', header=False, index=False)
        # print(f"✅ Signals logged successfully to {log_path}")
    except Exception as e:
        print(f"❌ Error logging signal: {e}")
