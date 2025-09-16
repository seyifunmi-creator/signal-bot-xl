# mt5_preload.py
import MetaTrader5 as mt5
import time

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "XAUUSD"]

# Initialize MT5
if not mt5.initialize():
    print("MT5 initialization failed")
    exit()

# Ensure symbols are selected
for pair in PAIRS:
    mt5.symbol_select(pair, True)

# Preload historical bars using M1
for pair in PAIRS:
    print(f"Preloading {pair} M1 bars...")
    rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M1, 0, 2000)
    if rates is None:
        print(f"Warning: {pair} has no bars yet")
    else:
        print(f"{pair} bars loaded: {len(rates)}")

# Wait a few seconds to ensure MT5 processes
time.sleep(5)
mt5.shutdown()
print("Preload complete! Now start main.exe")
