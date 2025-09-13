import MetaTrader5 as mt5
import csv
import os
from datetime import datetime
from config import LOT_SIZE, LOG_FILE, SL_VALUES, TP_VALUES

# === Trade Handling ===

active_trades = []
closed_trades = []

def calculate_tp_sl(entry, pair, direction):
    """
    Calculate TP and SL based on config values.
    """
    pair_type = "GOLD" if pair == "XAUUSD" else "FOREX"
    tps = []
    for t in TP_VALUES[pair_type]:
        if direction == "BUY":
            tps.append(round(entry + (t * 0.0001 if pair_type == "FOREX" else t), 5))
        else:
            tps.append(round(entry - (t * 0.0001 if pair_type == "FOREX" else t), 5))

    sl_val = round(entry - (SL_VALUES[pair_type] * 0.0001 if pair_type == "FOREX" else SL_VALUES[pair_type]), 5) \
             if direction == "BUY" else \
             round(entry + (SL_VALUES[pair_type] * 0.0001 if pair_type == "FOREX" else SL_VALUES[pair_type]), 5)

    return tps, sl_val

def place_trade(pair, direction, entry):
    """
    Create a trade dictionary and store in active_trades.
    """
    tps, sl_val = calculate_tp_sl(entry, pair, direction)

    trade = {
        "pair": pair,
        "direction": direction,
        "entry": entry,
        "tp": tps,
        "sl": sl_val,
        "lot_size": LOT_SIZE,
        "open_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "close_time": None,
        "status": "OPEN",
        "pnl": 0.0
    }

    active_trades.append(trade)
    log_trade(trade, "OPEN")
    return trade

def update_trade(trade, current_price):
    """
    Check if trade hit TP/SL, update P/L, and close if needed.
    """
    if trade["direction"] == "BUY":
        pnl = (current_price - trade["entry"]) * trade["lot_size"] * 100000
    else:
        pnl = (trade["entry"] - current_price) * trade["lot_size"] * 100000

    trade["pnl"] = round(pnl, 2)

    # TP hit
    for tp in trade["tp"]:
        if (trade["direction"] == "BUY" and current_price >= tp) or \
           (trade["direction"] == "SELL" and current_price <= tp):
            trade["status"] = "CLOSED"
            trade["close_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            closed_trades.append(trade)
            active_trades.remove(trade)
            log_trade(trade, "CLOSED")
            return "TP"

    # SL hit
    if (trade["direction"] == "BUY" and current_price <= trade["sl"]) or \
       (trade["direction"] == "SELL" and current_price >= trade["sl"]):
        trade["status"] = "CLOSED"
        trade["close_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        closed_trades.append(trade)
        active_trades.remove(trade)
        log_trade(trade, "CLOSED")
        return "SL"

    return None

def log_trade(trade, action):
    """
    Log trade to CSV file.
    """
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                "Time", "Action", "Pair", "Direction", "Entry",
                "TPs", "SL", "Lot Size", "P/L", "Status"
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            action,
            trade["pair"],
            trade["direction"],
            trade["entry"],
            trade["tp"],
            trade["sl"],
            trade["lot_size"],
            trade["pnl"],
            trade["status"]
        ])
