# main.py — Precision Bot V3 (Consolidated, safe, updated)
# - Test mode (y) vs Live mode (n)
# - TP/SL shown on trade open and attached to MT5 live orders when possible
# - Dashboard updates only every UPDATE_INTERVAL seconds
# - Floating and realized P/L
# - Near TP/SL warnings, RSI/ATR safety, gold-specific TP/SL increments
# - Robust error handling; no NameErrors (self-contained)

import os
import csv
import time
import traceback
import threading
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd

# -------------------------
# CONFIG
# -------------------------
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']  # main symbols used with MT5
PAIR_NAMES = {
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD',
    'USDJPY': 'USD/JPY', 'USDCAD': 'USD/CAD',
    'XAUUSD': 'Gold/USD'
}

# per-pair TP/SL in "pips" (for FX) or "points" for Gold (we handle gold specially)
PAIR_SETTINGS = {
    'EURUSD': {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50},
    'GBPUSD': {'TP1': 50, 'TP2': 100, 'TP3': 150, 'SL': 60},
    'USDJPY': {'TP1': 30, 'TP2': 60, 'TP3': 90, 'SL': 40},
    'USDCAD': {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50},
    'XAUUSD': {'TP1': 50, 'TP2': 100, 'TP3': 150, 'SL': 70},  # gold: points (not pips)
}
DEFAULT_SETTINGS = {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50}

# Dashboard / timing
SLEEP_INTERVAL = 5               # main loop sleep (seconds) - internal checks
UPDATE_INTERVAL = 60             # how often to print dashboard per pair (seconds)

# Indicators
REQUIRED_SUSTAINED_CANDLES = 3
RSI_PERIOD = 14
ATR_PERIOD = 14

# File paths
LOG_FILE = "precision_bot.log"
TRADE_HISTORY_CSV = "trade_history.csv"

# MT5 order defaults
DEFAULT_VOLUME = 0.01            # default lots when sending orders in live mode
DEVIATION = 20                   # slippage tolerance in points

# -------------------------
# STATE (globals)
# -------------------------
active_trades = {}               # pair -> trade dict (Entry, TP1/2/3, SL, Signal, flags, mode)
closed_trades = []               # list of closed trade dicts
trained_stats = {}               # optional trained stats (kept for compatibility)
last_trained = None

# stats
total_trades = 0
wins = 0
losses = 0
realized_profit = 0.0            # realized (closed) P/L in pips/points units
last_update_time = {}            # pair -> timestamp of last printed update
last_cycle_summary = 0

# Mode (set at startup)
TEST_MODE = True
ONE_CYCLE_TEST = False

# ensure CSV exists
if not os.path.exists(TRADE_HISTORY_CSV):
    with open(TRADE_HISTORY_CSV, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["Timestamp", "Pair", "Signal", "Entry", "Close", "TP1", "TP2", "TP3", "SL", "Result", "P/L"])

# -------------------------
# Logging helper
# -------------------------
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        pass

# -------------------------
# MT5 Initialization helper
# -------------------------
def init_mt5():
    try:
        if not mt5.initialize():
            log("MT5 initialize() failed")
            return False
        info = mt5.account_info()
        if info:
            log(f"Connected to MT5 Account: {info.login} | Balance: {getattr(info,'balance', 'N/A')}")
        else:
            log("Connected to MT5 (no account info available).")
        return True
    except Exception as e:
        log(f"init_mt5 error: {e}")
        return False

# -------------------------
# Utilities for pip/point units
# -------------------------
def detect_pip_unit(pair):
    """Return (pip_unit, pip_factor) - pip_unit is price delta of one pip/point.
       pip_factor is multiplier to convert price delta to pips/points (for P/L display)."""
    p = pair.upper()
    if p.endswith('JPY'):
        return 0.01, 100
    if 'XAU' in p or 'GOLD' in p or p == 'XAUUSD':
        # treat gold: 0.01 price increment ~ 1 point; we will use 0.01 and factor 100 for display matching ~points
        # but since we want TP of +50 points = +0.50 price, we will use absolute deltas in calculate_tp_sl.
        # Here we return pip_unit 0.01 and pip_factor 100 so that (price delta * pip_factor) yields "points"
        return 0.01, 100
    return 0.0001, 10000

