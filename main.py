# main.py
# Precision Bot V3 - Hybrid (MT5 + internal signal generation + optional TradingView webhook)
# Merged from user's original code; TP/accuracy/training preserved and re-integrated.

import warnings
warnings.filterwarnings('ignore')

import time
import math
import os
import sys
import traceback
from datetime import datetime
import threading

import pandas as pd
import MetaTrader5 as mt5
from flask import Flask, request, jsonify

# -------------------------------
# Flask Webhook Setup (optional use)
# -------------------------------
app = Flask(__name__)
signals = []  # Store incoming external signals

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON received"}), 400
    signals.append(data)
    print(f"[WEBHOOK] New external signal received: {data}")
    # We intentionally do NOT auto-override internal signals.
    # External signals will be processed by process_external_signals() in run loop.
    return jsonify({"status": "ok"})

def start_flask():
    # Run Flask in a separate thread; disable reloader to avoid double-thread issues
    app.run(port=5000, debug=False, use_reloader=False)

# ===========================
# CONFIGURATION (kept as in your code)
# ===========================
PAIRS = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCAD=X', 'GC=F']
PAIR_NAMES = {
    'EURUSD=X': 'EUR/USD', 'GBPUSD=X': 'GBP/USD',
    'USDJPY=X': 'USD/JPY', 'USDCAD=X': 'USD/CAD',
    'GC=F': 'Gold/USD'
}

# default (overridden by startup prompt)
TEST_MODE = False
ONE_CYCLE_TEST = True

# TP/SL config (pips)
TP1 = 40
TP2 = 40
TP3 = 40
SL = 50

# runtime/config
SLEEP_INTERVAL = 60  # seconds between loop cycles
CSV_FILE = "trades_log.csv"
LOG_FILE = "precision_bot_v3.log"

# training config
TRAIN_WINDOW_DAYS = 30   # 1 month
TRAIN_INTERVAL = '5m'    # 5 minute candles
RETRAIN_DAYS = 7

# live signal tuning
MIN_RSI = 30
MAX_RSI = 70
REQUIRED_SUSTAINED_CANDLES = 2

# ===========================
# STATE
# ===========================
active_trades = {}
closed_trades = []
initial_test_opened = set()
trained_stats = {}
last_trained = None

# ===========================
# UTILITIES / LOGGING
# ===========================
def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        try:
            print("LOG WRITE FAILED:", line)
        except:
            pass

def startup_banner():
    print(">>> Precision Bot V3 — Startup Initiated <<<")
    print(f"Pairs: {PAIRS}")
    print(f"Log file: {LOG_FILE}")
    print("Waiting for startup selection...")

# ===========================
# MARKET HELPERS
# ===========================
def detect_pip_unit(pair):
    """Return (pip_unit, pip_factor) for calculations (keeps previous behavior)."""
    pair = pair.upper()
    if pair.endswith('JPY'):
        return 0.01, 100
    if pair == 'GC=F' or 'XAU' in pair or 'GOLD' in pair:
        return 0.1, 10
    return 0.0001, 10000

def get_live_price(pair):
    """
    Try MT5 first (exact broker price). If unavailable, fall back to latest close from yfinance.
    Input pair should be in format like 'EURUSD=X' or 'GC=F' (like your PAIRS).
    """
    symbol_map = {
        'EURUSD=X': 'EURUSD',
        'GBPUSD=X': 'GBPUSD',
        'USDJPY=X': 'USDJPY',
        'USDCAD=X': 'USDCAD',
        'GC=F': 'XAUUSD'
    }
    mt5_symbol = symbol_map.get(pair, pair)
    # Try MT5 tick
    try:
        tick = mt5.symbol_info_tick(mt5_symbol)
        if tick and (tick.bid is not None):
            # Use mid price to be consistent with entry handling when both bid/ask available
            if tick.ask is not None:
                return float((tick.bid + tick.ask) / 2)
            return float(tick.bid)
    except Exception:
        # ignore and fallback
        pass

    # Fallback to yfinance last close
    try:
        df = yf.download(pair, period="1d", interval="1m", progress=False, auto_adjust=True)
        if df is not None and not df.empty:
            return float(df['Close'].iloc[-1])
    except Exception as e:
        log(f"get_live_price fallback failed for {pair}: {e}")
    return None

