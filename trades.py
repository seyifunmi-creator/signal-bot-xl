# trades.py
import time
import MetaTrader5 as mt5
from datetime import datetime
import config

# Global trade storage
active_trades = []
closed_trades = []

def get_price(pair):
    """Fetch live price from MT5 or return 0 if fail"""
    try:
        tick = mt5.symbol_info_tick(pair)
        if tick:
            return tick.bid
    except:
        return 0.0
    return 0.0


def open_trade(pair, direction, entry, tp_list, sl, lot=None):
    """Register a new trade (TEST or LIVE)."""
    trade = {
        "pair": pair,
        "direction": direction,
        "entry": entry,
        "tp": tp_list,
        "sl": sl,
        "lot_size": lot if lot else config.LOT_SIZE,
        "status": "OPEN",
        "tp_hit": [],
        "opened": datetime.now(),
        "closed": None,
        "live_pl": 0.0
    }
    active_trades.append(trade)
    return trade


def update_trade(trade):
    """Update trade state (P/L, TP, SL, BE, partial closes)."""
    current_price = get_price(trade["pair"])
    if not current_price:
        return

    # Update live P/L
    if trade["direction"] == "BUY":
        trade["live_pl"] = round((current_price - trade["entry"]) * trade["lot_size"] * 100000, 2)
    else:
        trade["live_pl"] = round((trade["entry"] - current_price) * trade["lot_size"] * 100000, 2)

    # Check TP hits
    for idx, tp in enumerate(trade["tp"]):
        if idx+1 not in trade["tp_hit"]:
            if (trade["direction"] == "BUY" and current_price >= tp) or \
               (trade["direction"] == "SELL" and current_price <= tp):

                trade["tp_hit"].append(idx+1)

                # Partial close at TP1
                if idx+1 == 1:
                    trade["lot_size"] = trade["lot_size"] / 2  # close half
                    print(f"[TRADE] Partial close at TP1 for {trade['pair']}")

                # Move SL to BE at TP2
                if idx+1 == 2:
                    trade["sl"] = trade["entry"]
                    print(f"[TRADE] SL moved to BE at TP2 for {trade['pair']}")

    # Stop-loss check
    if (trade["direction"] == "BUY" and current_price <= trade["sl"]) or \
       (trade["direction"] == "SELL" and current_price >= trade["sl"]):
        trade["status"] = "CLOSED"
        trade["closed"] = datetime.now()
        closed_trades.append(trade)
        active_trades.remove(trade)
        print(f"[TRADE] {trade['pair']} stopped out at SL")


def update_all_trades():
    """Loop over active trades and update them"""
    for trade in active_trades[:]:  # copy so we can modify list
        update_trade(trade)
