import MetaTrader5 as mt5
import pandas as pd
import time
import logging
from datetime import datetime

# ===============================
# CONFIG
# ===============================
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "XAUUSD"]
LOT = 0.1
TP_LEVELS = [0.0030, 0.0060, 0.0090, 0.0120]  # Example for forex (30, 60, 90, 120 pips)
XAU_TP = [50, 100, 150, 200]  # Gold points
XAU_SL = 70
FOREX_SL = 0.0040
LOG_FILE = "trade_log.csv"

# ===============================
# LOGGING SETUP
# ===============================
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ===============================
# HELPERS
# ===============================
def fmt_price(symbol, price):
    digits = mt5.symbol_info(symbol).digits
    return round(price, digits)

def get_symbol_info(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        logging.error(f"Symbol not found: {symbol}")
    return info

def calc_targets(symbol, entry, direction):
    if symbol == "XAUUSD":
        tps = [entry + (tp if direction == "BUY" else -tp) for tp in XAU_TP]
        sl = entry - XAU_SL if direction == "BUY" else entry + XAU_SL
    else:
        tps = [entry + (tp if direction == "BUY" else -tp) for tp in TP_LEVELS]
        sl = entry - FOREX_SL if direction == "BUY" else entry + FOREX_SL
    return [fmt_price(symbol, t) for t in tps], fmt_price(symbol, sl)

# ===============================
# TRADE EXECUTION
# ===============================
def open_trade(symbol, direction, live):
    price = mt5.symbol_info_tick(symbol).ask if direction == "BUY" else mt5.symbol_info_tick(symbol).bid
    tps, sl = calc_targets(symbol, price, direction)

    if live:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": LOT,
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tps[-1],  # Hard tp = TP4
            "deviation": 20,
            "magic": 123456,
            "comment": "Precision Bot",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"OrderSend failed for {symbol}: {result.comment}")
        else:
            logging.info(f"Opened {direction} {symbol} @ {price}")
    else:
        logging.info(f"[TEST] Open {direction} {symbol} @ {price} | SL={sl} | TP1–TP4={tps}")

    return {"symbol": symbol, "direction": direction, "entry": price, "tps": tps, "sl": sl, "open_time": datetime.now()}

# ===============================
# DASHBOARD + LOG
# ===============================
def display_dashboard(open_trades, closed_trades, balance, live):
    print("\n=== Dashboard ===")
    print(f"Mode: {'LIVE' if live else 'TEST'} | Active trades: {len(open_trades)} | Closed trades: {len(closed_trades)} | Balance: {balance}")

    for t in open_trades:
        tick = mt5.symbol_info_tick(t["symbol"])
        current_price = tick.ask if t["direction"] == "BUY" else tick.bid
        pl = (current_price - t["entry"]) * (1 if t["direction"] == "BUY" else -1)

        caution = " ⚠️" if (t["direction"] == "BUY" and current_price <= t["sl"] * 1.001) or \
                           (t["direction"] == "SELL" and current_price >= t["sl"] * 0.999) else ""

        tp_warning = ""
        if abs(t["tps"][2] - current_price) > abs(t["entry"] * 0.02):  # TP3 too far
            tp_warning = " ⚡TP3/4 may be unrealistic"

        print(f"{t['symbol']} {t['direction']} | Entry={t['entry']} | Now={current_price} | SL={t['sl']}{caution} | TP1–TP4={t['tps']} | Live P/L={pl:.2f}{tp_warning}")

def log_trade(trade, status):
    df = pd.DataFrame([{
        "Time": datetime.now(),
        "Symbol": trade["symbol"],
        "Direction": trade["direction"],
        "Entry": trade["entry"],
        "TPs": trade["tps"],
        "SL": trade["sl"],
        "Status": status
    }])
    df.to_csv(LOG_FILE, mode="a", header=not pd.io.common.file_exists(LOG_FILE), index=False)

# ===============================
# MAIN LOOP
# ===============================
def run_bot(live=False):
    if not mt5.initialize():
        print("[ERROR] MT5 initialize failed")
        return

    account_info = mt5.account_info()
    balance = account_info.balance if account_info else 100000

    open_trades = []
    closed_trades = []

    while True:
        for pair in PAIRS:
            direction = "BUY"  # <== strategy signal placeholder
            trade = open_trade(pair, direction, live)
            open_trades.append(trade)
            log_trade(trade, "OPEN")

        display_dashboard(open_trades, closed_trades, balance, live)
        time.sleep(10)  # refresh

if __name__ == "__main__":
    mode = input("Start in live mode? (y/n): ").lower()
    live = True if mode == "y" else False
    run_bot(live)
