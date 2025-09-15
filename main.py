# === main.py ===

# main.py imports
import time
import config
from trades import create_trade, update_trades
from signals import generate_signal
from dashboard import show_dashboard


def run_bot():
    print(f"Bot starting in {config.MODE} mode...")
    print(f"Trading pairs: {config.PAIRS}")
    print(f"Lot size: {config.LOT_SIZE}")
    print(f"Update interval: {config.UPDATE_INTERVAL} seconds")
    print(f"Logging trades to: {config.LOG_FILE}")

    mode_input = input("Start in live mode? (y/n): ").strip().lower()
    if mode_input == "y":
        config.MODE = "LIVE"
        print("[INFO] Running in LIVE mode")
    else:
        config.MODE = "TEST"
        print("[INFO] Running in TEST mode")

    trades = []

    while True:
        print(f"\n[INFO] Cycle started at {time.strftime('%H:%M:%S')}")

        # Generate signals for all pairs
        for pair in config.PAIRS:
            signal = generate_signal(pair)
            print(f"[SIGNAL] {pair}: {signal}")

            if signal in ["BUY", "SELL"]:
                trade = create_trade(pair, signal, config.LOT_SIZE)
                trades.append(trade)

        # Update all open trades (SL/TP/BE/partial closes)
        trades = update_trades(trades)

        # Show dashboard
        show_dashboard(trades)

        time.sleep(config.UPDATE_INTERVAL)


if __name__ == "__main__":
    run_bot()
