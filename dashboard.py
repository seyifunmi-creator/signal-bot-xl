from colorama import Fore, Style, init
from trades import active_trades, closed_trades
from config import MODE

init(autoreset=True)

def fmt_price(val):
    return f"{val:.5f}" if isinstance(val, float) else str(val)

def display_dashboard():
    print(Fore.CYAN + "\n=== DASHBOARD ===")
    print(f"Mode: {Fore.YELLOW}{MODE}{Style.RESET_ALL} | "
          f"Active trades: {len(active_trades)} | "
          f"Closed trades: {len(closed_trades)}")

    if not active_trades:
        print(Fore.LIGHTBLACK_EX + "No active trades.")
        return

    for t in active_trades:
        color = Fore.GREEN if t["direction"] == "BUY" else Fore.RED
        print(color + f"{t['pair']} {t['direction']} | "
              f"Entry={fmt_price(t['entry'])} | "
              f"SL={fmt_price(t['sl'])} | "
              f"TPs={[fmt_price(x) for x in t['tp']]} | "
              f"Live P/L={t['pnl']} | Status={t['status']}")