# ===========================
# HISTORICAL DATA & INDICATORS
# ===========================
def fetch_data(pair, interval='5m', period_days=30):
    """Fetch historical data and compute EMA/RSI (preserves your implementation)."""
    try:
        period_str = f"{period_days}d"
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, 500)  # example: 500 candles, 5m timeframe
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        if df is None or df.empty:
            return None
        if len(df) >= 5:
            df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
            df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1*delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + roll_up / (roll_down + 1e-8)))
        return df
    except Exception as e:
        log(f"fetch_data failed for {pair}: {e}")
        return None

def calculate_atr(df, period=14):
    try:
        dd = df.copy()
        dd['H-L'] = dd['High'] - dd['Low']
        dd['H-PC'] = abs(dd['High'] - dd['Close'].shift(1))
        dd['L-PC'] = abs(dd['Low'] - dd['Close'].shift(1))
        dd['TR'] = dd[['H-L','H-PC','L-PC']].max(axis=1)
        atr = dd['TR'].rolling(period).mean()
        return atr.iloc[-1] if not atr.empty else None
    except Exception as e:
        log(f"ATR calc failed: {e}")
        return None

# ===========================
# SIGNAL GENERATION
# ===========================
def generate_signal(df):
    """Sustained EMA crossover + RSI filter for higher confidence signals (as original)."""
    try:
        if df is None or len(df) < (REQUIRED_SUSTAINED_CANDLES + 5):
            return None
        sustained_buy = all(df['EMA5'].iloc[-(i+1)] > df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
        sustained_sell = all(df['EMA5'].iloc[-(i+1)] < df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
        rsi_last = df['RSI'].iloc[-1]
        if sustained_buy and rsi_last < MAX_RSI:
            return 'BUY'
        if sustained_sell and rsi_last > MIN_RSI:
            return 'SELL'
        return None
    except Exception as e:
        log(f"generate_signal error: {e}")
        return None

# ===========================
# BACKTEST / TRAINING (RECONSTRUCTED FROM USER CODE)
# ===========================
def backtest_pair(pair, df):
    """Simulate historical signals and record TP1/TP2/TP3 reached (reconstructed)."""
    try:
        pip_unit, pip_factor = detect_pip_unit(pair)
        results = {
            'trades': 0,
            'tp1_reached': 0,
            'tp2_reached': 0,
            'tp3_reached': 0,
            'tp3_given_tp1': 0,
            'tp3_given_tp2': 0
        }
        for idx in range(REQUIRED_SUSTAINED_CANDLES, len(df)-1):
            window = df.iloc[:idx+1]
            signal = generate_signal(window)
            if signal is None:
                continue
            entry_price = df['Close'].iloc[idx]
            atr = calculate_atr(window)
            if atr is not None and atr > 0:
                tp1_val = max(atr, TP1 * pip_unit)
                tp2_val = max(atr*2, (TP1+TP2) * pip_unit)
                tp3_val = max(atr*3, (TP1+TP2+TP3) * pip_unit)
                sl_val = max(atr*1.25, SL * pip_unit)
            else:
                tp1_val = TP1 * pip_unit
                tp2_val = (TP1+TP2) * pip_unit
                tp3_val = (TP1+TP2+TP3) * pip_unit
                sl_val = SL * pip_unit
            tp1_price = entry_price + tp1_val if signal == 'BUY' else entry_price - tp1_val
            tp2_price = entry_price + tp2_val if signal == 'BUY' else entry_price - tp2_val
            tp3_price = entry_price + tp3_val if signal == 'BUY' else entry_price - tp3_val
            sl_price = entry_price - sl_val if signal == 'BUY' else entry_price + sl_val

            reached_tp1 = reached_tp2 = reached_tp3 = False
            for j in range(idx+1, min(idx+1+500, len(df))):
                high = df['High'].iloc[j]
                low = df['Low'].iloc[j]
                if signal == 'BUY':
                    if high >= tp1_price and not reached_tp1:
                        reached_tp1 = True
                    if high >= tp2_price and not reached_tp2:
                        reached_tp2 = True
                    if high >= tp3_price and not reached_tp3:
                        reached_tp3 = True
                    if low <= sl_price:
                        break
                else:
                    if low <= tp1_price and not reached_tp1:
                        reached_tp1 = True
                    if low <= tp2_price and not reached_tp2:
                        reached_tp2 = True
                    if low <= tp3_price and not reached_tp3:
                        reached_tp3 = True
                    if high >= sl_price:
                        break
                if reached_tp3:
                    break

            results['trades'] += 1
            if reached_tp1: results['tp1_reached'] += 1
            if reached_tp2: results['tp2_reached'] += 1
            if reached_tp3: results['tp3_reached'] += 1
            if reached_tp1 and reached_tp3: results['tp3_given_tp1'] += 1
            if reached_tp2 and reached_tp3: results['tp3_given_tp2'] += 1

        trades = max(1, results['trades'])
        stats = {
            'trades': results['trades'],
            'p_tp1': results['tp1_reached'] / trades,
            'p_tp2': results['tp2_reached'] / trades,
            'p_tp3': results['tp3_reached'] / trades,
            'p_tp3_given_tp1': (results['tp3_given_tp1'] / results['tp1_reached']) if results['tp1_reached']>0 else 0.0,
            'p_tp3_given_tp2': (results['tp3_given_tp2'] / results['tp2_reached']) if results['tp2_reached']>0 else 0.0
        }
        return stats
    except Exception as e:
        log(f"backtest_pair error for {pair}: {e}")
        return None

def train_heuristic():
    """Train heuristic stats for each pair using recent historical data (preserve behavior)."""
    global trained_stats, last_trained
    try:
        log("Starting heuristic training...")
        trained_stats = {}
        for pair in PAIRS:
            df = fetch_data(pair, interval=TRAIN_INTERVAL, period_days=TRAIN_WINDOW_DAYS)
            if df is None:
                log(f"No historical data for {pair} (skipping training).")
                continue
            stats = backtest_pair(pair, df)
            if stats:
                trained_stats[pair] = stats
                log(f"Trained {pair}: trades={stats['trades']} p_tp3={stats['p_tp3']:.2f} p_tp3|tp1={stats['p_tp3_given_tp1']:.2f}")
        last_trained = datetime.now()
        log("Training complete.")
    except Exception as e:
        log(f"train_heuristic error: {e}")

# ===========================
# TRADING: open/check/log (kept intact)
# ===========================
def open_trade(pair, signal, current_price, df=None, mode='live'):
    """
    Opens a trade with properly scaled TP and SL for all pairs
    """
    try:
        # Determine pip unit based on pair
        pair_upper = pair.upper()
        if 'JPY' in pair_upper:
            pip_unit = 0.01
        elif pair == 'GC=F' or 'XAU' in pair_upper or 'GOLD' in pair_upper:
            pip_unit = 0.1
        else:
            pip_unit = 0.0001

        # ATR-based TP/SL if df is provided
        atr = calculate_atr(df) if df is not None else None
        if atr is not None:
            tp1_val = atr
            tp2_val = atr * 2
            tp3_val = atr * 3
            sl_val = atr * 1.25
        else:
            tp1_val = TP1 * pip_unit
            tp2_val = (TP1 + TP2) * pip_unit
            tp3_val = (TP1 + TP2 + TP3) * pip_unit
            sl_val = SL * pip_unit

        active_trades[pair] = {
            'Pair': pair,
            'Signal': signal,
            'Entry': current_price,
            'TP1': current_price + tp1_val if signal == 'BUY' else current_price - tp1_val,
            'TP2': current_price + tp2_val if signal == 'BUY' else current_price - tp2_val,
            'TP3': current_price + tp3_val if signal == 'BUY' else current_price - tp3_val,
            'SL': current_price - sl_val if signal == 'BUY' else current_price + sl_val,
            'TP1_hit': False,
            'TP2_hit': False,
            'TP3_hit': False,
            'SL_hit': False,
            'Entry_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mode': mode
        }

        log(f"Opened {pair} {signal} @ {current_price} mode={'TEST' if mode=='test' else 'LIVE'}")
        print(f"\033[96m[TRADE OPENED] {PAIR_NAMES.get(pair,pair)} {signal} @ {current_price}\033[0m")
    except Exception as e:
        log(f"open_trade error for {pair}: {e}")

def compute_live_pnl(trade, current_price):
    """
    Computes live P/L in pips for all pairs, including correct scaling for JPY and Gold.
    """
    pair = trade['Pair'].upper()

    # Determine pip factor for P/L calculation
    if 'JPY' in pair:
        pip_factor = 100
    elif pair == 'GC=F' or 'XAU' in pair or 'GOLD' in pair:
        pip_factor = 10  # Gold pip scaling
    else:
        pip_factor = 10000  # Standard Forex pairs

    # Compute P/L based on trade direction
    if trade['Signal'] == 'BUY':
        pnl = (current_price - trade['Entry']) * pip_factor
    else:  # SELL
        pnl = (trade['Entry'] - current_price) * pip_factor

    return round(pnl, 2)

def suggest_using_trained_stats(pair, trade, current_price):
    try:
        stats = trained_stats.get(pair)
        if not stats:
            return ("No trained data — hold.", 50)
        # choose conditional probability if TP1/TP2 hit
        base_prob = stats.get('p_tp3', 0.0)
        if trade.get('TP2_hit'):
            base_prob = stats.get('p_tp3_given_tp2', base_prob)
        elif trade.get('TP1_hit'):
            base_prob = stats.get('p_tp3_given_tp1', base_prob)
        pct = int(base_prob * 100)
        if pct >= 60:
            return (f"High chance to reach TP3 (~{pct}%). Hold for TP3.", pct)
        if pct >= 40:
            return (f"Moderate chance (~{pct}%). Consider partial lock or hold to TP2.", pct)
        return (f"Low chance (~{pct}%). Consider closing at TP1/TP2.", pct)
    except Exception as e:
        log(f"suggest_using_trained_stats error: {e}")
        return ("Error estimating — hold.", 50)

def suggest_tp(trade, historical_df, pair):
    if historical_df is None or historical_df.empty:
        return "No suggestion"
    atr = calculate_atr(historical_df)
    if atr is None:
        return "No suggestion"
    if trade['Signal'] == 'BUY':
        remaining = trade['TP3'] - trade['Entry']
    else:
        remaining = trade['Entry'] - trade['TP3']
    if remaining > 2 * atr:
        return "TP2 safer"
    elif remaining > atr:
        return "TP1 only"
    else:
        return "TP3 likely"

def log_trade_to_csv(trade):
    try:
        df = pd.DataFrame([{
            'Pair': PAIR_NAMES.get(trade['Pair'], trade['Pair']),
            'Signal': trade['Signal'],
            'Entry': trade['Entry'],
            'Close': trade.get('Close_Price', ''),
            'TP1': trade['TP1'],
            'TP2': trade['TP2'],
            'TP3': trade['TP3'],
            'SL': trade['SL'],
            'Entry_Time': trade['Entry_Time'],
            'Close_Time': trade.get('Close_Time', ''),
            'P/L': compute_live_pnl(trade, trade.get('Close_Price', trade['Entry'])),
            'Mode': trade.get('mode','live')
        }])
        if not os.path.isfile(CSV_FILE):
            df.to_csv(CSV_FILE, mode='w', header=True, index=False)
        else:
            df.to_csv(CSV_FILE, mode='a', header=False, index=False)
    except Exception as e:
        log(f"Failed to log trade to CSV: {e}")

# Checking active trades for TP/SL and suggestions (kept original behavior)
def check_trades(pair, current_price, df=None):
    if pair not in active_trades:
        return
    trade = active_trades[pair]
    try:
        if not trade['TP1_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP1']) or (trade['Signal']=='SELL' and current_price <= trade['TP1'])):
            trade['TP1_hit'] = True
            print(f"\033[93m[TP1 HIT] {PAIR_NAMES[pair]} reached TP1 @ {current_price} ✅\033[0m")
            log(f"{pair} TP1 hit @ {current_price}")
            if trade.get('mode')=='live':
                sugg, score = suggest_using_trained_stats(pair, trade, current_price)
                print(f"  Suggestion: {sugg} (Confidence {score}%)")

        if not trade['TP2_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP2']) or (trade['Signal']=='SELL' and current_price <= trade['TP2'])):
            trade['TP2_hit'] = True
            print(f"\033[93m[TP2 HIT] {PAIR_NAMES[pair]} reached TP2 @ {current_price} ✅\033[0m")
            log(f"{pair} TP2 hit @ {current_price}")
            if trade.get('mode')=='live':
                sugg, score = suggest_using_trained_stats(pair, trade, current_price)
                print(f"  Suggestion: {sugg} (Confidence {score}%)")

        if not trade['TP3_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP3']) or (trade['Signal']=='SELL' and current_price <= trade['TP3'])):
            trade['TP3_hit'] = True
            print(f"\033[93m[TP3 HIT] {PAIR_NAMES[pair]} reached TP3 @ {current_price} ✅\033[0m")
            log(f"{pair} TP3 hit @ {current_price}")

        if not trade['SL_hit'] and ((trade['Signal']=='BUY' and current_price <= trade['SL']) or (trade['Signal']=='SELL' and current_price >= trade['SL'])):
            trade['SL_hit'] = True
            print(f"\033[91m[SL HIT] {PAIR_NAMES[pair]} hit SL @ {current_price}\033[0m")
            log(f"{pair} SL hit @ {current_price}")

        # TP suggestion
        if not trade['SL_hit']:
            historical_df = fetch_data(pair, interval='5m', period_days=30)  # 1 month, 5m bars
            suggestion = suggest_tp(trade, historical_df, pair)
            print(f"\033[93m[Suggestion] {PAIR_NAMES[pair]}: {suggestion}\033[0m")

        # Close condition: TP3 or SL (keep original behavior: hold through TP1/TP2)
        if (trade['TP3_hit']) or trade['SL_hit']:
            trade['Close_Price'] = current_price
            trade['Close_Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            closed_trades.append(trade)
            log_trade_to_csv(trade)
            del active_trades[pair]
            if ((trade['Signal']=='BUY' and trade['Close_Price']>trade['Entry']) or (trade['Signal']=='SELL' and trade['Close_Price']<trade['Entry'])):
                print(f"\033[92m[TRADE CLOSED - WIN] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']}\033[0m")
                log(f"Closed WIN {pair} @ {trade['Close_Price']}")
            else:
                print(f"\033[91m[TRADE CLOSED - LOSS] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']}\033[0m")
                log(f"Closed LOSS {pair} @ {trade['Close_Price']}")
    except Exception as e:
        log(f"check_trades error for {pair}: {e}")

# ===========================
# DASHBOARD (preserve original look and contents)
# ===========================
def display_dashboard():
    try:
        print("\n====== Precision Bot V3 Dashboard ======")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print("Active Trades:")
        if active_trades:
            for trade in active_trades.values():
                live_price = get_live_price(trade['Pair'])
                if live_price is None:
                    live_price = trade['Entry']
                pnl = compute_live_pnl(trade, live_price)
                color = "\033[92m" if pnl>=0 else "\033[91m"
                reset = "\033[0m"
                tp_status = []
                if trade['TP1_hit']: tp_status.append("TP1✅")
                if trade['TP2_hit']: tp_status.append("TP2✅")
                if trade['TP3_hit']: tp_status.append("TP3✅")
                status_str = ", ".join(tp_status) if tp_status else "No TP hit"
                # Print entry with 5 decimals for FX, 2 for Gold
                if trade['Pair'] == 'GC=F':
                    entry_fmt = f"{trade['Entry']:.2f}"
                else:
                    entry_fmt = f"{trade['Entry']:.5f}"
                print(f"  {PAIR_NAMES[trade['Pair']]}: {trade['Signal']} @ {entry_fmt} | "
                      f"TP1: {trade['TP1']:.5f} | TP2: {trade['TP2']:.5f} | TP3: {trade['TP3']:.5f} | "
                      f"SL: {trade['SL']:.5f} | {status_str} | Live P/L: {color}{pnl:.2f}{reset} pips")
        else:
            for pair in PAIRS:
                print(f"  {PAIR_NAMES[pair]}: WAIT")

        # Closed trades summary (LIVE only)
        live_closed = [t for t in closed_trades if t.get('mode','live')=='live']
        wins = sum(1 for t in live_closed if (t['Signal']=='BUY' and t['Close_Price']>t['Entry']) or (t['Signal']=='SELL' and t['Close_Price']<t['Entry']))
        losses = len(live_closed) - wins
        total = len(live_closed)
        win_rate = (wins/total*100) if total>0 else 0.0
        print("\nClosed Trades Stats (LIVE only):")
        print(f"  Wins: {wins} | Losses: {losses} | Total: {total} | Win Rate: {win_rate:.2f}%")
        print("\nCumulative P/L per Pair (Closed Trades - LIVE only):")
        for pair in PAIRS:
            pair_trades = [t for t in live_closed if t['Pair']==pair]
            pf = 10 if pair == 'GC=F' else (100 if 'JPY' in pair else 10000)
            cum_pnl = sum((t['Close_Price']-t['Entry'])*pf if t['Signal']=='BUY' else (t['Entry']-t['Close_Price'])*pf for t in pair_trades)
            print(f"  {PAIR_NAMES[pair]}: {cum_pnl:.2f} pips")
        print("========================================")
    except Exception as e:
        log(f"display_dashboard error: {e}")

# ===========================
# PROCESS EXTERNAL SIGNALS (optional use)
# ===========================
def process_external_signals():
    """
    Process any signals collected by webhook. External signals become additional
    opportunities to open trades (they do not disable internal generation).
    """
    while signals:
        data = signals.pop(0)
        try:
            symbol = data.get('symbol')
            map_back = {'EURUSD':'EURUSD=X','GBPUSD':'GBPUSD=X','USDJPY':'USDJPY=X','USDCAD':'USDCAD=X','XAUUSD':'GC=F','GOLD':'GC=F'}
            if symbol in map_back:
                pair = map_back[symbol]
            else:
                pair = symbol
            action = data.get('action') or data.get('side') or data.get('signal')
            if isinstance(action, str):
                action = action.upper()
            price = data.get('price') or get_live_price(pair)
            # Only open if no active trade for that pair and price available
            if pair not in active_trades and price is not None and action in ('BUY','SELL'):
                open_trade(pair, action, price, df=fetch_data(pair), mode='live')
                log(f"[EXTERNAL] Opened {pair} {action} @ {price}")
        except Exception as e:
            log(f"process_external_signals error: {e}")

# ===========================
# MAIN BOT LOOP
# ===========================
def run_bot():
    global TEST_MODE, last_trained
    # Train on startup for initial heuristics
    train_heuristic()
    while True:
        try:
            # Process any external TradingView signals first (they don't block internal generation)
            process_external_signals()

            # For each pair: internal signal generation, trade checks
            for pair in PAIRS:
                # Get historical data and live price
                df = fetch_data(pair, interval=TRAIN_INTERVAL, period_days=7)  # smaller short fetch for signal
                price = get_live_price(pair)
                if price is None:
                    # If cannot fetch live price, skip pair this cycle
                    continue

                # One-cycle test: open only one trade per pair in test mode
                if TEST_MODE and pair not in active_trades:
                    # Keep your original behavior: open BUY for test cycles
                    open_trade(pair, 'BUY', price, df=df, mode='test')
                    initial_test_opened.add(pair)
                    log(f"[TEST] Opened test trade for {pair} @ {price}")
                elif not TEST_MODE:
                    # Internal signal generation using EMA/RSI
                    signal = generate_signal(df)
                    # Apply a small loosened acceptance filter using trained_stats (improves precision but not overly strict)
                    accept_signal = False
                    if signal:
                    # Pair-specific SL and TP rules
                    gold_pairs = ["XAU/USD", "GC=F", "Gold/USD"]

                    if signal == "BUY":
                        if pair in gold_pairs:
                            tp1 = entry_price + 0.0050   # +50 pips
                            tp2 = entry_price + 0.0100   # +100 pips
                            tp3 = entry_price + 0.0150   # +150 pips
                            sl  = entry_price - 0.0070   # -70 pips
                       else:
                           tp1 = entry_price + 0.0040   # +40 pips
                           tp2 = entry_price + 0.0080   # +80 pips
                           tp3 = entry_price + 0.0120   # +120 pips
                           sl  = entry_price - 0.0050   # -50 pips

                  elif signal == "SELL":
                      if pair in gold_pairs:
                          tp1 = entry_price - 0.0050   # -50 pips
                          tp2 = entry_price - 0.0100   # -100 pips
                          tp3 = entry_price - 0.0150   # -150 pips
                          sl  = entry_price + 0.0070   # +70 pips
                      else:
                          tp1 = entry_price - 0.0040   # -40 pips
                          tp2 = entry_price - 0.0080   # -80 pips
                          tp3 = entry_price - 0.0120   # -120 pips
                          sl  = entry_price + 0.0050   # +50 pips  
                        stats = trained_stats.get(pair)
                        if not stats:
                            # no trained stats: accept signal (keeps signals frequent)
                            accept_signal = True
                        else:
                            base_prob = stats.get('p_tp3', 0.15)  # fallback low base
                            if base_prob >= 0.10:
                                accept_signal = True
                            else:
                                # let sustained EMA condition allow acceptance even with low base_prob
                                sustained = False
                                try:
                                    if signal == 'BUY':
                                        sustained = all(df['EMA5'].iloc[-(i+1)] > df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
                                    else:
                                        sustained = all(df['EMA5'].iloc[-(i+1)] < df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
                                except Exception:
                                    sustained = False
                                accept_signal = sustained

                    if accept_signal and signal and pair not in active_trades:
                        open_trade(pair, signal, price, df=df, mode='live')
                        log(f"[INTERNAL] Opened {pair} {signal} @ {price}")

                # Check active trades for TP/SL hits (use current price)
                if pair in active_trades:
                    check_trades(pair, price, df=fetch_data(pair, interval='5m', period_days=30))

            # Display dashboard after all pairs processed
            display_dashboard()

            # Auto-disable test mode when all test trades are closed
            if TEST_MODE and not any(t.get('mode')=='test' for t in active_trades.values()):
                TEST_MODE = False
                print("\033[95m[INFO] Test mode completed. Switching to live EMA/RSI trading.\033[0m")
                log("Test mode completed, switching to live.")

            # Periodic retrain
            if last_trained is None or (datetime.now() - last_trained).days >= RETRAIN_DAYS:
                train_heuristic()

            time.sleep(SLEEP_INTERVAL)
        except Exception as e:
            log(f"run_bot loop error: {e}")
            traceback.print_exc()
            time.sleep(5)
            
# ===========================
# MT5 P/L monitor (prints MT5 positions P/L)
# ===========================
def pl_loop():
    # Monitor open positions in MT5 and print P/L to terminal (for parity with dashboard)
    while True:
        try:
            positions = mt5.positions_get()
            if positions:
                print("\n[MT5 POSITIONS P/L UPDATE]")
                for pos in positions:
                    try:
                        symbol = pos.symbol
                        trade_type = "Buy" if pos.type == 0 else "Sell"
                        entry_price = pos.price_open
                        tick = mt5.symbol_info_tick(symbol)
                        if tick and tick.bid is not None:
                            current_price = tick.bid if pos.type==0 else tick.ask
                            pip_factor = 10 if symbol=="XAUUSD" else (100 if "JPY" in symbol else 10000)
                            pl = (current_price - entry_price)*pip_factor if pos.type==0 else (entry_price-current_price)*pip_factor
                            print(f"{symbol} | {trade_type} | Entry: {entry_price} | Current: {current_price} | P/L: {pl:.2f}")
                    except Exception as e:
                        log(f"pl_loop per-position error: {e}")
            time.sleep(2)
        except Exception as e:
            log(f"pl_loop error: {e}")
            time.sleep(2)

# ===========================
# ENTRY POINT
# ===========================
def init_mt5_once():
    if not mt5.initialize():
        print("MT5 initialize() failed")
        mt5.shutdown()
    else:
        info = mt5.account_info()
        print(f"Connected to MT5 Demo Account: {info.login}, Balance: {info.balance}")

if __name__ == '__main__':
    try:
        startup_banner()
        # startup prompt
        mode_input = ''
        while mode_input not in ('y', 'n'):
            mode_input = input("Start in test mode? (y/n): ").strip().lower()
        if mode_input == 'y':
            TEST_MODE = True
            print("\033[93m[INFO] Starting in TEST MODE (one-cycle enabled).\033[0m")
        else:
            TEST_MODE = False
            print("\033[92m[INFO] Starting in LIVE MODE.\033[0m")

        print(f"\033[94m[INFO] Precision Bot V3 starting. Pairs: {PAIRS} | Test Mode: {TEST_MODE} | One-cycle test: {ONE_CYCLE_TEST}\033[0m")

        # Start Flask webhook thread
        threading.Thread(target=start_flask, daemon=True).start()

        # Initialize MT5 connection and start P/L monitor thread
        init_mt5_once()
        threading.Thread(target=pl_loop, daemon=True).start()

        # Start main bot loop (blocking)
        run_bot()

    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested (KeyboardInterrupt). Exiting.")
        log("Shutdown by user (KeyboardInterrupt).")
        try:
            mt5.shutdown()
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print("!!! FATAL ERROR DURING BOT STARTUP OR RUNTIME !!!")
        print(f"{type(e)._name_}: {e}")
        traceback.print_exc()
        log(f"FATAL error: {type(e)._name_}: {e}")
        try:
            mt5.shutdown()
        except:
            pass
        sys.exit(1)
