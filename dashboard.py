# dashboard.py

import config
from trades import open_trades
from colorama import Fore, Style

def show_dashboard(current_prices):
    print("\n=== DASHBOARD ===")
    print(f"Mode: {config.MODE}")

    active = [t for t in open_trades if t["status"] == "OPEN"]
    closed = [t for t in open_trades if t["status"] != "OPEN"]

    print(f"Active trades: {len(active)} | Closed trades: {len(closed)}")

    for trade in open_trades:
        pair = trade["pair"]
        status = trade["status"]
        price = current_prices.get(pair, None)

        # Floating P/L for TEST mode
        if config.MODE == "TEST" and price:
            if trade["direction"] == "BUY":
                pnl = (price - trade["entry"]) * 10000 * trade["lot"]
            else:
                pnl = (trade["entry"] - price) * 10000 * trade["lot"]
        else:
            pnl = 0

        # Status coloring
        if status == "OPEN":
            status_str = Fore.YELLOW + "OPEN" + Style.RESET_ALL
        elif status == "CLOSED_TP3":
            status_str = Fore.GREEN + "TP3 CLOSED" + Style.RESET_ALL
        elif status == "CLOSED_SL":
            status_str = Fore.RED + "STOP LOSS" + Style.RESET_ALL
        else:
            status_str = Fore.CYAN + status + Style.RESET_ALL

        print(f"{pair} | {trade['direction']} | {status_str} | Entry: {trade['entry']:.5f} | SL: {trade['sl']:.5f} | TP1: {trade['tp1']:.5f} | TP2: {trade['tp2']:.5f} | TP3: {trade['tp3']:.5f} | P/L: {pnl:.2f}")
