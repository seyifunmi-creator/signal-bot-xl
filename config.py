# === Configuration File ===

# Trading Pairs
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']

# Take-Profit (TP) Values
TP_VALUES = {
    'FOREX': [30, 60, 90, 120],   # in pips
    'GOLD': [50, 100, 150, 200]   # in points
}

# Stop-Loss (SL) Values
SL_VALUES = {
    'FOREX': 50,   # in pips
    'GOLD': 70     # in points
}

# Update interval for dashboard refresh
UPDATE_INTERVAL = 60  # seconds

# Modes: "TEST" (demo/simulated trades) | "LIVE" (real account)
MODE = "TEST"

# Lot size for all trades
LOT_SIZE = 0.1

# Logging
LOG_FILE = "trade_log.csv"
