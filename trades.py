# trades.py

import MetaTrader5 as mt5
import config
import time
import csv

# Store open trades in memory (for TEST mode)
open_trades = []

def open_trade(pair, direction, entry_price):
    """Open a trade in TEST or LIVE mode"""

    sl = entry_price - config.SL_VALUES['FOREX'] * 0.0001 if direction == "BUY" else entry_price + config.SL_VALUES['FOREX'] * 0.0001
    tp1 = entry_price + config.TP_VALUES['FOREX'][0] * 0.0001 if direction == "BUY" else entry_price - config.TP_VALUES['FOREX'][0] * 0.0001
    tp2 = entry_price + config.TP_VALUES['FOREX'][1] * 0.0001 if direction == "BUY" else entry_price - config.TP_VALUES['FOREX'][1] * 0.0001
    tp3 = entry_price + config.TP_VALUES['FOREX'][2] * 0.0001 if direction == "BUY" else entry_price - config.TP_VALUES['FOREX'][2] * 0.0001

    trade = {
        "pair": pair,
        "direction": direction,
        "entry": entry_price,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "lot": config.LOT_SIZE,
        "status": "OPEN",
        "partial_closed": False,
        "moved_to_be": False
    }

    if config.MODE == "TEST":
        open_trades.append(trade)
        print(f"[TEST TRADE OPENED] {pair} {direction} @ {entry_price:.5f} | SL: {sl:.5f} | TP1: {tp1:.5f} | TP2: {tp2:.5f} | TP3: {tp3:.5f}")
    else:
        # LIVE MODE (real MT5 order)
        order_type = mt5.ORDER_BUY if direction == "BUY" else mt5.ORDER_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pair,
            "volume": config.LOT_SIZE,
            "type": order_type,
            "price": entry_price,
            "sl": sl,
            "tp": tp1,  # Start with TP1
            "deviation": 20,
            "magic": 123456,
            "comment": "Bot Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        print(f"[LIVE TRADE OPENED] {result}")

def update_trades(current_prices):
    """Check open trades and apply TP/SL logic"""
    for trade in open_trades:
        if trade["status"] != "OPEN":
            continue

        price = current_prices.get(trade["pair"])
        if price is None:
            continue

        # Stop Loss hit
        if (trade["direction"] == "BUY" and price <= trade["sl"]) or \
           (trade["direction"] == "SELL" and price >= trade["sl"]):
            trade["status"] = "CLOSED_SL"
            print(f"[STOP LOSS] {trade['pair']} closed at {price:.5f}")
            continue

        # TP1 partial close
        if not trade["partial_closed"]:
            if (trade["direction"] == "BUY" and price >= trade["tp1"]) or \
               (trade["direction"] == "SELL" and price <= trade["tp1"]):
                trade["partial_closed"] = True
                print(f"[TP1 HIT] {trade['pair']} - Partial close at {price:.5f}")

        # TP2 → move SL to break-even
        if not trade["moved_to_be"]:
            if (trade["direction"] == "BUY" and price >= trade["tp2"]) or \
               (trade["direction"] == "SELL" and price <= trade["tp2"]):
                trade["sl"] = trade["entry"]  # BE
                trade["moved_to_be"] = True
                print(f"[TP2 HIT] {trade['pair']} - SL moved to BE")

        # TP3 → full close
        if (trade["direction"] == "BUY" and price >= trade["tp3"]) or \
           (trade["direction"] == "SELL" and price <= trade["tp3"]):
            trade["status"] = "CLOSED_TP3"
            print(f"[TP3 HIT] {trade['pair']} closed at {price:.5f}")
