# option3_fixed.py
"""
Option 3 - Fixed implementation with semi-automatic update protection.

Drop this into your project (replace your previous option 3 file).
Requires:
  - pandas
  - yfinance
  - python-dateutil (usually with pandas)
  - optional: git in PATH if you want git-based protection

Logging:
  - Trades / TP hits are appended to signals_log.csv (file created if missing).
  - Configure behavior via config.json (see default below) or environment variables.

Update protection:
  - Uses config.json key "UPDATE_PROTECT": true/false
  - Or presence of file ".update_protect" in repo root
  - If git present, additionally requires git status --porcelain to be empty to auto-update.
"""

import os
import json
import csv
import subprocess
from datetime import datetime
from pathlib import Path
import pandas as pd
import yfinance as yf

CONFIG_PATH = Path("config.json")
LOG_CSV = Path("signals_log.csv")
UPDATE_PROTECT_FLAG = Path(".update_protect")


DEFAULT_CONFIG = {
    "UPDATE_PROTECT": True,
    "YF_PERIOD": "7d",
    "YF_INTERVAL": "1m",
    "TP_THRESHOLDS": [0.002, 0.005, 0.01],  # example fractions (0.2%, 0.5%, 1%)
    "PAIR": "EURUSD=X",
    "PAPER_TRADING": True,
    "VERBOSE": True
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except Exception as e:
            print(f"[WARN] Failed to read config.json: {e} — using defaults.")
    return cfg


def is_git_clean():
    """Return True if git is available and working tree is clean (no uncommitted changes)."""
    try:
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            # git not initialized or error; return False to be safe (prevent auto-update)
            return False
        return res.stdout.strip() == ""
    except FileNotFoundError:
        # git not installed / not available
        return False
    except Exception:
        return False


def update_allowed(cfg):
    """Return True if it's safe to auto-update/deploy."""
    # 1) If config explicitly disables protection, allow.
    if not cfg.get("UPDATE_PROTECT", True):
        return True
    # 2) If the .update_protect file exists, block updates.
    if UPDATE_PROTECT_FLAG.exists():
        if cfg.get("VERBOSE"):
            print("[INFO] Update blocked: .update_protect file present.")
        return False
    # 3) If git is available, ensure working tree is clean.
    if is_git_clean():
        return True
    else:
        if cfg.get("VERBOSE"):
            print("[INFO] Update blocked: git working tree not clean or git not available.")
        return False


def safe_yf_download(pair, period, interval):
    """
    Downloads data using yfinance with explicit parameters and returns a DataFrame.
    Defensive: always returns a DataFrame (possibly empty).
    """
    # Avoid ambiguity when auto_adjust default changes: set arguments explicitly
    df = yf.download(pair, period=period, interval=interval, auto_adjust=True, threads=True, progress=False)
    if df is None:
        return pd.DataFrame()
    return df


def detect_signal(df: pd.DataFrame):
    """
    Placeholder signal detection for "option 3".
    Replace with your strategy logic.
    Returns a list of candidate signals, each dict containing:
      { 'timestamp', 'side' ('buy'/'sell'), 'entry', 'tps': [tp1, tp2, tp3], 'stop_loss' }
    """
    signals = []
    if df.empty:
        return signals

    # Example: simple momentum signal: if last candle closes higher than previous by > threshold
    if len(df) < 2:
        return signals

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Use numeric operations; don't do 'if df' which raises ValueError
    if (last['Close'] - prev['Close']) / prev['Close'] > 0.002:  # 0.2% up-move
        entry = last['Close']
        tps = [entry * (1 + p) for p in cfg.get("TP_THRESHOLDS", DEFAULT_CONFIG["TP_THRESHOLDS"])]
        signals.append({
            'timestamp': last.name.isoformat() if hasattr(last.name, 'isoformat') else str(last.name),
            'side': 'buy',
            'entry': float(entry),
            'tps': [float(x) for x in tps],
            'stop_loss': float(entry * 0.998),  # example 0.2% SL
        })
    return signals


def append_log(trade_record: dict):
    headers = ['timestamp', 'pair', 'side', 'entry', 'tps', 'stop_loss', 'status', 'notes', 'logged_at']
    write_header = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            writer.writeheader()
        row = {k: trade_record.get(k, "") for k in headers}
        # ensure lists are stringified
        if isinstance(row.get('tps'), (list, tuple)):
            row['tps'] = json.dumps(row['tps'])
        row['logged_at'] = datetime.utcnow().isoformat()
        writer.writerow(row)


def check_tp_hits(market_price: float, trade_record: dict):
    """
    Given a live market price and a trade record (with 'tps' list and a 'status' field),
    detect if any TP was hit and return updated trade_record and list of hits.
    """
    hits = []
    tps = trade_record.get('tps', [])
    side = trade_record.get('side', 'buy')
    remaining_tps = []
    for tp in tps:
        if side == 'buy':
            if market_price >= tp:
                hits.append(tp)
            else:
                remaining_tps.append(tp)
        else:
            if market_price <= tp:
                hits.append(tp)
            else:
                remaining_tps.append(tp)
    trade_record['tps'] = remaining_tps
    # update status
    if hits:
        trade_record['status'] = 'partial_tp_hit' if remaining_tps else 'all_tp_hit'
    return trade_record, hits


def simulate_paper_trade(signals, cfg):
    """
    Simulate / paper-trade signals. For each signal, we log the entry and monitor ticks
    (here represented by last close) to check TP hits. Replace this with your real
    execution/paper-trade backend if needed.
    """
    for sig in signals:
        record = {
            'timestamp': sig['timestamp'],
            'pair': cfg.get('PAIR'),
            'side': sig['side'],
            'entry': sig['entry'],
            'tps': sig['tps'],
            'stop_loss': sig['stop_loss'],
            'status': 'open',
            'notes': 'simulated paper trade'
        }
        # Log initial order
        append_log(record)
        if cfg.get("VERBOSE"):
            print(f"[PAPER] Logged new trade: entry={record['entry']}, tps={record['tps']}")

        # In real system: subscribe to live ticks / websocket. Here we'll re-evaluate with latest candle
        # For this example we'll fetch the latest close and treat it as the current market price.
        df_latest = safe_yf_download(cfg.get("PAIR"), period="1d", interval="1m")
        if not df_latest.empty:
            current_price = float(df_latest['Close'].iloc[-1])
            record, hits = check_tp_hits(current_price, record)
            if hits and cfg.get("VERBOSE"):
                print(f"[PAPER] TP(s) hit for trade at {record['timestamp']}: {hits}")
            append_log(record)  # append an update row (you can change behavior to update in-place if desired)


def main_option3():
    global cfg
    cfg = load_config()
    if cfg.get("VERBOSE"):
        print(f"[INFO] Running Option 3 - pair={cfg.get('PAIR')} period={cfg.get('YF_PERIOD')}")

    # Update protection check (if this module is used for auto-updating / deploying)
    if not update_allowed(cfg):
        if cfg.get("VERBOSE"):
            print("[INFO] Auto-update disabled by protection rules. Proceeding with signal generation only.")
    else:
        if cfg.get("VERBOSE"):
            print("[INFO] Update allowed by protection rules (no blocking flags detected).")

    # Fetch market data (defensive)
    try:
        df = safe_yf_download(cfg.get("PAIR"), period=cfg.get("YF_PERIOD"), interval=cfg.get("YF_INTERVAL"))
    except Exception as e:
        print(f"[ERROR] Failed to fetch market data: {e}")
        df = pd.DataFrame()

    # Run signal detection
    try:
        signals = detect_signal(df)
    except Exception as e:
        print(f"[ERROR] Signal detection failed: {e}")
        signals = []

    if not signals:
        if cfg.get("VERBOSE"):
            print("[INFO] No signals generated at this time.")
        return

    # Execute or simulate trades
    if cfg.get("PAPER_TRADING", True):
        simulate_paper_trade(signals, cfg)
    else:
        # Hook to real execution function
        for s in signals:
            # TODO: integrate with real execution code
            append_log({
                'timestamp': s['timestamp'],
                'pair': cfg.get('PAIR'),
                'side': s['side'],
                'entry': s['entry'],
                'tps': s['tps'],
                'stop_loss': s['stop_loss'],
                'status': 'sent_to_broker',
                'notes': 'sent to execution (placeholder)'
            })
            if cfg.get("VERBOSE"):
                print(f"[EXEC] Sent trade to broker (placeholder): {s}")

if __name__ == "__main__":
    main_option3()
