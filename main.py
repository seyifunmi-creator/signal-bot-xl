# main.py imports
import time
import config
import MetaTrader5 as mt5
from trades import create_trade, update_trades
from signals import generate_signal
from dashboard import show_dashboard
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)


def initialize_mt5():
    """Initialize MT5 connection using config credentials"""
    if not mt5.initialize(
        login=config.MT5_LOGIN,
        password=config.MT5_PASSWORD,
        server=config.MT5_SERVER
    ):
        print("[ERROR] MT5 initialization failed")
        print(mt5.last_error())
        return False
    print("[INFO] Connected to MT5 successfully")
    return True


def run_bot():
    # --- Initialize MT5 ---
    if not initialize_mt5():
        return  # Stop if MT5 connection failed

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

        # Collect latest snapshot for dashboard
        dashboard_snapshot = []

        # Generate signals for all pairs
        for pair in config.PAIRS:
            # --- Get signal and EMA/RSI for debug ---
            signal, ema_fast, ema_slow, rsi_val = generate_signal(pair, return_values=True)

            # Always print placeholder signal first
            print(f"[SIGNAL] {pair}: {signal}")

            # Color output
            if config.COLOR_OUTPUT:
                if signal == "BUY":
                    print(Fore.GREEN + f"[SIGNAL] {pair}: {signal}" + Style.RESET_ALL)
                elif signal == "SELL":
                    print(Fore.RED + f"[SIGNAL] {pair}: {signal}" + Style.RESET_ALL)
                elif signal is None:
                    # Print debug for None signals
                    print(
                        Fore.YELLOW
                        + f"[DEBUG] {pair} | EMA_FAST={ema_fast:.4f} EMA_SLOW={ema_slow:.4f} RSI={rsi_val:.2f} → No trade"
                        + Style.RESET_ALL
                    )

            # --- Execute trade if signal is valid ---
            if signal in ["BUY", "SELL"]:
                trade = create_trade(pair, signal, config.LOT_SIZE)
                trades.append(trade)

            # Add snapshot for dashboard (always include EMA/RSI)
            dashboard_snapshot.append({
                "pair": pair,
                "signal": signal,
                "ema_fast": round(ema_fast, 4),
                "ema_slow": round(ema_slow, 4),
                "rsi": round(rsi_val, 2),
            })

        # Update all open trades (SL/TP/BE/partial closes)
        trades = update_trades(trades)

        # Show dashboard (now with safe snapshot, no `t` error)
        show_dashboard(trades, dashboard_snapshot)

        time.sleep(config.UPDATE_INTERVAL)


if __name__ == "__main__":
    try:
        run_bot()
    finally:
        mt5.shutdown()
