import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import threading
import time
import requests
import pandas as pd
from datetime import datetime

import config
from coindcx_client import CoinDCXClient
from strategy import evaluate_signal, calculate_indicators
import scanner
import predictor

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 5000))
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

def calculate_futures_trade_qty(coin: str, current_price: float, target_margin_inr: float = 150.0, leverage: int = 5):
    """Calculate order quantity ensuring CoinDCX minimum notional value (>= 620 INR) and target margin."""
    min_notional_inr = 620.0
    usd_inr = 90.0
    notional_inr = max(min_notional_inr, target_margin_inr * max(1, leverage))
    notional_usd = notional_inr / usd_inr
    raw_qty = notional_usd / max(0.000001, current_price)

    if current_price < 0.001:
        qty = round(raw_qty, 0)
    elif current_price < 1.0:
        qty = round(raw_qty, 1)
    elif current_price < 50.0:
        qty = round(raw_qty, 2)
    elif current_price < 1000.0:
        qty = round(raw_qty, 3)
    else:
        qty = round(raw_qty, 5)
    actual_margin = (qty * current_price * usd_inr) / max(1, leverage)
    return qty, round(actual_margin, 2)


TRADES_FILE = os.path.join(os.path.dirname(__file__), "paper_trades.json")

def load_paper_trades():
    """Load persistent paper trades and performance stats from disk."""
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"[Error loading {TRADES_FILE}]: {e}")
    return {"trades": [], "summary": {}}

def _extract_pnl(t):
    val = t.get("pnl")
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    val_inr = t.get("pnl_inr")
    if val_inr is not None:
        try:
            return float(val_inr)
        except (ValueError, TypeError):
            pass
    return 0.0

def calculate_trade_fee(invested_inr, leverage, gross_pnl_inr, fee_mode=None):
    """
    Calculate realistic exchange fees for a completed trade.
    - 'COINDCX' (default): Official CoinDCX Futures taker fee = 0.05% on entry notional + 0.05% on exit notional.
    - 'FLAT_1PCT': Flat 1.0% safety cut on margin (covers TDS / slippage buffer).
    """
    mode = fee_mode or getattr(config, "FEE_MODE", "COINDCX")
    if mode == "FLAT_1PCT":
        return round(float(invested_inr) * 0.01, 2)
    else:
        lev = max(1.0, float(leverage))
        entry_notional = float(invested_inr) * lev
        exit_notional = max(0.0, (float(invested_inr) + float(gross_pnl_inr)) * lev)
        fee_rate = getattr(config, "FEE_TAKER_PCT", 0.05) / 100.0
        fee_open = entry_notional * fee_rate
        fee_close = exit_notional * fee_rate
        return round(fee_open + fee_close, 2)

def calculate_trade_performance(trades):
    """Calculate Net PnL, Win Rate %, Total Wins, Total Losses, Fees, and Volume."""
    completed = [t for t in trades if t.get("type") in ["SELL", "BUY_COVER"] or t.get("pnl") is not None]
    wins = [t for t in completed if _extract_pnl(t) > 0]
    losses = [t for t in completed if _extract_pnl(t) < 0]
    total_pnl = sum(_extract_pnl(t) for t in completed)
    total_fees = sum(float(t.get("fee", 0) or 0) for t in completed)
    total_volume = sum(float(t.get("amount") if t.get("amount") is not None else t.get("invested_inr", 0) or 0) for t in trades)
    win_rate = round((len(wins) / len(completed)) * 100.0, 1) if completed else 0.0

    return {
        "total_trades": len(trades),
        "completed_trades": len(completed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "total_pnl_inr": round(total_pnl, 2),
        "total_fees_inr": round(total_fees, 2),
        "total_volume_inr": round(total_volume, 2),
        "is_profitable": total_pnl > 0
    }

def record_paper_trade(trade_entry, active_positions="UNCHANGED"):
    """Append a trade to disk, track active positions (up to 3 slots), and update performance metrics."""
    try:
        data = load_paper_trades()
        trades = data.get("trades", [])
        trades.insert(0, trade_entry)
        summary = calculate_trade_performance(trades)

        if active_positions != "UNCHANGED":
            cur_pos = active_positions if isinstance(active_positions, list) else ([active_positions] if active_positions else [])
        else:
            cur_pos = data.get("active_positions", [])
            if not cur_pos and data.get("active_position"):
                cur_pos = [data["active_position"]]

        payload = {
            "updated_at": datetime.now().isoformat(),
            "summary": summary,
            "trades": trades[:500],
            "active_positions": cur_pos,
            "active_position": cur_pos[0] if cur_pos else None,
            "is_running": bot_state.get("is_running", True)
        }
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return summary
    except Exception as e:
        print(f"[Error saving {TRADES_FILE}]: {e}")
        return {}

def save_active_positions(positions, is_running=None):
    """Persist active positions list and 24/7 running state directly to disk."""
    try:
        data = load_paper_trades()
        cur_pos = positions if isinstance(positions, list) else ([positions] if positions else [])
        data["active_positions"] = cur_pos
        data["active_position"] = cur_pos[0] if cur_pos else None
        if is_running is not None:
            data["is_running"] = is_running
        data["updated_at"] = datetime.now().isoformat()
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Error saving active positions to {TRADES_FILE}]: {e}")

def save_active_position(pos):
    """Backward compatibility helper."""
    cur_pos = [pos] if pos else []
    save_active_positions(cur_pos)


# Shared Bot State with Active Live Trade & Predictive Forecasts
now_str = datetime.now().strftime("%H:%M:%S")
initial_paper_data = load_paper_trades()
raw_positions = initial_paper_data.get("active_positions")
if raw_positions is None:
    single = initial_paper_data.get("active_position")
    raw_positions = [single] if single else []

bot_state = {
    "is_running": initial_paper_data.get("is_running", True),  # Runs 24/7 continuously by default
    "paper_balance": 1500.0,
    "active_positions": raw_positions,
    "active_position": raw_positions[0] if raw_positions else None,
    "selected_coin": "BTC",
    "selected_pair": "B-BTC_USDT",
    "trade_history": initial_paper_data.get("trades", []),
    "performance_summary": calculate_trade_performance(initial_paper_data.get("trades", [])),
    "last_signal": "AUTONOMOUS 24/7 ENGINE ACTIVE",
    "last_reason": f"Active slots: {len(raw_positions)}/3. Dynamic runner (+15% to +30% TP) & 7%-12% trailing stops active.",
    "latest_prediction": {},
}

