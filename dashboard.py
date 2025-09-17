# dashboard.py
import config
from colorama import Fore, Style

def show_dashboard(trades):
    print("\n=== DASHBOARD ===")
    active_trades = [t for t in trades if t["status"] == "OPEN"]
    closed_trades = [t for t in trades if t["status"] == "CLOSED"]

    print(
        f"Mode: {config.MODE} | Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Balance: {config.BALANCE:.2f}"
    )

    print("\nPAIR     DIR   ENTRY      NOW        SL       P/L      TP HIT   STATUS")
    print("----------------------------------------------------------------------")
    for trade in trades:
        print(
            f"{trade['pair']:7} {trade['dir']:4} {trade['entry']:.5f}  {trade['now']:.5f}  {trade['sl']:.5f}  {trade['pl']:.2f}  {trade['tp_hit']}   {trade['status']}"
        )

    # Removed EMA/RSI debug completely

    print("=================")
