import MetaTrader5 as mt5
import config
import time

def initialize_mt5():
    """Initialize MT5 connection using config credentials"""
    if not mt5.initialize(
        login=config.MT5_LOGIN,
        password=config.MT5_PASSWORD,
        server=config.MT5_SERVER
    ):
        print("[ERROR] MT5 initialization failed")
        print(mt5.last_error())
        return False
    print("[INFO] Connected to MT5 successfully")
    return True


def ensure_connection(retries=3, delay=5):
    """Check and reconnect if MT5 is not initialized"""
    if mt5.version() is None:  # disconnected
        print("[WARN] Lost connection to MT5. Reconnecting...")
        for i in range(retries):
            if initialize_mt5():
                print("[INFO] Reconnected to MT5")
                return True
            print(f"[WARN] Retry {i+1}/{retries} failed. Retrying in {delay}s...")
            time.sleep(delay)
        print("[FATAL] Could not reconnect to MT5 after several attempts")
        return False
    return True


def shutdown_mt5():
    """Shutdown MT5 connection"""
    mt5.shutdown()
