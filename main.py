# Precision Bot V3 - Corrected Full Code
import warnings
warnings.filterwarnings('ignore')

import os
import csv
import time
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# -----------------------------
# INITIALIZATION
# -----------------------------
if not mt5.initialize():
    print("MT5 initialization failed")
    mt5.shutdown()

# -----------------------------
# SETTINGS
# -----------------------------
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD']
PAIR_NAMES = {
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD',
    'USDJPY': 'USD/JPY', 'USDCAD': 'USD/CAD',
    'XAUUSD': 'Gold/USD'
}
GOLD_PAIRS = ["XAUUSD"]
REQUIRED_SUSTAINED_CANDLES = 3
SLEEP_INTERVAL = 5

PAIR_SETTINGS = {
    'EURUSD': {'TP1': 40, 'TP2': 80, 'TP3': 120, 'SL': 50},
    'GBPUSD': {'TP1': 50, 'TP2': 100, 'TP3': 150, 'SL': 60},
    'USDJPY': {'TP1': 30, 'TP2': 60, 'TP3': 90, 'SL': 40},
    'USDCAD': {'TP1': 25, 'TP2': 50, 'TP3': 75, 'SL': 30},
    'XAUUSD': {'TP1': 500, 'TP2': 1000, 'TP3': 1500, 'SL': 600},
}

LOG_FILE = "precision_bot.log"
TRADE_CSV = "trade_history.csv"
if not os.path.exists(TRADE_CSV):
    with open(TRADE_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp","Pair","Signal","Entry","Close","TP1","TP2","TP3","SL","Result","P/L"])

# -----------------------------
# GLOBAL STATE
# -----------------------------
active_trades = {}
closed_trades = []
trained_stats = {}
last_trained = None

total_trades = 0
wins = 0
losses = 0
profit = 0.0

# -----------------------------
# UTILITIES
# -----------------------------
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")

def detect_pip_unit(pair):
    pair = pair.upper()
    if pair.endswith('JPY'): return 0.01, 100
    if pair in GOLD_PAIRS: return 0.1, 10
    return 0.0001, 10000

def compute_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0,1e-6)
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def calculate_atr(df, period=14):
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L','H-PC','L-PC']].max(axis=1)
    atr = df['TR'].rolling(period).mean()
    return atr.iloc[-1] if not atr.empty else None

def generate_signal(df):
    if df is None or len(df) < REQUIRED_SUSTAINED_CANDLES+5:
        return None
    df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
    df = compute_rsi(df)
    sustained_buy = all(df['EMA5'].iloc[-(i+1)] > df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
    sustained_sell = all(df['EMA5'].iloc[-(i+1)] < df['EMA12'].iloc[-(i+1)] for i in range(REQUIRED_SUSTAINED_CANDLES))
    rsi_last = df['RSI'].iloc[-1]
    if sustained_buy and rsi_last < 70: return "BUY"
    if sustained_sell and rsi_last > 30: return "SELL"
    return None

def fmt_price(pair, price):
    return round(price, 2) if pair in GOLD_PAIRS else round(price, 5)

def compute_live_pnl(trade, price):
    _, pip_factor = detect_pip_unit(trade['Pair'])
    if trade['Signal']=="BUY":
        return round((price - trade['Entry'])*pip_factor,2)
    else:
        return round((trade['Entry'] - price)*pip_factor,2)

def log_trade_to_csv(trade, result):
    pl = compute_live_pnl(trade, trade.get('Close', trade['Entry']))
    with open(TRADE_CSV,'a',newline='') as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), trade['Pair'], trade['Signal'], trade['Entry'],
                         trade.get('Close',''), trade['TP1'], trade['TP2'], trade['TP3'], trade['SL'], result, pl])

