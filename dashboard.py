# dashboard.py
import config
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def show_dashboard(trades, signals_log=None):
    """
    Display the dashboard in the console.
    Compact table for core info, TPs listed below.
    If signals_log is provided, show EMA/RSI for None signals.
    """
    # Header
    print("\n=== DASHBOARD ===")
    print(f"Mode: {config.MODE} | Active trades: {len(trades)} | Closed trades: {sum(t['status']=='CLOSED' for t in trades)} | Balance: {config.BALANCE}")
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

        # Color coding
        if pl > 0:
            pl_colored = Fore.GREEN + f"{pl:.2f}" + Style.RESET_ALL
        elif pl < 0:
            pl_colored = Fore.RED + f"{pl:.2f}" + Style.RESET_ALL
        else:
            pl_colored = f"{pl:.2f}"

        if status == "PARTIAL":
            status_colored = Fore.YELLOW + status + Style.RESET_ALL
        elif status == "CLOSED":
            status_colored = Fore.RED + status + Style.RESET_ALL
        else:
            status_colored = Fore.CYAN + status + Style.RESET_ALL

        print(f"{pair:<7} {direction:<4} {entry:<10.5f} {now:<10.5f} {sl:<8.5f} {pl_colored:<8} {tp_hit:<7} {status_colored}")

    # Show TP levels
    print("\n--- Take Profit Levels ---")
    if trades:
        for t in trades:
            pair = t['pair']
            tps = t['tp']
            tp_str = ', '.join([f"TP{i+1}={tp:.5f}" for i, tp in enumerate(tps)])
            print(f"{pair}: {tp_str}")
    else:
        print("No active trades yet.")

    # Show EMA/RSI for None signals
    if signals_log:
        print("\n--- Signal Debug (None signals) ---")
        for pair, sig, ema_fast, ema_slow, rsi in signals_log:
            if sig is None:
                print(f"{pair}: EMA_FAST={ema_fast:.5f} EMA_SLOW={ema_slow:.5f} RSI={rsi:.2f} → No trade")
