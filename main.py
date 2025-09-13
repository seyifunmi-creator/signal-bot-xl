import MetaTrader5 as mt5
import pandas as pd
import yfinance as yf
import time
from datetime import datetime

# --- Configuration ---
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
TP_VALUES = {'FOREX': [30, 30, 30, 30], 'GOLD': [50, 50, 50, 50]}
SL_VALUES = {'FOREX': 50, 'GOLD': 70}
UPDATE_INTERVAL = 60  # seconds

# --- Global Trade Tracking ---
active_trades = []
closed_trades = []

# --- Helper Functions ---
def get_current_price(pair):
    try:
        tick = mt5.symbol_info_tick(pair)
        if tick is not None:
            return tick.bid
        return 0.0
    except Exception:
        return 0.0

def calculate_tp_sl(entry, pair_type='FOREX'):
    tp = TP_VALUES[pair_type]
    sl = SL_VALUES[pair_type]
    tps = [round(entry + t*0.0001 if pair_type != 'GOLD' else entry + t, 5) for t in tp]
    sl_val = round(entry - (sl*0.0001 if pair_type != 'GOLD' else sl), 5)
    return tps, sl_val

def check_tp_reached(trade, current_price):
    reached = []
    for idx, tp in enumerate(trade['tp']):
        if (trade['direction'] == 'BUY' and current_price >= tp) or (trade['direction'] == 'SELL' and current_price <= tp):
            reached.append(idx+1)
    return reached

def update_live_pl(trade, current_price):
    if trade['direction'] == 'BUY':
        return round((current_price - trade['entry'])*trade['lot_size']*100000, 2)
    else:
        return round((trade['entry'] - current_price)*trade['lot_size']*100000, 2)

def fmt_price(val):
    return f"{val:.5f}" if isinstance(val, float) else str(val)

def display_dashboard():
    print(f"=== Dashboard ===\nMode: TEST | Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Balance: {mt5.account_info().balance if mt5.initialize() else 0}")
    for t in active_trades:
        current_price = get_current_price(t['pair'])
        live_pl = update_live_pl(t, current_price)
        tps_reached = check_tp_reached(t, current_price)
        sl_warning = ' ⚠️' if (t['direction']=='BUY' and current_price <= t['sl']+0.0001) or (t['direction']=='SELL' and current_price >= t['sl']-0.0001) else ''
        tp_warning = ' ⚡TP3/4 may be unrealistic' if t['pair']=='XAUUSD' and max(t['tp'])-current_price>50 else ''
        t['live_pl'] = live_pl
        print(f"{t['pair']} {t['direction']} | Entry={fmt_price(t['entry'])} | Now={fmt_price(current_price)} | SL={fmt_price(t['sl'])}{sl_warning} | TP1–TP4={[fmt_price(x) for x in t['tp']]}{tp_warning} | Live P/L={live_pl} | TP reached: {tps_reached}")

# --- Main Bot Loop ---
def run_bot():
    if not mt5.initialize():
        print("[ERROR] MT5 connection failed")
        return
    print(f"[INFO] Connected to MT5 Account: {mt5.account_info().login} | Balance: {mt5.account_info().balance}")

    # Initialize dummy trades for simulation
    for pair in PAIRS:
        entry_price = get_current_price(pair)
        pair_type = 'GOLD' if pair=='XAUUSD' else 'FOREX'
        tps, sl_val = calculate_tp_sl(entry_price, pair_type)
        active_trades.append({
            'pair': pair,
            'direction': 'BUY',
            'entry': entry_price,
            'tp': tps,
            'sl': sl_val,
            'lot_size': 0.1,
            'live_pl': 0.0
        })

    while True:
        display_dashboard()
        time.sleep(UPDATE_INTERVAL)

if __name__ == '__main__':
    run_bot()