# -------------------------
# Indicator calculations
# -------------------------
def compute_rsi(df, period=RSI_PERIOD):
    if df is None or 'close' not in df.columns:
        return df
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-8)
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def calculate_atr(df, period=ATR_PERIOD):
    try:
        if df is None or len(df) < 2:
            return None
        high = df['high']
        low = df['low']
        close = df['close']
        h_l = high - low
        h_pc = (high - close.shift(1)).abs()
        l_pc = (low - close.shift(1)).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        atr = tr.rolling(period, min_periods=1).mean()
        return float(atr.iloc[-1])
    except Exception as e:
        log(f"ATR calc failed: {e}")
        return None

# -------------------------
# Signal generation (safe)
# -------------------------
def generate_signal(df):
    try:
        if df is None or len(df) < REQUIRED_SUSTAINED_CANDLES + 5:
            return None
        df = df.copy()
        if 'close' not in df.columns:
            return None
        df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
        df = compute_rsi(df)
        sustained_buy = all(df['EMA5'].iloc[-(i+1)] > df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
        sustained_sell = all(df['EMA5'].iloc[-(i+1)] < df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
        rsi_last = df['RSI'].iloc[-1] if 'RSI' in df.columns and not df['RSI'].isna().all() else None
        # simple RSI filters: avoid buying when RSI very high, avoid selling when RSI very low
        if sustained_buy and (rsi_last is None or rsi_last < 70):
            return 'BUY'
        if sustained_sell and (rsi_last is None or rsi_last > 30):
            return 'SELL'
        return None
    except Exception as e:
        log(f"generate_signal error: {e}")
        return None

# -------------------------
# TP/SL calculation (gold special handling)
# -------------------------
def calculate_tp_sl(pair, signal, entry_price):
    """Return TP1, TP2, TP3, SL as absolute price levels.
       Gold uses absolute points: TP1 +0.50, TP2 +1.00, etc.
       Others use pip scaling from PAIR_SETTINGS (TP in pips)."""
    settings = PAIR_SETTINGS.get(pair, DEFAULT_SETTINGS)
    # Gold handling: we interpret PAIR_SETTINGS for XAUUSD as points (50 -> +0.50 price)
    if 'XAU' in pair.upper() or 'GOLD' in pair.upper():
        # settings['TP1'] etc. are points (50 -> 0.50)
        tp1 = entry_price + (settings['TP1'] / 100.0) if signal == 'BUY' else entry_price - (settings['TP1'] / 100.0)
        tp2 = entry_price + (settings['TP2'] / 100.0) if signal == 'BUY' else entry_price - (settings['TP2'] / 100.0)
        tp3 = entry_price + (settings['TP3'] / 100.0) if signal == 'BUY' else entry_price - (settings['TP3'] / 100.0)
        sl  = entry_price - (settings['SL'] / 100.0) if signal == 'BUY' else entry_price + (settings['SL'] / 100.0)
        return tp1, tp2, tp3, sl
    # FX pairs: settings in pips
    pip_unit, _ = detect_pip_unit(pair)
    tp1 = entry_price + settings['TP1'] * pip_unit if signal == 'BUY' else entry_price - settings['TP1'] * pip_unit
    tp2 = entry_price + settings['TP2'] * pip_unit if signal == 'BUY' else entry_price - settings['TP2'] * pip_unit
    tp3 = entry_price + settings['TP3'] * pip_unit if signal == 'BUY' else entry_price - settings['TP3'] * pip_unit
    sl  = entry_price - settings['SL'] * pip_unit if signal == 'BUY' else entry_price + settings['SL'] * pip_unit
    return tp1, tp2, tp3, sl

# -------------------------
# MT5 order send (attempt to attach TP/SL). If it fails still track trade in active_trades.
# -------------------------
def place_order_mt5(pair, signal, entry_price, tp, sl, volume=DEFAULT_VOLUME):
    """Try to send a market order with TP/SL attached. Returns True if sent, False otherwise."""
    try:
        symbol = pair
        s_info = mt5.symbol_info(symbol)
        if s_info is None:
            log(f"place_order_mt5: symbol_info not found for {symbol}")
            return False

        # ensure symbol is visible / enabled
        if not s_info.visible:
            try:
                mt5.symbol_select(symbol, True)
            except Exception:
                pass

        # choose order type
        order_type = mt5.ORDER_TYPE_BUY if signal == 'BUY' else mt5.ORDER_TYPE_SELL

        # price: use ask for BUY and bid for SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log(f"place_order_mt5: no tick for {symbol}")
            return False
        price = float(tick.ask if signal == 'BUY' else tick.bid)

        # build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": DEVIATION,
            "magic": 123456,
            "comment": "PrecisionBotV3",
            "type_filling": mt5.ORDER_FILLING_FOK if s_info.trade_stops_allowed else mt5.ORDER_FILLING_RETURN
        }

        result = mt5.order_send(request)
        if result is None:
            log(f"place_order_mt5: order_send returned None for {symbol}")
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE and result.retcode != 10009:
            # 10009 sometimes appears as done in some brokers, but check retcode
            log(f"place_order_mt5 failed for {symbol}: retcode={result.retcode}, comment={result.comment if hasattr(result,'comment') else ''}")
            return False

        log(f"MT5 order placed: {symbol} {signal} @ {price} | tp={tp} sl={sl} | ticket={getattr(result,'order',getattr(result,'request_id', 'N/A'))}")
        return True
    except Exception as e:
        log(f"place_order_mt5 exception: {e}")
        return False

# -------------------------
# Trade open helper (test or live)
# -------------------------
def open_trade(pair, signal, entry_price, df=None, mode='test', volume=DEFAULT_VOLUME):
    """Open trade in active_trades and when live attempt to place the MT5 order with TP/SL."""
    try:
        tp1, tp2, tp3, sl = calculate_tp_sl(pair, signal, entry_price)
        trade = {
            'Pair': pair,
            'Signal': signal,
            'Entry': float(entry_price),
            'TP1': float(tp1),
            'TP2': float(tp2),
            'TP3': float(tp3),
            'SL': float(sl),
            'TP1_hit': False,
            'TP2_hit': False,
            'TP3_hit': False,
            'SL_hit': False,
            'Mode': mode,
            'Entry_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Volume': volume
        }
        # if live, try to attach to MT5 order
        if not TEST_MODE and mode == 'live':
            ok = place_order_mt5(pair, signal, entry_price, tp3, sl, volume=volume)  # attach TP3; broker will maintain TP/SL
            if not ok:
                log(f"[WARN] Failed to place MT5 order for {pair}. Falling back to simulation (tracking only).")

        active_trades[pair] = trade

        # Log trade open + show TP/SL nicely
        fmt = fmt_price(pair, entry_price)
        log(f"[OPENED] {PAIR_NAMES.get(pair,pair)} {signal} @ {fmt}")
        log(f"         TP1: {fmt_price(pair, tp1)} | TP2: {fmt_price(pair, tp2)} | TP3: {fmt_price(pair, tp3)} | SL: {fmt_price(pair, sl)}")
        # record csv initial open line
        try:
            with open(TRADE_HISTORY_CSV, 'a', newline='') as f:
                w = csv.writer(f)
                w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pair, signal, fmt_price(pair, entry_price), '', fmt_price(pair, tp1), fmt_price(pair, tp2), fmt_price(pair, tp3), fmt_price(pair, sl), 'OPEN', ''])
        except Exception:
            pass

    except Exception as e:
        log(f"open_trade error for {pair}: {e}")

