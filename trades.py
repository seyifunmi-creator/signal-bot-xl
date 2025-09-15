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

    # ✅ Determine pair type safely
    if pair.upper() == "XAUUSD":
        pair_type = "GOLD"
    else:
        pair_type = "FOREX"

    # ✅ Pull TP/SL settings for this type
    tp_values = config.TP_VALUES.get(pair_type, [])
    sl_value = config.SL_VALUES.get(pair_type, 0)

    # ✅ Build TP levels & SL
    if pair_type == "FOREX":
        tp_levels = [round(entry + (tp * 0.0001 if direction == "BUY" else -tp * 0.0001), 5) for tp in tp_values]
        sl_val = round(entry - (sl_value * 0.0001) if direction == "BUY" else entry + (sl_value * 0.0001), 5)
    else:  # GOLD
        tp_levels = [round(entry + (tp if direction == "BUY" else -tp), 2) for tp in tp_values]
        sl_val = round(entry - sl_value if direction == "BUY" else entry + sl_value, 2)

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
