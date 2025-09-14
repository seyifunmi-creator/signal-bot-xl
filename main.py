# main.py

import MetaTrader5 as mt5
import time
from datetime import datetime
import config
from signals import generate_signal
from trades import open_trade, update_trades, active_trades, closed_trades
from dashboard import display_dashboard

def run_bot():
    # --- Initialize MT5 ---
    if not mt5.initialize():
        print("[ERROR] MT5 connection failed")
        return
    
    print(f"Bot starting in {config.MODE} mode...")
    print(f"Trading pairs: {config.PAIRS}")
    print(f"Lot size: {config.LOT_SIZE}")
    print(f"Update interval: {config.UPDATE_INTERVAL} seconds")
    print(f"Logging trades to: {config.LOG_FILE}")

    # Ask mode (optional, override config.MODE interactively)
    choice = input("Start in live mode? (y/n): ").lower()
    mode = "LIVE" if choice == "y" else "TEST"
    print(f"[INFO] Running in {mode} mode")

    while True:
        print(f"\n[INFO] Cycle started at {datetime.now().strftime('%H:%M:%S')}")

        # --- Signal Generation ---
        for pair in config.PAIRS:
            signal = generate_signal(pair)
            print(f"[SIGNAL] {pair}: {signal}")
            if signal in ["BUY", "SELL"]:
                open_trade(pair, signal, config.LOT_SIZE, mode)

        # --- Update Trades (TP, SL, BE, partial closes) ---
        update_trades(mode)

        # --- Dashboard ---
        display_dashboard(mode)

        # Sleep until next cycle
        time.sleep(config.UPDATE_INTERVAL)

if __name__ == "__main__":
    run_bot()