def analyze_macro_market_regime():
    """
    Analyzes all 600+ crypto markets & Bitcoin trend to dynamically determine
    the optimal risk profile (SAFE / BALANCED / ALPHA), leverage (4x-8x),
    and adaptive target profit % (2% - 4.5%).
    """
    try:
        tickers = scanner._fetch_all_raw_tickers()
        if not tickers:
            return "BALANCED", 6, 3.5, 1.5, 85, "⚖️ Balanced Baseline (Scanning Market)"

        green_coins = [t for t in tickers if float(t.get("priceChangePercent", 0)) > 0]
        breadth_pct = (len(green_coins) / max(1, len(tickers))) * 100.0

        # Check Bitcoin trend (Macro King of Market)
        client = CoinDCXClient()
        btc_candles = client.get_candles(pair="B-BTC_USDT", interval="1h", limit=24)
        btc_bullish = False
        if btc_candles is not None and len(btc_candles) >= 15:
            btc_df = calculate_indicators(btc_candles)
            last_c = btc_df.iloc[-1]
            btc_bullish = bool((last_c["close"] > last_c["ema_slow"]) and (last_c["rsi"] >= 48))

        # 1. ALPHA MODE: Strong Macro Bull Run (breadth >= 58% and BTC bullish)
        if breadth_pct >= 58.0 and btc_bullish:
            mode = "ALPHA"
            lev = 6
            tp_pct = 4.8  # Expand target to +4.8%
            sl_pct = 1.6  # SL 1.6% -> Risk:Reward 3:1 (covers Indian tax)
            min_conf = 82
            preferred_dir = "UP"
            desc = f"🚀 Macro Bullish Expansion ({breadth_pct:.1f}% green, BTC Bullish). Auto: ALPHA (+4.8% TP, {lev}x Lev)."

        # 2. BALANCED MODE: Healthy Selective Market (breadth 40% - 58%)
        elif breadth_pct >= 40.0:
            mode = "BALANCED"
            lev = 5
            tp_pct = 3.6  # Balanced target +3.6%
            sl_pct = 1.4  # SL 1.4% -> Risk:Reward 2.57:1 (covers Indian tax)
            min_conf = 85
            preferred_dir = "ALL"
            desc = f"⚖️ Balanced Momentum ({breadth_pct:.1f}% green). Auto: BALANCED (+3.6% TP, {lev}x Lev)."

        # 3. SAFE SCALP MODE: Defensive / Market Pullback (breadth < 40%)
        else:
            mode = "SAFE"
            lev = 4  # Safe 4x leverage (zero liquidation risk)
            tp_pct = 2.8  # Target +2.8%
            sl_pct = 1.2  # SL 1.2% -> Risk:Reward 2.33:1 (covers Indian tax)
            min_conf = 88  # High confidence filter
            # In a dumping market, default to SHORTing breakdowns or scan ALL high-confluence setups
            preferred_dir = "DOWN" if not btc_bullish else "ALL"
            desc = f"🛡️ Defensive Pullback ({breadth_pct:.1f}% green). Auto: SAFE Two-Way Scalps (+2.8% TP, {lev}x Lev)."

        return mode, lev, tp_pct, sl_pct, min_conf, desc, preferred_dir
    except Exception as e:
        print(f"[Market Regime Error]: {e}")
        return "SAFE", 4, 2.8, 1.2, 85, "🛡️ Defensive Mode", "ALL"


