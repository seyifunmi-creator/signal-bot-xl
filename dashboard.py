# dashboard.py
import config
import MetaTrader5 as mt5
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def show_dashboard(trades, snapshot):
    """
    Full dashboard:
    - Stats
    - Signals with EMA/RSI (even for None)
    - Trade table
    - TP levels
    """
    # --- Account balance ---
    balance = 100000  # default for TEST
    if config.MODE == "LIVE":
        account = mt5.account_info()
        if account:
            balance = account.balance

    # Header
    print("\n=== DASHBOARD ===")
    active = len([t for t in trades if t['status'] == "OPEN"])
    closed = len([t for t in trades if t['status'] == "CLOSED"])

    print(f"Mode: {config.MODE} | Active trades: {active} | Closed trades: {closed} | Balance: {balance:.2f}")

    # --- Signals Section ---
    print("\nSignals:")
    for entry in snapshot:
        pair = entry["pair"]
        signal = entry["signal"]
        ema_fast = entry["ema_fast"]
        ema_slow = entry["ema_slow"]
        rsi = entry["rsi"]

        if signal == "BUY":
            sig_str = Fore.GREEN + f"{pair}: {signal}" + Style.RESET_ALL
        elif signal == "SELL":
            sig_str = Fore.RED + f"{pair}: {signal}" + Style.RESET_ALL
        else:
            sig_str = Fore.YELLOW + f"{pair}: None" + Style.RESET_ALL

        print(f"{sig_str} | EMA_FAST={ema_fast:.5f} EMA_SLOW={ema_slow:.5f} RSI={rsi:.2f}")

    # --- Trades Section ---
    print("\nPAIR     DIR   ENTRY      NOW        SL       P/L      TP HIT   STATUS")
    print("-"*70)

    for t in trades:
        pair = t['pair']
        direction = t['direction']
        entry = t['entry']
        now = t['now']
        sl = t['sl']
        pl = t['live_pl']
        tp_hit = ','.join(map(str, t['tp_hit'])) if t['tp_hit'] else "-"
        status = t['status']

        # Color coding for PL
        if pl > 0:
            pl_colored = Fore.GREEN + f"{pl:.2f}" + Style.RESET_ALL
        elif pl < 0:
            pl_colored = Fore.RED + f"{pl:.2f}" + Style.RESET_ALL
        else:
            pl_colored = f"{pl:.2f}"

        # Status colors
        if status == "PARTIAL":
            status_colored = Fore.YELLOW + status + Style.RESET_ALL
        elif status == "CLOSED":
            status_colored = Fore.RED + status + Style.RESET_ALL
        else:
            status_colored = Fore.CYAN + status + Style.RESET_ALL

        print(f"{pair:<7} {direction:<4} {entry:<10.5f} {now:<10.5f} {sl:<8.5f} {pl_colored:<8} {tp_hit:<7} {status_colored}")

    # --- TP Levels ---
    if trades:
        print("\n--- Take Profit Levels ---")
        for t in trades:
            pair = t['pair']
            tps = t['tp']
            tp_str = ', '.join([f"TP{i+1}={tp:.5f}" for i, tp in enumerate(tps)])
            print(f"{pair}: {tp_str}")

    print("\n=================\n")
