import yfinance as yf
import pandas as pd
import time
from datetime import datetime

# ================== CONFIGURATION (Embedded) ==================
PAIRS = {
    'EURUSD=X': 'EUR/USD',
    'GBPUSD=X': 'GBP/USD',
    'USDJPY=X': 'USD/JPY',
    'USDCAD=X': 'USD/CAD',
    'GC=F': 'Gold/USD'
}

TP1 = 40  # in pips
TP2 = 40
TP3 = 40
SL = 50
MONITOR_SLEEP = 10  # seconds between checks
PAPER_TRADING = True  # True = paper trading, False = live

# ================== STATE TRACKING ==================
active_trades = {}
closed_trades = {pair: [] for pair in PAIRS.keys()}

# ================== UTILITY FUNCTIONS ==================
def fetch_data(pair, interval='1m', period='7d'):
    try:
        df = yf.download(pair, period=period, interval=interval, progress=False)
        if df.empty:
            raise ValueError(f"No data for {pair}")
        return df
    except Exception as e:
        print(f"[WARN] Failed to fetch {pair}: {e}")
        return None

def compute_indicators(df):
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def generate_signal(df):
    if df.empty or len(df) < 26:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # Simple EMA + RSI logic
    if prev['EMA5'] < prev['EMA12'] and last['EMA5'] > last['EMA12'] and last['RSI'] < 70:
        return 'BUY'
    elif prev['EMA5'] > prev['EMA12'] and last['EMA5'] < last['EMA12'] and last['RSI'] > 30:
        return 'SELL'
    else:
        return None

def compute_ATR(df, period=14):
    try:
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L','H-PC','L-PC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(period).mean()
        return df
    except:
        return None

def open_trade(pair, signal, price):
    global active_trades
    pip_factor = 0.0001 if 'JPY' not in pair else 0.01
    tp1_price = price + TP1 * pip_factor if signal=='BUY' else price - TP1 * pip_factor
    tp2_price = tp1_price + TP2 * pip_factor if signal=='BUY' else tp1_price - TP2 * pip_factor
    tp3_price = tp2_price + TP3 * pip_factor if signal=='BUY' else tp2_price - TP3 * pip_factor
    sl_price = price - SL * pip_factor if signal=='BUY' else price + SL * pip_factor
    active_trades[pair] = {
        'signal': signal,
        'entry': price,
        'TP1': tp1_price,
        'TP2': tp2_price,
        'TP3': tp3_price,
        'SL': sl_price,
        'hit': {'TP1': False,'TP2': False,'TP3': False,'SL': False}
    }

def check_trades(df_pair, pair):
    global active_trades, closed_trades
    if pair not in active_trades:
        return
    trade = active_trades[pair]
    last_price = float(df_pair['Close'].iloc[-1])
    # Check TP/SL hits
    if not trade['hit']['TP1']:
        if (trade['signal']=='BUY' and last_price >= trade['TP1']) or (trade['signal']=='SELL' and last_price <= trade['TP1']):
            trade['hit']['TP1'] = True
    if not trade['hit']['TP2']:
        if (trade['signal']=='BUY' and last_price >= trade['TP2']) or (trade['signal']=='SELL' and last_price <= trade['TP2']):
            trade['hit']['TP2'] = True
    if not trade['hit']['TP3']:
        if (trade['signal']=='BUY' and last_price >= trade['TP3']) or (trade['signal']=='SELL' and last_price <= trade['TP3']):
            trade['hit']['TP3'] = True
    if not trade['hit']['SL']:
        if (trade['signal']=='BUY' and last_price <= trade['SL']) or (trade['signal']=='SELL' and last_price >= trade['SL']):
            trade['hit']['SL'] = True
    # Close trade if all TP or SL hit
    if trade['hit']['SL'] or (trade['hit']['TP1'] and trade['hit']['TP2'] and trade['hit']['TP3']):
        closed_trades[pair].append({
            'signal': trade['signal'],
            'entry': trade['entry'],
            'TP1': trade['TP1'],
            'TP2': trade['TP2'],
            'TP3': trade['TP3'],
            'SL': trade['SL'],
            'hit': trade['hit']
        })
        del active_trades[pair]

def display_dashboard():
    print("\n====== Precision Bot Live Dashboard ======")
    print("Time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"\n")
    print("Active Trades:\n")
    for pair, trade in active_trades.items():
        tp1_status = "✔" if trade['hit']['TP1'] else "…"
        tp2_status = "✔" if trade['hit']['TP2'] else "…"
        tp3_status = "✔" if trade['hit']['TP3'] else "…"
        sl_status = "✔" if trade['hit']['SL'] else "…"
        print(f"  {PAIRS[pair]}: {trade['signal']} @ {trade['entry']:.5f} | "
              f"TP1: {trade['TP1']:.5f}{tp1_status} | "
              f"TP2: {trade['TP2']:.5f}{tp2_status} | "
              f"TP3: {trade['TP3']:.5f}{tp3_status} | "
              f"SL: {trade['SL']:.5f}{sl_status} | "
              f"Live P/L: {0.0:.1f} pips")
    if not active_trades:
        print("  None")

    print("\nClosed Trades Stats:")
    total_wins = sum(1 for trades in closed_trades.values() for t in trades if any([t['hit']['TP1'],t['hit']['TP2'],t['hit']['TP3']]))
    total_losses = sum(1 for trades in closed_trades.values() for t in trades if t['hit']['SL'])
    total_trades = total_wins + total_losses
    win_rate = (total_wins/total_trades*100) if total_trades else 0
    print(f"  Wins: {total_wins} | Losses: {total_losses} | Total: {total_trades} | Win Rate: {win_rate:.2f}%\n")

    print("Cumulative P/L per Pair (Closed Trades):")
    for pair, trades in closed_trades.items():
        pip_total = 0
        for t in trades:
            pip_factor = 0.0001 if 'JPY' not in pair else 0.01
            profit = 0
            for key in ['TP1','TP2','TP3']:
                if t['hit'][key]:
                    if t['signal']=='BUY':
                        profit += (t[key]-t['entry'])/pip_factor
                    else:
                        profit += (t['entry']-t[key])/pip_factor
            if t['hit']['SL']:
                if t['signal']=='BUY':
                    profit += (t['SL']-t['entry'])/pip_factor
                else:
                    profit += (t['entry']-t['SL'])/pip_factor
            pip_total += profit
        print(f"  {PAIRS[pair]}: {pip_total:.1f} pips")
    print("========================================\n")

# ================== MAIN BOT LOOP ==================
def run_bot():
    print("[INFO] Precision Bot (enhanced, precise + TP sequence dashboard) starting. Pairs:", list(PAIRS.keys()))
    while True:
        for pair in PAIRS.keys():
            df = fetch_data(pair)
            if df is None:
                continue
            df = compute_indicators(df)
            df = compute_ATR(df)
            check_trades(df, pair)
            if pair not in active_trades:
                signal = generate_signal(df)
                if signal:
                    last_price = float(df['Close'].iloc[-1])
                    open_trade(pair, signal, last_price)
        display_dashboard()
        time.sleep(MONITOR_SLEEP)

if __name__ == "__main__":
    run_bot()
