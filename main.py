import MetaTrader5 as mt5
import pandas as pd
import time
import os
from datetime import datetime

# === CONFIG ===
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "XAUUSD"]
LOT = 0.1
MAGIC = 123456
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# === HELPERS ===
def fmt_price(symbol, price):
    digits = mt5.symbol_info(symbol).digits
    return round(price, digits)

def log_trade(row):
    log_file = os.path.join(LOG_DIR, f"{datetime.now().date()}.csv")
    df = pd.DataFrame([row])
    if not os.path.exists(log_file):
        df.to_csv(log_file, index=False, mode="w")
    else:
        df.to_csv(log_file, index=False, mode="a", header=False)

    # TXT log too
    txt_file = os.path.join(LOG_DIR, f"{datetime.now().date()}.txt")
    with open(txt_file, "a") as f:
        f.write(str(row) + "\n")

def calc_tp_sl(symbol, entry, direction):
    if symbol == "XAUUSD":
        tp_step = 50
        sl_step = 70
    else:
        tp_step = 40
        sl_step = 50

    if direction == "BUY":
        return [entry + tp_step, entry + tp_step*2, entry + tp_step*3, entry + tp_step*4], entry - sl_step
    else:
        return [entry - tp_step, entry - tp_step*2, entry - tp_step*3, entry - tp_step*4], entry + sl_step

def open_trade(symbol, direction):
    price = mt5.symbol_info_tick(symbol).ask if direction == "BUY" else mt5.symbol_info_tick(symbol).bid
    price = fmt_price(symbol, price)
    tps, sl = calc_tp_sl(symbol, price, direction)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": fmt_price(symbol, sl),
        "tp": fmt_price(symbol, tps[-1]),  # Final TP only, others tracked manually
        "magic": MAGIC,
        "comment": "Precision Bot V3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[ERROR] open_trade error for {symbol}: {result.comment}")
        return None

    print(f"[TRADE OPENED] {symbol} {direction} @ {price}")
    trade = {
        "symbol": symbol, "direction": direction, "entry": price,
        "tp1": tps[0], "tp2": tps[1], "tp3": tps[2], "tp4": tps[3],
        "sl": sl, "opened": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "OPEN"
    }
    return trade

def check_trade(trade):
    price = mt5.symbol_info_tick(trade["symbol"]).bid if trade["direction"] == "SELL" else mt5.symbol_info_tick(trade["symbol"]).ask
    price = fmt_price(trade["symbol"], price)

    # Warnings
    if abs(trade["tp3"] - trade["entry"]) > abs(trade["entry"]*0.01):  # unrealistic tp3
        print(f"[⚡ ALERT] {trade['symbol']} TP3 looks unrealistic!")
    if abs(trade["tp4"] - trade["entry"]) > abs(trade["entry"]*0.015):  # unrealistic tp4
        print(f"[⚡ ALERT] {trade['symbol']} TP4 looks unrealistic!")

    if trade["direction"] == "BUY":
        if price >= trade["tp1"]: return "TP1"
        if price >= trade["tp2"]: return "TP2"
        if price >= trade["tp3"]: return "TP3"
        if price >= trade["tp4"]: return "TP4"
        if price <= trade["sl"]: return "SL"
    else:
        if price <= trade["tp1"]: return "TP1"
        if price <= trade["tp2"]: return "TP2"
        if price <= trade["tp3"]: return "TP3"
        if price <= trade["tp4"]: return "TP4"
        if price >= trade["sl"]: return "SL"
    return None

def close_trade(trade, reason):
    price = mt5.symbol_info_tick(trade["symbol"]).bid if trade["direction"] == "BUY" else mt5.symbol_info_tick(trade["symbol"]).ask
    price = fmt_price(trade["symbol"], price)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": trade["symbol"],
        "volume": LOT,
        "type": mt5.ORDER_TYPE_SELL if trade["direction"] == "BUY" else mt5.ORDER_TYPE_BUY,
        "position": mt5.positions_get(symbol=trade["symbol"])[0].ticket if mt5.positions_get(symbol=trade["symbol"]) else 0,
        "price": price,
        "magic": MAGIC,
        "comment": f"Closed by bot ({reason})",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    trade["status"] = "CLOSED"
    trade["closed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade["exit"] = price
    trade["reason"] = reason
    log_trade(trade)

    print(f"[TRADE CLOSED] {trade['symbol']} {trade['direction']} closed at {price} | Reason: {reason}")

# === MAIN BOT ===
def run_bot(mode="TEST"):
    trades = []
    balance = mt5.account_info().balance if mode == "LIVE" else 100000.0
    print(f"[INFO] Starting in {mode} MODE")

    while True:
        for symbol in PAIRS:
            # Only open if no active trade
            active = [t for t in trades if t["symbol"] == symbol and t["status"] == "OPEN"]
            if not active:
                trade = open_trade(symbol, "BUY")  # just for testing, replace with your signal logic
                if trade: trades.append(trade)

        # Update active trades
        for trade in trades:
            if trade["status"] == "OPEN":
                result = check_trade(trade)
                if result:
                    close_trade(trade, result)

        # Dashboard (every 60s)
        print("=== Dashboard ===")
        active = [t for t in trades if t["status"] == "OPEN"]
        closed = [t for t in trades if t["status"] == "CLOSED"]
        print(f"Active trades: {len(active)} | Closed trades: {len(closed)} | Balance: {balance}")
        time.sleep(60)

# === STARTUP ===
if __name__ == "__main__":
    if not mt5.initialize():
        print("[ERROR] Failed to initialize MT5")
        quit()

    mode = input("Start in live mode? (y/n): ").strip().lower()
    if mode == "y":
        run_bot("LIVE")
    else:
        run_bot("TEST")
