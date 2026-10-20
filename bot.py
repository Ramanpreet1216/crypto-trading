import sys
import time
import json
import os
from datetime import datetime
import config
from coindcx_client import CoinDCXClient
from strategy import evaluate_signal, calculate_turtle_position_size
from predictor import predict_next_move

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

TRADES_LOG_FILE = "paper_trades.json"


class TurtleTradingBot:
    """
    Dedicated Autonomous Turtle Trading Bot (Richard Dennis System 2).
    - Entry: 55-period Donchian High Breakout
    - Volatility Risk: 2N ATR Volatility Stop Loss
    - Trailing Trend Exit: 20-period Donchian Low Channel
    - Dynamic Sizing: 1 Unit calibrated to 2% account risk
    """
    def __init__(self):
        self.client = CoinDCXClient()
        self.current_position = None
        self.paper_balance_inr = getattr(config, "STARTING_WALLET_INR", 30000.0)
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.trade_history = self._load_trade_history()

    def _load_trade_history(self):
        if os.path.exists(TRADES_LOG_FILE):
            try:
                with open(TRADES_LOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.paper_balance_inr = float(data.get("paper_balance", data.get("balance_inr", 30000.0)))
                    self.current_position = data.get("current_position") or data.get("active_position")
                    return data.get("trades", [])
            except Exception as e:
                print(f"[Notice loading {TRADES_LOG_FILE}]: {e}")
        return []

    def _save_trade_history(self):
        try:
            summary = {
                "total_trades": self.total_trades,
                "wins": self.winning_trades,
                "losses": self.losing_trades,
                "win_rate_pct": round((self.winning_trades / max(1, self.total_trades)) * 100.0, 1) if self.total_trades > 0 else 0.0,
                "is_profitable": self.winning_trades > self.losing_trades
            }
            with open(TRADES_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.now().isoformat(),
                    "paper_balance": round(self.paper_balance_inr, 2),
                    "starting_balance": getattr(config, "STARTING_WALLET_INR", 30000.0),
                    "strategy": "TURTLE_SYSTEM_2",
                    "current_position": self.current_position,
                    "active_position": self.current_position,
                    "active_positions": [self.current_position] if self.current_position else [],
                    "summary": summary,
                    "trades": self.trade_history,
                    "is_running": True
                }, f, indent=2)
        except Exception as e:
            print(f"[Error saving state]: {e}")

    def execute_buy(self, price: float, metrics: dict):
        n_val = metrics.get("n_volatility", price * 0.02)
        risk_pct = getattr(config, "TURTLE_RISK_PER_TRADE_PCT", 2.0)
        
        # 1 Unit Turtle Position Sizing
        sizing = calculate_turtle_position_size(
            deposit=self.paper_balance_inr,
            current_price=price,
            n_volatility=n_val,
            risk_pct=risk_pct
        )
        
        # Cap investment to max configured trade allocation
        max_alloc = getattr(config, "INVESTMENT_PER_TRADE_INR", 6000.0)
        spend_amount = min(sizing.get("invested_inr", max_alloc), max_alloc, self.paper_balance_inr)
        
        if spend_amount < 50:
            print("[Alert] Insufficient INR balance to place trade.")
            return

        crypto_quantity = spend_amount / price
        stop_loss_price = metrics.get("turtle_stop_loss", price - (2.0 * n_val))
        target_price = metrics.get("turtle_take_profit", price + (2.0 * max(price * 0.005, price - stop_loss_price)))

        order = self.client.place_order(
            side="buy",
            symbol=config.SYMBOL,
            quantity=crypto_quantity,
            price_per_unit=price
        )

        if order.get("status") == "success" or order.get("simulated"):
            self.paper_balance_inr -= spend_amount
            
            self.current_position = {
                "symbol": config.SYMBOL,
                "strategy": "TURTLE_1_TO_2",
                "buy_price": price,
                "quantity": crypto_quantity,
                "invested_inr": spend_amount,
                "stop_loss": stop_loss_price,
                "target": target_price,
                "n_volatility": n_val,
                "entry_channel_high": metrics.get("donchian_high"),
                "exit_channel_low": metrics.get("exit_low"),
                "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.trade_history.insert(0, {
                "type": "BUY",
                "strategy": "TURTLE_1_TO_2",
                "time": self.current_position["buy_time"],
                "price": price,
                "quantity": crypto_quantity,
                "invested_inr": spend_amount,
                "stop_loss": stop_loss_price,
                "target": target_price,
                "n_volatility": n_val,
                "metrics": metrics
            })
            self._save_trade_history()
            print(f"\n🐢 >>> [1:2 TURTLE BUY] {crypto_quantity:.6f} {config.SYMBOL} @ INR {price:,.2f}")
            print(f"       1R Stop Loss: INR {stop_loss_price:,.2f} | +2R Take Profit: INR {target_price:,.2f} | Margin: INR {spend_amount:,.2f}")

    def execute_sell(self, price: float, reason: str, metrics: dict):
        if not self.current_position:
            return

        quantity = self.current_position["quantity"]
        invested = self.current_position["invested_inr"]
        buy_price = self.current_position["buy_price"]
        proceeds = quantity * price
        pnl_inr = proceeds - invested
        pnl_pct = ((price - buy_price) / buy_price) * 100.0

        order = self.client.place_order(
            side="sell",
            symbol=config.SYMBOL,
            quantity=quantity,
            price_per_unit=price
        )

        if order.get("status") == "success" or order.get("simulated"):
            self.paper_balance_inr += proceeds
            self.total_trades += 1
            if pnl_inr >= 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            self.trade_history.insert(0, {
                "type": "SELL",
                "strategy": "TURTLE_EXIT",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "price": price,
                "proceeds_inr": proceeds,
                "pnl_inr": pnl_inr,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "metrics": metrics
            })

            tag = "PROFIT" if pnl_inr >= 0 else "LOSS"
            print(f"\n🐢 <<< [TURTLE SELL - {tag}] Sold @ INR {price:,.2f} | PnL: INR {pnl_inr:+.2f} ({pnl_pct:+.2f}%) | Reason: {reason}")
            self.current_position = None
            self._save_trade_history()

    def print_dashboard(self, metrics: dict, signal: str, reason: str, prediction: dict = None):
        now_str = datetime.now().strftime("%H:%M:%S")
        mode_str = "SIMULATION (PAPER TRADING)" if config.DRY_RUN else "LIVE TRADING (REAL MONEY)"
        
        print("\n" + "=" * 70)
        print(f"  TURTLE TRADING SYSTEM (Dennis System 2)  |  {now_str}")
        print(f"  EXECUTION MODE: {mode_str}")
        print("=" * 70)
        print(f" Market Pair       : {config.SYMBOL} ({config.TIMEFRAME} candles)")
        print(f" Current Price     : INR {metrics.get('price', 0):,.2f}")
        print(f" 55-Bar Breakout   : High: INR {metrics.get('donchian_high', 0):,.2f} | Low: INR {metrics.get('donchian_low', 0):,.2f}")
        print(f" Volatility (N/ATR): INR {metrics.get('n_volatility', 0):,.2f} | 2N Stop Distance: INR {metrics.get('n_volatility', 0) * 2:,.2f}")
        print(f" 20-Bar Trail Exit : Low Floor: INR {metrics.get('exit_low', 0):,.2f}")
        
        # Balance & Position
        pos_str = "Flat (Awaiting 55-Bar Breakout)"
        if self.current_position:
            buy_p = self.current_position["buy_price"]
            curr_p = metrics.get("price", buy_p)
            pnl_p = ((curr_p - buy_p) / buy_p) * 100.0
            pnl_inr = (self.current_position["quantity"] * curr_p) - self.current_position["invested_inr"]
            pos_str = f"ACTIVE LONG ({pnl_p:+.2f}% | INR {pnl_inr:+.2f}) 2N SL: INR {self.current_position.get('stop_loss', 0):,.2f}"
            
        print(f" Position Status   : {pos_str}")
        print(f" Paper Balance     : INR {self.paper_balance_inr:,.2f}")
        
        if prediction:
            print("-" * 70)
            print(f" Predictive Pulse  : {prediction.get('direction', 'SIDEWAYS')} ({prediction.get('probability', 50)}% confidence)")
        
        print("-" * 70)
        print(f" Turtle Signal     : [{signal}] -> {reason}")
        print("=" * 70)

    def run(self, poll_interval_sec: int = 15):
        print("=" * 70)
        print("Starting Autonomous Turtle Trading Bot...")
        print(f"Strategy: Richard Dennis System 2 (55-Breakout / 2N ATR Volatility Stop)")
        print(f"Mode    : {'DRY_RUN (Safe Virtual Paper Trading)' if config.DRY_RUN else 'LIVE REAL ORDERS'}")
        print(f"Symbol  : {config.SYMBOL} | Timeframe: {config.TIMEFRAME}")
        print(f"Wallet  : INR {self.paper_balance_inr:,.2f}")
        print("=" * 70)
        print("Press Ctrl+C anytime to stop.\n")

        while True:
            try:
                # 1. Fetch latest candles with enough lookback for 55-bar Donchian channel
                df = self.client.get_candles(limit=100)
                if df is None or len(df) == 0:
                    print("[Warning] Could not fetch candle data. Retrying in 15s...")
                    time.sleep(poll_interval_sec)
                    continue

                # 2. Strict Turtle Strategy evaluation
                signal, reason, metrics = evaluate_signal(df, self.current_position)
                prediction = predict_next_move(df)

                # 3. Print live status dashboard
                self.print_dashboard(metrics, signal, reason, prediction)

                # 4. Act strictly on Turtle Signal (No external override)
                current_price = metrics["price"]
                if signal == "BUY" and self.current_position is None:
                    self.execute_buy(current_price, metrics)
                elif signal == "SELL" and self.current_position is not None:
                    self.execute_sell(current_price, reason, metrics)

            except KeyboardInterrupt:
                print("\n[Stopped by user] Turtle Bot shut down safely.")
                break
            except Exception as e:
                print(f"[Loop Exception] {e}")

            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    bot = TurtleTradingBot()
    bot.run()
