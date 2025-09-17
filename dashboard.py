# dashboard.py
import config
from colorama import Fore, Style

def show_dashboard(trades, ema_debug=None):
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

    # Only show EMA/RSI debug when no trades are active
    if ema_debug and len(active_trades) == 0:
        print("\n--- EMA/RSI Debug (No trades active) ---")
        for pair, ema_fast, ema_slow, rsi_val in ema_debug:
            if ema_fast > ema_slow:
                color = Fore.GREEN
            elif ema_fast < ema_slow:
                color = Fore.RED
            else:
                color = Fore.YELLOW

            print(
                color
                + f"{pair}: EMA_FAST={ema_fast:.5f} EMA_SLOW={ema_slow:.5f} RSI={rsi_val:.2f}"
                + Style.RESET_ALL
            )

    print("=================")
