import time
import MetaTrader5 as mt5
import config
from signals import generate_signal
from trades import place_trade, update_trade, active_trades
from dashboard import display_dashboard
from datetime import datetime

def run_bot():
    # === Print config settings at startup ===
    print(f"Bot starting in {config.MODE} mode...")
    print(f"Trading pairs: {config.PAIRS}")
    print(f"Lot size: {config.LOT_SIZE}")
    print(f"Update interval: {config.UPDATE_INTERVAL} seconds")
    print(f"Logging trades to: {config.LOG_FILE}")

    # Ask user if they want LIVE mode
    choice = input("Start in live mode? (y/n): ").strip().lower()
    mode = "LIVE" if choice == "y" else config.MODE
    print(f"[INFO] Running in {mode} mode")

    # Initialize MT5 only for LIVE mode
    if mode == "LIVE":
        if not mt5.initialize():
            print("[ERROR] MT5 connection failed")
            return
        account_info = mt5.account_info()
        print(f"[INFO] Connected to MT5 Account: {account_info.login} | Balance: {account_info.balance}")

    # --- Main Bot Loop ---
    while True:
        print(f"\n[INFO] Cycle started at {datetime.now().strftime('%H:%M:%S')}")

        for pair in config.PAIRS:
            # 1. Generate signal using MT5 prices
            signal = generate_signal(pair)
            print(f"[SIGNAL] {pair}: {signal}")

            # 2. Place trade if BUY/SELL signal and no active trade exists
            if signal in ["BUY", "SELL"]:
                if not any(t["pair"] == pair and t["status"] == "OPEN" for t in active_trades):
                    entry_price = mt5.symbol_info_tick(pair).bid if mode == "LIVE" else 1.00000
                    place_trade(pair, signal, entry_price)

        # 3. Update all active trades
        for trade in active_trades[:]:  # copy to avoid modification issues
            current_price = mt5.symbol_info_tick(trade["pair"]).bid if mode == "LIVE" else trade["entry"]
            update_trade(trade, current_price)

        # 4. Display dashboard
        display_dashboard()

        time.sleep(config.UPDATE_INTERVAL)

if __name__ == "__main__":
    run_bot()
