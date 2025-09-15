# trades.py

import time
import config
from signals import generate_signal
from dashboard import show_dashboard
from datetime import datetime

# --- Global trade list ---
trades = []

def open_trade(pair, direction, entry, lot_size, tp_levels, sl):
    trade = {
        'pair': pair,
        'direction': direction,
        'entry': entry,
        'lot_size': lot_size,
        'tp_levels': tp_levels,
        'sl': sl,
        'status': 'OPEN',  # OPEN, PARTIAL, BE, CLOSED
        'profit': 0.0,
        'current_price': entry,
        'current_tp': 0,
        'opened_at': datetime.now(),
        'closed_at': None
    }
    trades.append(trade)
    return trade

def update_trade(trade, price):
    trade['current_price'] = price

    # --- Profit calculation ---
    if trade['direction'] == 'BUY':
        trade['profit'] = (price - trade['entry']) * trade['lot_size'] * 100000
    else:
        trade['profit'] = (trade['entry'] - price) * trade['lot_size'] * 100000

    # --- Check TP / partial close / BE ---
    for idx, tp in enumerate(trade['tp_levels']):
        if trade['direction'] == 'BUY' and price >= tp:
            if idx + 1 > trade['current_tp']:
                trade['current_tp'] = idx + 1
                # BE after TP2
                if trade['current_tp'] >= 2 and trade['status'] == 'OPEN':
                    trade['status'] = 'BE'
        elif trade['direction'] == 'SELL' and price <= tp:
            if idx + 1 > trade['current_tp']:
                trade['current_tp'] = idx + 1
                if trade['current_tp'] >= 2 and trade['status'] == 'OPEN':
                    trade['status'] = 'BE'

    # --- Check SL hit ---
    if trade['direction'] == 'BUY' and price <= trade['sl']:
        trade['status'] = 'CLOSED'
        trade['closed_at'] = datetime.now()
    elif trade['direction'] == 'SELL' and price >= trade['sl']:
        trade['status'] = 'CLOSED'
        trade['closed_at'] = datetime.now()

def run_trade_cycle():
    """
    Call this in main loop: checks signals, opens/updates trades, refreshes dashboard
    """
    for pair in config.PAIRS:
        signal = generate_signal(pair)

        # Open new trade if no open trade exists for this pair
        open_trades = [t for t in trades if t['pair'] == pair and t['status'] in ['OPEN', 'PARTIAL', 'BE']]
        if signal and not open_trades:
            # Fetch current price
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(pair)
            entry = tick.bid if signal == 'BUY' else tick.ask
            tp_levels = [round(entry + (tp*0.0001 if pair != 'XAUUSD' else tp), 5) for tp in config.TP_VALUES['FOREX' if pair != 'XAUUSD' else 'GOLD']]
            sl_val = round(entry - (config.SL_VALUES['FOREX' if pair != 'XAUUSD' else 'GOLD']*0.0001 if pair != 'XAUUSD' else config.SL_VALUES['GOLD']), 5)
            open_trade(pair, signal, entry, config.LOT_SIZE, tp_levels, sl_val)

    # Update all open trades
    for trade in [t for t in trades if t['status'] in ['OPEN', 'BE', 'PARTIAL']]:
        tick = mt5.symbol_info_tick(trade['pair'])
        price = tick.bid if trade['direction']=='BUY' else tick.ask
        update_trade(trade, price)

    # Show dashboard
    show_dashboard(trades)
