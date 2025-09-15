# trades.py

import MetaTrader5 as mt5
from datetime import datetime
import config
from signals import generate_signal

# --- Global trade list ---
trades = []

# --- Create a new trade ---
def create_trade(pair, direction, lot_size):
    tick = mt5.symbol_info_tick(pair)
    if not tick:
        return None

    entry = tick.bid if direction == "BUY" else tick.ask
    pair_type = "GOLD" if pair == "XAUUSD" else "FOREX"
    tp_levels = [round(entry + (tp*0.0001 if pair_type == "FOREX" else tp), 5) for tp in config.TP_VALUES[pair_type]]
    sl_val = round(entry - (config.SL_VALUES[pair_type]*0.0001 if pair_type == "FOREX" else config.SL_VALUES[pair_type]), 5)

    trade = {
        "pair": pair,
        "direction": direction,
        "entry": entry,
        "lot_size": lot_size,
        "tp_levels": tp_levels,
        "sl": sl_val,
        "status": "OPEN",  # OPEN, BE, PARTIAL, CLOSED
        "profit": 0.0,
        "current_price": entry,
        "current_tp": 0,
        "opened_at": datetime.now(),
        "closed_at": None
    }
    trades.append(trade)
    return trade

# --- Update all open trades ---
def update_trades(trade_list):
    updated_trades = []
    for trade in trade_list:
        tick = mt5.symbol_info_tick(trade["pair"])
        if not tick:
            updated_trades.append(trade)
            continue

        price = tick.bid if trade["direction"] == "BUY" else tick.ask
        trade["current_price"] = price

        # --- Profit calculation ---
        if trade["direction"] == "BUY":
            trade["profit"] = (price - trade["entry"]) * trade["lot_size"] * 100000
        else:
            trade["profit"] = (trade["entry"] - price) * trade["lot_size"] * 100000

        # --- Check TP / partial close / BE ---
        for idx, tp in enumerate(trade["tp_levels"]):
            if trade["direction"] == "BUY" and price >= tp:
                if idx + 1 > trade["current_tp"]:
                    trade["current_tp"] = idx + 1
                    if trade["current_tp"] >= 2 and trade["status"] == "OPEN":
                        trade["status"] = "BE"
            elif trade["direction"] == "SELL" and price <= tp:
                if idx + 1 > trade["current_tp"]:
                    trade["current_tp"] = idx + 1
                    if trade["current_tp"] >= 2 and trade["status"] == "OPEN":
                        trade["status"] = "BE"

        # --- Check SL hit ---
        if trade["direction"] == "BUY" and price <= trade["sl"]:
            trade["status"] = "CLOSED"
            trade["closed_at"] = datetime.now()
        elif trade["direction"] == "SELL" and price >= trade["sl"]:
            trade["status"] = "CLOSED"
            trade["closed_at"] = datetime.now()

        updated_trades.append(trade)

    return updated_trades