# -----------------------------
# TRADING FUNCTIONS
# -----------------------------
def open_trade(pair, signal, price):
    settings = PAIR_SETTINGS.get(pair, {'TP1':40,'TP2':80,'TP3':120,'SL':50})
    tp1_val, tp2_val, tp3_val, sl_val = settings['TP1'], settings['TP2'], settings['TP3'], settings['SL']
    pip_unit,_ = detect_pip_unit(pair)
    active_trades[pair] = {
        'Pair': pair,
        'Signal': signal,
        'Entry': price,
        'TP1': price + tp1_val*pip_unit if signal=="BUY" else price - tp1_val*pip_unit,
        'TP2': price + tp2_val*pip_unit if signal=="BUY" else price - tp2_val*pip_unit,
        'TP3': price + tp3_val*pip_unit if signal=="BUY" else price - tp3_val*pip_unit,
        'SL': price - sl_val*pip_unit if signal=="BUY" else price + sl_val*pip_unit,
        'TP1_hit': False,'TP2_hit':False,'TP3_hit':False,'SL_hit':False
    }
    log(f"Opened {signal} trade for {pair} @ {fmt_price(pair, price)}")

def check_trades():
    global total_trades,wins,losses,profit
    for pair, trade in list(active_trades.items()):
        tick = mt5.symbol_info_tick(pair)
        if not tick: continue
        price = (tick.ask + tick.bid)/2
        # TP1/TP2/TP3
        if not trade['TP1_hit'] and ((trade['Signal']=="BUY" and price>=trade['TP1']) or (trade['Signal']=="SELL" and price<=trade['TP1'])):
            trade['TP1_hit']=True
        if not trade['TP2_hit'] and ((trade['Signal']=="BUY" and price>=trade['TP2']) or (trade['Signal']=="SELL" and price<=trade['TP2'])):
            trade['TP2_hit']=True
        if not trade['TP3_hit'] and ((trade['Signal']=="BUY" and price>=trade['TP3']) or (trade['Signal']=="SELL" and price<=trade['TP3'])):
            trade['TP3_hit']=True
        if not trade['SL_hit'] and ((trade['Signal']=="BUY" and price<=trade['SL']) or (trade['Signal']=="SELL" and price>=trade['SL'])):
            trade['SL_hit']=True
        # Close trade logic
        if trade['TP3_hit'] or trade['SL_hit']:
            trade['Close'] = price
            pnl = compute_live_pnl(trade, price)
            result = "WIN" if trade['TP3_hit'] else "LOSS"
            total_trades +=1
            if result=="WIN": wins+=1
            else: losses+=1
            profit += pnl
            log_trade_to_csv(trade, result)
            closed_trades.append(trade)
            del active_trades[pair]
            log(f"Closed {trade['Signal']} trade for {pair} @ {fmt_price(pair, price)} | Result: {result} | P/L: {pnl}")

def fetch_candle_data(pair, n=50, timeframe=mt5.TIMEFRAME_M5):
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None or len(rates)==0: return None
    df = pd.DataFrame(rates)
    df['time']=pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'close':'close','open':'open','high':'high','low':'low'}, inplace=True)
    return df

# -----------------------------
# MAIN LOOP
# -----------------------------
def run_cycle():
    for pair in PAIRS:
        df = fetch_candle_data(pair)
        signal = generate_signal(df)
        tick = mt5.symbol_info_tick(pair)
        if not tick: continue
        price = tick.ask if signal=="BUY" else tick.bid if signal=="SELL" else None
        if signal and pair not in active_trades:
            open_trade(pair, signal, price)
    check_trades()
    # DASHBOARD
    log(f"Active trades: {len(active_trades)} | Closed trades: {len(closed_trades)} | Wins: {wins} | Losses: {losses} | Profit: {profit:.2f}")

if __name__=="__main__":
    log("Precision Bot V3 Started")
    try:
        while True:
            run_cycle()
            time.sleep(SLEEP_INTERVAL)
    except KeyboardInterrupt:
        log("Bot Stopped by user")
    finally:
        mt5.shutdown()
