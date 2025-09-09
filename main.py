import yfinance as yf
import pandas as pd
import time
from datetime import datetime
import os

# ===========================
# Configuration
# ===========================
PAIRS = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCAD=X', 'GC=F']
PAIR_NAMES = {
    'EURUSD=X': 'EUR/USD',
    'GBPUSD=X': 'GBP/USD',
    'USDJPY=X': 'USD/JPY',
    'USDCAD=X': 'USD/CAD',
    'GC=F': 'Gold/USD'
}
TP1 = 40
TP2 = 40
TP3 = 40
SL = 50
SLEEP_INTERVAL = 60  # seconds
CSV_FILE = "trades_log.csv"
TEST_MODE = True  # True = test trades, False = live EMA/RSI

# ===========================
# Bot State
# ===========================
active_trades = {}
closed_trades = []

# ===========================
# Utilities
# ===========================
def fetch_data(pair, interval='1m', period='3d'):
    try:
        df = yf.download(pair, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        if len(df) >= 12:
            df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
            df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1*delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + roll_up / (roll_down + 1e-8)))
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch {pair}: {e}")
        return None

def get_live_price(pair):
    try:
        ticker = yf.Ticker(pair)
        return float(ticker.fast_info['last_price'])
    except:
        return None

def generate_signal(df):
    if df is None or len(df) < 26:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    ema5_last = last['EMA5'].item()
    ema12_last = last['EMA12'].item()
    ema5_prev = prev['EMA5'].item()
    ema12_prev = prev['EMA12'].item()
    rsi_last = last['RSI'].item()

    if ema5_prev < ema12_prev and ema5_last > ema12_prev and rsi_last < 70:
        return 'BUY'
    elif ema5_prev > ema12_prev and ema5_last < ema12_prev and rsi_last > 30:
        return 'SELL'
    else:
        return None

def calculate_atr(df, period=14):
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L','H-PC','L-PC']].max(axis=1)
    atr = df['TR'].rolling(period).mean()
    return atr.iloc[-1].item() if not atr.empty else None

