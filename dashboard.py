# dashboard.py
import config
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def show_dashboard(trades):
    """
    Display the dashboard in the console.
    Shows signals with EMA/RSI for None signals,
    compact table for active trades, TP levels below.
    """
    # Separate active and closed trades
    active_trades = [t for t in trades if t['status'] != 'CLOSED']
    closed_trades = [t for t in trades if t['status'] == 'CLOSED']

    print("\n=== DASHBOARD ===")
    print(f"Mode: {config.MODE} | Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Balance: {config.BALANCE}")
    print()

    # --- Signals section ---
    print("Signals:")
    for pair in config.PAIRS:
        trade = next((t for t in active_trades if t['pair']==pair), None)
        if trade:
            signal = trade['direction']
        else:
            signal = "None"

        # Color coding
        if signal == "BUY":
            sig_col = Fore.GREEN + signal + Style.RESET_ALL
        elif signal == "SELL":
            sig_col = Fore.RED + signal + Style.RESET_ALL
        else:
            sig_col = Fore.WHITE + signal + Style.RESET_ALL

        print(f"{pair}: {sig_col}")

        # --- Show EMA/RSI for None trades ---
        if signal == "None" and trade is None:
            # Check if debug info exists in trade dict
            ema_fast = t.get('ema_fast', 0.0)
            ema_slow = t.get('ema_slow', 0.0)
            rsi = t.get('rsi', 0.0)
            print(f"[DEBUG] {pair} | EMA_FAST={ema_fast:.5f} EMA_SLOW={ema_slow:.5f} RSI={rsi:.2f} → No trade")

    print()

    # --- Active trades table ---
    print("PAIR     DIR   ENTRY      NOW        SL       P/L      TP HIT   STATUS")
    print("-"*70)

    for t in active_trades:
        pair = t['pair']
        direction = t['direction']
        entry = t['entry']
        now = t['now']
        sl = t['sl']
        pl = t['live_pl']
        tp_hit = ','.join(map(str, t['tp_hit'])) if t['tp_hit'] else "-"
        status = t['status']

        # Color coding P/L
        if pl > 0:
            pl_colored = Fore.GREEN + f"{pl:.2f}" + Style.RESET_ALL
        elif pl < 0:
            pl_colored = Fore.RED + f"{pl:.2f}" + Style.RESET_ALL
        else:
            pl_colored = f"{pl:.2f}"

        # Color coding status
        if status == "PARTIAL":
            status_colored = Fore.YELLOW + status + Style.RESET_ALL
        elif status == "CLOSED":
            status_colored = Fore.RED + status + Style.RESET_ALL
        else:
            status_colored = Fore.CYAN + status + Style.RESET_ALL

        print(f"{pair:<7} {direction:<4} {entry:<10.5f} {now:<10.5f} {sl:<8.5f} {pl_colored:<8} {tp_hit:<7} {status_colored}")

    # --- TP Levels below table ---
    print("\n--- Take Profit Levels ---")
    for t in active_trades:
        pair = t['pair']
        tps = t['tp']
        tp_str = ', '.join([f"TP{i+1}={tp:.5f}" for i, tp in enumerate(tps)])
        print(f"{pair}: {tp_str}")
