import MetaTrader5 as mt5
import time
from datetime import datetime
import logging
import pytz

# ------------------ CONFIG ------------------
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
FOREX_TP = [30, 60, 90, 120]  # in pips
FOREX_SL = 50
GOLD_TP = [50, 100, 150, 200]
GOLD_SL = 70
UPDATE_INTERVAL = 60  # seconds
XAU_UPDATE_INTERVAL = 30
LOG_FILE = 'trade_log.txt'
RISK_PERCENT = 1  # percent of balance per trade
TEST_MODE = True

# ------------------ LOGGING ------------------
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(message)s')

# ------------------ MT5 CONNECTION ------------------
if not mt5.initialize():
    logging.error("MT5 initialization failed")
    raise SystemExit

account_info = mt5.account_info()
logging.info(f"Connected to MT5 Account: {account_info.login} | Balance: {account_info.balance}")

# ------------------ UTILS ------------------
def pips_to_price(pair, pips):
    if pair == 'XAUUSD':
        return pips  # already in price points
    else:
        if 'JPY' in pair:
            return pips / 100
        else:
            return pips / 10000


def get_tp_sl(pair, entry, direction):
    if pair == 'XAUUSD':
        tp_list = [entry + (t if direction == 'BUY' else -t) for t in GOLD_TP]
        sl = entry - GOLD_SL if direction == 'BUY' else entry + GOLD_SL
    else:
        tp_list = [entry + (t if direction == 'BUY' else -t) for t in FOREX_TP]
        sl = entry - FOREX_SL if direction == 'BUY' else entry + FOREX_SL
    return tp_list, sl


def get_current_price(pair):
    tick = mt5.symbol_info_tick(pair)
    if tick:
        return tick.bid if tick.bid else tick.ask
    return None

# ------------------ TRADE MANAGEMENT ------------------
active_trades = []
closed_trades = []


def open_trade(pair, direction, lot):
    entry_price = get_current_price(pair)
    if entry_price is None:
        logging.error(f"Price fetch failed for {pair}")
        return
    tp_list, sl = get_tp_sl(pair, entry_price, direction)
    trade = {
        'pair': pair,
        'direction': direction,
        'entry': entry_price,
        'lot': lot,
        'tp': tp_list,
        'sl': sl,
        'live_pl': 0.0,
        'partial_tp_hits': [False]*4
    }
    active_trades.append(trade)
    logging.info(f"Opened {direction} trade for {pair} @ {entry_price} | TP1–TP4={tp_list} | SL={sl}")


def calculate_pl(trade):
    current = get_current_price(trade['pair'])
    if current is None:
        return 0
    if trade['direction'] == 'BUY':
        pl = (current - trade['entry']) * (100 if 'JPY' in trade['pair'] else 10000) * trade['lot']
    else:
        pl = (trade['entry'] - current) * (100 if 'JPY' in trade['pair'] else 10000) * trade['lot']
    trade['live_pl'] = pl
    return pl


def check_trades():
    for trade in active_trades[:]:
        pl = calculate_pl(trade)
        # Partial TP checks
        for i, tp_price in enumerate(trade['tp']):
            if not trade['partial_tp_hits'][i]:
                if (trade['direction'] == 'BUY' and get_current_price(trade['pair']) >= tp_price) or \
                   (trade['direction'] == 'SELL' and get_current_price(trade['pair']) <= tp_price):
                    trade['partial_tp_hits'][i] = True
                    logging.info(f"Partial TP{i+1} hit for {trade['pair']} | Current P/L={pl}")
        # SL warning
        if (trade['direction'] == 'BUY' and get_current_price(trade['pair']) <= trade['sl'] + 0.0005) or \
           (trade['direction'] == 'SELL' and get_current_price(trade['pair']) >= trade['sl'] - 0.0005):
            logging.warning(f"⚠️ SL approaching for {trade['pair']} | Current P/L={pl}")
        # Break-even
        half_tp = trade['tp'][0] / 2 if trade['direction']=='BUY' else trade['entry'] - trade['tp'][0]/2
        if pl >= half_tp:
            trade['sl'] = trade['entry']  # move SL to break-even
            logging.info(f"SL moved to break-even for {trade['pair']}")

# ------------------ DASHBOARD ------------------
def display_dashboard():
    print(f"=== Dashboard ===")
    mode_str = 'TEST' if TEST_MODE else 'LIVE'
    print(f"Mode: {mode_str} | Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Balance: {account_info.balance}")
    for t in active_trades:
        pl_color = '\033[92m' if t['live_pl']>0 else '\033[91m'
        tp_warning = ' ⚡TP3/4 may be unrealistic' if abs(t['tp'][2]-t['entry'])>2*FOREX_TP[0] else ''
        sl_warning = ' ⚠️' if abs(t['sl'] - get_current_price(t['pair'])) < 0.0005 else ''
        print(f"{pl_color}{t['pair']} {t['direction']} | Entry={t['entry']} | Now={get_current_price(t['pair'])} | SL={t['sl']}{sl_warning} | TP1–TP4={t['tp']}{tp_warning} | Live P/L={t['live_pl']}␀
        33[0m")

#------------------ MAIN LOOP ------------------
def run_bot():
    while True:
        check_trades()
        display_dashboard()
        time.sleep(UPDATE_INTERVAL)


# ------------------ START ------------------
if __name__ == '__main__':
    mode = input("Start in live mode? (y/n): ")
    TEST_MODE = True if mode.lower() == 'n' else False
    logging.info(f"Starting in {'TEST' if TEST_MODE else 'LIVE'} MODE")
    # Example trade open simulation
    for pair in PAIRS:
        open_trade(pair, 'BUY', lot=0.1)
    run_bot()        
