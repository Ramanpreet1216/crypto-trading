"""
CoinDCX Official Real-Time WebSocket Streaming Engine (Socket.IO v3/v4).
Provides 0ms live price feeds for active trading positions with automatic reconnection
and hybrid REST fallback.
"""
import time
import json
import threading
from typing import Dict, Any, Optional, Set

try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False


class CoinDCXWebSocketStream:
    def __init__(self):
        self.sio = None
        self.is_connected = False
        self.subscribed_channels: Set[str] = set()
        self.active_coins: Set[str] = set()
        self.live_prices: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.worker_thread = None
        self._should_run = False

    def start(self):
        if not SOCKETIO_AVAILABLE:
            print("[CoinDCX WS Notice]: python-socketio not available, running REST fallback.")
            return

        if self.worker_thread and self.worker_thread.is_alive():
            return

        self._should_run = True
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self._should_run = False
        if self.sio and self.is_connected:
            try:
                self.sio.disconnect()
            except Exception:
                pass

    def subscribe_coin(self, coin: str):
        clean = coin.upper().replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "")
        with self.lock:
            self.active_coins.add(clean)
        channel = f"B-{clean}_USDT@trades"
        if self.sio and self.is_connected and channel not in self.subscribed_channels:
            try:
                self.sio.emit("join", {"channelName": channel})
                self.subscribed_channels.add(channel)
                print(f"[⚡ CoinDCX WS] Subscribed real-time stream: {channel}")
            except Exception as e:
                print(f"[CoinDCX WS Subscribe Error]: {e}")

    def update_active_coins(self, coins: list):
        for c in coins:
            self.subscribe_coin(c)

    def get_live_price(self, coin: str, max_age_seconds: float = 15.0) -> Optional[float]:
        clean = coin.upper().replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "")
        with self.lock:
            data = self.live_prices.get(clean)
            if data and (time.time() - float(data.get("timestamp", 0))) <= max_age_seconds:
                return float(data.get("price", 0))
        return None

    def get_all_live_prices(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.live_prices)

    def _run_loop(self):
        while self._should_run:
            try:
                self.sio = socketio.Client(
                    reconnection=True,
                    reconnection_attempts=0,
                    reconnection_delay=1,
                    reconnection_delay_max=5
                )

                @self.sio.event
                def connect():
                    self.is_connected = True
                    print("[⚡ CoinDCX WebSocket Connected] Streaming real-time futures ticks!")
                    with self.lock:
                        coins_to_join = list(self.active_coins)
                    for c in coins_to_join:
                        ch = f"B-{c}_USDT@trades"
                        try:
                            self.sio.emit("join", {"channelName": ch})
                            self.subscribed_channels.add(ch)
                            print(f"[⚡ CoinDCX WS Connected] Joined {ch}")
                        except Exception:
                            pass

                @self.sio.event
                def disconnect():
                    self.is_connected = False
                    self.subscribed_channels.clear()
                    print("[CoinDCX WebSocket] Disconnected, auto-reconnecting...")

                @self.sio.event
                def connect_error(data):
                    self.is_connected = False

                @self.sio.on("new-trade")
                def on_trade(msg):
                    try:
                        raw = msg.get("data")
                        data = json.loads(raw) if isinstance(raw, str) else raw
                        sym = data.get("s", "")
                        price = float(data.get("p", 0))
                        clean = sym.replace("B-", "").replace("_USDT", "")
                        if price > 0 and clean:
                            with self.lock:
                                self.live_prices[clean] = {
                                    "price": price,
                                    "symbol": sym,
                                    "timestamp": time.time(),
                                    "trade_time": data.get("T")
                                }
                    except Exception:
                        pass

                self.sio.connect("https://stream.coindcx.com", transports=["websocket", "polling"])
                self.sio.wait()
            except Exception as e:
                self.is_connected = False
                time.sleep(3)


# Global singleton instance
ws_stream = CoinDCXWebSocketStream()

def get_ws_stream() -> CoinDCXWebSocketStream:
    return ws_stream
