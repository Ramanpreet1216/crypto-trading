"""
Execution & Risk Management Engine for Trading-bot-XAU.
Manages:
- Dynamic lot sizing based on account balance & stop-loss distance
- Trailing Stop & Breakeven logic
- Pre-News defensive management (auto-breakeven or risk lockdown)
- Real-time PnL calculation & trade persistence (xau_trades.json)
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import config

TRADES_FILE = os.path.join(os.path.dirname(__file__), "xau_trades.json")

class TradeEngine:
    def __init__(self):
        self.balance = config.INITIAL_BALANCE
        self.equity = config.INITIAL_BALANCE
        self.positions: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self.load_state()

    def load_state(self):
        """Load persistent trading state."""
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.balance = data.get("balance", config.INITIAL_BALANCE)
                    self.equity = data.get("equity", self.balance)
                    self.positions = data.get("positions", [])
                    self.closed_trades = data.get("closed_trades", [])
            except Exception as e:
                print(f"[TradeEngine] Error loading state: {e}")

    def save_state(self):
        """Save persistent trading state."""
        try:
            data = {
                "balance": round(self.balance, 2),
                "equity": round(self.equity, 2),
                "positions": self.positions,
                "closed_trades": self.closed_trades,
                "last_updated": time.time()
            }
            with open(TRADES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[TradeEngine] Error saving state: {e}")

    def calculate_lot_size(self, entry_price: float, sl_price: float) -> float:
        """
        Calculate institutional lot size based on fixed account risk %:
        Lots = (Account Balance * Risk %) / (SL Distance * Contract Size)
        """
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0:
            return 0.01

        risk_usd = self.balance * (config.RISK_PER_TRADE_PERCENT / 100.0)
        contract_size = config.CONTRACT_SIZE # 100 oz
        raw_lots = risk_usd / (sl_distance * contract_size)
        
        # Clamp to realistic min/max lots (0.01 to 5.0 lots)
        lots = max(0.01, min(5.0, round(raw_lots, 2)))
        return lots

    def open_position(self, signal: Dict) -> Tuple[bool, str]:
        """Open a new BUY or SELL position with strict risk management."""
        if len(self.positions) >= config.MAX_OPEN_POSITIONS:
            return False, f"Maximum open positions ({config.MAX_OPEN_POSITIONS}) already reached"

        side = signal["action"] # BUY or SELL
        entry_price = signal["price"]
        sl = signal["sl"]
        tp = signal["tp"]
        sl_dist = abs(entry_price - sl)
        lots = float(signal.get("lots")) if signal.get("lots") else self.calculate_lot_size(entry_price, sl)
        lots = max(0.01, min(5.0, round(lots, 2)))

        pos_id = f"XAU_{int(time.time())}_{side}"
        pos = {
            "id": pos_id,
            "symbol": config.SYMBOL,
            "side": side,
            "entry_price": entry_price,
            "current_price": entry_price,
            "lots": lots,
            "sl": sl,
            "tp": tp,
            "initial_sl_dist": sl_dist,
            "open_time": time.time(),
            "open_time_str": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "pnl": 0.0,
            "pnl_percent": 0.0,
            "is_breakeven": False,
            "trailing_active": False,
            "highest_price": entry_price,
            "lowest_price": entry_price,
            "reason": signal.get("reason", "Strategy Signal")
        }

        self.positions.append(pos)
        self.save_state()
        return True, f"Opened {side} {lots} Lots at ${entry_price:.2f} (SL: ${sl:.2f}, TP: ${tp:.2f})"

    def update_positions(self, current_price: float, news_status: Dict) -> List[Dict]:
        """
        Update open positions on every tick:
        - Calculate floating PnL
        - Check TP and SL hits
        - Apply Auto-Breakeven logic
        - Apply Trailing Stop logic
        - Apply Pre-News Defensive Breakeven Protection
        """
        closed_this_tick = []
        contract_size = config.CONTRACT_SIZE

        remaining_positions = []
        for pos in self.positions:
            side = pos["side"]
            entry = pos["entry_price"]
            lots = pos["lots"]
            sl = pos["sl"]
            tp = pos["tp"]
            sl_dist = pos["initial_sl_dist"]

            pos["current_price"] = current_price

            # Calculate floating PnL
            if side == "BUY":
                pnl = (current_price - entry) * lots * contract_size
                pnl_dist = current_price - entry
                if current_price > pos["highest_price"]:
                    pos["highest_price"] = current_price
            else: # SELL
                pnl = (entry - current_price) * lots * contract_size
                pnl_dist = entry - current_price
                if current_price < pos["lowest_price"]:
                    pos["lowest_price"] = current_price

            pos["pnl"] = round(pnl, 2)
            pos["pnl_percent"] = round((pnl / (self.balance * (config.RISK_PER_TRADE_PERCENT / 100.0))) * 100.0, 1)

            # R-Multiple achieved so far
            current_r = pnl_dist / sl_dist if sl_dist > 0 else 0.0

            # 1. PRE-NEWS DEFENSIVE SHIELD:
            # If high-impact news is coming in <= 30 mins and we are in profit (>0.5R), move SL to Breakeven immediately!
            if news_status.get("is_locked", False) and config.AUTO_BREAKEVEN_BEFORE_NEWS:
                if not pos["is_breakeven"] and current_r >= 0.5:
                    if side == "BUY":
                        pos["sl"] = round(entry + 0.10, 2) # entry + 10 cents
                    else:
                        pos["sl"] = round(entry - 0.10, 2)
                    pos["is_breakeven"] = True
                    print(f"[NewsShield Defense] Auto-moved SL to Breakeven for {pos['id']} ahead of news!")

            # 2. STANDARD AUTO-BREAKEVEN:
            # When trade reaches +1.2R profit, move SL to entry to eliminate downside risk
            if not pos["is_breakeven"] and current_r >= config.BREAKEVEN_TRIGGER_R:
                if side == "BUY":
                    pos["sl"] = round(entry + 0.15, 2)
                else:
                    pos["sl"] = round(entry - 0.15, 2)
                pos["is_breakeven"] = True
                print(f"[Breakeven] Activated for {pos['id']} at +{current_r:.2f}R!")

            # 3. TRAILING STOP:
            # When trade reaches +1.5R profit, trail SL behind price
            if config.TRAILING_STOP_ENABLED and current_r >= config.TRAILING_STOP_TRIGGER_R:
                pos["trailing_active"] = True
                trail_distance = sl_dist * 0.8
                if side == "BUY":
                    new_sl = round(pos["highest_price"] - trail_distance, 2)
                    if new_sl > pos["sl"]:
                        pos["sl"] = new_sl
                else: # SELL
                    new_sl = round(pos["lowest_price"] + trail_distance, 2)
                    if new_sl < pos["sl"]:
                        pos["sl"] = new_sl

            # 4. CHECK EXIT CONDITIONS (TP or SL)
            close_reason = None
            if side == "BUY":
                if current_price >= tp:
                    close_reason = f"Take-Profit target reached (${tp:.2f})"
                elif current_price <= sl:
                    close_reason = f"Stop-Loss hit at ${sl:.2f} (Risk Defense)"
            else: # SELL
                if current_price <= tp:
                    close_reason = f"Take-Profit target reached (${tp:.2f})"
                elif current_price >= sl:
                    close_reason = f"Stop-Loss hit at ${sl:.2f} (Risk Defense)"

            if close_reason:
                pos["exit_price"] = current_price
                pos["close_time"] = time.time()
                pos["close_time_str"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                pos["close_reason"] = close_reason
                pos["final_pnl"] = pos["pnl"]
                pos["is_win"] = (pos["pnl"] > 0)
                
                # Update balance
                self.balance = round(self.balance + pos["pnl"], 2)
                self.closed_trades.append(pos)
                closed_this_tick.append(pos)
            else:
                remaining_positions.append(pos)

        self.positions = remaining_positions
        # Update equity
        floating_sum = sum(p["pnl"] for p in self.positions)
        self.equity = round(self.balance + floating_sum, 2)
        self.save_state()
        return closed_this_tick

    def get_performance_metrics(self) -> Dict:
        """Calculate comprehensive trading audit metrics."""
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_profit": 0.0,
                "profit_factor": 0.0,
                "balance": self.balance,
                "equity": self.equity
            }

        wins = [t for t in self.closed_trades if t.get("is_win", False)]
        losses = [t for t in self.closed_trades if not t.get("is_win", False)]
        
        gross_profit = sum(t.get("final_pnl", 0) for t in wins)
        gross_loss = abs(sum(t.get("final_pnl", 0) for t in losses))
        net_profit = round(gross_profit - gross_loss, 2)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0
        win_rate = round((len(wins) / total_trades) * 100.0, 1)

        return {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_profit": net_profit,
            "profit_factor": profit_factor,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2)
        }
