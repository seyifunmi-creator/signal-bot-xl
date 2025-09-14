import time

# ======================
# Trade Management Module
# ======================

def create_trade(pair, direction, entry, tp_levels, sl, lot_size=0.1):
    """Create a new trade dictionary"""
    return {
        "pair": pair,
        "direction": direction,   # "BUY" or "SELL"
        "entry": entry,
        "tp_levels": tp_levels,   # [TP1, TP2, TP3]
        "sl": sl,
        "lot_size": lot_size,
        "status": "OPEN",         # OPEN / CLOSED / BE
        "current_tp": 0,          # which TP is active
        "profit": 0.0,
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "closed_at": None
    }

# Backward compatibility (for main.py that still calls open_trade)
def open_trade(pair, direction, entry, tp_levels, sl, lot_size=0.1):
    """Alias for backward compatibility"""
    return create_trade(pair, direction, entry, tp_levels, sl, lot_size)


def update_trades(trades, price_data):
    """Update open trades with live prices"""
    for trade in trades:
        if trade["status"] != "OPEN":
            continue

        pair = trade["pair"]
        current_price = price_data.get(pair)
        if current_price is None:
            continue

        # Calculate floating P/L
        if trade["direction"] == "BUY":
            trade["profit"] = (current_price - trade["entry"]) * trade["lot_size"] * 100000
        else:  # SELL
            trade["profit"] = (trade["entry"] - current_price) * trade["lot_size"] * 100000

        # Check SL
        if trade["direction"] == "BUY" and current_price <= trade["sl"]:
            trade["status"] = "CLOSED"
            trade["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        elif trade["direction"] == "SELL" and current_price >= trade["sl"]:
            trade["status"] = "CLOSED"
            trade["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Check TP levels
        elif trade["current_tp"] < len(trade["tp_levels"]):
            target = trade["tp_levels"][trade["current_tp"]]
            if trade["direction"] == "BUY" and current_price >= target:
                trade["current_tp"] += 1
                if trade["current_tp"] == 2:  # BE after TP2
                    trade["sl"] = trade["entry"]
                if trade["current_tp"] >= len(trade["tp_levels"]):
                    trade["status"] = "CLOSED"
                    trade["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            elif trade["direction"] == "SELL" and current_price <= target:
                trade["current_tp"] += 1
                if trade["current_tp"] == 2:  # BE after TP2
                    trade["sl"] = trade["entry"]
                if trade["current_tp"] >= len(trade["tp_levels"]):
                    trade["status"] = "CLOSED"
                    trade["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    return trades
