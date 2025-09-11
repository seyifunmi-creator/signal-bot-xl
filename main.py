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
import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 initialization failed")
    mt5.shutdown()
import pandas as pd
import csv
import os
import threading
import logging

# --- Logging setup ---
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- Trade Tracking Globals ---
wins, losses, profit = 0, 0, 0
trades = []
REQUIRED_SUSTAINED_CANDLES = 3
# --- Global trade stats ---
total_trades = 0
wins = 0
losses = 0
profit = 0.0

# --- Pair Settings (TP/SL per instrument) ---
PAIR_SETTINGS = {
    'EURUSD': {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50},
    'GBPUSD': {'TP1': 50, 'TP2': 100, 'TP3': 150, 'SL': 60},
    'USDJPY': {'TP1': 30, 'TP2': 60, 'TP3': 90, 'SL': 40},
    'USDCAD': {'TP1': 25, 'TP2': 50, 'TP3': 75, 'SL': 30},
    'XAUUSD': {'TP1': 500, 'TP2': 1000, 'TP3': 1500, 'SL': 600},
}
DEFAULT_SETTINGS = {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50}

# --- Pairs & Names ---
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
PAIR_NAMES = {
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD',
    'USDJPY': 'USD/JPY', 'USDCAD': 'USD/CAD',
    'XAUUSD': 'Gold/USD'
}

# --- Trade history CSV setup ---
HISTORY_FILE = "trade_history.csv"
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Pair", "Signal", "Entry", "Exit", "Target", "Result", "Profit/Loss"])

