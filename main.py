#!/usr/bin/env python3
"""
option3_persistent_multi_precise.py

Precision Bot - Multi-pair persistent trades (append-only CSV) with improved strategy
and live performance tracking (win_rate appended into CSV on every trade close).

Drop into your repo alongside config.json and run:
    python option3_persistent_multi_precise.py
"""

import json
import csv
import time
import uuid
import math
import traceback
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

# ----------------- Paths & defaults -----------------
BASE = Path(".")
CONFIG_PATH = BASE / "config.json"
LOG_CSV = BASE / "signals_log.csv"
ERROR_LOG = BASE / "error.log"
UPDATE_PROTECT_FLAG = BASE / ".update_protect"

DEFAULT_CONFIG = {
    "UPDATE_PROTECT": True,
    "PAIRS": ["CADX", "JPYX", "GBPUSDX", "EURUSDX", "GC=F"],
    "YF_PERIOD": "3d",
    "YF_INTERVAL": "1m",
    "TRADE_SETTINGS": {
        "TP1_PIPS": 40,
        "TP2_PIPS": 40,
        "TP3_PIPS": 40,
        "STOP_LOSS_PIPS": 50
    },
    "PAPER_TRADING": True,
    "VERBOSE": True,
    "MONITOR_SLEEP": 900,
    "MAX_RETRIES": 3,
    "SIGNAL_COOLDOWN_SECONDS": 5
}

LOG_HEADERS = [
    "trade_id", "pair", "side", "entry", "tps", "stop_loss",
    "status", "result", "notes", "market_price", "timestamp", "win_rate", "logged_at"
]

# ----------------- Utilities -----------------
def safe_write_error(msg: str):
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()} ERROR: {msg}\n")
    except Exception:
        pass

def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k != "TRADE_SETTINGS"})
            if "TRADE_SETTINGS" in user_cfg:
                ts = cfg["TRADE_SETTINGS"].copy()
                ts.update(user_cfg["TRADE_SETTINGS"])
                cfg["TRADE_SETTINGS"] = ts
        except Exception as e:
            safe_write_error(f"Failed to load config.json: {e}")
    return cfg

def is_git_clean() -> bool:
    try:
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
        return res.returncode == 0 and res.stdout.strip() == ""
    except Exception:
        return False

def update_allowed(cfg: Dict[str, Any]) -> bool:
    if not cfg.get("UPDATE_PROTECT", True):
        return True
    if UPDATE_PROTECT_FLAG.exists():
        return False
    return is_git_clean()

