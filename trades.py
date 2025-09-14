# trades.py

import time

def create_trade(pair, direction, entry, tp_levels, sl, lot_size=0.1):
    """Create a new trade dictionary."""
    return {
        'pair': pair,
        'direction': direction,
        'entry': entry,
        'tp': tp_levels,          # list of 4 TP levels
        'sl': sl,
        'lot_size': lot_size,
        'live_pl': 0.0,
        'tp_hit': [False, False, False, False],
        'status': "ACTIVE",
        'opened_at': time.strftime("%Y-%m-%d %H:%M:%S")
    }


def update_trades(active_trades, current_prices):
    """Update all active trades with current prices, BE + partial closes."""
    closed_trades = []

    for trade in active_trades[:]:  # copy since we may remove trades
        pair = trade['pair']
        price = current_prices.get(pair, None)
        if price is None:
            continue

        direction = trade['direction']
        entry = trade['entry']
        sl = trade['sl']
        tp_levels = trade['tp']
        lot = trade['lot_size']

        # --- Update Live P/L ---
        if direction == "BUY":
            trade['live_pl'] = round((price - entry) * lot * 100000, 2)
        else:
            trade['live_pl'] = round((entry - price) * lot * 100000, 2)

        # --- Check TP hits ---
        hit_tps = []
        for i, tp in enumerate(tp_levels):
            if direction == "BUY" and price >= tp and not trade['tp_hit'][i]:
                trade['tp_hit'][i] = True
                hit_tps.append(i+1)
            elif direction == "SELL" and price <= tp and not trade['tp_hit'][i]:
                trade['tp_hit'][i] = True
                hit_tps.append(i+1)

        # --- Partial close + BE logic ---
        if 1 in hit_tps:  # TP1 hit → partial close
            trade['lot_size'] = round(lot / 2, 2) if lot > 0.01 else lot
            trade['status'] = "PARTIAL"

        if 2 in hit_tps:  # TP2 hit → move SL to BE
            trade['sl'] = entry
            trade['status'] = "BE ACTIVE"

        # --- Close at SL or TP4 ---
        if (direction == "BUY" and price <= trade['sl']) or \
           (direction == "SELL" and price >= trade['sl']):
            trade['status'] = "STOPPED"
            closed_trades.append(trade)
            active_trades.remove(trade)

        elif trade['tp_hit'][3]:  # TP4 hit → close trade fully
            trade['status'] = "TP4 HIT"
            closed_trades.append(trade)
            active_trades.remove(trade)

    return closed_trades
