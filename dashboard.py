# dashboard.py

import config
from datetime import datetime
from colorama import Fore, Style, init
init(autoreset=True)

def show_dashboard(trades):
    active_trades = [t for t in trades if t['status'] in ['OPEN', 'BE', 'PARTIAL']]
    closed_trades = [t for t in trades if t['status'] == 'CLOSED']

    print("\n=== DASHBOARD ===")
    print(f"Mode: {config.MODE} | Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Balance: {config.BALANCE}\n")

    # Table header
    print(f"{'PAIR':<8} {'DIR':<5} {'ENTRY':<10} {'NOW':<10} {'SL':<10} {'TP1-TP4':<30} {'P/L':<10} {'TP HIT':<8} {'STATUS':<12}")
    print("-"*105)

    for t in active_trades:
        pair = t['pair']
        direction = t['direction']
        entry = f"{t['entry']:.5f}"
        now = f"{t.get('current_price', t['entry']):.5f}"
        sl = f"{t['sl']:.5f}"
        tp_str = ','.join([f"{x:.5f}" for x in t['tp_levels']])
        pl = t.get('profit', 0.0)
        current_tp = ','.join([str(i+1) for i in range(len(t['tp_levels'])) if i < t.get('current_tp', 0)])
        status = t.get('status', 'OPEN')

        # --- Color rules ---
        pl_color = Fore.GREEN if pl > 0 else Fore.RED
        status_color = Fore.YELLOW if status in ['PARTIAL', 'BE'] else Fore.WHITE

        print(f"{pair:<8} {direction:<5} {entry:<10} {now:<10} {sl:<10} "
              f"{tp_str:<30} {pl_color}{pl:<10.2f}{Style.RESET_ALL} "
              f"{current_tp:<8} {status_color}{status:<12}{Style.RESET_ALL}")

    # --- Closed trades ---
    if closed_trades:
        print("\nClosed Trades:")
        for t in closed_trades:
            pair = t['pair']
            direction = t['direction']
            entry = f"{t['entry']:.5f}"
            closed_at = t.get('closed_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            pl = f"{t.get('profit', 0.0):.2f}"
            print(f"{pair} {direction} | Entry={entry} | Closed={closed_at} | P/L={pl}")
