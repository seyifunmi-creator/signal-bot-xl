import MetaTrader5 as mt5
import time
from datetime import datetime
import pandas as pd
import sys

# --------------------------- CONFIG ---------------------------
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
TP_POINTS = {'default': [30, 60, 90, 120], 'XAUUSD': [50, 100, 150, 200]}  # in pips
SL_POINTS = {'default': 40, 'XAUUSD': 70}  # in pips
LOT_SIZE = 0.1
UPDATE_INTERVAL = 60  # seconds
LOG_FILE = 'trades_log.csv'

# --------------------------- INIT ----------------------------
def connect_mt5():
    if not mt5.initialize():
        print(f"[ERROR] MT5 initialize failed, error code: {mt5.last_error()}")
        sys.exit()
    account_info = mt5.account_info()
    if account_info is None:
        print("[ERROR] Could not get account info")
        sys.exit()
    print(f"[INFO] Connected to MT5 Account: {account_info.login} | Balance: {account_info.balance}")
    return True

# --------------------------- UTILS ---------------------------
def fmt_price(price):
    if isinstance(price, float):
        return round(price, 5) if price < 100 else round(price, 3)
    return price

def calc_tp_sl(entry, pair, direction):
    tp_list = []
    tp_points = TP_POINTS.get(pair, TP_POINTS['default'])
    sl_point = SL_POINTS.get(pair, SL_POINTS['default'])
    for i in tp_points:
        tp_price = entry + i * 0.0001 if direction == 'BUY' else entry - i * 0.0001
        tp_list.append(fmt_price(tp_price))
    sl_price = entry - sl_point * 0.0001 if direction == 'BUY' else entry + sl_point * 0.0001
    sl_price = fmt_price(sl_price)
    return tp_list, sl_price

def get_price(pair):
    tick = mt5.symbol_info_tick(pair)
    if tick:
        return tick.ask, tick.bid
    return None, None

def calc_pl(entry, current, direction, pair):
    multiplier = 1 if direction == 'BUY' else -1
    if 'XAU' in pair:
        return round((current - entry) * 100, 2) * multiplier
    return round((current - entry) * 10000, 2) * multiplier

# --------------------------- TRADES ---------------------------
class Trade:
    def __init__(self, pair, direction, entry):
        self.pair = pair
        self.direction = direction
        self.entry = entry
        self.tp_list, self.sl = calc_tp_sl(entry, pair, direction)
        self.active = True
        self.live_pl = 0.0
        self.tp_warning = False
        self.sl_warning = False
        self.tp_hit = [False] * 4

    def update(self):
        ask, bid = get_price(self.pair)
        current = ask if self.direction == 'BUY' else bid
        if current is None:
            return
        self.live_pl = calc_pl(self.entry, current, self.direction, self.pair)

        # Check SL warning
        if self.direction == 'BUY' and current <= self.sl + 0.0005:
            self.sl_warning = True
        elif self.direction == 'SELL' and current >= self.sl - 0.0005:
            self.sl_warning = True
        else:
            self.sl_warning = False

        # Check TP warnings
        for i, tp in enumerate(self.tp_list[2:]):  # Only TP3/4
            if self.direction == 'BUY' and tp - current > 0.01:
                self.tp_warning = True
            elif self.direction == 'SELL' and current - tp > 0.01:
                self.tp_warning = True
            else:
                self.tp_warning = False

        # Check if TP hit
        for i, tp in enumerate(self.tp_list):
            if not self.tp_hit[i]:
                if self.direction == 'BUY' and current >= tp:
                    self.tp_hit[i] = True
                elif self.direction == 'SELL' and current <= tp:
                    self.tp_hit[i] = True

# --------------------------- DASHBOARD ---------------------------
def display_dashboard(trades, mode):
    print(f"\n=== Dashboard ===\nMode: {mode} | Active trades: {len(trades)} | Balance: {fmt_price(mt5.account_info().balance)}")
    for t in trades:
        sl_display = f"{t.sl} ⚠️" if t.sl_warning else t.sl
        tp_display = [f"{tp}{' ✅' if hit else ''}" for tp, hit in zip(t.tp_list, t.tp_hit)]
        tp_warning_icon = " ⚡TP3/4 may be unrealistic" if t.tp_warning else ""
        print(f"{t.pair} {t.direction} | Entry={t.entry} | Now={(get_price(t.pair)[0] if t.direction=='BUY' else get_price(t.pair)[1])} | SL={sl_display} | TP1–TP4={tp_display}{tp_warning_icon} | Live P/L={t.live_pl}")

# --------------------------- LOGGING ---------------------------
def log_trades(trades):
    rows = []
    for t in trades:
        rows.append({
            'Time': datetime.now(),
            'Pair': t.pair,
            'Direction': t.direction,
            'Entry': t.entry,
            'SL': t.sl,
            'TP1': t.tp_list[0],
            'TP2': t.tp_list[1],
            'TP3': t.tp_list[2],
            'TP4': t.tp_list[3],
            'Live_P/L': t.live_pl
        })
    df = pd.DataFrame(rows)
    df.to_csv(LOG_FILE, index=False)

# --------------------------- MAIN LOOP ---------------------------
def main():
    mode = input("Start in live mode? (y/n): ").lower()
    mode_text = "LIVE" if mode == 'y' else "TEST"
    connect_mt5()

    trades = []
    # Example: initialize test trades (you can adjust for live signals)
    for pair in PAIRS:
        direction = 'BUY'
        entry = get_price(pair)[0] if direction == 'BUY' else get_price(pair)[1]
        trades.append(Trade(pair, direction, fmt_price(entry)))

    while True:
        for t in trades:
            t.update()
        display_dashboard(trades, mode_text)
        log_trades(trades)
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    main()