# ----------------- CSV logging (append-only) -----------------
def ensure_log_exists():
    if not LOG_CSV.exists():
        try:
            with LOG_CSV.open("w", newline='', encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
                writer.writeheader()
        except Exception as e:
            safe_write_error(f"Failed to create log CSV: {e}")

def append_log_row(row: Dict[str, Any]):
    try:
        ensure_log_exists()
        normalized = {h: row.get(h, "") for h in LOG_HEADERS}
        if isinstance(normalized.get("tps"), (list, tuple)):
            normalized["tps"] = json.dumps(normalized["tps"])
        # ensure win_rate is string/floatable
        if "win_rate" in normalized and normalized["win_rate"] is None:
            normalized["win_rate"] = ""
        normalized["logged_at"] = datetime.utcnow().isoformat()
        with LOG_CSV.open("a", newline='', encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writerow(normalized)
    except Exception as e:
        safe_write_error(f"Failed to append log row: {e}")

def read_latest_states_by_pair() -> Dict[str, Dict[str, Any]]:
    try:
        if not LOG_CSV.exists():
            return {}
        df = pd.read_csv(LOG_CSV, dtype=str)
        if df.empty:
            return {}
        last_by_pair: Dict[str, Dict[str, Any]] = {}
        for _, r in df.iterrows():
            p = str(r.get("pair", "") or "")
            if not p:
                continue
            last_by_pair[p] = r.to_dict()
        return last_by_pair
    except Exception as e:
        safe_write_error(f"Failed to read latest states: {e}")
        return {}

# ----------------- Market helpers -----------------
def safe_yf_download(pair: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(pair, period=period, interval=interval, auto_adjust=True, threads=True, progress=False)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        safe_write_error(f"yfinance download failed for {pair}: {e}")
        return pd.DataFrame()

def safe_get_latest_price(pair: str) -> Optional[float]:
    try:
        df = safe_yf_download(pair, period="1d", interval="1m")
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as e:
        safe_write_error(f"safe_get_latest_price failed for {pair}: {e}")
        return None

# ----------------- Indicator functions -----------------
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(period, min_periods=period).mean()
    ma_down = down.rolling(period, min_periods=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

# ----------------- Precision signal logic -----------------
def detect_signal_for_pair(pair: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        df = safe_yf_download(pair, period=cfg.get("YF_PERIOD"), interval=cfg.get("YF_INTERVAL"))
        if df.empty or len(df) < 20:
            return None

        close = df["Close"].astype(float)
        vol = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=close.index)

        ema9 = ema(close, 9)
        ema21 = ema(close, 21)
        rsi14 = rsi(close, 14)
        atr14 = atr(df, 14)

        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        last_ema9 = float(ema9.iloc[-1])
        prev_ema9 = float(ema9.iloc[-2])
        last_ema21 = float(ema21.iloc[-1])
        prev_ema21 = float(ema21.iloc[-2])
        last_rsi = float(rsi14.iloc[-1]) if not np.isnan(rsi14.iloc[-1]) else 50.0
        last_atr = float(atr14.iloc[-1]) if not np.isnan(atr14.iloc[-1]) else 0.0
        avg_vol = float(vol[-20:].mean()) if len(vol) >= 20 else float(vol.mean() if len(vol) > 0 else 0.0)
        last_vol = float(vol.iloc[-1]) if len(vol) > 0 else 0.0

        buy_cross = (prev_ema9 <= prev_ema21) and (last_ema9 > last_ema21)
        sell_cross = (prev_ema9 >= prev_ema21) and (last_ema9 < last_ema21)

        price_move = abs(last_close - prev_close)
        atr_condition = (last_atr > 0) and (price_move >= 0.25 * last_atr)

        vol_condition = True
        if avg_vol > 0:
            vol_condition = last_vol >= (0.9 * avg_vol)

        rsi_ok = (last_rsi >= 30 and last_rsi <= 70)

        side = None
        if buy_cross and atr_condition and vol_condition and rsi_ok and last_close > last_ema9:
            side = "buy"
        elif sell_cross and atr_condition and vol_condition and rsi_ok and last_close < last_ema9:
            side = "sell"

        if side is None:
            return None

        pip = get_pip_size(pair)
        ts = cfg.get("TRADE_SETTINGS", {})
        p1 = ts.get("TP1_PIPS", 40)
        p2 = ts.get("TP2_PIPS", 40)
        p3 = ts.get("TP3_PIPS", 40)
        sl_pips = ts.get("STOP_LOSS_PIPS", 50)

        if side == "buy":
            tps = [round(last_close + (p * pip), 6) for p in (p1, p2, p3)]
            stop_loss = round(last_close - (sl_pips * pip), 6)
        else:
            tps = [round(last_close - (p * pip), 6) for p in (p1, p2, p3)]
            stop_loss = round(last_close + (sl_pips * pip), 6)

        trade = {
            "trade_id": str(uuid.uuid4()),
            "pair": pair,
            "side": side,
            "entry": round(last_close, 6),
            "tps": tps,
            "stop_loss": stop_loss,
            "timestamp": datetime.utcnow().isoformat()
        }
        return trade
    except Exception:
        safe_write_error(f"detect_signal_for_pair error for {pair}: {traceback.format_exc()}")
        return None

# ----------------- pip sizing -----------------
def get_pip_size(pair: str) -> float:
    pair = pair.upper()
    if "JPY" in pair:
        return 0.01
    if pair.endswith("=F") or "XAU" in pair or "GC" in pair:
        return 0.1
    return 0.0001

# ----------------- TP/SL checking -----------------
def parse_tps_field(raw: Any) -> List[float]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    s = str(raw).strip()
    if s.startswith("["):
        try:
            return [float(x) for x in json.loads(s)]
        except Exception:
            s = s.strip("[]")
    try:
        return [float(x) for x in s.replace(" ", "").split(",") if x != ""]
    except Exception:
        return []

def compute_win_rate_with_new_result(new_result: str) -> float:
    """
    Compute win rate after including this new_result (WIN/LOSS).
    This reads current CSV closed trades, adds this new_result and returns the percentage (0-100).
    """
    try:
        if not LOG_CSV.exists():
            # no previous closed trades, so win_rate is 100 if WIN else 0
            return 100.0 if new_result == "WIN" else 0.0
        df = pd.read_csv(LOG_CSV, dtype=str)
        if df.empty:
            return 100.0 if new_result == "WIN" else 0.0
        closed = df[df["result"].isin(["WIN", "LOSS"])]
        wins = closed[closed["result"] == "WIN"].shape[0]
        total = closed.shape[0]
        # include new_result
        if new_result == "WIN":
            wins += 1
        total += 1
        if total == 0:
            return 0.0
        return round((wins / total) * 100.0, 2)
    except Exception:
        safe_write_error(f"compute_win_rate error: {traceback.format_exc()}")
        return 0.0

def check_trade_for_pair(latest_price: float, last_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    updates = []
    try:
        status = (last_row.get("status") or "").lower()
        if status in ("all_tp_hit", "stopped_out", "closed_manual"):
            return updates

        trade_id = last_row.get("trade_id")
        side = (last_row.get("side") or "buy").lower()
        entry = float(last_row.get("entry")) if last_row.get("entry") not in (None, "") else None
        stop_loss = float(last_row.get("stop_loss")) if last_row.get("stop_loss") not in (None, "") else None
        remaining_tps = parse_tps_field(last_row.get("tps"))

        tps_hit_now = []
        tps_remaining_after = []
        for tp in remaining_tps:
            if side == "buy":
                if latest_price is not None and latest_price >= float(tp):
                    tps_hit_now.append(tp)
                else:
                    tps_remaining_after.append(tp)
            else:
                if latest_price is not None and latest_price <= float(tp):
                    tps_hit_now.append(tp)
                else:
                    tps_remaining_after.append(tp)

        if tps_hit_now:
            new_status = "all_tp_hit" if not tps_remaining_after else "tp_hit"
            result = "WIN" if not tps_remaining_after else ""
            # compute win_rate now if this is final close
            win_rate = None
            if new_status == "all_tp_hit":
                win_rate = compute_win_rate_with_new_result("WIN")
            updates.append({
                "trade_id": trade_id,
                "pair": last_row.get("pair"),
                "side": side,
                "entry": entry,
                "tps": tps_remaining_after,
                "stop_loss": stop_loss,
                "status": new_status,
                "result": result,
                "notes": f"tps_hit:{json.dumps(tps_hit_now)}",
                "market_price": latest_price,
                "timestamp": datetime.utcnow().isoformat(),
                "win_rate": win_rate
            })

        if (stop_loss is not None) and (latest_price is not None):
            sl_hit = False
            if side == "buy" and latest_price <= stop_loss:
                sl_hit = True
            if side == "sell" and latest_price >= stop_loss:
                sl_hit = True
            if sl_hit:
                # SL closes the trade (LOSS)
                win_rate = compute_win_rate_with_new_result("LOSS")
                updates.append({
                    "trade_id": trade_id,
                    "pair": last_row.get("pair"),
                    "side": side,
                    "entry": entry,
                    "tps": tps_remaining_after if tps_remaining_after else [],
                    "stop_loss": stop_loss,
                    "status": "stopped_out",
                    "result": "LOSS",
                    "notes": "stop_loss_hit",
                    "market_price": latest_price,
                    "timestamp": datetime.utcnow().isoformat(),
                    "win_rate": win_rate
                })
        return updates
    except Exception:
        safe_write_error(f"check_trade_for_pair error for {last_row.get('trade_id')}: {traceback.format_exc()}")
        return updates

# ----------------- Main controller -----------------
def main_loop():
    cfg = load_config()
    ensure_log_exists()
    if cfg.get("VERBOSE"):
        print(f"[INFO] Precision Bot (precise + performance) starting. Pairs: {cfg.get('PAIRS')}")
    if not update_allowed(cfg) and cfg.get("VERBOSE"):
        print("[INFO] Auto-update blocked by protection (will still run).")

    # initial signals where no open trade exists
    try:
        last_states = read_latest_states_by_pair()
        for pair in cfg.get("PAIRS", []):
            last = last_states.get(pair)
            is_open = False
            if last:
                st = (last.get("status") or "").lower()
                if st not in ("all_tp_hit", "stopped_out", "closed_manual"):
                    is_open = True
            if not is_open:
                new = detect_signal_for_pair(pair, cfg)
                if new:
                    append_log_row({
                        "trade_id": new["trade_id"],
                        "pair": new["pair"],
                        "side": new["side"],
                        "entry": new["entry"],
                        "tps": new["tps"],
                        "stop_loss": new["stop_loss"],
                        "status": "open",
                        "result": "",
                        "notes": "signal_generated",
                        "market_price": "",
                        "timestamp": new.get("timestamp"),
                        "win_rate": ""
                    })
                    if cfg.get("VERBOSE"):
                        print(f"[SIGNAL] New signal for {pair}: id={new['trade_id']} entry={new['entry']} tps={new['tps']}")
    except Exception:
        safe_write_error(f"Startup signal generation error: {traceback.format_exc()}")

    # monitor loop
    retry_count = 0
    while True:
        try:
            cfg = load_config()
            latest_states = read_latest_states_by_pair()
            for pair in cfg.get("PAIRS", []):
                try:
                    latest_price = safe_get_latest_price(pair)
                    if latest_price is None:
                        continue
                    last_row = latest_states.get(pair)
                    should_generate = False
                    if not last_row:
                        should_generate = True
                    else:
                        st = (last_row.get("status") or "").lower()
                        if st in ("all_tp_hit", "stopped_out", "closed_manual"):
                            should_generate = True

                    if last_row and (not should_generate):
                        updates = check_trade_for_pair(latest_price, last_row)
                        if updates:
                            for u in updates:
                                # If this update is a closing row with a computed win_rate included,
                                # the win_rate was computed inside check_trade_for_pair before appending.
                                append_log_row(u)
                                # Print performance for closes
                                if u.get("status") in ("all_tp_hit", "stopped_out"):
                                    # Determine human-readable result
                                    res = u.get("result", "")
                                    wr = u.get("win_rate", "")
                                    if cfg.get("VERBOSE"):
                                        print(f"[UPDATE] {pair} status={u.get('status')} notes={u.get('notes')} price={u.get('market_price')}")
                                        print(f"[PERFORMANCE] Accuracy: {wr}% after closing trade {u.get('trade_id')} ({res})")
                                else:
                                    if cfg.get("VERBOSE"):
                                        print(f"[UPDATE] {pair} partial update notes={u.get('notes')} price={u.get('market_price')}")
                            # refresh states after appends
                            latest_states = read_latest_states_by_pair()
                            last_row = latest_states.get(pair)

                    # if no open trade now -> generate new signal
                    is_open_now = False
                    if last_row:
                        st_now = (last_row.get("status") or "").lower()
                        if st_now not in ("all_tp_hit", "stopped_out", "closed_manual"):
                            is_open_now = True

                    if not is_open_now:
                        new = detect_signal_for_pair(pair, cfg)
                        if new:
                            append_log_row({
                                "trade_id": new["trade_id"],
                                "pair": new["pair"],
                                "side": new["side"],
                                "entry": new["entry"],
                                "tps": new["tps"],
                                "stop_loss": new["stop_loss"],
                                "status": "open",
                                "result": "",
                                "notes": "signal_generated_after_close",
                                "market_price": "",
                                "timestamp": new.get("timestamp"),
                                "win_rate": ""
                            })
                            if cfg.get("VERBOSE"):
                                print(f"[SIGNAL] New post-close signal for {pair}: id={new['trade_id']} entry={new['entry']}")
                            time.sleep(int(cfg.get("SIGNAL_COOLDOWN_SECONDS", 2)))
                except Exception:
                    safe_write_error(f"Per-pair loop error for {pair}: {traceback.format_exc()}")

            time.sleep(int(cfg.get("MONITOR_SLEEP", 900)))
        except KeyboardInterrupt:
            if cfg.get("VERBOSE"):
                print("[INFO] KeyboardInterrupt received — exiting gracefully.")
            break
        except Exception:
            safe_write_error(f"Main loop exception: {traceback.format_exc()}")
            time.sleep(5)
            continue

if __name__ == "__main__":
    main_loop()