# === MAIN CYCLE LOOP (run periodically in your scheduler) ===
def run_cycle():
    global total_trades, wins, losses, profit

    for pair in PAIRS:
        name = PAIR_NAMES.get(pair, pair)
        # --- Fecth latest price from MT5---
        tick = mt5.symbol_info_tick(pair)
        if tick is None:
            log(f"[WARN] No tick data for {pair}. Skipping this pair.")
            continue

        # Use the 'ask' price for BUY trades and 'bid' for SELL trades
        price = tick.ask if signal == "BUY" else tick.bid

        # Safety check
        if price <= 0.0:
            log(f"[WARN] Invalid price {price} for {pair}. Skipping trade.")
            continue
        # --- Fetch latest candles from MT5 ---
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M15, 0, 50)
        df = pd.DataFrame(rates)
        df['EMA5'] = df['close'].ewm(span=5).mean()
        df['EMA12'] = df['close'].ewm(span=12).mean()

        # --- Initialize signal safely ---
        signal = None
        if all(df['EMA5'].iloc[-(i+1)] > df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES)):
            signal = "BUY"
        elif all(df['EMA5'].iloc[-(i+1)] < df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES)):
            signal = "SELL"

        # --- Only act if a signal exists ---
        if signal:
            settings = PAIR_SETTINGS.get(pair, DEFAULT_SETTINGS)
            tp1, tp2, tp3, sl = settings['TP1'], settings['TP2'], settings['TP3'], settings['SL']
            current_price = df['close'].iloc[-1]

            # Open trade safely
            open_trade(pair, signal, current_price, df=df, mode='live',
                       tp1=tp1, tp2=tp2, tp3=tp3, sl=sl)

        # --- Update closed trades and stats ---
        closed_trades = update_closed_trades(pair)  # your existing function
        for trade in closed_trades:
            total_trades += 1
            if trade['result'] == 'WIN':
                wins += 1
            else:
                losses += 1
            profit += trade['pnl']
            logger.info(f"[CLOSED] {trade['pair']} | Result: {trade['result']} | P/L: {trade['pnl']:.2f}")

    # --- Cycle summary ---
    logger.info(f"[SUMMARY] Cycle finished | Total trades: {total_trades}, Wins: {wins}, Losses: {losses}, Net P/L: {profit:.2f}")

    # Optional: any end-of-cycle logic from old loop (e.g., sleep, dashboard update)
    
    # Example: processing closed trades
    for trade in closed_trades:
        total_trades += 1
        if trade['result'] == 'WIN':
                wins += 1
        else:
            losses += 1
        profit += trade['pnl']
        logger.info(
            f"[CLOSED] {trade['pair']} | Result: {trade['result']} | P/L: {trade['pnl']:.2f}"
        )

    # ✅ after all pairs processed in this cycle
    logger.info(
        f"[SUMMARY] Cycle finished | Total trades: {total_trades}, "
        f"Wins: {wins}, Losses: {losses}, Net P/L: {profit:.2f}"
    )

    for trade in trades:
        symbol = trade['pair'].replace('/', '')  # MT5 symbol format
        current_price = float(mt5.symbol_info_tick(symbol).last)

        # BUY Trades
        if trade['signal'] == "BUY":
            if not trade['TP1_hit'] and current_price >= trade['TP1']:
                trade['TP1_hit'] = True; wins += 1; profit += (trade['TP1'] - trade['entry'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP1'], "TP1", "WIN", trade['TP1'] - trade['entry']])
                print(f"{trade['pair']} hit TP1✅"); logger.info(f"{trade['pair']} hit TP1✅")
            if not trade['TP2_hit'] and current_price >= trade['TP2']:
                trade['TP2_hit'] = True; wins += 1; profit += (trade['TP2'] - trade['entry'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP2'], "TP2", "WIN", trade['TP2'] - trade['entry']])
                print(f"{trade['pair']} hit TP2✅"); logger.info(f"{trade['pair']} hit TP2✅")
            if not trade['TP3_hit'] and current_price >= trade['TP3']:
                trade['TP3_hit'] = True; wins += 1; profit += (trade['TP3'] - trade['entry'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP3'], "TP3", "WIN", trade['TP3'] - trade['entry']])
                print(f"{trade['pair']} hit TP3✅"); logger.info(f"{trade['pair']} hit TP3✅")
                closed_trades.append(trade)
            if not trade['SL_hit'] and current_price <= trade['SL']:
                trade['SL_hit'] = True; losses += 1; profit -= (trade['entry'] - trade['SL'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['SL'], "SL", "LOSS", -(trade['entry'] - trade['SL'])])
                print(f"{trade['pair']} SL❌"); logger.info(f"{trade['pair']} SL❌")
                closed_trades.append(trade)

        # SELL Trades
        elif trade['signal'] == "SELL":
            if not trade['TP1_hit'] and current_price <= trade['TP1']:
                trade['TP1_hit'] = True; wins += 1; profit += (trade['entry'] - trade['TP1'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP1'], "TP1", "WIN", trade['entry'] - trade['TP1']])
                print(f"{trade['pair']} hit TP1✅"); logger.info(f"{trade['pair']} hit TP1✅")
            if not trade['TP2_hit'] and current_price <= trade['TP2']:
                trade['TP2_hit'] = True; wins += 1; profit += (trade['entry'] - trade['TP2'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP2'], "TP2", "WIN", trade['entry'] - trade['TP2']])
                print(f"{trade['pair']} hit TP2✅"); logger.info(f"{trade['pair']} hit TP2✅")
            if not trade['TP3_hit'] and current_price <= trade['TP3']:
                trade['TP3_hit'] = True; wins += 1; profit += (trade['entry'] - trade['TP3'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['TP3'], "TP3", "WIN", trade['entry'] - trade['TP3']])
                print(f"{trade['pair']} hit TP3✅"); logger.info(f"{trade['pair']} hit TP3✅")
                closed_trades.append(trade)
            if not trade['SL_hit'] and current_price >= trade['SL']:
                trade['SL_hit'] = True; losses += 1; profit -= (trade['SL'] - trade['entry'])
                with open(HISTORY_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([trade['pair'], trade['signal'], trade['entry'], trade['SL'], "SL", "LOSS", -(trade['SL'] - trade['entry'])])
                print(f"{trade['pair']} SL❌"); logger.info(f"{trade['pair']} SL❌")
                closed_trades.append(trade)

        # Print + log trade status
        tp_status = []
        if trade['TP1_hit']: tp_status.append("TP1✅")
        if trade['TP2_hit']: tp_status.append("TP2✅")
        if trade['TP3_hit']: tp_status.append("TP3✅")
        if trade['SL_hit']:  tp_status.append("SL❌")

        status_msg = (f"{trade['pair']} {trade['signal']} | Entry {trade['entry']} | "
                      f"TPs {trade['TP1']}/{trade['TP2']}/{trade['TP3']} | SL {trade['SL']} | "
                      f"Status: {' '.join(tp_status) if tp_status else 'Active'}")
        print(status_msg); logger.info(status_msg)

    # --- remove closed trades ---
    for ct in closed_trades:
        trades.remove(ct)

    # --- cycle summary ---
    total_trades = wins + losses
    accuracy = (wins / total_trades * 100) if total_trades > 0 else 0

    print(f"\nCycle Summary → Total trades {total_trades}, Wins {wins}, Losses {losses}, Accuracy {accuracy:.2f}%, Net P/L {profit:.2f}\n")
    logger.info(f"Cycle Summary → Total trades {total_trades}, Wins {wins}, Losses {losses}, Accuracy {accuracy:.2f}%, Net P/L {profit:.2f}")

    # --- After processing all pairs in this cycle ---
    total_trades = wins + losses
    accuracy = (wins / total_trades * 100) if total_trades > 0 else 0

    # Console + log file
    print(f"\nCycle Summary → Total trades {total_trades}, Wins {wins}, Losses {losses}, Accuracy {accuracy:.2f}%, Net P/L {profit:.2f}\n")
    logger.info(f"Cycle Summary → Total trades {total_trades}, Wins {wins}, Losses {losses}, Accuracy {accuracy:.2f}%, Net P/L {profit:.2f}")
      
# ------------------------
# After all pairs in this cycle
# ------------------------
if total_trades > 0:
    accuracy = (wins / total_trades) * 100
else:
    accuracy = 0

print(f"\nCycle Summary → Total trades {total_trades}, Wins {wins}, Losses {losses}, Accuracy {accuracy:.2f}%, Net P/L {profit:.2f}\n")

# default (overridden by startup prompt)
TEST_MODE = False
ONE_CYCLE_TEST = True

pair = 'EURUSD=X'  # this should be the pair currently being traded

# Use pair-specific settings, fallback to default if missing
DEFAULT_SETTINGS = {'TP1': 40, 'TP2': 40, 'TP3': 40, 'SL': 50}
settings = PAIR_SETTINGS.get(pair, DEFAULT_SETTINGS)

TP1, TP2, TP3, SL = settings['TP1'], settings['TP2'], settings['TP3'], settings['SL']
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
def open_trade(pair, signal, current_price, df=None, mode='live', tp1=None, tp2=None, tp3=None, sl=None):
    try:
        pair_upper = pair.upper()
        if 'JPY' in pair_upper:
            pip_unit = 0.01
        elif pair == 'GC=F' or 'XAU' in pair_upper or 'GOLD' in pair_upper:
            pip_unit = 0.1
        else:
            pip_unit = 0.0001

        atr = calculate_atr(df) if df is not None else None
        if atr is not None:
            tp1_val = atr
            tp2_val = atr*2
            tp3_val = atr*3
            sl_val = atr*1.25
        else:
            tp1_val = tp1*pip_unit if tp1 is not None else 40*pip_unit
            tp2_val = tp2*pip_unit if tp2 is not None else 80*pip_unit
            tp3_val = tp3*pip_unit if tp3 is not None else 120*pip_unit
            sl_val  = sl*pip_unit if sl is not None else 50*pip_unit

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
                if trade['SL_hit']:  tp_status.append("SL❌")   # 👈 new line

                total_trades += 1

                if hit_tp1 or hit_tp2 or hit_tp3:
                    wins += 1
                    profit += actual_profit   # replace with how you calculate P/L
                elif hit_sl:
                    losses += 1
                    profit -= actual_loss     # replace with how you calculate P/L
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
# MAIN BOT LOOP
# ===========================
# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

def run_bot():
    global total_trades, wins, losses, profit, last_trained

    initial_test_opened = set()
    gold_pairs = ["XAU/USD", "GC=F", "Gold/USD"]

    while True:
        try:
            open_trades_snapshot = []

            for pair in PAIRS:
                name = PAIR_NAMES.get(pair, pair)

                # --- Fetch current price ---
                tick = mt5.symbol_info_tick(pair)
                if tick is None:
                    log(f"[WARN] No tick data for {pair}. Skipping.")
                    continue

                # --- Fetch historical data ---
                rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M15, 0, 50)
                df = pd.DataFrame(rates)
                if df.empty:
                    log(f"[WARN] No historical data for {pair}. Skipping.")
                    continue

                # --- Calculate EMAs ---
                df['EMA5'] = df['close'].ewm(span=5).mean()
                df['EMA12'] = df['close'].ewm(span=12).mean()

                # --- Generate signal ---
                signal = generate_signal(df)
                if signal is None:
                    log(f"[WARN] No signal for {pair}. Skipping.")
                    continue

                # --- Determine entry price ---
                price = tick.ask if signal == 'BUY' else tick.bid
                if price <= 0.0:
                    log(f"[WARN] Invalid price {price} for {pair}. Skipping.")
                    continue

                # --- Calculate TP/SL ---
                if signal == "BUY":
                    if pair in gold_pairs:
                        tp1, tp2, tp3, sl = price+0.0050, price+0.0100, price+0.0150, price-0.0070
                    else:
                        tp1, tp2, tp3, sl = price+0.0040, price+0.0080, price+0.0120, price-0.0050
                else:  # SELL
                    if pair in gold_pairs:
                        tp1, tp2, tp3, sl = price-0.0050, price-0.0100, price-0.0150, price+0.0070
                    else:
                        tp1, tp2, tp3, sl = price-0.0040, price-0.0080, price-0.0120, price+0.0050

                # --- Preview signal with risk check and color ---
                buffer = 0.0002 if pair not in gold_pairs else 0.5
                near_tp_sl = ""
                if signal == 'BUY':
                    color = GREEN
                    if price >= tp1 - buffer:
                        near_tp_sl = f"{YELLOW}⚡ Near TP1!{RESET}"
                    elif price <= sl + buffer:
                        near_tp_sl = f"{MAGENTA}⚠ Near SL!{RESET}"
                else:  # SELL
                    color = RED
                    if price <= tp1 + buffer:
                        near_tp_sl = f"{YELLOW}⚡ Near TP1!{RESET}"
                    elif price >= sl - buffer:
                        near_tp_sl = f"{MAGENTA}⚠ Near SL!{RESET}"

                log(f"{color}[PREVIEW]{RESET} {pair} | Signal: {signal} | Entry: {price} | TP1: {tp1} | TP2: {tp2} | TP3: {tp3} | SL: {sl} {near_tp_sl}")

                # --- Open trade if allowed ---
                if pair not in active_trades:
                    mode = 'test' if TEST_MODE else 'live'
                    open_trade(pair, signal, price, df=df, tp1=tp1, tp2=tp2, tp3=tp3, sl=sl, mode=mode)
                    log_type = "[TEST]" if TEST_MODE else "[TRADE OPENED]"
                    log(f"{color}{log_type}{RESET} {pair} | Signal: {signal} | Entry: {price} | TP1: {tp1} | TP2: {tp2} | TP3: {tp3} | SL: {sl}")
                    if TEST_MODE:
                        initial_test_opened.add(pair)

                # --- Add to dashboard snapshot ---
                if pair in active_trades:
                    trade = active_trades[pair]
                    # compute P/L
                    if trade['Signal'] == 'BUY':
                        pnl = price - trade['Entry']
                    else:
                        pnl = trade['Entry'] - price
                    open_trades_snapshot.append({
                        'pair': pair,
                        'signal': trade['Signal'],
                        'entry': trade['Entry'],
                        'TP1_hit': trade.get('TP1_hit', False),
                        'TP2_hit': trade.get('TP2_hit', False),
                        'TP3_hit': trade.get('TP3_hit', False),
                        'SL_hit': trade.get('SL_hit', False),
                        'current_price': price,
                        'pnl': pnl
                    })

            # --- Update closed trades ---
            closed_trades = []
            for trade in list(active_trades.values()):
                tick = mt5.symbol_info_tick(trade['Pair'])
                price = tick.last if tick else None
                if price is None:
                    continue

                if trade['Signal'] == 'BUY':
                    if price >= trade['TP1'] and not trade['TP1_hit']:
                        trade['TP1_hit'] = True
                        closed_trades.append({'pair': trade['Pair'], 'result': 'WIN', 'pnl': trade['TP1'] - trade['Entry']})
                        del active_trades[trade['Pair']]
                    elif price <= trade['SL']:
                        trade['SL_hit'] = True
                        closed_trades.append({'pair': trade['Pair'], 'result': 'LOSS', 'pnl': price - trade['Entry']})
                        del active_trades[trade['Pair']]
                else:  # SELL
                    if price <= trade['TP1'] and not trade['TP1_hit']:
                        trade['TP1_hit'] = True
                        closed_trades.append({'pair': trade['Pair'], 'result': 'WIN', 'pnl': trade['Entry'] - trade['TP1']})
                        del active_trades[trade['Pair']]
                    elif price >= trade['SL']:
                        trade['SL_hit'] = True
                        closed_trades.append({'pair': trade['Pair'], 'result': 'LOSS', 'pnl': trade['Entry'] - price})
                        del active_trades[trade['Pair']]

            for trade in closed_trades:
                total_trades += 1
                if trade['result'] == 'WIN':
                    wins += 1
                else:
                    losses += 1
                profit += trade['pnl']
                logger.info(f"[CLOSED] {trade['pair']} | Result: {trade['result']} | P/L: {trade['pnl']:.2f}")

            # --- Dashboard summary with P/L color ---
            if open_trades_snapshot:
                log("----- OPEN TRADES DASHBOARD -----")
                for t in open_trades_snapshot:
                    dash_color = GREEN if t['signal'] == 'BUY' else RED
                    pnl_color = GREEN if t['pnl'] >= 0 else RED
                    near_tp_sl = ""
                    if t['signal'] == 'BUY':
                        if t['current_price'] >= t['entry'] + 0.002:  # simple buffer
                            near_tp_sl = f"{YELLOW}⚡ Near TP1{RESET}"
                        elif t['current_price'] <= t['entry'] - 0.002:
                            near_tp_sl = f"{MAGENTA}⚠ Near SL{RESET}"
                    else:
                        if t['current_price'] <= t['entry'] - 0.002:
                            near_tp_sl = f"{YELLOW}⚡ Near TP1{RESET}"
                        elif t['current_price'] >= t['entry'] + 0.002:
                            near_tp_sl = f"{MAGENTA}⚠ Near SL{RESET}"

                    log(f"{dash_color}{t['pair']}{RESET} | Signal: {t['signal']} | Entry: {t['entry']} | Current: {t['current_price']} | P/L: {pnl_color}{t['pnl']:.4f}{RESET} | TP1_hit: {t['TP1_hit']} | TP2_hit: {t['TP2_hit']} | TP3_hit: {t['TP3_hit']} | SL_hit: {t['SL_hit']} {near_tp_sl}")
                log("----- END DASHBOARD -----")

            # --- Retrain heuristic if needed ---
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