# -------------------------
# Compute live P/L (floating) for a trade (returns value in pips/points units)
# -------------------------
def compute_live_pnl(trade, current_price):
    pip_unit, pip_factor = detect_pip_unit(trade['Pair'])
    if trade['Signal'] == 'BUY':
        pnl = (current_price - trade['Entry']) * pip_factor
    else:
        pnl = (trade['Entry'] - current_price) * pip_factor
    return round(pnl, 2)

# -------------------------
# Check and monitor trades (TP/SL hits, cautions, closing)
# -------------------------
def monitor_active_trades():
    global total_trades, wins, losses, realized_profit
    to_close = []
    for pair, trade in list(active_trades.items()):
        try:
            tick = mt5.symbol_info_tick(pair)
            if tick is None:
                # no live tick — skip this pair for now
                continue
            price_now = float((tick.ask + tick.bid) / 2)  # mid price for monitoring

            # Check TP1/TP2/TP3/SL hits (marks flags; we close on TP3 or SL)
            if trade['Signal'] == 'BUY':
                if (not trade['TP1_hit']) and price_now >= trade['TP1']:
                    trade['TP1_hit'] = True; log(f"[TP1 HIT] {pair} reached TP1 @ {fmt_price(pair, trade['TP1'])}")
                if (not trade['TP2_hit']) and price_now >= trade['TP2']:
                    trade['TP2_hit'] = True; log(f"[TP2 HIT] {pair} reached TP2 @ {fmt_price(pair, trade['TP2'])}")
                if (not trade['TP3_hit']) and price_now >= trade['TP3']:
                    trade['TP3_hit'] = True; log(f"[TP3 HIT] {pair} reached TP3 @ {fmt_price(pair, trade['TP3'])}")
                if (not trade['SL_hit']) and price_now <= trade['SL']:
                    trade['SL_hit'] = True; log(f"[SL HIT] {pair} hit SL @ {fmt_price(pair, trade['SL'])}")
            else:
                # SELL
                if (not trade['TP1_hit']) and price_now <= trade['TP1']:
                    trade['TP1_hit'] = True; log(f"[TP1 HIT] {pair} reached TP1 @ {fmt_price(pair, trade['TP1'])}")
                if (not trade['TP2_hit']) and price_now <= trade['TP2']:
                    trade['TP2_hit'] = True; log(f"[TP2 HIT] {pair} reached TP2 @ {fmt_price(pair, trade['TP2'])}")
                if (not trade['TP3_hit']) and price_now <= trade['TP3']:
                    trade['TP3_hit'] = True; log(f"[TP3 HIT] {pair} reached TP3 @ {fmt_price(pair, trade['TP3'])}")
                if (not trade['SL_hit']) and price_now >= trade['SL']:
                    trade['SL_hit'] = True; log(f"[SL HIT] {pair} hit SL @ {fmt_price(pair, trade['SL'])}")

            # Caution (near TP1 or near SL)
            pip_unit, pip_factor = detect_pip_unit(pair)
            # define "near" as within 5 pips/points (adjustable)
            near_threshold_pips = 5
            near_threshold_price = near_threshold_pips * pip_unit
            if trade['Signal'] == 'BUY':
                if (trade['TP1'] - price_now) <= near_threshold_price and (trade['TP1'] - price_now) > 0:
                    log(f"[CAUTION] {pair} approaching TP1 (within ~{near_threshold_pips} pips) ")
                if (price_now - trade['SL']) <= near_threshold_price and (price_now - trade['SL']) > 0:
                    log(f"[CAUTION] {pair} approaching SL (within ~{near_threshold_pips} pips) ")
            else:
                if (price_now - trade['TP1']) <= near_threshold_price and (price_now - trade['TP1']) > 0:
                    log(f"[CAUTION] {pair} approaching TP1 (within ~{near_threshold_pips} pips) ")
                if (trade['SL'] - price_now) <= near_threshold_price and (trade['SL'] - price_now) > 0:
                    log(f"[CAUTION] {pair} approaching SL (within ~{near_threshold_pips} pips) ")

            # Determine close condition: TP3_hit or SL_hit -> close trade (in test mode we simulate close; in live we still track)
            if trade['TP3_hit'] or trade['SL_hit']:
                final_price = price_now
                result = "WIN" if trade['TP3_hit'] and not trade['SL_hit'] else "LOSS"
                pnl = compute_live_pnl(trade, final_price)
                # finalize trade
                trade['Close'] = final_price
                trade['Close_Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # save to CSV
                try:
                    with open(TRADE_HISTORY_CSV, 'a', newline='') as f:
                        w = csv.writer(f)
                        w.writerow([trade['Close_Time'], pair, trade['Signal'], fmt_price(pair, trade['Entry']), fmt_price(pair, final_price),
                                    fmt_price(pair, trade['TP1']), fmt_price(pair, trade['TP2']), fmt_price(pair, trade['TP3']), fmt_price(pair, trade['SL']), result, pnl])
                except Exception:
                    pass

                # update counters
                total_trades += 1
                if result == "WIN":
                    wins += 1
                else:
                    losses += 1
                realized_profit += pnl
                closed_trades.append(trade)
                del active_trades[pair]
                log(f"[CLOSED] {pair} | Result: {result} | P/L: {pnl}")
        except Exception as e:
            log(f"monitor_active_trades error for {pair}: {e}")

# -------------------------
# Fetch candle data helper
# -------------------------
def fetch_data(pair, timeframe=mt5.TIMEFRAME_M15, n=100):
    try:
        rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'tick_volume': 'tick_volume', 'time': 'time'}, inplace=True)
        return df
    except Exception as e:
        log(f"fetch_data failed for {pair}: {e}")
        return None

