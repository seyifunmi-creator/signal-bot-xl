import MetaTrader5 as mt5
import time
from config import PAIRS, UPDATE_INTERVAL, MODE
from signals import generate_signal
from trades import place_trade, update_trade, active_trades
from dashboard import display_dashboard
from datetime import datetime

# === Bot Runner ===
def run_bot():
    # Ask user if they want LIVE mode
    mode = MODE
    choice = input("Start in live mode? (y/n): ").strip().lower()
    if choice == "y":
        mode = "LIVE"
    else:
        mode = "TEST"

    print(f"[INFO] Running in {mode} mode")

    # Try connecting MT5 (only relevant for LIVE mode)
    if mode == "LIVE":
        if not mt5.initialize():
            print("[ERROR] MT5 connection failed")
            return
        print(f"[INFO] Connected to MT5 Account: {mt5.account_info().login} | Balance: {mt5.account_info().balance}")

    while True:
        print(f"\n[INFO] Cycle started at {datetime.now().strftime('%H:%M:%S')}")
        
        for pair in PAIRS:
            # 1. Generate signal
            signal = generate_signal(pair)
            print(f"[SIGNAL] {pair}: {signal}")

            # 2. Place trade if BUY/SELL signal
            if signal in ["BUY", "SELL"]:
                if not any(t["pair"] == pair and t["status"] == "OPEN" for t in active_trades):
                    entry_price = mt5.symbol_info_tick(pair).bid if mode == "LIVE" else 1.00000
                    place_trade(pair, signal, entry_price)

        # 3. Update active trades
        for trade in active_trades[:]:  # copy to avoid modification issues
            current_price = mt5.symbol_info_tick(trade["pair"]).bid if mode == "LIVE" else trade["entry"]
            update_trade(trade, current_price)

        # 4. Show dashboard
        display_dashboard()

        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    run_bot()
