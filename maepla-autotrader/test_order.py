import MetaTrader5 as mt5
import datetime

r = mt5.initialize()
if not r:
    print(f"Init failed: {mt5.last_error()}")
    exit()

ti = mt5.terminal_info()
ai = mt5.account_info()
now = datetime.datetime.now()
print(f"Date: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})")
print(f"trade_allowed={ti.trade_allowed} tradeapi_disabled={ti.tradeapi_disabled}")
print(f"connected={ti.connected}")

info = mt5.symbol_info("XAUUSD")
if info:
    print(f"trade_mode={info.trade_mode}")

tick = mt5.symbol_info_tick("XAUUSD")
if tick:
    print(f"bid={tick.bid} ask={tick.ask}")
else:
    print("No tick data")

if ti.tradeapi_disabled:
    print("\n=== AutoTrading is STILL DISABLED in MT5 ===")
    print("Enable: Ctrl+O > Expert Advisors > Allow algorithmic trading")
else:
    print("\n=== AutoTrading is ENABLED ===")
    if tick and tick.ask > 0:
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "sl": round(tick.ask - 10, 2),
            "tp": round(tick.ask + 20, 2),
            "deviation": 50,
            "magic": 20260709,
            "comment": "TestOrder",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(req)
        print(f"Order result: retcode={result.retcode} comment={result.comment}")

mt5.shutdown()