def open_trade(pair, signal, current_price, df=None):
    # Determine pip unit
    pip_unit = 0.0001
    if 'JPY' in pair:
        pip_unit = 0.01
    elif pair == 'GC=F':
        pip_unit = 0.1

    # ATR-based TP/SL
    atr = calculate_atr(df) if df is not None else None
    if atr is not None:
        tp1_val = atr
        tp2_val = atr * 2
        tp3_val = atr * 3
        sl_val = atr * 1.25
    else:
        tp1_val = TP1 * pip_unit
        tp2_val = (TP1+TP2) * pip_unit
        tp3_val = (TP1+TP2+TP3) * pip_unit
        sl_val = SL * pip_unit

    active_trades[pair] = {
        'Pair': pair,
        'Signal': signal,
        'Entry': current_price,
        'TP1': current_price + tp1_val if signal=='BUY' else current_price - tp1_val,
        'TP2': current_price + tp2_val if signal=='BUY' else current_price - tp2_val,
        'TP3': current_price + tp3_val if signal=='BUY' else current_price - tp3_val,
        'SL': current_price - sl_val if signal=='BUY' else current_price + sl_val,
        'TP1_hit': False,
        'TP2_hit': False,
        'TP3_hit': False,
        'SL_hit': False,
        'Entry_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    print(f"\033[96m[TRADE OPENED] {PAIR_NAMES[pair]} {signal} @ {current_price:.5f}\033[0m")

def compute_live_pnl(trade, current_price):
    pip_factor = 10000 if 'JPY' not in trade['Pair'] else 100
    return (current_price - trade['Entry']) * pip_factor if trade['Signal']=='BUY' else (trade['Entry'] - current_price) * pip_factor

def log_trade_to_csv(trade):
    df = pd.DataFrame([{
        'Pair': PAIR_NAMES[trade['Pair']],
        'Signal': trade['Signal'],
        'Entry': trade['Entry'],
        'Close': trade['Close_Price'],
        'TP1': trade['TP1'],
        'TP2': trade['TP2'],
        'TP3': trade['TP3'],
        'SL': trade['SL'],
        'Entry_Time': trade['Entry_Time'],
        'Close_Time': trade['Close_Time'],
        'P/L': compute_live_pnl(trade, trade['Close_Price'])
    }])
    if not os.path.isfile(CSV_FILE):
        df.to_csv(CSV_FILE, mode='w', header=True, index=False)
    else:
        df.to_csv(CSV_FILE, mode='a', header=False, index=False)

def check_trades(pair, current_price):
    if pair not in active_trades:
        return
    trade = active_trades[pair]

    # Check TPs/SL
    if not trade['TP1_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP1']) or (trade['Signal']=='SELL' and current_price <= trade['TP1'])):
        trade['TP1_hit'] = True
    if not trade['TP2_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP2']) or (trade['Signal']=='SELL' and current_price <= trade['TP2'])):
        trade['TP2_hit'] = True
    if not trade['TP3_hit'] and ((trade['Signal']=='BUY' and current_price >= trade['TP3']) or (trade['Signal']=='SELL' and current_price <= trade['TP3'])):
        trade['TP3_hit'] = True
    if not trade['SL_hit'] and ((trade['Signal']=='BUY' and current_price <= trade['SL']) or (trade['Signal']=='SELL' and current_price >= trade['SL'])):
        trade['SL_hit'] = True

    if (trade['TP1_hit'] and trade['TP2_hit'] and trade['TP3_hit']) or trade['SL_hit']:
        trade['Close_Price'] = current_price
        trade['Close_Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        closed_trades.append(trade)
        log_trade_to_csv(trade)
        del active_trades[pair]
        # Color-coded result
        if ((trade['Signal']=='BUY' and trade['Close_Price']>trade['Entry']) or (trade['Signal']=='SELL' and trade['Close_Price']<trade['Entry'])):
            print(f"\033[92m[TRADE CLOSED - WIN] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']:.5f}\033[0m")
        else:
            print(f"\033[91m[TRADE CLOSED - LOSS] {PAIR_NAMES[pair]} {trade['Signal']} @ {trade['Close_Price']:.5f}\033[0m")

# ===========================
# Dashboard
# ===========================
def display_dashboard():
    print("\n====== Precision Bot Live Dashboard ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print("Active Trades:")
    if active_trades:
        for trade in active_trades.values():
            live_price = get_live_price(trade['Pair'])
            if live_price is None:
                live_price = trade['Entry']
            pnl = compute_live_pnl(trade, live_price)
            color = "\033[92m" if pnl>=0 else "\033[91m"
            reset = "\033[0m"
            print(f"  {PAIR_NAMES[trade['Pair']]}: {trade['Signal']} @ {trade['Entry']:.5f} | "
                  f"TP1: {trade['TP1']:.5f} | TP2: {trade['TP2']:.5f} | TP3: {trade['TP3']:.5f} | "
                  f"SL: {trade['SL']:.5f} | Live P/L: {color}{pnl:.2f} pips{reset}")
    else:
        for pair in PAIRS:
            print(f"  {PAIR_NAMES[pair]}: WAIT")

    print("\nClosed Trades Stats:")
    wins = sum(1 for t in closed_trades if (t['Signal']=='BUY' and t['Close_Price']>t['Entry']) or (t['Signal']=='SELL' and t['Close_Price']<t['Entry']))
    losses = len(closed_trades) - wins
    total = len(closed_trades)
    win_rate = (wins/total*100) if total>0 else 0.0
    print(f"  Wins: {wins} | Losses: {losses} | Total: {total} | Win Rate: {win_rate:.2f}%")

    print("\nCumulative P/L per Pair (Closed Trades):")
    for pair in PAIRS:
        pair_trades = [t for t in closed_trades if t['Pair']==pair]
        pip_factor = 10000 if 'JPY' not in pair else 100
        cum_pnl = sum((t['Close_Price']-t['Entry'])*pip_factor if t['Signal']=='BUY' else (t['Entry']-t['Close_Price'])*pip_factor for t in pair_trades)
        print(f"  {PAIR_NAMES[pair]}: {cum_pnl:.2f} pips")

    print("\nRecent Closed Trades (last 5):")
    recent = closed_trades[-5:] if len(closed_trades) >= 5 else closed_trades
    if recent:
        for t in recent:
            pnl = compute_live_pnl(t, t['Close_Price'])
            color = "\033[92m" if pnl>=0 else "\033[91m"
            reset = "\033[0m"
            print(f"  {PAIR_NAMES[t['Pair']]}: {t['Signal']} Entry:{t['Entry']:.5f} Close:{t['Close_Price']:.5f} P/L:{color}{pnl:.2f}{reset}")

    print("========================================")

# ===========================
# Main Bot Loop
# ===========================
def run_bot():
    global TEST_MODE
    test_trades_opened = {pair: False for pair in PAIRS}  # single test trade per pair

    while True:
        for pair in PAIRS:
            live_price = get_live_price(pair)
            if live_price is None:
                continue

            # TEST MODE
            if TEST_MODE and not test_trades_opened[pair]:
                open_trade(pair, 'BUY', live_price)
                test_trades_opened[pair] = True

            # NORMAL SIGNAL MODE
            elif not TEST_MODE:
                df = fetch_data(pair)
                if df is None:
                    continue
                signal = generate_signal(df)
                if signal is not None and pair not in active_trades:
                    open_trade(pair, signal, live_price, df)

            # CHECK TRADES
            check_trades(pair, live_price)

        # DASHBOARD
        display_dashboard()

        # AUTO DISABLE TEST MODE
        if TEST_MODE:
            all_test_closed = all(pair not in active_trades for pair in PAIRS)
            if all_test_closed:
                TEST_MODE = False
                print("\033[95m[INFO] Test mode complete. Resuming normal live trading.\033[0m")

        time.sleep(SLEEP_INTERVAL)

# ===========================
# Run
# ===========================
if __name__ == "__main__":
    print(f"\033[94m[INFO] Precision Bot starting. Pairs: {PAIRS} | Test Mode: {TEST_MODE}\033[0m")
    run_bot()