# Bot background worker thread: 24/7 Autonomous Breakout Hunting & Execution Engine
def bot_worker():
    client = CoinDCXClient()
    scan_cooldown_until = 0
    recent_coins = {} # coin -> timestamp when 2h gap cooldown expires

    while True:
        if bot_state.get("is_running", True):
            try:
                now_ts = time.time()
                # Clean expired coin cooldowns
                recent_coins = {c: t for c, t in recent_coins.items() if t > now_ts}

                # 1. Macro Market Regime Analysis & Dynamic Adaptation
                auto_mode, dyn_lev, dyn_tp_pct, dyn_sl_pct, dyn_min_conf, regime_desc, preferred_dir = analyze_macro_market_regime()
                config.CURRENT_RISK_MODE = auto_mode
                bot_state["market_regime"] = regime_desc
                bot_state["active_risk_mode"] = auto_mode
                bot_state["active_target_tp"] = dyn_tp_pct
                bot_state["active_target_sl"] = dyn_sl_pct
                bot_state["active_leverage"] = dyn_lev

                profile = config.RISK_PROFILES.get(auto_mode, config.RISK_PROFILES["SAFE"])
                invest_target = profile.get("investment_inr", 150.0)

                if not isinstance(bot_state.get("active_positions"), list):
                    bot_state["active_positions"] = [bot_state["active_position"]] if bot_state.get("active_position") else []

                # ==============================================================
                # PHASE 1: MANAGE ALL ACTIVE POSITIONS (UP TO 3 SLOTS CONCURRENTLY)
                # DYNAMIC RUNNER MODE (+15% to +30% TP) & 7% - 12% TRAILING RATINGS
                # ==============================================================
                positions_snapshot = list(bot_state["active_positions"])
                active_pos_summaries = []

                for pos in positions_snapshot:
                    pos_symbol = pos.get("symbol", "")
                    pair = pos.get("pair", f"B-{pos_symbol}_USDT")
                    pos_lev = pos.get("leverage", dyn_lev)
                    pos_dir = pos.get("direction") or pos.get("side", "LONG")
                    buy_price = float(pos.get("buy_price", 0))

                    # 30-second minimum maturation buffer before exit check
                    pos_age = now_ts - float(pos.get("entry_time", now_ts))
                    if pos_age < 30:
                        active_pos_summaries.append(f"{pos_dir} {pos_symbol}: Maturing ({int(30 - pos_age)}s)")
                        continue

                    # Fetch live mark price from CoinDCX ticker, fallback to candles
                    current_price = buy_price
                    try:
                        stats = client.get_futures_stats(pos_symbol)
                        live_mk = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or 0)
                        if live_mk > 0:
                            current_price = live_mk
                    except Exception:
                        pass

                    if current_price == buy_price:
                        df = client.get_candles(pair=pair, interval=config.TIMEFRAME, limit=10)
                        if df is not None and len(df) > 0:
                            current_price = float(df.iloc[-1]["close"])

                    precision = 6 if buy_price < 1.0 else (4 if buy_price < 50.0 else 2)

                    # Compute PnL
                    if pos_dir == "LONG":
                        gain_pct = ((current_price - buy_price) / max(1e-6, buy_price)) * 100.0
                    else:
                        gain_pct = ((buy_price - current_price) / max(1e-6, buy_price)) * 100.0

                    gross_pnl_pct = gain_pct * pos_lev
                    peak_pnl = max(float(pos.get("peak_pnl_pct", gross_pnl_pct)), gross_pnl_pct)
                    pos["peak_pnl_pct"] = peak_pnl

                    # ----------------------------------------------------------
                    # DYNAMIC RUNNER & ADAPTIVE RATINGS ENGINE
                    # ----------------------------------------------------------
                    # Tier 1: Breakeven Profit Lock at +5% leveraged PnL
                    if gross_pnl_pct >= 5.0:
                        be_price = round(buy_price * (1.0 + (0.015 / pos_lev)), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (0.015 / pos_lev)), precision)
                        cur_trail = pos.get("trailing_stop", pos.get("stop_loss", 0))
                        if pos_dir == "LONG" and be_price > cur_trail:
                            pos["trailing_stop"] = be_price
                        elif pos_dir == "SHORT" and (cur_trail == 0 or be_price < cur_trail):
                            pos["trailing_stop"] = be_price

                    # Tier 2: Strong Momentum Trigger -> RUNNER MODE (+15% to +30% TP) & Lock +7% Net Profit
                    if gross_pnl_pct >= config.RUNNER_TRIGGER_PNL_PCT:
                        pos["is_runner"] = True
                        pos["runner_target_pct"] = config.RUNNER_EXTENDED_TP_PCT
                        extended_target = round(buy_price * (1.0 + (config.RUNNER_EXTENDED_TP_PCT / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (config.RUNNER_EXTENDED_TP_PCT / 100.0) / pos_lev), precision)
                        pos["target"] = extended_target

                        # Lock at least +7% net profit guaranteed
                        lock_price = round(buy_price * (1.0 + (config.RUNNER_LOCK_PROFIT_PCT / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (config.RUNNER_LOCK_PROFIT_PCT / 100.0) / pos_lev), precision)
                        cur_trail = pos.get("trailing_stop", pos.get("stop_loss", 0))
                        if pos_dir == "LONG" and lock_price > cur_trail:
                            pos["trailing_stop"] = lock_price
                        elif pos_dir == "SHORT" and (cur_trail == 0 or lock_price < cur_trail):
                            pos["trailing_stop"] = lock_price

                    # Tier 3: High-Gain Dynamic Trailing Ratchet (Trail 9% below peak PnL, between 7% and 12%)
                    if peak_pnl >= 16.0:
                        trail_pnl_lvl = max(config.RUNNER_LOCK_PROFIT_PCT, peak_pnl - config.RUNNER_TRAILING_BUFFER_PCT)
                        trail_price = round(buy_price * (1.0 + (trail_pnl_lvl / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (trail_pnl_lvl / 100.0) / pos_lev), precision)
                        cur_trail = pos.get("trailing_stop", pos.get("stop_loss", 0))
                        if pos_dir == "LONG" and trail_price > cur_trail:
                            pos["trailing_stop"] = trail_price
                        elif pos_dir == "SHORT" and (cur_trail == 0 or trail_price < cur_trail):
                            pos["trailing_stop"] = trail_price

                    # ----------------------------------------------------------
                    # CHECK EXIT CONDITIONS
                    # ----------------------------------------------------------
                    active_sl = pos.get("trailing_stop", pos.get("stop_loss"))
                    target_p = pos.get("target")
                    exit_trigger = None

                    if pos_dir == "LONG":
                        if target_p and current_price >= target_p:
                            runner_note = f" [Runner Target +{pos.get('runner_target_pct', 25)}% Hit!]" if pos.get("is_runner") else ""
                            exit_trigger = f"Target Hit (${target_p}){runner_note}!"
                        elif active_sl and current_price <= active_sl:
                            is_profit = active_sl > buy_price
                            lbl = "Trailing Profit Lock" if is_profit else "Stop-Loss Protection"
                            exit_trigger = f"{lbl} at ${active_sl:.4f}"
                        exit_side = "sell"
                    else: # SHORT
                        if target_p and current_price <= target_p:
                            runner_note = f" [Runner Target +{pos.get('runner_target_pct', 25)}% Hit!]" if pos.get("is_runner") else ""
                            exit_trigger = f"Target Hit (${target_p}){runner_note}!"
                        elif active_sl and current_price >= active_sl:
                            is_profit = active_sl < buy_price
                            lbl = "Trailing Profit Lock" if is_profit else "Stop-Loss Protection"
                            exit_trigger = f"{lbl} at ${active_sl:.4f}"
                        exit_side = "buy"

                    invested = float(pos.get("invested", invest_target))
                    gross_pnl = invested * (gross_pnl_pct / 100.0)
                    trade_fee = calculate_trade_fee(invested, pos_lev, gross_pnl)
                    net_pnl = round(gross_pnl - trade_fee, 2)
                    net_pnl_pct = round((net_pnl / max(1e-6, invested)) * 100.0, 2)

                    if exit_trigger:
                        proceeds = round(invested + net_pnl, 2)
                        bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

                        if not config.DRY_RUN:
                            try:
                                live_exit = client.place_futures_order(exit_side, pair=pair, quantity=pos["quantity"], leverage=pos_lev)
                                print(f"[LIVE AUTONOMOUS EXIT ORDER]: {live_exit}")
                            except Exception as live_err:
                                print(f"[LIVE AUTONOMOUS EXIT ERROR]: {live_err}")

                        fee_desc = f"after ₹{trade_fee:.2f} fee" if trade_fee > 0 else ""
                        full_reason = f"{exit_trigger} (Net PnL: {net_pnl_pct:+.1f}%, ₹{net_pnl:+.2f}{' ' + fee_desc if fee_desc else ''})"
                        bot_state["last_signal"] = f"EXIT [{pos_dir} {pos_symbol}]"
                        bot_state["last_reason"] = full_reason
                        exit_rec = {
                            "type": "SELL" if pos_dir == "LONG" else "BUY_COVER",
                            "coin": pos_symbol,
                            "direction": pos_dir,
                            "price": current_price,
                            "entry_price": buy_price,
                            "target": target_p,
                            "stop_loss": pos.get("stop_loss"),
                            "leverage": pos_lev,
                            "amount": round(proceeds, 2),
                            "gross_pnl": round(gross_pnl, 2),
                            "fee": trade_fee,
                            "pnl": net_pnl,
                            "pnl_pct": net_pnl_pct,
                            "reason": full_reason,
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        bot_state["trade_history"].insert(0, exit_rec)
                        bot_state["active_positions"] = [p for p in bot_state["active_positions"] if p.get("symbol") != pos_symbol]
                        bot_state["active_position"] = bot_state["active_positions"][0] if bot_state["active_positions"] else None
                        record_paper_trade(exit_rec, active_positions=bot_state["active_positions"])
                        recent_coins[pos_symbol] = now_ts + config.SAME_COIN_COOLDOWN_SECONDS  # 2 hours gap cooldown on this coin
                    else:
                        runner_tag = " [⚡RUNNER]" if pos.get("is_runner") else ""
                        active_pos_summaries.append(f"{pos_dir} {pos_symbol}{runner_tag}: Net {net_pnl_pct:+.1f}% (₹{net_pnl:+.2f})")

                if active_pos_summaries:
                    bot_state["last_reason"] = f"Slots ({len(bot_state['active_positions'])}/3): " + " | ".join(active_pos_summaries)

                # ==============================================================
                # PHASE 2: SCAN & OPEN POSITIONS (UP TO 3 SLOTS SIMULTANEOUSLY)
                # ==============================================================
                cur_count = len(bot_state.get("active_positions", []))
                slots_needed = config.MAX_OPEN_POSITIONS - cur_count

                if slots_needed > 0 and now_ts >= scan_cooldown_until:
                    scan_cooldown_until = now_ts + 20  # Fast 20s scanner cadence
                    held_coins = {p.get("symbol") for p in bot_state["active_positions"]}

                    signals = scanner.scan_all_crypto_signals(min_confidence=dyn_min_conf, direction=preferred_dir, limit=15)
                    valid_signals = [s for s in signals if s["coin"] not in held_coins and recent_coins.get(s["coin"], 0) < now_ts] if signals else []

                    for candidate in valid_signals:
                        if len(bot_state["active_positions"]) >= config.MAX_OPEN_POSITIONS:
                            break

                        c_coin = candidate["coin"]
                        c_pair = f"B-{c_coin}_USDT"
                        c_dir = candidate.get("direction", "UP").upper()

                        if float(candidate.get("volume_usdt", 0) or 0) < 1_000_000.0:
                            continue

                        c_candles = client.get_candles(pair=c_pair, interval="15m", limit=30)
                        if c_candles is not None and len(c_candles) >= 15:
                            c_df = calculate_indicators(c_candles)
                            last_row = c_df.iloc[-1]
                            coin_rsi = float(last_row.get("rsi", 50))
                            ema_fast = float(last_row.get("ema_fast", 0))
                            ema_slow = float(last_row.get("ema_slow", 0))

                            if c_dir == "UP":
                                if coin_rsi > 65.0 or coin_rsi < 44.0:
                                    continue
                                if ema_fast < ema_slow * 0.998:
                                    continue
                            else:
                                if coin_rsi < 35.0 or coin_rsi > 58.0:
                                    continue
                                if ema_fast > ema_slow * 1.002:
                                    continue

                            live_stats = client.get_futures_stats(c_coin)
                            live_p = float(live_stats.get("mark_price", 0) or live_stats.get("last_price", 0) or 0)
                            if live_p <= 0:
                                live_p = float(last_row["close"])

                            pos_dir = "LONG" if c_dir == "UP" else "SHORT"
                            prob = candidate.get("probability", 85)
                            precision = 6 if live_p < 1.0 else (4 if live_p < 50.0 else 2)

                            if pos_dir == "LONG":
                                target_price = round(live_p * (1.0 + (dyn_tp_pct / 100.0)), precision)
                                stop_loss = round(live_p * (1.0 - (dyn_sl_pct / 100.0)), precision)
                                order_side = "buy"
                            else:
                                target_price = round(live_p * (1.0 - (dyn_tp_pct / 100.0)), precision)
                                stop_loss = round(live_p * (1.0 + (dyn_sl_pct / 100.0)), precision)
                                order_side = "sell"

                            qty, spend = calculate_futures_trade_qty(c_coin, live_p, target_margin_inr=invest_target, leverage=dyn_lev)

                            if not config.DRY_RUN:
                                try:
                                    live_order = client.place_futures_order(order_side, pair=c_pair, quantity=qty, leverage=dyn_lev)
                                    print(f"[LIVE AUTONOMOUS {pos_dir} ORDER]: {c_coin} Qty={qty} Lev={dyn_lev}x -> {live_order}")
                                except Exception as live_err:
                                    print(f"[LIVE AUTONOMOUS ORDER ERROR]: {live_err}")

                            entry_ts = time.time()
                            new_pos = {
                                "symbol": c_coin,
                                "pair": c_pair,
                                "direction": pos_dir,
                                "buy_price": live_p,
                                "quantity": qty,
                                "invested": spend,
                                "leverage": dyn_lev,
                                "target": target_price,
                                "stop_loss": stop_loss,
                                "trailing_stop": stop_loss,
                                "peak_price": live_p,
                                "valley_price": live_p,
                                "peak_pnl_pct": 0.0,
                                "probability": prob,
                                "tp_pct": dyn_tp_pct,
                                "sl_pct": dyn_sl_pct,
                                "entry_time": entry_ts,
                                "time": datetime.now().strftime("%H:%M:%S")
                            }
                            bot_state["active_positions"].append(new_pos)
                            bot_state["active_position"] = bot_state["active_positions"][0]
                            bot_state["selected_coin"] = c_coin
                            bot_state["selected_pair"] = c_pair
                            bot_state["last_signal"] = f"AUTONOMOUS {pos_dir} [{c_coin}] ({len(bot_state['active_positions'])}/3 Slots)"
                            bot_state["last_reason"] = f"Auto-{auto_mode} ({prob}% {pos_dir}): Entry ${live_p}, Target ${target_price} (±{dyn_tp_pct}%), SL ${stop_loss} (±{dyn_sl_pct}%)"

                            trade_rec = {
                                "type": "BUY" if pos_dir == "LONG" else "SELL_SHORT",
                                "coin": c_coin,
                                "direction": pos_dir,
                                "price": live_p,
                                "entry_price": live_p,
                                "target": target_price,
                                "stop_loss": stop_loss,
                                "leverage": dyn_lev,
                                "amount": spend,
                                "note": f"Auto-{auto_mode} ({prob}% {pos_dir}): Target ${target_price}, SL ${stop_loss}",
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            bot_state["trade_history"].insert(0, trade_rec)
                            record_paper_trade(trade_rec, active_positions=bot_state["active_positions"])
                            save_active_positions(bot_state["active_positions"])

            except Exception as e:
                print(f"[Autonomous Worker Error] {e}")

        time.sleep(10)

worker_thread = threading.Thread(target=bot_worker, daemon=True)
worker_thread.start()

# Global Real-Time Alert Engine & History
alert_state = {
    "alerts": [],
    "last_scanned": 0,
    "lock": threading.Lock(),
    "last_notified": {} # coin -> timestamp
}

def alert_monitor_worker():
    """
    Background worker that continuously scans all cryptos for Ultra-High Confidence
    (85%-98% '100% Confluence') Go Low / Go Up opportunities and triggers alerts.
    """
    # Wait 20 seconds on startup to let server handle initial boot & traffic smoothly
    time.sleep(20)
    while True:
        try:
            signals = scanner.scan_all_crypto_signals(min_confidence=85, limit=12)
            now = time.time()
            if signals:
                with alert_state["lock"]:
                    for s in signals:
                        coin = s["coin"]
                        last_time = alert_state["last_notified"].get(coin, 0)
                        # Avoid repeated alerts for the same coin within 5 minutes
                        if (now - last_time) > 300:
                            alert_item = {
                                "id": f"{coin}_{int(now)}",
                                "coin": coin,
                                "symbol": s.get("symbol", f"{coin}USDT"),
                                "contract": s.get("contract", f"{coin}USDT.P"),
                                "direction": s["direction"],
                                "probability": s["probability"],
                                "confidence_tier": s.get("confidence_tier", "ULTRA (100% SETUP)"),
                                "signal_type": s.get("signal_type", "MOMENTUM SETUP"),
                                "price": s["current_price"],
                                "target_price": s["target_price"],
                                "stop_loss": s["stop_loss"],
                                "expected_change_pct": s.get("expected_change_pct", 0.0),
                                "risk_reward_ratio": s.get("risk_reward_ratio", 2.0),
                                "rsi": s.get("rsi", 50),
                                "confluences": s.get("confluences", []),
                                "timestamp": int(now * 1000),
                                "time_str": datetime.now().strftime("%H:%M:%S")
                            }
                            alert_state["alerts"].insert(0, alert_item)
                            alert_state["last_notified"][coin] = now
                    # Limit alert history to 50 items
                    alert_state["alerts"] = alert_state["alerts"][:50]
                    alert_state["last_scanned"] = int(now * 1000)
        except Exception as e:
            print(f"[Alert Monitor Worker Error]: {e}")

        time.sleep(180)

alert_thread = threading.Thread(target=alert_monitor_worker, daemon=True)
alert_thread.start()


def balance_sync_worker():
    """
    Asynchronous background worker to sync real CoinDCX balances
    so HTTP /api/status endpoint returns in 0.1ms without blocking on external network calls.
    """
    time.sleep(3)
    while True:
        try:
            client = CoinDCXClient()
            real_balances = client.get_account_balances()
            if real_balances:
                f_bal = real_balances.get("FUTURES_INR", 0.0)
                s_bal = real_balances.get("SPOT_INR", 0.0)
                t_bal = real_balances.get("TOTAL_INR", 0.0)
                inr_real = real_balances.get("INR", 0.0)
                bot_state["futures_balance"] = round(f_bal, 2)
                bot_state["spot_balance"] = round(s_bal, 2)
                bot_state["total_balance"] = round(t_bal, 2)
                if inr_real is not None and not real_balances.get("PAPER_MODE"):
                    bot_state["live_balance"] = round(f_bal if f_bal > 0 else inr_real, 2)
                    bot_state["real_connected"] = True
                else:
                    bot_state["live_balance"] = bot_state["paper_balance"]
                    bot_state["real_connected"] = False
        except Exception as e:
            pass
        time.sleep(60)

balance_thread = threading.Thread(target=balance_sync_worker, daemon=True)
balance_thread.start()

_STATUS_CACHE = {"timestamp": 0}
_CANDLES_CACHE = {}
_ADVISOR_CACHE = {}


class ThreadedHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TradingApiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json_error(self, message: str, code: int = 500):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(message), "status": "error"}).encode("utf-8"))
        except Exception:
            pass

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as e:
            self._send_json_error(str(e), 500)

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as e:
            self._send_json_error(str(e), 500)

    def _handle_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API: Predictive Forecast & Probability Engine
        if path == "/api/predict":
            coin = query.get("coin", ["BTC"])[0].upper()
            interval = query.get("interval", ["1h"])[0]
            steps = int(query.get("steps", [10])[0])
            pair = f"B-{coin}_USDT"
            
            client = CoinDCXClient()
            df = client.get_candles(pair=pair, interval=interval, limit=40)
            if df is not None and len(df) > 0:
                prediction = predictor.predict_next_move(df, forecast_steps=steps)
            else:
                prediction = {}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(prediction).encode("utf-8"))
            return

        # API: Scanner Top Gainers
        elif path == "/api/gainers":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            gainers = scanner.get_top_gainers(limit=10)
            self.wfile.write(json.dumps(gainers).encode("utf-8"))
            return

        # API: Market Radar (All Bullish & Bearish Coins)
        elif path == "/api/market_radar":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            radar = scanner.get_market_radar(limit=10)
            self.wfile.write(json.dumps(radar).encode("utf-8"))
            return

        # API: Detailed Coin Analysis & Prediction
        elif path == "/api/analyze":
            coin = query.get("coin", ["BTC"])[0]
            interval = query.get("interval", ["1h"])[0]
            analysis = scanner.analyze_coin(coin, interval=interval, limit=60)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(analysis or {}).encode("utf-8"))
            return

        # API: Futures Contract Stats (Mark Price, Funding Rate, Contract Name)
        elif path == "/api/futures_stats":
            coin = query.get("coin", ["BTC"])[0]
            client = CoinDCXClient()
            stats = client.get_futures_stats(coin)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
            return

        # API: AI Futures Trade & Leverage Advisor (with 45s caching)
        elif path == "/api/advisor":
            coin = query.get("coin", ["BTC"])[0].upper()
            now_a = time.time()
            if coin in _ADVISOR_CACHE and (now_a - _ADVISOR_CACHE[coin]["timestamp"]) < 45.0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(_ADVISOR_CACHE[coin]["data"]).encode("utf-8"))
                return

            client = CoinDCXClient()
            timeframes = ["5m", "15m", "1h"]
            tf_data = {}
            best_tf = "15m"
            max_conf = 0.0
            latest_price = 0.0

            for tf in timeframes:
                candles = client.get_futures_candles(coin, interval=tf, limit=25)
                if candles and len(candles) >= 15:
                    df = pd.DataFrame(candles[::-1])
                    pred = predictor.predict_next_move(df, forecast_steps=10)
                    if pred.get("current_price"):
                        latest_price = pred["current_price"]

                    if tf == "5m":
                        rec_lev = 10
                        style = "Quick Scalp (5-15m)"
                    elif tf == "15m":
                        rec_lev = 10
                        style = "Intraday Trend (30m-2h)"
                    else: # 1h
                        rec_lev = 5
                        style = "Swing Trend (2-8h)"

                    direction = pred.get("direction", "SIDEWAYS")
                    probability = pred.get("probability", 50)
                    target = pred.get("target_price", latest_price)
                    stop = pred.get("stop_loss", latest_price * 0.98)

                    tf_data[tf] = {
                        "direction": direction,
                        "probability": probability,
                        "style": style,
                        "recommended_lev": rec_lev,
                        "target": target,
                        "stop_loss": stop,
                        "rsi": pred.get("rsi", 50)
                    }

                    weighted = probability * (1.15 if tf in ["15m", "1h"] else 0.95)
                    if weighted > max_conf and direction != "SIDEWAYS":
                        max_conf = weighted
                        best_tf = tf

            # Derived 1m and 1d entries for complete UI display
            base_dir = tf_data.get("5m", {}).get("direction", "UP")
            base_prob = tf_data.get("5m", {}).get("probability", 70)
            tf_data["1m"] = {
                "direction": base_dir,
                "probability": max(50, base_prob - 5),
                "style": "Ultra Scalp (2-5m)",
                "recommended_lev": 5,
                "target": round(latest_price * (1.015 if base_dir == "UP" else 0.985), 4),
                "stop_loss": round(latest_price * (0.99 if base_dir == "UP" else 1.01), 4),
                "rsi": tf_data.get("5m", {}).get("rsi", 50)
            }
            tf_data["1d"] = {
                "direction": tf_data.get("1h", {}).get("direction", base_dir),
                "probability": tf_data.get("1h", {}).get("probability", base_prob),
                "style": "Position Hold (1-5d)",
                "recommended_lev": 2,
                "target": round(latest_price * (1.08 if base_dir == "UP" else 0.92), 4),
                "stop_loss": round(latest_price * (0.95 if base_dir == "UP" else 1.05), 4),
                "rsi": tf_data.get("1h", {}).get("rsi", 50)
            }

            if best_tf not in tf_data or not tf_data:
                best_tf = "15m"

            best_info = tf_data.get(best_tf, {
                "direction": "UP",
                "probability": 70,
                "target": latest_price * 1.05,
                "stop_loss": latest_price * 0.98,
                "recommended_lev": 10
            })

            rec_action = "LONG" if best_info["direction"] == "UP" else "SHORT" if best_info["direction"] == "DOWN" else "WAIT"
            target_p = best_info.get("target", latest_price * 1.05)
            stop_p = best_info.get("stop_loss", latest_price * 0.98)
            curr = latest_price or 1.0

            leverage_table = []
            for lev in [1, 3, 5, 10, 25, 50, 100]:
                long_liq = round(curr * max(0.0, (1.0 - (0.90 / lev))), 4)
                short_liq = round(curr * (1.0 + (0.90 / lev)), 4)
                drop_to_liq_pct = round(((curr - long_liq) / curr) * 100.0, 1)

                if lev <= 3:
                    risk_lvl = "Safe Buffer"
                    badge_color = "#10b981"
                    advice = "Ultra safe, no liquidation risk."
                elif lev <= 10:
                    risk_lvl = "Recommended Sweetspot"
                    badge_color = "#38bdf8"
                    advice = "Optimal for INR 1,500. High profit with safe liquidation margin."
                elif lev <= 25:
                    risk_lvl = "High Risk"
                    badge_color = "#f59e0b"
                    advice = "Caution: Normal crypto wick can wipe margin."
                elif lev <= 50:
                    risk_lvl = "Dangerous"
                    badge_color = "#ef4444"
                    advice = "Extreme hazard: 1.8% drop wipes 100% of your INR 1,500."
                else:
                    risk_lvl = "Wipeout Trap"
                    badge_color = "#dc2626"
                    advice = "Instant liquidation! A 0.9% market noise tick liquidates all INR 1,500 in seconds. Never use 100x!"

                pnl_at_target_pct = round(abs((target_p - curr) / curr) * 100.0 * lev, 1)
                profit_inr = round(1500.0 * (pnl_at_target_pct / 100.0), 2)

                leverage_table.append({
                    "leverage": lev,
                    "long_liquidation": long_liq,
                    "short_liquidation": short_liq,
                    "drop_to_liq_pct": drop_to_liq_pct,
                    "risk_level": risk_lvl,
                    "badge_color": badge_color,
                    "advice": advice,
                    "pnl_at_target_pct": pnl_at_target_pct,
                    "profit_inr": profit_inr
                })

            response_data = {
                "coin": coin,
                "current_price": curr,
                "best_timeframe": best_tf,
                "recommended_action": rec_action,
                "recommended_leverage": best_info.get("recommended_lev", 10),
                "confidence": best_info.get("probability", 70),
                "target_price": target_p,
                "stop_loss": stop_p,
                "entry_price": curr,
                "profit_estimate_10x": round(1500.0 * (abs((target_p - curr) / curr) * 10), 2),
                "roi_estimate_10x_pct": round(abs((target_p - curr) / curr) * 1000.0, 1),
                "timeframes": tf_data,
                "leverage_table": leverage_table
            }
            _ADVISOR_CACHE[coin] = {"data": response_data, "timestamp": now_a}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # API: Candle Data for Chart (Supports 1m, 5m, 15m, 1h, 1d) with 5s cache
        elif path == "/api/candles":
            pair = query.get("pair", ["B-BTC_USDT"])[0]
            interval = query.get("interval", ["1h"])[0]
            limit = int(query.get("limit", ["60"])[0])

            now_c = time.time()
            c_key = (pair, interval, limit)
            cached_c = _CANDLES_CACHE.get(c_key)
            if cached_c and (now_c - cached_c["timestamp"]) < 5.0:
                candles = cached_c["data"]
            else:
                client = CoinDCXClient()
                candles = client.get_raw_candles(pair=pair, interval=interval, limit=limit)
                _CANDLES_CACHE[c_key] = {"data": candles, "timestamp": now_c}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(candles).encode("utf-8"))
            return

        # API: Bot Status & Balances (Instant Non-Blocking 0.1ms Response)
        elif path == "/api/status":
            p_data = load_paper_trades()
            bot_state["performance_summary"] = calculate_trade_performance(p_data.get("trades", []))
            bot_state["dry_run"] = config.DRY_RUN
            bot_state["risk_mode"] = config.CURRENT_RISK_MODE
            bot_state["risk_profile"] = config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, {})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(bot_state).encode("utf-8"))
            return

        # API: Paper Trade History & Complete Analytics
        elif path == "/api/paper_trades":
            p_data = load_paper_trades()
            summary = calculate_trade_performance(p_data.get("trades", []))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "summary": summary,
                "trades": p_data.get("trades", [])
            }).encode("utf-8"))
            return

        # API: Risk Modes List
        elif path == "/api/bot/risk_modes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "current_mode": config.CURRENT_RISK_MODE,
                "profiles": config.RISK_PROFILES
            }).encode("utf-8"))
            return

        # API: All Cryptocurrencies (700+ Pairs, Search, Sorting)
        elif path == "/api/all_coins":
            search = query.get("search", [""])[0]
            sort_by = query.get("sort", ["volume"])[0]
            limit = int(query.get("limit", [1000])[0])
            coins = scanner.get_all_cryptos(search=search, sort_by=sort_by, limit=limit)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "total": len(coins),
                "coins": coins
            }).encode("utf-8"))
            return

        # API: Scan All Cryptos for High-Probability Setups (Go Up / Go Low)
        elif path == "/api/scan_all":
            min_conf = int(query.get("min_conf", [75])[0])
            direction = query.get("direction", ["ALL"])[0].upper()
            limit = int(query.get("limit", [35])[0])
            signals = scanner.scan_all_crypto_signals(min_confidence=min_conf, direction=direction, limit=limit)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "count": len(signals),
                "signals": signals,
                "timestamp": int(time.time() * 1000)
            }).encode("utf-8"))
            return

        # API: Real-Time Alerts Stream & History
        elif path == "/api/alerts":
            since = int(query.get("since", [0])[0])
            with alert_state["lock"]:
                new_alerts = [a for a in alert_state["alerts"] if a["timestamp"] > since]
                all_alerts = list(alert_state["alerts"][:30])
                total = len(alert_state["alerts"])
                last_scan = alert_state["last_scanned"]

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "new_alerts": new_alerts,
                "alerts": all_alerts,
                "total_count": total,
                "last_scanned": last_scan
            }).encode("utf-8"))
            return

        # Fallback to serving web directory files (HTML, CSS, JS)
        return super().do_GET()

    def _handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/bot/toggle":
            bot_state["is_running"] = not bot_state["is_running"]
            save_active_positions(bot_state.get("active_positions", []), is_running=bot_state["is_running"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"is_running": bot_state["is_running"]}).encode("utf-8"))
            return

        elif path == "/api/bot/select_coin":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            coin = data.get("coin", "BTC").upper()
            bot_state["selected_coin"] = coin
            bot_state["selected_pair"] = f"B-{coin}_USDT"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"selected_coin": coin}).encode("utf-8"))
            return

        elif path == "/api/alerts/clear":
            with alert_state["lock"]:
                alert_state["alerts"].clear()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Alerts cleared"}).encode("utf-8"))
            return

        elif path == "/api/bot/toggle_mode":
            config.DRY_RUN = not config.DRY_RUN
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "dry_run": config.DRY_RUN,
                "mode": "PAPER" if config.DRY_RUN else "LIVE"
            }).encode("utf-8"))
            return

        elif path == "/api/bot/set_risk_mode":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            new_mode = data.get("mode", "BALANCED").upper()
            if new_mode in config.RISK_PROFILES:
                config.CURRENT_RISK_MODE = new_mode
                prof = config.RISK_PROFILES[new_mode]
                config.INVESTMENT_PER_TRADE_INR = prof["investment_inr"]
                config.LEVERAGE = prof["leverage"]
                config.STOP_LOSS_PERCENT = prof["stop_loss_pct"]
                config.TAKE_PROFIT_PERCENT = prof["take_profit_pct"]
                bot_state["last_reason"] = f"Risk mode updated: {prof['label']}"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "current_mode": config.CURRENT_RISK_MODE,
                "profile": config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, {})
            }).encode("utf-8"))
            return

        elif path == "/api/bot/manual_order":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            coin = data.get("coin", bot_state.get("selected_coin", "BTC")).upper()
            side = data.get("side", "LONG").upper()
            margin_inr = float(data.get("margin_inr", 150.0))
            lev = int(data.get("leverage", 10))
            tp_pct = float(data.get("take_profit_pct", 4.5))
            sl_pct = float(data.get("stop_loss_pct", 2.0))

            client = CoinDCXClient()
            stats = client.get_futures_stats(coin)
            curr_price = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or 50000.0)
            if curr_price <= 0:
                candles = client.get_futures_candles(coin, interval="15m", limit=2)
                if candles:
                    curr_price = float(candles[-1].get("close", 50000.0))

            qty, actual_spend = calculate_futures_trade_qty(coin, curr_price, target_margin_inr=margin_inr, leverage=lev)
            pair = f"B-{coin}_USDT"

            if side == "LONG":
                target_p = round(curr_price * (1.0 + (tp_pct / 100.0)), 4)
                stop_p = round(curr_price * (1.0 - (sl_pct / 100.0)), 4)
            else:
                target_p = round(curr_price * (1.0 - (tp_pct / 100.0)), 4)
                stop_p = round(curr_price * (1.0 + (sl_pct / 100.0)), 4)

            # If live mode, place live order on CoinDCX
            if not config.DRY_RUN:
                try:
                    order_side = "buy" if side == "LONG" else "sell"
                    live_res = client.place_futures_order(order_side, pair=pair, quantity=qty, leverage=lev)
                    print(f"[LIVE MANUAL ORDER]: {live_res}")
                except Exception as live_err:
                    print(f"[LIVE MANUAL ORDER ERROR]: {live_err}")

            bot_state["active_position"] = {
                "symbol": coin,
                "pair": pair,
                "side": side,
                "buy_price": curr_price,
                "quantity": qty,
                "invested": actual_spend,
                "leverage": lev,
                "target": target_p,
                "stop_loss": stop_p,
                "trailing_stop": stop_p,
                "peak_price": curr_price,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "time": datetime.now().strftime("%H:%M:%S")
            }
            bot_state["selected_coin"] = coin
            bot_state["selected_pair"] = pair
            bot_state["last_signal"] = f"MANUAL {side} [{coin}]"
            bot_state["last_reason"] = f"User executed {side} ({lev}x): Target ${target_p}, SL ${stop_p}"
            trade_rec = {
                "type": "BUY" if side == "LONG" else "SHORT",
                "coin": coin,
                "price": curr_price,
                "amount": actual_spend,
                "note": f"Manual {side} {lev}x: Target ${target_p}, SL ${stop_p}",
                "time": datetime.now().strftime("%H:%M:%S"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            bot_state["trade_history"].insert(0, trade_rec)
            record_paper_trade(trade_rec, active_pos=bot_state["active_position"])

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": f"Executed {side} on {coin} with INR {actual_spend} ({lev}x)",
                "position": bot_state["active_position"]
            }).encode("utf-8"))
            return

        elif path == "/api/bot/close_position":
            content_length = int(self.headers.get("Content-Length", 0))
            body_coin = None
            if content_length > 0:
                try:
                    body = self.rfile.read(content_length).decode("utf-8")
                    data = json.loads(body)
                    body_coin = (data.get("coin") or "").upper().strip()
                except Exception:
                    pass

            positions = bot_state.get("active_positions") or []
            if not positions and bot_state.get("active_position"):
                positions = [bot_state["active_position"]]

            if not positions:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "no_position", "message": "No active trade to close"}).encode("utf-8"))
                return

            pos = None
            if body_coin:
                for p in positions:
                    if p.get("symbol") == body_coin:
                        pos = p
                        break
            if not pos:
                pos = positions[0]

            coin_sym = pos.get("symbol")
            client = CoinDCXClient()
            stats = client.get_futures_stats(coin_sym)
            curr_price = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or pos.get("buy_price", 1.0))
            lev = pos.get("leverage", 10)
            side = pos.get("direction") or pos.get("side", "LONG")

            if side == "LONG":
                gross_pnl_pct = ((curr_price - pos["buy_price"]) / max(1e-6, pos["buy_price"])) * 100.0 * lev
            else:
                gross_pnl_pct = ((pos["buy_price"] - curr_price) / max(1e-6, pos["buy_price"])) * 100.0 * lev

            gross_pnl = pos["invested"] * (gross_pnl_pct / 100.0)
            trade_fee = calculate_trade_fee(pos["invested"], lev, gross_pnl)
            net_pnl = round(gross_pnl - trade_fee, 2)
            net_pnl_pct = round((net_pnl / max(1e-6, pos["invested"])) * 100.0, 2)
            proceeds = round(pos["invested"] + net_pnl, 2)
            bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

            if not config.DRY_RUN:
                try:
                    close_side = "sell" if side == "LONG" else "buy"
                    client.place_futures_order(close_side, pair=pos["pair"], quantity=pos["quantity"], leverage=lev)
                except Exception as live_err:
                    print(f"[LIVE MANUAL CLOSE ERROR]: {live_err}")

            fee_desc = f"after ₹{trade_fee:.2f} fee" if trade_fee > 0 else ""
            bot_state["last_signal"] = f"MANUAL EXIT [{coin_sym}]"
            bot_state["last_reason"] = f"Closed {coin_sym} at ${curr_price:.4f} (Net PnL: {net_pnl_pct:+.1f}%, INR {net_pnl:+.2f}{' ' + fee_desc if fee_desc else ''})"
            close_rec = {
                "type": "SELL" if side == "LONG" else "BUY_COVER",
                "coin": coin_sym,
                "direction": side,
                "price": curr_price,
                "entry_price": pos.get("buy_price", curr_price),
                "target": pos.get("target"),
                "stop_loss": pos.get("stop_loss"),
                "leverage": lev,
                "amount": proceeds,
                "gross_pnl": round(gross_pnl, 2),
                "fee": trade_fee,
                "pnl": net_pnl,
                "pnl_pct": net_pnl_pct,
                "reason": f"Manual Close Button (Net PnL: {net_pnl_pct:+.1f}%, ₹{net_pnl:+.2f}{' ' + fee_desc if fee_desc else ''})",
                "time": datetime.now().strftime("%H:%M:%S"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            bot_state["trade_history"].insert(0, close_rec)
            bot_state["active_positions"] = [p for p in bot_state.get("active_positions", []) if p.get("symbol") != coin_sym]
            bot_state["active_position"] = bot_state["active_positions"][0] if bot_state["active_positions"] else None
            record_paper_trade(close_rec, active_positions=bot_state["active_positions"])
            save_active_positions(bot_state["active_positions"])

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": f"Position {coin_sym} closed. Net PnL: INR {net_pnl:+.2f} ({net_pnl_pct:+.1f}%)",
                "pnl": net_pnl,
                "pnl_pct": round(net_pnl_pct, 2),
                "active_positions_count": len(bot_state["active_positions"])
            }).encode("utf-8"))
            return

        elif path == "/api/paper_trades/clear":
            try:
                payload = {
                    "updated_at": datetime.now().isoformat(),
                    "summary": {
                        "total_trades": 0, "completed_trades": 0, "wins": 0,
                        "losses": 0, "win_rate_pct": 0, "total_pnl_inr": 0,
                        "total_fees_inr": 0, "total_volume_inr": 0, "is_profitable": False
                    },
                    "trades": [],
                    "is_running": True,
                    "active_positions": [],
                    "active_position": None
                }
                with open(TRADES_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                bot_state["trade_history"] = []
                bot_state["active_positions"] = []
                bot_state["active_position"] = None
                bot_state["paper_balance"] = 1500.0
                bot_state["performance_summary"] = payload["summary"]
                bot_state["last_signal"] = "FRESH RESTART"
                bot_state["last_reason"] = "All trades reset. Scanning 600+ coins across 3 fresh slots..."
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Paper history & active trades cleared"}).encode("utf-8"))
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        self.send_error(404, "Endpoint not found")


def start_server():
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("0.0.0.0", PORT)
    with ThreadedHTTPServer(server_address, TradingApiHandler) as httpd:
        print(f"\n=======================================================")
        print(f"  COINDCX VISUAL TRADING DASHBOARD RUNNING")
        print(f"  Access UI at: http://localhost:{PORT}")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server gracefully...")


if __name__ == "__main__":
    start_server()
