# ===============================
# CONFIGURATION FILE
# ===============================

# --- Set default mode for main.py ---
MODE = "TEST"  # or MODE = TRADE_MODE if you want it linked to TRADE_MODE

# --- MT5 CONNECTION SETTINGS ---
MT5_LOGIN = 10007528925        # Your MT5 demo account number
MT5_PASSWORD = "_7LxJKPs"  
MT5_SERVER = "MetaQuotes-Demo"  # e.g. "Exness-MT5Trial", "ICMarketsSC-Demo"


# --- RISK MANAGEMENT ---
BALANCE = 100000
RISK_PER_TRADE = 0.01       # 1% risk per trade
LOT_SIZE = 0.1              # fixed lot if not using risk-based
USE_RISK_BASED = False      # if True → lot auto-calculated

# --- TRADE PARAMETERS ---
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "XAUUSD"]
EMA_FAST = 3
EMA_SLOW = 6
TP1_MULTIPLIER = 1.0        # 1R
TP2_MULTIPLIER = 2.0        # 2R
TP3_MULTIPLIER = 3.0        # 3R
STOP_LOSS_MULTIPLIER = 1.0  # 1R

# --- TRADE MANAGEMENT ---
PARTIAL_CLOSE = True
PARTIAL_CLOSE_RATIO = 0.5   # Close 50% at TP1
BREAK_EVEN_AT_TP2 = True    # Move SL to BE at TP2
MAX_TRADES_PER_PAIR = 3
MAX_TOTAL_TRADES = 10
MAX_DRAWDOWN_PERCENT = 20   # stop trading after 20% loss

# --- FILTERS ---
USE_SESSION_FILTER = True
SESSION_START = "07:00"
SESSION_END = "20:00"
USE_NEWS_FILTER = False     # future: avoid high-impact news

# --- BACKTEST & SIMULATION ---
BACKTEST_MODE = False
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2024-12-31"

# --- LOGGING & REPORTS ---
TRADE_LOG = "trade_log.csv"
DAILY_REPORT = True
REPORT_FILE = "daily_report.txt"
LOG_FILE = TRADE_LOG

# --- DASHBOARD SETTINGS ---
SHOW_PNL = True
SHOW_WINRATE = True
REFRESH_INTERVAL = 60       # seconds
COLOR_OUTPUT = True

# --- For main.py compatibility ---
UPDATE_INTERVAL = REFRESH_INTERVAL


# --- SAFETY ---
AUTO_RESTART = True
EQUITY_PROTECTION = True
MIN_EQUITY = 5000           # stop if balance falls below
