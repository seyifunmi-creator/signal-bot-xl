# precision_bot_v3_full.py
# Full Precision Bot V3 - copy/paste into main.py
# Features: integrated training (1 month, 5m), one-cycle test, TP check marks,
# suggestions at TP1 & TP2 using trained stats, separate test/live accuracy,
# quiet error logging, and a y/n startup prompt.

import warnings
warnings.filterwarnings('ignore')

import time
import math
import os
import sys
import traceback
from datetime import datetime
# ===========================
# Pip unit helper and TP/SL calculation
# ===========================

def get_pip_unit(pair: str) -> float:
    """
    Returns the correct pip unit based on the trading pair.
    - JPY pairs use 0.01
    - Gold (XAU/USD) uses 1.0
    - Other forex pairs use 0.0001
    """
    pair = pair.upper()
    if "JPY" in pair:
        return 0.01
    elif "XAU" in pair or "GOLD" in pair:
        return 1.0
    else:
        return 0.0001


# delayed import of heavy libs inside try to log errors cleanly
try:
    import yfinance as yf
    import pandas as pd
except Exception as e:
    print("!!! IMPORT ERROR !!!")
    print("Make sure yfinance and pandas are installed in this Python environment.")
    print(f"{type(e)._name_}: {e}")
    traceback.print_exc()
    sys.exit(1)

# ===========================
# CONFIGURATION
# ===========================
PAIRS = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCAD=X', 'GC=F']
PAIR_NAMES = {
    'EURUSD=X': 'EUR/USD',
    'GBPUSD=X': 'GBP/USD',
    'USDJPY=X': 'USD/JPY',
    'USDCAD=X': 'USD/CAD',
    'GC=F': 'Gold/USD'
}

