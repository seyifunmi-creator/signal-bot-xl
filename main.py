import yfinance as yf
import pandas as pd
import time
from datetime import datetime

# ===========================
# Embedded Configuration
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
PAPER_TRADING = True
SLEEP_INTERVAL = 60  # seconds between updates

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
        df = yf.download(pair, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1*delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + roll_up / roll_down))
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch {pair}: {e}")
        return None

def generate_signal(df):
    if df is None or len(df) < 26:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Convert to scalars
    ema5_last = float(last['EMA5'])
    ema12_last = float(last['EMA12'])
    ema5_prev = float(prev['EMA5'])
    ema12_prev = float(prev['EMA12'])
    rsi_last = float(last['RSI'])

    if ema5_prev < ema12_prev and ema5_last > ema12_last and rsi_last < 70:
        return 'BUY'
    elif ema5_prev > ema12_prev and ema5_last < ema12_last and rsi_last > 30:
        return 'SELL'
    else:
        return None

def check_trades(pair, df):
    if pair not in active_trades or df is None or df.empty:
        return
    trade = active_trades[pair]
    current_price = float(df.iloc[-1]['Close'])
    # Convert TP/SL to floats
    tp1 = float(trade['TP1'])
    tp2 = float(trade['TP2'])
    tp3 = float(trade['TP3'])
    sl = float(trade['SL'])

    if not trade['TP1_hit'] and current_price >= tp1:
        trade['TP1_hit'] = True
    if not trade['TP2_hit'] and current_price >= tp2:
        trade['TP2_hit'] = True
    if not trade['TP3_hit'] and current_price >= tp3:
        trade['TP3_hit'] = True
    if not trade['SL_hit'] and current_price <= sl:
        trade['SL_hit'] = True

    # If any TP or SL is hit, close trade
    if trade['TP1_hit'] and trade['TP2_hit'] and trade['TP3_hit'] or trade['SL_hit']:
        trade['Close_Price'] = current_price
        trade['Close_Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        closed_trades.append(trade)
        del active_trades[pair]

def open_trade(pair, signal, current_price):
    active_trades[pair] = {
        'Pair': pair,
        'Signal': signal,
        'Entry': current_price,
        'TP1': current_price + TP1*0.0001 if signal=='BUY' else current_price - TP1*0.0001,
        'TP2': current_price + (TP1+TP2)*0.0001 if signal=='BUY' else current_price - (TP1+TP2)*0.0001,
        'TP3': current_price + (TP1+TP2+TP3)*0.0001 if signal=='BUY' else current_price - (TP1+TP2+TP3)*0.0001,
        'SL': current_price - SL*0.0001 if signal=='BUY' else current_price + SL*0.0001,
        'TP1_hit': False,
        'TP2_hit': False,
        'TP3_hit': False,
        'SL_hit': False,
        'Entry_Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def compute_live_pnl(trade, current_price):
    pip_factor = 10000 if 'JPY' not in trade['Pair'] else 100
    if trade['Signal'] == 'BUY':
        return (current_price - trade['Entry']) * pip_factor
    else:
        return (trade['Entry'] - current_price) * pip_factor

# ===========================
# Dashboard
# ===========================
def display_dashboard():
    print("\n====== Precision Bot Live Dashboard ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print("Active Trades:")
    if active_trades:
        for trade in active_trades.values():
            df = fetch_data(trade['Pair'], interval='1m', period='1d')
            current_price = float(df.iloc[-1]['Close'])
            live_pnl = compute_live_pnl(trade, current_price)
            print(f"  {PAIR_NAMES[trade['Pair']]}: {trade['Signal']} @ {trade['Entry']:.5f} | "
                  f"TP1: {trade['TP1']:.5f} | TP2: {trade['TP2']:.5f} | TP3: {trade['TP3']:.5f} | "
                  f"SL: {trade['SL']:.5f} | Live P/L: {live_pnl:.2f} pips")
    else:
        for pair in PAIRS:
            print(f"  {PAIR_NAMES.get(pair, pair)}: WAIT")

    print("\nClosed Trades Stats:")
    wins = sum(1 for t in closed_trades if t['Close_Price'] >= t['Entry'])
    losses = len(closed_trades) - wins
    total = len(closed_trades)
    win_rate = (wins/total*100) if total>0 else 0.0
    print(f"  Wins: {wins} | Losses: {losses} | Total: {total} | Win Rate: {win_rate:.2f}%")
    print("\nCumulative P/L per Pair (Closed Trades):")
    for pair in PAIRS:
        pair_trades = [t for t in closed_trades if t['Pair']==pair]
        pip_factor = 10000 if 'JPY' not in pair else 100
        cum_pnl = sum((t['Close_Price']-t['Entry'])*pip_factor if t['Signal']=='BUY' else (t['Entry']-t['Close_Price'])*pip_factor for t in pair_trades)
        print(f"  {PAIR_NAMES.get(pair,pair)}: {cum_pnl:.2f} pips")
    print("========================================")

# ===========================
# Main Bot Loop
# ===========================
def run_bot():
    while True:
        for pair in PAIRS:
            df = fetch_data(pair)
            if df is None:
                continue
            signal = generate_signal(df)
            # Open trade if none active
            if pair not in active_trades and signal is not None:
                open_trade(pair, signal, float(df.iloc[-1]['Close']))
            check_trades(pair, df)
        display_dashboard()
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    print(f"[INFO] Precision Bot (enhanced, precise + TP sequence dashboard + logging) starting. Pairs: {PAIRS}")
    run_bot()