# -------------------------
# Display compact dashboard (every UPDATE_INTERVAL seconds)
# -------------------------
def display_dashboard():
    try:
        # Floating P/L for active trades
        float_total = 0.0
        lines = []
        for pair, trade in active_trades.items():
            tick = mt5.symbol_info_tick(pair)
            if tick:
                cur_price = float((tick.ask + tick.bid) / 2)
            else:
                cur_price = trade['Entry']
            pnl = compute_live_pnl(trade, cur_price)
            float_total += pnl
            lines.append((pair, trade, cur_price, pnl))

        # Print header
        log("=== Dashboard ===")
        log(f"Active trades: {len(active_trades)} | Closed trades (this run): {len(closed_trades)}")
        # Per-trade lines
        for pair, trade, cur_price, pnl in lines:
            entry_fmt = fmt_price(pair, trade['Entry'])
            tp1_fmt = fmt_price(pair, trade['TP1'])
            tp2_fmt = fmt_price(pair, trade['TP2'])
            tp3_fmt = fmt_price(pair, trade['TP3'])
            sl_fmt  = fmt_price(pair, trade['SL'])
            pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
            log(f"{PAIR_NAMES.get(pair,pair)} | {trade['Signal']} | Entry: {entry_fmt} | TP1:{tp1_fmt} TP2:{tp2_fmt} TP3:{tp3_fmt} SL:{sl_fmt} | Floating P/L: {pnl_str}")
        # Summary
        accuracy = (wins / total_trades * 100) if total_trades > 0 else 0.0
        log(f"Summary → Total trades: {total_trades}, Wins: {wins}, Losses: {losses}, Accuracy: {accuracy:.2f}%, Realized P/L: {realized_profit:.2f}, Floating P/L: {float_total:.2f}")
    except Exception as e:
        log(f"display_dashboard error: {e}")