# default (will be overridden by startup prompt)
TEST_MODE = False   # If True -> test mode (one-cycle if ONE_CYCLE_TEST True)
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
RETRAIN_DAYS = 7         # not auto-scheduled; used if implementing retrain schedule

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
    """Append a timestamped message to LOG_FILE (quiet on console)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        # last-resort print if logging fails
        try:
            print("LOG WRITE FAILED:", line)
        except:
            pass

# pretty startup banner (console)
def startup_banner():
    print(">>> Precision Bot V3 — Startup Initiated <<<")
    print(f"Pairs: {PAIRS}")
    print(f"Log file: {LOG_FILE}")
    print("Waiting for startup selection...")

# ===========================
# MARKET & INDICATOR HELPERS
# ===========================
def detect_pip_unit(pair):
    """Return (pip_unit, pip_factor) for calculations."""
    if pair.endswith('JPY'):
        return 0.01, 100
    if pair == 'GC=F':
        # keep user-chosen earlier behavior (you told me you fixed gold pip unit)
        return 0.1, 10
    return 0.0001, 10000

def fetch_data(pair, interval='5m', period_days=30):
    """Fetch historical data (auto_adjust=True)."""
    try:
        period_str = f"{period_days}d"
        df = yf.download(pair, period=period_str, interval=interval, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        # compute indicators
        if len(df) >= 12:
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

def get_live_price(pair):
    """Try fast_info last_price, fallback to 1m history close"""
    try:
        ticker = yf.Ticker(pair)
        info = getattr(ticker, 'fast_info', None)
        if info and 'last_price' in info:
            return float(info['last_price'])
        h = ticker.history(period='1d', interval='1m')
        if not h.empty:
            return float(h['Close'].iloc[-1])
        return None
    except Exception as e:
        log(f"get_live_price failed for {pair}: {e}")
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
    """Sustained EMA crossover + RSI filter for higher confidence signals."""
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
# BACKTEST / TRAINING (INTEGRATED)
# ===========================
def backtest_pair(pair, df):
    """Simulate historical signals and record whether TP1/TP2/TP3 were reached."""
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
        # iterate through candles and simulate entries
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
            # look ahead up to 500 candles (arbitrary cap to limit runtime)
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
            if reached_tp1:
                results['tp1_reached'] += 1
            if reached_tp2:
                results['tp2_reached'] += 1
            if reached_tp3:
                results['tp3_reached'] += 1
            if reached_tp1 and reached_tp3:
                results['tp3_given_tp1'] += 1
            if reached_tp2 and reached_tp3:
                results['tp3_given_tp2'] += 1

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
    """Train (compute empirical stats) for each pair using recent historical data."""
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
# TRADING: open/check/log
# ===========================


def open_trade(pair, signal, current_price, df=None):
    """
    Opens a trade with properly scaled TP and SL for all pairs
    Includes try/except to prevent runtime crashes
    """
    try: 
        # Pip unit & TP/SL calculation (pair & current_price are defined here)
        pip_unit = get_pip_unit(pair)
        tp1_price = current_price + (TP1 * pip_unit) if signal == 'BUY' else current_price - (TP1 * pip_unit)
        tp2_price = current_price + ((TP1+TP2) * pip_unit) if signal == 'BUY' else current_price - ((TP1+TP2) * pip_unit)
        tp3_price = current_price + ((TP1+TP2+TP3) * pip_unit) if signal == 'BUY' else current_price - ((TP1+TP2+TP3) * pip_unit)
        sl_price  = current_price - (SL * pip_unit) if signal == 'BUY' else current_price + (SL * pip_unit)

        # ATR-based TP/SL adjustments
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

        # Save trade
        active_trades[pair] = {
            'Pair': pair,
            'Signal': signal,
            'Entry': current_price,
            'TP1': current_price + tp1_val if signal=='BUY' else current_price - tp1_val,
            'TP2': current_price + tp2_val if signal=='BUY' else current_price - tp2_val,
            'TP3': current_price + tp3_val if signal=='BUY' else current_price - tp3_val,
            'SL': current_price - sl_val if signal=='BUY' else current_price + sl_val,
            'TP1_hit': False,
            'TP2_hit': False,
            'TP3_hit': False,
            'SL_hit': False,
            'Entry_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Logging
        log(f"Opened {pair} {signal} @ {current_price} mode={'TEST' if TEST_MODE else 'LIVE'}")
        print(f"\033[96m[TRADE OPENED] {PAIR_NAMES[pair]} {signal} @ {current_price:.5f}\033[0m")

    except Exception as e:
        log(f"open_trade error for {pair}: {e}")
def compute_live_pnl(trade, current_price):
    """
    Calculates live P/L in pips using the same pip_unit logic as TP/SL
    """
    try:
        # Determine pip unit
        def get_pip_unit(pair: str) -> float:
            pair = pair.upper()
            if "JPY" in pair:
                return 0.01
            elif "XAU" in pair or "GOLD" in pair:
                return 1.0
            else:
                return 0.0001

        pip_unit = get_pip_unit(trade['Pair'])

        # Calculate P/L in pips
        if trade['Signal'] == 'BUY':
            return (current_price - trade['Entry']) / pip_unit
        else:
            return (trade['Entry'] - current_price) / pip_unit

    except Exception as e:
        log(f"compute_live_pnl error for {trade['Pair']}: {e}")
        return 0.0
def log_trade_to_csv(trade):
    try:
        df = pd.DataFrame([{
            'Pair': PAIR_NAMES[trade['Pair']],
            'Signal': trade['Signal'],
            'Entry': trade['Entry'],
            'Close': trade['Close_Price'],
            'TP1': trade['TP1'],
            'TP2': trade['TP2'],
            'TP3': trade['TP3'],
            'SL': trade['SL'],
            'Entry_Time': trade['Entry_Time'],
            'Close_Time': trade['Close_Time'],
            'P/L': compute_live_pnl(trade, trade['Close_Price']),
            'Mode': trade.get('mode','live')
        }])
        if not os.path.isfile(CSV_FILE):
            df.to_csv(CSV_FILE, mode='w', header=True, index=False)
        else:
            df.to_csv(CSV_FILE, mode='a', header=False, index=False)
    except Exception as e:
        log(f"Failed to log trade to CSV: {e}")

# Heuristic suggestion using trained stats
def suggest_using_trained_stats(pair, trade, current_price):
    try:
        stats = trained_stats.get(pair)
        if not stats:
            return ("No trained data — hold.", 50)
        pip_unit, _ = detect_pip_unit(pair)
        # choose conditional probability if TP1/TP2 hit
        base_prob = stats.get('p_tp3', 0.0)
        if trade['TP2_hit']:
            base_prob = stats.get('p_tp3_given_tp2', base_prob)
        elif trade['TP1_hit']:
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

# Checking active trades for TP/SL and suggestions
def check_trades(pair, current_price, df=None):
    if pair not in active_trades:
        return
    trade = active_trades[pair]
    try:
        if not trade['TP1_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP1']) or (trade['Signal']=='SELL' and current_price <= trade['TP1'])):
            trade['TP1_hit'] = True
            print(f"\033[93m[TP1 HIT] {PAIR_NAMES[pair]} reached TP1 @ {current_price:.5f} ✅\033[0m")
            log(f"{pair} TP1 hit @ {current_price}")
            if trade.get('mode')=='live':
                sugg, score = suggest_using_trained_stats(pair, trade, current_price)
                print(f"  Suggestion: {sugg} (Confidence {score}%)")

        if not trade['TP2_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP2']) or (trade['Signal']=='SELL' and current_price <= trade['TP2'])):
            trade['TP2_hit'] = True
            print(f"\033[93m[TP2 HIT] {PAIR_NAMES[pair]} reached TP2 @ {current_price:.5f} ✅\033[0m")
            log(f"{pair} TP2 hit @ {current_price}")
            if trade.get('mode')=='live':
                sugg, score = suggest_using_trained_stats(pair, trade, current_price)
                print(f"  Suggestion: {sugg} (Confidence {score}%)")

        if not trade['TP3_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP3']) or (trade['Signal']=='SELL' and current_price <= trade['TP3'])):
            trade['TP3_hit'] = True
            print(f"\033[93m[TP3 HIT] {PAIR_NAMES[pair]} reached TP3 @ {current_price:.5f} ✅\033[0m")
            log(f"{pair} TP3 hit @ {current_price}")

        if not trade['SL_hit'] and ((trade['Signal']=='BUY' and current_price <= trade['SL']) or (trade['Signal']=='SELL' and current_price >= trade['SL'])):
            trade['SL_hit'] = True
            print(f"\033[91m[SL HIT] {PAIR_NAMES[pair]} hit SL @ {current_price:.5f}\033[0m")
            log(f"{pair} SL hit @ {current_price}")

        # Close condition: TP3 or SL (keeps previous behavior of holding through TP1/TP2)
        if (trade['TP3_hit']) or trade['SL_hit']:
            trade['Close_Price'] = current_price
            trade['Close_Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            closed_trades.append(trade)
            log_trade_to_csv(trade)
            del active_trades[pair]
            if ((trade['Signal']=='BUY' and trade['Close_Price']>trade['Entry']) or (trade['Signal']=='SELL' and trade['Close_Price']<trade['Entry'])):
                print(f"\033[92m[TRADE CLOSED - WIN] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']:.5f}\033[0m")
                log(f"Closed WIN {pair} @ {trade['Close_Price']}")
            else:
                print(f"\033[91m[TRADE CLOSED - LOSS] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']:.5f}\033[0m")
                log(f"Closed LOSS {pair} @ {trade['Close_Price']}")
    except Exception as e:
        log(f"check_trades error for {pair}: {e}")

# ===========================
# DASHBOARD
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
                print(f"  {PAIR_NAMES[trade['Pair']]}: {trade['Signal']} @ {trade['Entry']:.5f} | "
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
# MAIN BOT LOOP
# ===========================
def run_bot():
    global TEST_MODE
    while True:
        for pair in PAIRS:
            price = get_live_price(pair)
            if price is None:
                continue

            # Test mode: open single trade per pair if not active
            if TEST_MODE and pair not in active_trades:
                open_trade(pair, 'BUY', price)  # log inside open_trade()
            elif not TEST_MODE:
                df = fetch_data(pair)
                signal = generate_signal(df)
                if signal and pair not in active_trades:
                    open_trade(pair, signal, price, df)

            check_trades(pair, price)

        display_dashboard()

        # Disable test mode automatically if all test trades closed
        if TEST_MODE and not active_trades:
            TEST_MODE = False
            print("\033[95m[INFO] Test mode completed. Switching to live EMA/RSI trading.\033[0m")

        time.sleep(SLEEP_INTERVAL)

# ===========================
# ENTRY POINT (with y/n startup prompt and safety)
# ===========================
if __name__ == '__main__':
    try:
        startup_banner()
        # prompt (strict y or n)
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
        run_bot()
    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested (KeyboardInterrupt). Exiting.")
        log("Shutdown by user (KeyboardInterrupt).")
        sys.exit(0)
    except Exception as e:
        print("!!! FATAL ERROR DURING BOT STARTUP OR RUNTIME !!!")
        print(f"{type(e)._name_}: {e}")
        traceback.print_exc()
        log(f"FATAL error: {type(e)._name_}: {e}")
        sys.exit(1)
