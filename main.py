import warnings
warnings.filterwarnings('ignore')

import time
import math
import os
import sys
import traceback
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5
from flask import Flask, request, jsonify
import threading

# ======================= CONFIG =======================
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
TP_PIPS = 40
SL_PIPS = 50
RETRAIN_DAYS = 30
ONE_CYCLE_TEST = False

# Trade log CSV
TRADE_LOG_FILE = "trades_log.csv"

# Flask App for TradingView webhooks
app = Flask(__name__)
webhook_signals = []

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'pair' not in data or 'signal' not in data:
        return jsonify({"status": "error", "msg": "Invalid payload"}), 400
    webhook_signals.append(data)
    return jsonify({"status": "ok"}), 200

def start_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# ======================= MT5 Helpers =======================
def init_mt5():
    if not mt5.initialize():
        print("[ERROR] MT5 initialization failed")
        sys.exit(1)
    print("[INFO] MT5 initialized successfully.")

def get_mt5_price(pair):
    symbol = pair
    if not mt5.symbol_select(symbol, True):
        print(f"[ERROR] Failed to select {symbol}")
        return None
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.bid
    return None

# ======================= Precision Bot Logic =======================
def calculate_signals(pair):
    """Generates precision signals using EMA, RSI, and sustained candle logic."""
    rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, 200)
    if rates is None or len(rates) < 20:
        return None

    df = pd.DataFrame(rates)
    df['ema5'] = df['close'].ewm(span=5).mean()
    df['ema12'] = df['close'].ewm(span=12).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    if last['ema5'] > last['ema12'] and prev['ema5'] <= prev['ema12'] and last['rsi'] > 55:
        signal = 'BUY'
    elif last['ema5'] < last['ema12'] and prev['ema5'] >= prev['ema12'] and last['rsi'] < 45:
        signal = 'SELL'

    return signal

def calculate_trade_levels(pair, signal, entry):
    if "JPY" in pair:
        pip = 0.01
    elif "XAU" in pair:
        pip = 0.1
    else:
        pip = 0.0001

    if signal == "BUY":
        tp1 = entry + TP_PIPS * pip
        tp2 = entry + (TP_PIPS * 2) * pip
        tp3 = entry + (TP_PIPS * 3) * pip
        sl = entry - SL_PIPS * pip
    else:
        tp1 = entry - TP_PIPS * pip
        tp2 = entry - (TP_PIPS * 2) * pip
        tp3 = entry - (TP_PIPS * 3) * pip
        sl = entry + SL_PIPS * pip

    return tp1, tp2, tp3, sl

# ======================= Trade Logger =======================
def log_trade(pair, signal, entry, tp1, tp2, tp3, sl, result):
    exists = os.path.exists(TRADE_LOG_FILE)
    df = pd.DataFrame([{
        "time": datetime.now(),
        "pair": pair,
        "signal": signal,
        "entry": entry,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "result": result
    }])
    if exists:
        df.to_csv(TRADE_LOG_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(TRADE_LOG_FILE, index=False)

# ======================= Bot Runner =======================
def run_bot():
    init_mt5()

    while True:
        for pair in PAIRS:
            # Check TradingView webhook first
            signal = None
            if webhook_signals:
                data = webhook_signals.pop(0)
                if data['pair'] == pair:
                    signal = data['signal'].upper()

            # Otherwise generate signals internally
            if not signal:
                signal = calculate_signals(pair)

            if signal:
                entry = get_mt5_price(pair)
                if entry:
                    tp1, tp2, tp3, sl = calculate_trade_levels(pair, signal, entry)
                    print(f"{pair}: {signal} @ {entry:.5f} | TP1: {tp1:.5f} | TP2: {tp2:.5f} | TP3: {tp3:.5f} | SL: {sl:.5f}")

                    # Log trade (result placeholder for now)
                    log_trade(pair, signal, entry, tp1, tp2, tp3, sl, "OPEN")

        if ONE_CYCLE_TEST:
            break

        time.sleep(60)

# ======================= Entry Point =======================
if __name__ == '__main__':
    try:
        mode_input = ''
        while mode_input not in ('y', 'n'):
            mode_input = input("Start in test mode? (y/n): ").strip().lower()
        TEST_MODE = (mode_input == 'y')
        print(f"[INFO] Bot starting | Pairs: {PAIRS} | Test Mode: {TEST_MODE}")

        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()

        run_bot()
    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested.")
        sys.exit(0)
    except Exception as e:
        print("!!! FATAL ERROR !!!")
        traceback.print_exc()
        sys.exit(1)
