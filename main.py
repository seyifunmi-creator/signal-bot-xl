import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# ----------------- CONFIG -----------------
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
TP_DIST = {'EURUSD': [30, 60, 90, 120],
           'GBPUSD': [30, 60, 90, 120],
           'USDJPY': [0.3, 0.6, 0.9, 1.2],
           'USDCAD': [30, 60, 90, 120],
           'XAUUSD': [50, 100, 150, 200]}
SL_DIST = {'EURUSD': 40, 'GBPUSD': 40, 'USDJPY': 0.4, 'USDCAD': 40, 'XAUUSD': 70}
UPDATE_INTERVAL = 60  # seconds

# ----------------- INITIALIZATION -----------------
mode_input = input("Start in live mode? (y/n): ").lower()
LIVE_MODE = True if mode_input == 'y' else False

if not mt5.initialize():
    print("[ERROR] MT5 initialize() failed")
    mt5.shutdown()
    exit()

account_info = mt5.account_info()
print(f"[INFO] Connected to MT5 Account: {account_info.login} | Balance: {account_info.balance}")

# ----------------- DATA STRUCTURES -----------------
trades = []

# ----------------- UTILITIES -----------------
def fmt_price(price):
    return round(price, 5 if 'USD' in PAIRS[0] else 2)

def calculate_levels(pair, entry, direction):
    tp_levels = []
    sl = entry - SL_DIST[pair] if direction == 'BUY' else entry + SL_DIST[pair]
    for dist in TP_DIST[pair]:
        tp = entry + dist if direction == 'BUY' else entry - dist
        tp_levels.append(tp)
    return sl, tp_levels

def calculate_live_pl(entry, now, direction):
    diff = now - entry
    return diff if direction == 'BUY' else -diff

def check_tp_warning(tp_levels, now, direction):
    # TP3/4 may be unrealistic if far from current price
    if direction == 'BUY' and (tp_levels[2] - now) > TP_DIST[PAIRS[0]][2]*2:
        return True
    if direction == 'SELL' and (now - tp_levels[2]) > TP_DIST[PAIRS[0]][2]*2:
        return True
    return False

# ----------------- TRADING FUNCTIONS -----------------
def open_trade(pair, direction):
    entry = mt5.symbol_info_tick(pair).ask if direction == 'BUY' else mt5.symbol_info_tick(pair).bid
    sl, tp_levels = calculate_levels(pair, entry, direction)
    trade = {'pair': pair, 'direction': direction, 'entry': entry, 'sl': sl, 'tp_levels': tp_levels, 'manual_close': False}
    trades.append(trade)
    if LIVE_MODE:
        symbol = pair
        volume = 0.1
        price = entry
        deviation = 10
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp_levels[-1],
            "deviation": deviation,
            "magic": 234000,
            "comment": "PrecisionBot"
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[ERROR] open_trade error for {pair}: {result.retcode}")

# ----------------- DASHBOARD -----------------
def display_dashboard():
    print("\n=== Dashboard ===")
    print(f"Mode: {'LIVE' if LIVE_MODE else 'TEST'} | Active trades: {len(trades)} | Balance: {mt5.account_info().balance if LIVE_MODE else 99999.97}")
    for t in trades:
        tick = mt5.symbol_info_tick(t['pair'])
        now = tick.last if tick else t['entry']
        live_pl = calculate_live_pl(t['entry'], now, t['direction'])
        sl_warning = '⚠️' if (t['direction'] == 'BUY' and now - t['sl'] < 0.0005) or (t['direction']=='SELL' and t['sl'] - now < 0.0005) else ''
        tp_warning = '⚡TP3/4 may be unrealistic' if check_tp_warning(t['tp_levels'], now, t['direction']) else ''
        tp_checks = ['✔️' if (t['direction']=='BUY' and now>=tp) or (t['direction']=='SELL' and now<=tp) else '–' for tp in t['tp_levels']]
        print(f"{t['pair']} {t['direction']} | Entry={fmt_price(t['entry'])} | Now={fmt_price(now)} | SL={fmt_price(t['sl'])} {sl_warning} | TP1–TP4={tp_checks} | Live P/L={round(live_pl, 2)} {tp_warning}")

# ----------------- MAIN LOOP -----------------
def run_bot():
    while True:
        display_dashboard()
        time.sleep(UPDATE_INTERVAL)

# ----------------- EXAMPLE INITIAL TRADES -----------------
for pair in PAIRS:
    open_trade(pair, 'BUY')  # For demo, all BUY trades

run_bot()
