# dashboard.py
import config
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def show_dashboard(trades, debug_signals=None):
    """
    Display the dashboard in the console.
    Compact table for core info, TPs listed below.
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
        now = t['current_price']
        sl = t['sl']
        pl = t['profit']
        tp_hit = f"TP{t['current_tp']}" if t['current_tp'] > 0 else "-"
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

    # Show TP levels if trades exist
    if trades:
        print("\n--- Take Profit Levels ---")
        for t in trades:
            pair = t['pair']
            tps = t['tp_levels']
            tp_str = ', '.join([f"TP{i+1}={tp:.5f}" for i, tp in enumerate(tps)])
            print(f"{pair}: {tp_str}")

    # Show debug EMA/RSI for None signals (passed in from main.py)
    if debug_signals:
        print("\n--- Debug (No Trade Signals) ---")
        for pair, vals in debug_signals.items():
            ema_fast, ema_slow, rsi = vals
            print(f"{pair}: EMA_FAST={ema_fast:.5f} EMA_SLOW={ema_slow:.5f} RSI={rsi:.2f}")
