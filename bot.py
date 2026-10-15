import sys
import time
import json
import os
from datetime import datetime
import config
from coindcx_client import CoinDCXClient
from strategy import evaluate_signal
from predictor import predict_next_move

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

TRADES_LOG_FILE = "paper_trades.json"


class TradingBot:
    def __init__(self):
        self.client = CoinDCXClient()
        self.current_position = None
        self.paper_balance_inr = getattr(config, "STARTING_WALLET_INR", 30000.0)  # Initial paper balance
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.trade_history = self._load_trade_history()

    def _load_trade_history(self):
        if os.path.exists(TRADES_LOG_FILE):
            try:
                with open(TRADES_LOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.paper_balance_inr = data.get("paper_balance", data.get("balance_inr", 30000.0))
                    self.current_position = data.get("current_position", None)
                    return data.get("trades", [])
            except Exception:
                pass
        return []

    def _save_trade_history(self):
        try:
            with open(TRADES_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "balance_inr": round(self.paper_balance_inr, 2),
                    "current_position": self.current_position,
                    "trades": self.trade_history
                }, f, indent=2)
        except Exception as e:
            print(f"[Error saving state]: {e}")

    def execute_buy(self, price: float, metrics: dict, prediction: dict = None):
        spend_amount = min(config.INVESTMENT_PER_TRADE_INR, self.paper_balance_inr)
        if spend_amount < 50:
            print("[Alert] Insufficient INR balance to place trade.")
            return

        crypto_quantity = spend_amount / price

        order = self.client.place_order(
            side="buy",
            symbol=config.SYMBOL,
            quantity=crypto_quantity,
            price_per_unit=price
        )

        if order.get("status") == "success" or order.get("simulated"):
            self.paper_balance_inr -= spend_amount
            target = prediction.get("target_price", price * 1.03) if prediction else price * 1.03
            stop = prediction.get("stop_loss", price * 0.985) if prediction else price * 0.985
            
            self.current_position = {
                "symbol": config.SYMBOL,
                "buy_price": price,
                "quantity": crypto_quantity,
                "invested_inr": spend_amount,
                "target": target,
                "stop_loss": stop,
                "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.trade_history.append({
                "type": "BUY",
                "time": self.current_position["buy_time"],
                "price": price,
                "quantity": crypto_quantity,
                "invested_inr": spend_amount,
                "target": target,
                "metrics": metrics
            })
            self._save_trade_history()
            print(f"\n>>> [PREDICTIVE BUY] {crypto_quantity:.6f} {config.SYMBOL} @ INR {price:,.2f} | Target: INR {target:,.2f}")

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

            self.trade_history.append({
                "type": "SELL",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "price": price,
                "proceeds_inr": proceeds,
                "pnl_inr": pnl_inr,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "metrics": metrics
            })

            tag = "PROFIT" if pnl_inr >= 0 else "LOSS"
            print(f"\n<<< [SELL EXECUTED - {tag}] Sold @ INR {price:,.2f} | PnL: INR {pnl_inr:+.2f} ({pnl_pct:+.2f}%) | Reason: {reason}")
            self.current_position = None
            self._save_trade_history()

    def print_dashboard(self, metrics: dict, signal: str, reason: str, prediction: dict = None):
        now_str = datetime.now().strftime("%H:%M:%S")
        mode_str = "SIMULATION (PAPER TRADING)" if config.DRY_RUN else "LIVE TRADING (REAL MONEY)"
        
        print("\n" + "=" * 68)
        print(f"  COINDCX QUANT BOT  |  {now_str}  |  MODE: {mode_str}")
        print("=" * 68)
        print(f" Market Pair    : {config.SYMBOL} ({config.TIMEFRAME} candles)")
        print(f" Current Price  : INR {metrics.get('price', 0):,.2f}")
        print(f" Moving Averages: Fast EMA(9): INR {metrics.get('ema_fast', 0):,.1f} | Slow EMA(21): INR {metrics.get('ema_slow', 0):,.1f}")
        print(f" RSI (14)       : {metrics.get('rsi', 0):.2f}")
        
        # Balance & Position
        pos_str = "None (Cash)"
        if self.current_position:
            buy_p = self.current_position["buy_price"]
            curr_p = metrics.get("price", buy_p)
            pnl_p = ((curr_p - buy_p) / buy_p) * 100.0
            pnl_inr = (self.current_position["quantity"] * curr_p) - self.current_position["invested_inr"]
            pos_str = f"ACTIVE ({pnl_p:+.2f}% | INR {pnl_inr:+.2f}) Target: INR {self.current_position.get('target', 0):,.2f}"
            
        print(f" Position       : {pos_str}")
        print(f" Wallet Balance : INR {self.paper_balance_inr:,.2f}")
        
        if prediction:
            dir_tag = f"▲ {prediction['direction']}" if prediction['direction'] == 'UP' else f"▼ {prediction['direction']}" if prediction['direction'] == 'DOWN' else "► SIDEWAYS"
            print("-" * 68)
            print(f" 🔮 WHAT HAPPENS NEXT: [{dir_tag}] ({prediction['probability']}% Confidence)")
            print(f" Projected Target   : INR {prediction['target_price']:,.2f} ({prediction['expected_change_pct']:+.2f}%)")
            print(f" Invalidation Floor : INR {prediction['stop_loss']:,.2f}")
            print(f" Evidence           : {', '.join(prediction.get('confluences', [])[:2])}")
        
        print("-" * 68)
        print(f" Bot Decision   : [{signal}] -> {reason}")
        print("=" * 68)

    def run(self, poll_interval_sec: int = 15):
        print("Starting CoinDCX Predictive Algorithmic Trading Bot...")
        print(f"Mode: {'DRY_RUN (Safe Virtual Trading)' if config.DRY_RUN else 'LIVE REAL ORDERS'}")
        print(f"Pair: {config.SYMBOL} | Timeframe: {config.TIMEFRAME}")
        print("Press Ctrl+C anytime to stop.\n")

        while True:
            try:
                # 1. Fetch latest candles
                df = self.client.get_candles(limit=50)
                if df is None or len(df) == 0:
                    print("[Warning] Could not fetch candle data. Retrying...")
                    time.sleep(poll_interval_sec)
                    continue

                # 2. Run predictive model and indicators
                prediction = predict_next_move(df)
                signal, reason, metrics = evaluate_signal(df, self.current_position)

                # Predictive override: If model has >= 70% UP probability, upgrade to PREDICTIVE BUY
                if signal == "HOLD" and prediction["direction"] == "UP" and prediction["probability"] >= 70 and self.current_position is None:
                    signal = "BUY"
                    reason = f"Predictive model triggered: {prediction['probability']}% UP probability to {prediction['target_price']}"

                # 3. Print live status dashboard
                self.print_dashboard(metrics, signal, reason, prediction)

                # 4. Act on signal
                current_price = metrics["price"]
                if signal == "BUY" and self.current_position is None:
                    self.execute_buy(current_price, metrics, prediction)
                elif signal == "SELL" and self.current_position is not None:
                    self.execute_sell(current_price, reason, metrics)

            except KeyboardInterrupt:
                print("\n[Stopped by user] Bot shut down safely.")
                break
            except Exception as e:
                print(f"[Loop Exception] {e}")

            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
