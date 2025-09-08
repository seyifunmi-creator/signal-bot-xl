# option3_persistent_multi.py
"""
Precision Bot - Option 3 (Multi-pair, persistent, append-only CSV logging)

Behavior:
- One active trade per pair at a time.
- When an active trade closes (all TPs hit OR stop loss hit), the bot logs the result and immediately generates a new signal for that pair.
- Append-only CSV (signals_log.csv) records every event (open, tp hit updates, closed, new open, etc).
- Semi-automatic update protection preserved.
- Exceptions recorded to error.log (no noisy tracebacks on console).
- Replace detect_signal_for_pair() with your Option 3 strategy logic.

Run:
    python option3_persistent_multi.py
"""

import os
import csv
import json
import uuid
import time
import traceback
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
import yfinance as yf

# ---------- Paths & Defaults ----------
BASE_DIR = Path(".")
CONFIG_PATH = BASE_DIR / "config.json"
LOG_CSV = BASE_DIR / "signals_log.csv"
ERROR_LOG = BASE_DIR / "error.log"
UPDATE_PROTECT_FLAG = BASE_DIR / ".update_protect"

DEFAULT_CONFIG = {
    "UPDATE_PROTECT": True,
    "PAIRS": ["EURUSD=X"],
    "YF_PERIOD": "3d",
    "YF_INTERVAL": "1m",
    "TP_THRESHOLDS": [0.002, 0.005, 0.01],
    "PAPER_TRADING": True,
    "VERBOSE": True,
    "MONITOR_SLEEP": 30,
    "MAX_RETRIES": 3,
    "SIGNAL_COOLDOWN_SECONDS": 5
}

LOG_HEADERS = [
    "trade_id", "pair", "side", "entry", "tps", "stop_loss",
    "status", "result", "notes", "market_price", "timestamp", "logged_at"
]


# ---------- Helpers ----------
def safe_write_error(msg: str):
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()} ERROR: {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except Exception as e:
            safe_write_error(f"Failed to load config.json: {e}")
    return cfg


def is_git_clean() -> bool:
    try:
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
        return res.returncode == 0 and res.stdout.strip() == ""
    except Exception:
        return False


def update_allowed(cfg: dict) -> bool:
    if not cfg.get("UPDATE_PROTECT", True):
        return True
    if UPDATE_PROTECT_FLAG.exists():
        return False
    return is_git_clean()


def ensure_log_exists():
    if not LOG_CSV.exists():
        try:
            with LOG_CSV.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
                writer.writeheader()
        except Exception as e:
            safe_write_error(f"Failed to create log CSV: {e}")


def append_log_row(row: dict):
    try:
        ensure_log_exists()
        normalized = {h: row.get(h, "") for h in LOG_HEADERS}
        if isinstance(normalized.get("tps"), (list, tuple)):
            normalized["tps"] = json.dumps(normalized["tps"])
        normalized["logged_at"] = datetime.utcnow().isoformat()
        with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writerow(normalized)
    except Exception as e:
        safe_write_error(f"Failed to append log row: {e}")


def read_latest_states_by_pair() -> Dict[str, Dict[str, Any]]:
    """
    Reads CSV and returns mapping: pair -> last row dict (latest event for that pair).
    If there are multiple trades history for a pair, the last row (by file order) is considered current.
    """
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


# ---------- yfinance helpers ----------
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


# ---------- Signal generation (placeholder) ----------
def detect_signal_for_pair(pair: str, cfg: dict) -> Optional[Dict[str, Any]]:
    """
    Replace this with your Option 3 strategy logic for a given pair.
    Returns a single new trade dict or None if no signal.

    Returned trade dict keys:
      - trade_id, pair, side, entry, tps (list), stop_loss, timestamp
    """
    try:
        df = safe_yf_download(pair, period=cfg.get("YF_PERIOD"), interval=cfg.get("YF_INTERVAL"))
        if df.empty or len(df) < 2:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-2]
        try:
            last_close = float(last["Close"])
            prev_close = float(prev["Close"])
        except Exception:
            return None
        # Example: simple momentum buy signal if last > prev by threshold
        if (last_close - prev_close) / prev_close > 0.002:
            entry = round(last_close, 6)
            tps = [round(entry * (1 + p), 6) for p in cfg.get("TP_THRESHOLDS", DEFAULT_CONFIG["TP_THRESHOLDS"])]
            stop_loss = round(entry * 0.998, 6)
            return {
                "trade_id": str(uuid.uuid4()),
                "pair": pair,
                "side": "buy",
                "entry": entry,
                "tps": tps,
                "stop_loss": stop_loss,
                "timestamp": (last.name.isoformat() if hasattr(last.name, "isoformat") else str(last.name))
            }
        # Add sell logic if you want (e.g., last < prev by threshold)
        if (prev_close - last_close) / prev_close > 0.002:
            entry = round(last_close, 6)
            tps = [round(entry * (1 - p), 6) for p in cfg.get("TP_THRESHOLDS", DEFAULT_CONFIG["TP_THRESHOLDS"])]
            stop_loss = round(entry * 1.002, 6)
            return {
                "trade_id": str(uuid.uuid4()),
                "pair": pair,
                "side": "sell",
                "entry": entry,
                "tps": tps,
                "stop_loss": stop_loss,
                "timestamp": (last.name.isoformat() if hasattr(last.name, "isoformat") else str(last.name))
            }
    except Exception as e:
        safe_write_error(f"detect_signal_for_pair error for {pair}: {e}")
    return None