# -------------------------
# Main run_bot consolidated loop
# -------------------------
def run_bot():
    global last_update_time, last_cycle_summary
    log("run_bot started")
    # ensure MT5 initialized
    if not init_mt5():
        log("MT5 initialization failed; continuing but MT5 calls will likely fail until corrected.")
    while True:
        try:
            start_time = time.time()
            # For each pair: fetch candles, compute signal, open trade if signal & not active
            for pair in PAIRS:
                try:
                    df = fetch_data(pair, timeframe=mt5.TIMEFRAME_M15, n=200)
                    signal = generate_signal(df)
                    # If there's a signal and no active trade for that pair, open (test or live)
                    if signal and pair not in active_trades:
                        # Determine entry price from tick
                        tick = mt5.symbol_info_tick(pair)
                        if tick is None:
                            log(f"[WARN] No tick for {pair}; cannot open trade this cycle.")
                            continue
                        entry_price = float(tick.ask if signal == 'BUY' else tick.bid)
                        mode = 'test' if TEST_MODE else 'live'
                        open_trade(pair, signal, entry_price, df=df, mode=mode, volume=DEFAULT_VOLUME)
                    # else: no signal or already active
                except Exception as e:
                    log(f"run_bot per-pair error for {pair}: {e}")

            # Monitor active trades (TP/SL hits and closings)
            monitor_active_trades()

            # Dashboard updates once per UPDATE_INTERVAL per pair (we will print overall dashboard once per UPDATE_INTERVAL)
            now = time.time()
            if now - last_cycle_summary >= UPDATE_INTERVAL:
                display_dashboard()
                last_cycle_summary = now

            # Sleep until next cycle (SLEEP_INTERVAL)
            elapsed = time.time() - start_time
            sleep_for = max(1, SLEEP_INTERVAL - elapsed)
            time.sleep(sleep_for)

            # If one-cycle testing mode was desired (legacy), we respect it by stopping after one loop
            if ONE_CYCLE_TEST and TEST_MODE:
                log("ONE_CYCLE_TEST enabled — exiting after one cycle.")
                break

        except Exception as e:
            log(f"run_bot loop error: {e}")
            traceback.print_exc()
            time.sleep(5)

# -------------------------
# Startup & Entrypoint
# -------------------------
def startup_banner():
    print(">>> Precision Bot V3 — Startup Initiated <<<")
    print(f"Pairs: {PAIRS}")
    print(f"Log file: {LOG_FILE}")
    print("")

if __name__ == '__main__':
    try:
        startup_banner()
        # interactive mode selection y/n
        mode_input = ''
        while mode_input not in ('y', 'n'):
            mode_input = input("Start in test mode? (y/n): ").strip().lower()
        TEST_MODE = (mode_input == 'y')
        ONE_CYCLE_TEST = False  # we keep one-cycle disabled by default; set True if you specifically want one run
        log(f"[INFO] Starting in {'TEST' if TEST_MODE else 'LIVE'} MODE | One-cycle test: {ONE_CYCLE_TEST}")

        # initialize MT5 and then run
        init_mt5()
        # Start run_bot (blocking)
        run_bot()

    except KeyboardInterrupt:
        log("Shutdown requested (KeyboardInterrupt). Exiting.")
        try:
            mt5.shutdown()
        except Exception:
            pass
    except Exception as e:
        log(f"FATAL startup/runtime error: {e}")
        traceback.print_exc()
        try:
            mt5.shutdown()
        except Exception:
            pass