# ---------- TP/SL checking ----------
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
    # fallback split by comma
    try:
        return [float(x) for x in s.replace(" ", "").split(",") if x != ""]
    except Exception:
        return []


def check_trade_for_pair(latest_price: float, last_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Given latest_price and the last CSV row for a trade (dict of strings),
    return a list of update rows to append (could be empty).
    """
    updates = []
    try:
        status = (last_row.get("status") or "").lower()
        if status in ("all_tp_hit", "stopped_out", "closed_manual"):
            return updates  # already closed

        trade_id = last_row.get("trade_id")
        pair = last_row.get("pair")
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

        # If TP(s) hit now -> record update
        if tps_hit_now:
            # If none remain after hits => all_tp_hit (closed)
            new_status = "all_tp_hit" if not tps_remaining_after else f"tp_hit"
            updates.append({
                "trade_id": trade_id,
                "pair": pair,
                "side": side,
                "entry": entry,
                "tps": tps_remaining_after,
                "stop_loss": stop_loss,
                "status": new_status,
                "result": "WIN" if not tps_remaining_after else "",
                "notes": f"tps_hit:{json.dumps(tps_hit_now)}",
                "market_price": latest_price,
                "timestamp": datetime.utcnow().isoformat()
            })

        # Check SL (only if not already closed by TP)
        if (stop_loss is not None) and (latest_price is not None):
            sl_hit = False
            if side == "buy" and latest_price <= stop_loss:
                sl_hit = True
            if side == "sell" and latest_price >= stop_loss:
                sl_hit = True
            if sl_hit:
                updates.append({
                    "trade_id": trade_id,
                    "pair": pair,
                    "side": side,
                    "entry": entry,
                    "tps": tps_remaining_after if tps_remaining_after else [],
                    "stop_loss": stop_loss,
                    "status": "stopped_out",
                    "result": "LOSS",
                    "notes": "stop_loss_hit",
                    "market_price": latest_price,
                    "timestamp": datetime.utcnow().isoformat()
                })
        return updates
    except Exception as e:
        safe_write_error(f"check_trade_for_pair error: {e}")
        return updates


# ---------- Main controller ----------
def main_loop():
    cfg = load_config()
    ensure_log_exists()

    if cfg.get("VERBOSE"):
        print(f"[INFO] Starting Precision Bot (multi-pair). Pairs: {cfg.get('PAIRS')}")

    if not update_allowed(cfg) and cfg.get("VERBOSE"):
        print("[INFO] Auto-update blocked by protection (will still run).")

    # On start: for each pair, if no open trade exists, generate one
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
                # create a new signal now
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
                        "timestamp": new.get("timestamp")
                    })
                    if cfg.get("VERBOSE"):
                        print(f"[SIGNAL] New signal for {pair}: id={new['trade_id']} entry={new['entry']} tps={new['tps']}")
                else:
                    if cfg.get("VERBOSE"):
                        print(f"[SIGNAL] No initial signal for {pair} at startup.")
    except Exception as e:
        safe_write_error(f"Startup signal generation error: {traceback.format_exc()}")

    # Main monitor loop
    retry_count = 0
    while True:
        try:
            cfg = load_config()  # reload config each loop in case you tweak it on disk
            latest_states = read_latest_states_by_pair()
            for pair in cfg.get("PAIRS", []):
                try:
                    latest_price = safe_get_latest_price(pair)
                    if latest_price is None:
                        continue
                    last_row = latest_states.get(pair)
                    # If no last_row or last is closed -> generate new signal (if not just created)
                    should_generate = False
                    if not last_row:
                        should_generate = True
                    else:
                        st = (last_row.get("status") or "").lower()
                        if st in ("all_tp_hit", "stopped_out", "closed_manual"):
                            should_generate = True

                    # If open, check TP/SL
                    if last_row and (not should_generate):
                        updates = check_trade_for_pair(latest_price, last_row)
                        if updates:
                            for u in updates:
                                append_log_row(u)
                                if cfg.get("VERBOSE"):
                                    print(f"[UPDATE] {pair} {u.get('status')} notes={u.get('notes')} price={u.get('market_price')}")
                            # If any update closed the trade, we will generate a new signal below after a tiny cooldown
                            # Refresh last_row from file
                            latest_states = read_latest_states_by_pair()
                            last_row = latest_states.get(pair)

                    # If no open trade now -> generate new signal (immediately after close)
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
                                "timestamp": new.get("timestamp")
                            })
                            if cfg.get("VERBOSE"):
                                print(f"[SIGNAL] New post-close signal for {pair}: id={new['trade_id']} entry={new['entry']}")
                            # tiny cooldown to avoid immediate re-evaluation race
                            time.sleep(int(cfg.get("SIGNAL_COOLDOWN_SECONDS", 2)))
                except Exception as pair_e:
                    safe_write_error(f"Per-pair loop error for {pair}: {traceback.format_exc()}")

            # sleep
            time.sleep(int(cfg.get("MONITOR_SLEEP", 30)))
        except KeyboardInterrupt:
            print("[INFO] KeyboardInterrupt — exiting gracefully.")
            break
        except Exception as e:
            safe_write_error(f"Main loop exception: {traceback.format_exc()}")
            time.sleep(5)
            continue


if __name__ == "__main__":
    main_loop()
