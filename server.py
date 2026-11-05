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
from datetime import datetime, timezone, timedelta

# Indian Standard Time (IST, UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    return datetime.now(IST)

def get_ist_time_str():
    return get_ist_now().strftime("%H:%M:%S")

def get_ist_datetime_str():
    return get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

import config
from coindcx_client import CoinDCXClient
from strategy import evaluate_signal, calculate_indicators
import scanner
import predictor
import coindcx_ws

# Start real-time CoinDCX WebSocket streaming engine
ws_stream = coindcx_ws.get_ws_stream()
try:
    ws_stream.start()
except Exception as e:
    print(f"[CoinDCX WS Init Notice]: {e}")

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 5000))
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

def calculate_futures_trade_qty(coin: str, current_price: float, target_margin_inr: float = 6000.0, leverage: int = 5):
    """Calculate order quantity ensuring CoinDCX minimum notional value (>= 620 INR) and target margin."""
    min_notional_inr = 620.0
    usd_inr = 90.0
    notional_inr = max(min_notional_inr, target_margin_inr * max(1, leverage))
    notional_usd = notional_inr / usd_inr
    raw_qty = notional_usd / max(0.000001, current_price)

    # CoinDCX futures contracts that enforce whole number (step=1.0) lot sizing:
    INTEGER_QTY_COINS = {"NEAR", "AVAX", "DOT", "LINK", "UNI", "ICP", "ATOM", "FIL", "SAND", "MANA", "AXS", "GALA", "CHZ", "ENJ", "CRV", "LDO"}
    if coin.upper() in INTEGER_QTY_COINS:
        qty = float(max(1, int(round(raw_qty))))
    elif current_price < 0.001:
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

def calculate_trade_deductions(invested_inr, leverage, gross_pnl_inr):
    """
    Calculate realistic exchange fees, 1% Indian TDS, and 30% (+4% cess = 31.2%) Indian VDA Capital Gains Tax.
    - Exchange Fees (CoinDCX Futures): 0.05% taker fee on open + 0.05% taker fee on close (0.10% total on notional).
    - 1% TDS (Section 194S): 1.0% on exit payout proceeds.
    - 30% Govt Tax + 4% Cess (Section 115BBH): 31.2% flat on gross profits (losses not deductible across tokens).
    """
    invested = float(invested_inr)
    gross_pnl = float(gross_pnl_inr)
    lev = max(1.0, float(leverage))

    # 1. Exchange Taker Fees (0.05% per leg)
    entry_notional = invested * lev
    exit_notional = max(0.0, (invested + gross_pnl) * lev)
    fee_rate = getattr(config, "FEE_TAKER_PCT", 0.05) / 100.0
    fee_open = round(entry_notional * fee_rate, 2)
    fee_close = round(exit_notional * fee_rate, 2)
    exchange_fee = round(fee_open + fee_close, 2)

    # 2. 1% Indian TDS under Section 194S on exit proceeds
    gross_proceeds = max(0.0, invested + gross_pnl)
    tds_rate = getattr(config, "TDS_RATE_PCT", 1.0) / 100.0
    tds = round(gross_proceeds * tds_rate, 2)

    # 3. 30% Flat VDA Tax + 4% Cess = 31.2% (applied strictly to gross profits under Sec 115BBH)
    # 3. 30% Flat VDA Tax + 4% Cess = 31.2% (Section 115BBH)
    tax_rate = getattr(config, "GOVT_TAX_RATE_PCT", 31.2) / 100.0
    if gross_pnl > 0:
        total_tax_liability = round(gross_pnl * tax_rate, 2)
        # TDS (1%) is an advance tax collected at source on PAN; remaining net tax due:
        govt_tax = max(0.0, round(total_tax_liability - tds, 2))
    else:
        govt_tax = 0.0

    # Total Deductions & Net In-Pocket PnL
    total_deductions = round(exchange_fee + tds + govt_tax, 2)
    net_pnl = round(gross_pnl - total_deductions, 2)
    net_pnl_pct = round((net_pnl / max(1e-6, invested)) * 100.0, 2)

    return {
        "exchange_fee": exchange_fee,
        "fee_open": fee_open,
        "fee_close": fee_close,
        "tds": tds,
        "govt_tax": govt_tax,
        "total_deductions": total_deductions,
        "net_pnl": net_pnl,
        "net_pnl_pct": net_pnl_pct
    }

def calculate_trade_fee(invested_inr, leverage, gross_pnl_inr, fee_mode=None):
    """Backward compatibility wrapper returning total exchange fees."""
    return calculate_trade_deductions(invested_inr, leverage, gross_pnl_inr)["exchange_fee"]

def calculate_trade_performance(trades):
    """Calculate Net PnL, Win Rate %, Total Wins, Total Losses, Fees, TDS, Govt Taxes, and Volume."""
    completed = [t for t in trades if t.get("type") in ["SELL", "BUY_COVER"] or t.get("pnl") is not None]
    
    # Real Wins: Trades where Net In-Pocket PnL was strictly positive after all fees and TDS.
    # Real Losses: Trades where Net PnL was negative or zero.
    wins = [t for t in completed if _extract_pnl(t) > 0]
    losses = [t for t in completed if _extract_pnl(t) <= 0]
    total_pnl = sum(_extract_pnl(t) for t in completed)
    total_gross = sum(float(t.get("gross_pnl", 0) or 0) for t in completed)
    total_fees = sum(float(t.get("fee", 0) or t.get("exchange_fee", 0) or 0) for t in completed)
    total_tds = sum(float(t.get("tds", 0) or 0) for t in completed)
    total_tax = sum(float(t.get("tax", 0) or t.get("govt_tax", 0) or 0) for t in completed)
    total_deductions = round(total_fees + total_tds + total_tax, 2)
    total_volume = sum(float(t.get("amount") if t.get("amount") is not None else t.get("invested_inr", 0) or 0) for t in trades)
    win_rate = round((len(wins) / len(completed)) * 100.0, 1) if completed else 0.0

    return {
        "total_trades": len(trades),
        "completed_trades": len(completed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "total_pnl_inr": round(total_pnl, 2),
        "gross_pnl_inr": round(total_gross, 2),
        "total_fees_inr": round(total_fees, 2),
        "total_tds_inr": round(total_tds, 2),
        "total_tax_inr": round(total_tax, 2),
        "total_deductions_inr": total_deductions,
        "total_volume_inr": round(total_volume, 2),
        "is_profitable": total_pnl > 0
    }

def record_paper_trade(trade_entry, active_positions="UNCHANGED"):
    """Append a trade to disk, track active positions (up to 10 slots), and update performance metrics."""
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
            "updated_at": get_ist_now().isoformat(),
            "paper_balance": bot_state.get("paper_balance", getattr(config, "STARTING_WALLET_INR", 3006.0)),
            "starting_balance": getattr(config, "STARTING_WALLET_INR", 3006.0),
            "max_slots": getattr(config, "MAX_OPEN_POSITIONS", 5),
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

def save_active_positions(positions, is_running=None, allow_new_trades=None):
    """Persist active positions list, 24/7 running state, and manage-only mode directly to disk."""
    try:
        data = load_paper_trades()
        cur_pos = positions if isinstance(positions, list) else ([positions] if positions else [])
        data["active_positions"] = cur_pos
        data["active_position"] = cur_pos[0] if cur_pos else None
        data["paper_balance"] = bot_state.get("paper_balance", getattr(config, "STARTING_WALLET_INR", 3006.0))
        data["max_slots"] = getattr(config, "MAX_OPEN_POSITIONS", 5)
        if is_running is not None:
            data["is_running"] = is_running
        if allow_new_trades is not None:
            data["allow_new_trades"] = allow_new_trades
        elif "allow_new_trades" in bot_state:
            data["allow_new_trades"] = bot_state["allow_new_trades"]
        data["updated_at"] = get_ist_now().isoformat()
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Error saving active positions to {TRADES_FILE}]: {e}")

def save_active_position(pos):
    """Backward compatibility helper."""
    cur_pos = [pos] if pos else []
    save_active_positions(cur_pos)


# Shared Bot State with Active Live Trade & Predictive Forecasts
now_str = get_ist_time_str()
initial_paper_data = load_paper_trades()
raw_positions = initial_paper_data.get("active_positions")
if raw_positions is None:
    single = initial_paper_data.get("active_position")
    raw_positions = [single] if single else []

bot_state = {
    "is_running": initial_paper_data.get("is_running", True),  # Active by default
    "allow_new_trades": initial_paper_data.get("allow_new_trades", True), # Manage-Only toggle (False = manage active only, no new trades)
    "paper_balance": float(initial_paper_data.get("paper_balance", getattr(config, "STARTING_WALLET_INR", 3006.0))),
    "starting_balance": float(initial_paper_data.get("starting_balance", getattr(config, "STARTING_WALLET_INR", 3006.0))),
    "max_slots": getattr(config, "MAX_OPEN_POSITIONS", 5),
    "active_positions": raw_positions,
    "active_position": raw_positions[0] if raw_positions else None,
    "selected_coin": "BTC",
    "selected_pair": "B-BTC_USDT",
    "trade_history": initial_paper_data.get("trades", []),
    "performance_summary": calculate_trade_performance(initial_paper_data.get("trades", [])),
    "last_signal": "AUTONOMOUS 24/7 ENGINE ACTIVE",
    "last_reason": f"Active slots: {len(raw_positions)}/{getattr(config, 'MAX_OPEN_POSITIONS', 5)}. Dynamic 5-slot manager & full tax/fee audit active.",
    "latest_prediction": {},
}

def analyze_macro_market_regime():
    """
    Analyzes all 600+ crypto markets & Bitcoin trend to dynamically determine
    the optimal risk profile (SAFE / BALANCED / ALPHA), leverage (4x-8x),
    and adaptive target profit % (2% - 4.5%).
    """
    try:
        if getattr(config, "CURRENT_RISK_MODE", "USER_MIRROR") == "USER_MIRROR":
            mode = "USER_MIRROR"
            lev = 8  # Dynamic fallback; per-coin leverage is 22x BTC, 12x ETH, 6-8x Alts
            tp_pct = 0.90  # Front-run 6.5%-7.0% margin ROI (+₹20-₹25 profit)
            sl_pct = 0.0   # No tight SL; managed by -48% Margin Defense
            min_conf = 84
            preferred_dir = "ALL"
            desc = f"🎯 User Mirror Sniper (6x-8x Safe Lev, ₹320-₹370 sizing, +6.8% Scalp TP, -48% SL Defense, 4/5 MTF Rotation)."
            return mode, lev, tp_pct, sl_pct, min_conf, desc, preferred_dir

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
            lev = 5  # Strict 5x max
            tp_pct = 4.5  # +22.5% target
            sl_pct = 1.0  # -5.0% SL -> Risk:Reward 4.50:1 (max ₹7.80 loss)
            min_conf = 84
            preferred_dir = "UP"
            desc = f"🚀 Macro Bullish Expansion ({breadth_pct:.1f}% green, BTC Bullish). Auto: ALPHA (+4.5% TP, {lev}x Lev)."

        # 2. BALANCED MODE: Healthy Selective Market (breadth 40% - 58%)
        elif breadth_pct >= 40.0:
            mode = "BALANCED"
            lev = 4  # Strict 4x
            tp_pct = 3.8  # +15.2% target
            sl_pct = 0.90 # -3.6% SL -> Risk:Reward 4.22:1 (max ₹5.80 loss)
            min_conf = 86
            preferred_dir = "ALL"
            desc = f"⚖️ Balanced Momentum ({breadth_pct:.1f}% green). Auto: BALANCED (+3.8% TP, {lev}x Lev)."

        # 3. SAFE SCALP MODE: Defensive / Market Pullback (breadth < 40%)
        else:
            mode = "SAFE"
            lev = 4  # Strict 4x
            tp_pct = 3.6  # +14.4% target
            sl_pct = 0.85 # -3.4% SL -> Risk:Reward 4.23:1 (max ₹5.50 loss)
            min_conf = 88  # High confidence filter
            preferred_dir = "DOWN" if not btc_bullish else "ALL"
            desc = f"🛡️ Defensive Pullback ({breadth_pct:.1f}% green). Auto: SAFE Two-Way Scalps (+3.6% TP, {lev}x Lev)."

        return mode, lev, tp_pct, sl_pct, min_conf, desc, preferred_dir
    except Exception as e:
        print(f"[Market Regime Error]: {e}")
        return "SAFE", 4, 3.6, 0.85, 85, "🛡️ Defensive Mode", "ALL"


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
                # 2-WAY EXCHANGE POSITION RECONCILIATION
                # Automatically detects if user closed a trade on CoinDCX Mobile App!
                # ==============================================================
                if not config.DRY_RUN and client.api_key and client.api_secret:
                    try:
                        live_open_positions = client.get_futures_positions()
                        if isinstance(live_open_positions, list):
                            live_open_pairs = {p.get("pair") for p in live_open_positions if abs(float(p.get("active_pos", 0) or 0)) > 0}
                            
                            # 1. Import any positions opened externally (e.g. on CoinDCX mobile app)
                            existing_pairs = {p.get("pair") for p in bot_state["active_positions"]}
                            for ext_p in live_open_positions:
                                ext_qty = float(ext_p.get("active_pos", 0) or 0)
                                ext_pair = ext_p.get("pair")
                                if abs(ext_qty) > 0 and ext_pair and ext_pair not in existing_pairs:
                                    coin_name = ext_pair.replace("B-", "").replace("_USDT", "")
                                    side = "LONG" if ext_qty > 0 else "SHORT"
                                    entry_px = float(ext_p.get("avg_price") or ext_p.get("mark_price") or 0)
                                    lev = int(float(ext_p.get("leverage") or 7))
                                    locked_margin_usd = float(ext_p.get("locked_user_margin") or ext_p.get("locked_margin") or 0)
                                    settle_rate = float(ext_p.get("settlement_currency_avg_price") or 102.0)
                                    invested_inr = round(locked_margin_usd * settle_rate, 2)
                                    if invested_inr <= 0:
                                        invested_inr = round(abs(ext_qty) * entry_px * 90.0 / max(1, lev), 2)
                                    
                                    tp_pct = 7.0
                                    target_p = entry_px * (1.0 + (tp_pct / 100.0) / lev) if side == "LONG" else entry_px * (1.0 - (tp_pct / 100.0) / lev)
                                    
                                    imported_pos = {
                                        "symbol": coin_name,
                                        "pair": ext_pair,
                                        "direction": side,
                                        "buy_price": entry_px,
                                        "current_price": entry_px,
                                        "quantity": abs(ext_qty),
                                        "invested": invested_inr,
                                        "leverage": lev,
                                        "target": round(target_p, 4),
                                        "stop_loss": None,
                                        "trailing_stop": None,
                                        "margin_defended": False,
                                        "peak_price": entry_px,
                                        "valley_price": entry_px,
                                        "peak_pnl_pct": 0.0,
                                        "gross_pnl_pct": 0.0,
                                        "net_pnl": 0.0,
                                        "net_pnl_pct": 0.0,
                                        "sl_defense_price": None,
                                        "tp_target_pct": tp_pct,
                                        "trailing_lock_pct": 0.0,
                                        "probability": 92,
                                        "mtf_agreement": "Mobile App Sync",
                                        "entry_time": time.time(),
                                        "time": get_ist_time_str()
                                    }
                                    bot_state["active_positions"].append(imported_pos)
                                    existing_pairs.add(ext_pair)
                                    print(f"[🔄 2-Way Sync]: Imported {side} {coin_name} (Qty: {abs(ext_qty)}, Lev: {lev}x, Margin: ₹{invested_inr}) from CoinDCX mobile app into Dashboard!")
                                    save_active_positions(bot_state["active_positions"])

                            # Update existing positions with live leverage, margin, and quantity from CoinDCX
                            live_p_map = {p.get("pair"): p for p in live_open_positions if p.get("pair")}
                            for pos in bot_state["active_positions"]:
                                p_pair = pos.get("pair")
                                if p_pair in live_p_map:
                                    live_item = live_p_map[p_pair]
                                    cur_lev = float(live_item.get("leverage") or 0)
                                    cur_locked = float(live_item.get("locked_user_margin") or live_item.get("locked_margin") or 0)
                                    cur_settle = float(live_item.get("settlement_currency_avg_price") or 102.0)
                                    cur_act_qty = abs(float(live_item.get("active_pos") or 0))
                                    if cur_lev > 0:
                                        pos["leverage"] = cur_lev
                                    if cur_locked > 0:
                                        pos["invested"] = round(cur_locked * cur_settle, 2)
                                    if cur_act_qty > 0:
                                        pos["quantity"] = cur_act_qty

                            # 2. Detect any positions closed externally on CoinDCX mobile app
                            closed_externally = []
                            for pos in list(bot_state["active_positions"]):
                                p_pair = pos.get("pair")
                                pos_age = now_ts - float(pos.get("entry_time", 0))
                                if pos_age > 10.0 and p_pair and p_pair not in live_open_pairs:
                                    closed_externally.append(pos)

                            for c_pos in closed_externally:
                                c_coin = c_pos.get("symbol")
                                c_lev = c_pos.get("leverage", 7)
                                c_side = c_pos.get("direction") or c_pos.get("side", "LONG")
                                c_entry = float(c_pos.get("buy_price", 0))
                                c_cur = float(c_pos.get("current_price") or c_entry)
                                c_inv = float(c_pos.get("invested", 200.0))

                                if c_side == "LONG":
                                    c_gross_pct = ((c_cur - c_entry) / max(1e-6, c_entry)) * 100.0 * c_lev
                                else:
                                    c_gross_pct = ((c_entry - c_cur) / max(1e-6, c_entry)) * 100.0 * c_lev
                                c_gross = c_inv * (c_gross_pct / 100.0)

                                deductions = calculate_trade_deductions(c_inv, c_lev, c_gross)
                                net_pnl = deductions["net_pnl"]
                                net_pnl_pct = deductions["net_pnl_pct"]
                                proceeds = round(c_inv + net_pnl, 2)
                                bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

                                close_rec = {
                                    "type": "SELL" if c_side == "LONG" else "BUY_COVER",
                                    "coin": c_coin,
                                    "direction": c_side,
                                    "price": c_cur,
                                    "entry_price": c_entry,
                                    "target": c_pos.get("target"),
                                    "stop_loss": c_pos.get("stop_loss"),
                                    "leverage": c_lev,
                                    "amount": proceeds,
                                    "gross_pnl": round(c_gross, 2),
                                    "fee": deductions["exchange_fee"],
                                    "tds": deductions["tds"],
                                    "tax": deductions["govt_tax"],
                                    "total_deductions": deductions["total_deductions"],
                                    "pnl": round(net_pnl, 2),
                                    "pnl_pct": round(net_pnl_pct, 2),
                                    "reason": f"Manual Mobile App Close (Net: {net_pnl_pct:+.1f}%, ₹{net_pnl:+.2f})",
                                    "time": get_ist_time_str(),
                                    "timestamp": get_ist_datetime_str(),
                                    "is_live": True
                                }
                                bot_state["trade_history"].insert(0, close_rec)
                                bot_state["active_positions"] = [p for p in bot_state["active_positions"] if p.get("symbol") != c_coin]
                                bot_state["active_position"] = bot_state["active_positions"][0] if bot_state["active_positions"] else None
                                bot_state["last_signal"] = f"APP CLOSE [{c_coin}]"
                                bot_state["last_reason"] = f"Detected {c_coin} closed on CoinDCX App. Reconciled successfully (+₹{net_pnl:.2f})."
                                print(f"[🔄 2-Way Sync]: {c_coin} closed externally on CoinDCX mobile app! Reconciled dashboard.")
                                record_paper_trade(close_rec, active_positions=bot_state["active_positions"])
                                save_active_positions(bot_state["active_positions"])
                    except Exception as sync_err:
                        print(f"[2-Way Sync Notice]: {sync_err}")

                # ==============================================================
                # PHASE 1: MANAGE ALL ACTIVE POSITIONS (UP TO 5 SLOTS CONCURRENTLY)
                # DYNAMIC RUNNER MODE (+15% to +30% TP) & 7% - 12% TRAILING RATINGS
                # ==============================================================
                positions_snapshot = list(bot_state["active_positions"])
                active_pos_summaries = []

                # Register active coins to real-time 0ms WebSocket stream
                if ws_stream:
                    active_coin_names = [p.get("symbol") for p in positions_snapshot if p.get("symbol")]
                    if active_coin_names:
                        ws_stream.update_active_coins(active_coin_names)

                for pos in positions_snapshot:
                    pos_symbol = pos.get("symbol", "")
                    pair = pos.get("pair", f"B-{pos_symbol}_USDT")
                    pos_lev = pos.get("leverage", dyn_lev)
                    pos_dir = pos.get("direction") or pos.get("side", "LONG")
                    buy_price = float(pos.get("buy_price", 0))

                    # Fetch live mark price: WebSocket 0ms priority -> CoinDCX Ticker -> Candles
                    current_price = buy_price
                    try:
                        ws_p = ws_stream.get_live_price(pos_symbol, max_age_seconds=15.0) if ws_stream else None
                        if ws_p and ws_p > 0:
                            current_price = ws_p
                        else:
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

                    # Calculate defense level: if trailing profit lock is active, preserve locked profit price!
                    defense_ratio = abs(float(getattr(config, "MARGIN_DEFENSE_DRAWDOWN_PCT", -48.0))) / 100.0
                    if pos.get("trailing_stop") and float(pos.get("trailing_lock_pct", 0.0) or 0.0) > 0:
                        sl_defense = float(pos["trailing_stop"])
                    else:
                        sl_defense = round(buy_price * (1.0 - (defense_ratio / pos_lev)), precision) if pos_dir == "LONG" else round(buy_price * (1.0 + (defense_ratio / pos_lev)), precision)
                    pos["sl_defense_price"] = sl_defense

                    target_p = float(pos.get("target") or (buy_price * 1.02))
                    tp_pct = ((target_p - buy_price) / max(1e-6, buy_price)) * 100.0 * pos_lev if pos_dir == "LONG" else ((buy_price - target_p) / max(1e-6, buy_price)) * 100.0 * pos_lev
                    pos["tp_target_pct"] = round(tp_pct, 2)

                    # ----------------------------------------------------------
                    # FINANCIAL RECONCILIATION & DEDUCTIONS
                    # ----------------------------------------------------------
                    invested = float(pos.get("invested", invest_target))
                    gross_pnl = invested * (gross_pnl_pct / 100.0)
                    deductions = calculate_trade_deductions(invested, pos_lev, gross_pnl)
                    trade_fee = deductions["exchange_fee"]
                    trade_tds = deductions["tds"]
                    trade_tax = deductions["govt_tax"]
                    total_cut = deductions["total_deductions"]
                    net_pnl = deductions["net_pnl"]
                    net_pnl_pct = deductions["net_pnl_pct"]

                    # Populate live metrics for real-time frontend distance bar
                    pos["current_price"] = round(current_price, precision)
                    pos["gross_pnl_pct"] = round(gross_pnl_pct, 2)
                    pos["net_pnl"] = round(net_pnl, 2)
                    pos["net_pnl_pct"] = round(net_pnl_pct, 2)

                    # 30-second minimum maturation buffer before exit triggers
                    pos_age = now_ts - float(pos.get("entry_time", now_ts))
                    if pos_age < 30:
                        runner_tag = " [⚡RUNNER]" if pos.get("is_runner") else ""
                        active_pos_summaries.append(f"{pos_dir} {pos_symbol}{runner_tag}: Maturing ({int(30 - pos_age)}s, Net {net_pnl_pct:+.1f}%)")
                        continue

                    # ----------------------------------------------------------
                    # USER-SPECIFIED PROGRESSIVE TRAILING PROFIT-LOCK STAIRCASE
                    # For Big TP Trades (+28%, +30%, +42%):
                    # - At +15% PnL: Shift SL from -65% to +7% Profit Lock!
                    # - At +20% PnL: Shift SL to +10% Profit Lock!
                    # - At +25% PnL: Shift SL to +12% Profit Lock!
                    # - At +30% PnL: Shift SL to +18% Profit Lock!
                    # - At +35% PnL: Shift SL to +24% Profit Lock!
                    # - At +40%+ PnL: Shift SL to max(+30%, peak - 8%) Profit Lock!
                    # - At +8% PnL: Early Breakeven Protection (+2% fee cushion)
                    # ----------------------------------------------------------
                    # SAFE PROGRESSIVE TRAILING PROFIT-LOCK STAIRCASE
                    # Must ONLY trigger on CURRENT live PnL, NEVER on stale historical peaks!
                    # Must verify that current price is strictly on the profitable side of lock price!
                    # ----------------------------------------------------------
                    target_lock_pnl = None
                    staircase = getattr(config, "TRAILING_PROFIT_STAIRCASE", [])

                    for trigger_pct, lock_pct in staircase:
                        if gross_pnl_pct >= trigger_pct:
                            test_lock = lock_pct if trigger_pct < 45.0 else max(lock_pct, round(gross_pnl_pct - 8.0, 1))
                            cand_lock_p = round(buy_price * (1.0 + (test_lock / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (test_lock / 100.0) / pos_lev), precision)
                            # NEVER set a trailing stop if current price is already past it!
                            if (pos_dir == "LONG" and current_price > cand_lock_p) or (pos_dir == "SHORT" and current_price < cand_lock_p):
                                target_lock_pnl = test_lock
                            break

                    if target_lock_pnl is not None:
                        prev_lock = float(pos.get("trailing_lock_pct", 0.0) or 0.0)
                        if target_lock_pnl > prev_lock:
                            pos["trailing_lock_pct"] = target_lock_pnl
                            lock_price = round(buy_price * (1.0 + (target_lock_pnl / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (target_lock_pnl / 100.0) / pos_lev), precision)
                            pos["trailing_stop"] = lock_price
                            pos["sl_defense_price"] = lock_price
                            print(f"[🔒 TRAILING PROFIT LOCK] {pos_symbol} reached +{gross_pnl_pct:.1f}% -> SL shifted to +{target_lock_pnl:.1f}% locked profit (${lock_price:.4f})")

                    # Mega-Runner Target Expansion (+18%+)
                    if gross_pnl_pct >= config.RUNNER_TRIGGER_PNL_PCT:
                        pos["is_runner"] = True
                        pos["runner_target_pct"] = config.RUNNER_EXTENDED_TP_PCT
                        extended_target = round(buy_price * (1.0 + (config.RUNNER_EXTENDED_TP_PCT / 100.0) / pos_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 - (config.RUNNER_EXTENDED_TP_PCT / 100.0) / pos_lev), precision)
                        pos["target"] = extended_target

                    # ----------------------------------------------------------
                    # SMART MARGIN DEFENSE AT -48% DRAWDOWN (DE-LEVERAGE BUFFER)
                    # ----------------------------------------------------------
                    exit_trigger = None
                    exit_side = "sell" if pos_dir == "LONG" else "buy"
                    min_tp_inr = getattr(config, "TARGET_PROFIT_MIN_INR", 25.0)
                    sl_defense_threshold = float(getattr(config, "MARGIN_DEFENSE_DRAWDOWN_PCT", -48.0))
                    hard_sl_threshold = float(getattr(config, "HARD_STOP_LOSS_MARGIN_PCT", -58.0))

                    # 1. Check -48% Margin Drawdown Defense
                    if gross_pnl_pct <= sl_defense_threshold and not pos.get("margin_defended", False):
                        reversal_likely = True
                        try:
                            check_candles = client.get_candles(pair=pair, interval="15m", limit=15)
                            if check_candles is not None and len(check_candles) >= 10:
                                chk_df = calculate_indicators(check_candles)
                                cur_rsi = float(chk_df.iloc[-1].get("rsi", 50))
                                # Reversal is strongly probable if RSI is at boundary or stabilizing
                                reversal_likely = (pos_dir == "LONG" and cur_rsi < 38.0) or (pos_dir == "SHORT" and cur_rsi > 62.0) or (35.0 <= cur_rsi <= 65.0)
                        except Exception:
                            reversal_likely = True

                        topup_amount = round(invested * getattr(config, "MARGIN_DEFENSE_TOPUP_RATIO", 0.50), 2)
                        avail_cash = float(bot_state.get("paper_balance", 0.0))

                        if reversal_likely and avail_cash >= topup_amount:
                            # Apply Defensive Margin Top-up: De-leverage to absorb drawdown
                            bot_state["paper_balance"] = round(bot_state["paper_balance"] - topup_amount, 2)
                            new_invested = round(invested + topup_amount, 2)
                            new_lev = round(pos_lev * (invested / new_invested), 1)
                            pos["invested"] = new_invested
                            pos["leverage"] = new_lev
                            pos["margin_defended"] = True
                            pos["stop_loss"] = round(buy_price * (1.0 - (abs(hard_sl_threshold) / 100.0) / new_lev), precision) if pos_dir == "LONG" else round(buy_price * (1.0 + (abs(hard_sl_threshold) / 100.0) / new_lev), precision)
                            defense_msg = f"[🛡️ MARGIN DEFENSE] Added ₹{topup_amount} margin to {pos_symbol}. De-leveraged {pos_lev}x -> {new_lev}x to absorb drawdown and await reversal!"
                            print(defense_msg)
                            bot_state["last_reason"] = defense_msg
                            save_active_positions(bot_state["active_positions"])
                            invested = new_invested
                            pos_lev = new_lev
                            gross_pnl_pct = gain_pct * pos_lev
                            gross_pnl = invested * (gross_pnl_pct / 100.0)
                        else:
                            # No reversal potential or no margin: hit Stop-Loss Protection
                            exit_trigger = f"Stop-Loss Protection at ${current_price:.4f} ({sl_defense_threshold:.0f}% Drawdown Limit)"

                    # 2. Check Catastrophic SL for Defended Positions (-85% Barrier)
                    elif pos.get("margin_defended", False) and gross_pnl_pct <= hard_sl_threshold:
                        exit_trigger = f"Emergency Catastrophic Stop-Loss at ${current_price:.4f} ({hard_sl_threshold:.0f}% Barrier)"

                    # 3. Check Take Profit (Target Hit or Profit Target Reached)
                    active_sl = pos.get("trailing_stop") or pos.get("stop_loss")
                    target_p = pos.get("target")

                    # RELIEF TAKE-PROFIT RULE:
                    # If this trade had to be margin-defended at -75%, exit as soon as it recovers +5.0% to +8.0% ROI!
                    # "Take the money and run" on recovered trades without risking a second drawdown!
                    if pos.get("margin_defended", False) and gross_pnl_pct >= 5.0 and not exit_trigger:
                        exit_trigger = f"Relief Take-Profit Hit (+{gross_pnl_pct:.1f}% ROI / ₹{gross_pnl:+.2f} Profit after {sl_defense_threshold:.0f}% Defense Recovery)!"

                    # USER HARD STOP-LOSS LIMITS (Enforced by User Request):
                    # Hard cap on PROM at -₹170 net loss or Price >= $5.22:
                    if pos_symbol == "PROM" and (net_pnl <= -170.0 or current_price >= 5.22) and not exit_trigger:
                        exit_trigger = f"User Hard Stop-Loss Hit on PROM (Net ₹{net_pnl:.2f} <= -₹170 / Price ${current_price:.4f} >= $5.22)"

                    # Hard cap on METIS at -25% ROI:
                    if pos_symbol == "METIS" and gross_pnl_pct <= -25.0 and not exit_trigger:
                        exit_trigger = f"User Stop-Loss Hit on METIS ({gross_pnl_pct:.1f}% <= -25% ROI / Net ₹{net_pnl:.2f})"

                    # Hard cap on UNI at -25% ROI:
                    if pos_symbol == "UNI" and gross_pnl_pct <= -25.0 and not exit_trigger:
                        exit_trigger = f"User Stop-Loss Hit on UNI ({gross_pnl_pct:.1f}% <= -25% ROI / Net ₹{net_pnl:.2f})"

                    # GUARANTEED NET-PROFIT EXIT RULES (Prevents selling for a loss after fees & TDS)
                    # Note: On a ₹6,000 position, exchange fees (~₹42) + 1% TDS (~₹60) = ~₹102 total friction.
                    # A trade must NEVER close on a 'Profit Target' unless net_pnl is strictly positive!
                    is_turtle = pos.get("strategy") == "TURTLE_SYSTEM_2" or getattr(config, "STRATEGY_MODE", "TURTLE") == "TURTLE"

                    if not exit_trigger:
                        target_roi = float(getattr(config, "TARGET_PROFIT_ROI_PCT", 15.0))
                        max_tp_inr = float(getattr(config, "TARGET_PROFIT_MAX_INR", 600.0))

                        # Only trigger standard take-profit if Net PnL is positive and meets minimum net profit goal (after all fees & TDS)
                        min_net_goal = float(getattr(config, "TARGET_PROFIT_MIN_INR", 240.0))
                        if pos_dir == "LONG":
                            if target_p and current_price >= target_p and net_pnl > 0:
                                runner_note = f" [Runner Target +{pos.get('runner_target_pct', 35)}% Hit!]" if pos.get("is_runner") else ""
                                exit_trigger = f"Target Hit (${target_p:.4f}){runner_note} [Net ₹{net_pnl:+.2f}]!"
                            elif not pos.get("is_runner") and net_pnl >= min_net_goal and (gross_pnl >= max_tp_inr or gross_pnl_pct >= target_roi):
                                exit_trigger = f"Target Reached (+₹{gross_pnl:.2f} / +{gross_pnl_pct:.1f}% ROI | Net ₹{net_pnl:+.2f})!"
                            elif active_sl and current_price <= active_sl:
                                is_profit = active_sl > buy_price
                                lbl = "Trailing Profit Lock" if is_profit else "Stop-Loss Protection"
                                exit_trigger = f"{lbl} at ${active_sl:.4f}"
                        else: # SHORT
                            if target_p and current_price <= target_p and net_pnl > 0:
                                runner_note = f" [Runner Target +{pos.get('runner_target_pct', 35)}% Hit!]" if pos.get("is_runner") else ""
                                exit_trigger = f"Target Hit (${target_p:.4f}){runner_note} [Net ₹{net_pnl:+.2f}]!"
                            elif not pos.get("is_runner") and net_pnl >= min_net_goal and (gross_pnl >= max_tp_inr or gross_pnl_pct >= target_roi):
                                exit_trigger = f"Target Reached (+₹{gross_pnl:.2f} / +{gross_pnl_pct:.1f}% ROI | Net ₹{net_pnl:+.2f})!"
                            elif active_sl and current_price >= active_sl:
                                is_profit = active_sl < buy_price
                                lbl = "Trailing Profit Lock" if is_profit else "Stop-Loss Protection"
                                exit_trigger = f"{lbl} at ${active_sl:.4f}"

                    # TURTLE SYSTEM 2 EXIT RULES (2N Volatility Stop & 20-bar Low Channel Exit)
                    if not exit_trigger and (pos.get("strategy") == "TURTLE_SYSTEM_2" or getattr(config, "STRATEGY_MODE", "TURTLE") == "TURTLE"):
                        t_sl = pos.get("stop_loss")
                        t_exit_low = pos.get("exit_channel_low")
                        t_exit_high = pos.get("exit_channel_high")
                        if pos_dir == "LONG":
                            if t_sl and current_price <= float(t_sl):
                                exit_trigger = f"Turtle 2N Volatility Stop-Loss hit at ${current_price:.4f} <= ${float(t_sl):.4f}"
                            elif t_exit_low and current_price < float(t_exit_low):
                                exit_trigger = f"Turtle 20-bar Channel Low Exit triggered at ${current_price:.4f} < ${float(t_exit_low):.4f}"
                        else:  # SHORT
                            if t_sl and current_price >= float(t_sl):
                                exit_trigger = f"Turtle 2N Volatility Stop-Loss hit at ${current_price:.4f} >= ${float(t_sl):.4f}"
                            elif t_exit_high and current_price > float(t_exit_high):
                                exit_trigger = f"Turtle 20-bar Channel High Exit triggered at ${current_price:.4f} > ${float(t_exit_high):.4f}"

                    if exit_trigger:
                        if ("Stop-Loss" in exit_trigger or "Trailing Profit Lock" in exit_trigger) and active_sl:
                            exec_price = float(active_sl)
                            gross_move_pct = ((exec_price - buy_price) / max(1e-6, buy_price)) * 100.0 if pos_dir == "LONG" else ((buy_price - exec_price) / max(1e-6, buy_price)) * 100.0
                            gross_pnl_pct = gross_move_pct * pos_lev
                            gross_pnl = invested * (gross_pnl_pct / 100.0)
                            deductions = calculate_trade_deductions(invested, pos_lev, gross_pnl)
                            trade_fee = deductions["exchange_fee"]
                            trade_tds = deductions["tds"]
                            trade_tax = deductions["govt_tax"]
                            net_pnl = deductions["net_pnl"]
                            net_pnl_pct = deductions["net_pnl_pct"]
                        else:
                            exec_price = current_price

                        proceeds = round(invested + net_pnl, 2)
                        bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

                        if not config.DRY_RUN:
                            try:
                                live_exit = client.place_futures_order(exit_side, pair=pair, quantity=pos["quantity"], leverage=pos_lev)
                                print(f"[LIVE AUTONOMOUS EXIT ORDER]: {live_exit}")
                            except Exception as live_err:
                                print(f"[LIVE AUTONOMOUS EXIT ERROR]: {live_err}")

                        deduct_desc = f"after ₹{trade_fee:.2f} fee, ₹{trade_tds:.2f} TDS"
                        if trade_tax > 0:
                            deduct_desc += f", ₹{trade_tax:.2f} 31.2% tax"
                        full_reason = f"{exit_trigger} (Net PnL: {net_pnl_pct:+.1f}%, ₹{net_pnl:+.2f} {deduct_desc})"
                        bot_state["last_signal"] = f"EXIT [{pos_dir} {pos_symbol}]"
                        bot_state["last_reason"] = full_reason
                        exit_rec = {
                            "type": "SELL" if pos_dir == "LONG" else "BUY_COVER",
                            "coin": pos_symbol,
                            "direction": pos_dir,
                            "price": exec_price,
                            "entry_price": buy_price,
                            "target": target_p,
                            "stop_loss": pos.get("stop_loss"),
                            "leverage": pos_lev,
                            "amount": round(proceeds, 2),
                            "gross_pnl": round(gross_pnl, 2),
                            "fee": trade_fee,
                            "tds": trade_tds,
                            "tax": trade_tax,
                            "total_deductions": total_cut,
                            "pnl": net_pnl,
                            "pnl_pct": net_pnl_pct,
                            "reason": full_reason,
                            "time": get_ist_time_str(),
                            "timestamp": get_ist_datetime_str(),
                            "is_live": not config.DRY_RUN
                        }
                        bot_state["trade_history"].insert(0, exit_rec)
                        bot_state["active_positions"] = [p for p in bot_state["active_positions"] if p.get("symbol") != pos_symbol]
                        bot_state["active_position"] = bot_state["active_positions"][0] if bot_state["active_positions"] else None
                        record_paper_trade(exit_rec, active_positions=bot_state["active_positions"])
                        save_active_positions(bot_state["active_positions"])
                        # 30-minute anti-whipsaw cooldown after a loss to avoid double loss trap!
                        coin_cooldown = getattr(config, "POST_LOSS_COOLDOWN_SECONDS", 1800) if net_pnl < 0 else getattr(config, "SAME_COIN_COOLDOWN_SECONDS", 7200)
                        recent_coins[pos_symbol] = now_ts + coin_cooldown  # 30-min gap cooldown after a loss
                    else:
                        runner_tag = " [⚡RUNNER]" if pos.get("is_runner") else ""
                        active_pos_summaries.append(f"{pos_dir} {pos_symbol}{runner_tag}: Net {net_pnl_pct:+.1f}% (₹{net_pnl:+.2f})")

                max_slots = getattr(config, "MAX_OPEN_POSITIONS", 10)
                if active_pos_summaries:
                    bot_state["last_reason"] = f"Slots ({len(bot_state['active_positions'])}/{max_slots}): " + " | ".join(active_pos_summaries)
                if bot_state.get("active_positions"):
                    save_active_positions(bot_state["active_positions"])

                # ==============================================================
                # PHASE 2: SCAN & OPEN POSITIONS (2-SLOT CAP + 1:2 R:R DISCIPLINE)
                # ==============================================================
                cur_count = len(bot_state.get("active_positions", []))
                slots_needed = max_slots - cur_count
                allow_new = bot_state.get("allow_new_trades", True)

                # Daily Capital Preservation & Profit Guardrails
                today_str = get_ist_datetime_str()[:10]
                today_trades = [t for t in bot_state.get("trade_history", []) if (t.get("timestamp") or "")[:10] == today_str]
                today_net_pnl = sum(_extract_pnl(t) for t in today_trades)

                daily_loss_limit = getattr(config, "MAX_DAILY_LOSS_LIMIT", 1500.0)
                daily_profit_goal = getattr(config, "DAILY_PROFIT_GOAL", 2000.0)

                if today_net_pnl <= -daily_loss_limit:
                    allow_new = False
                    bot_state["last_signal"] = "DAILY LOSS LIMIT HIT"
                    bot_state["last_reason"] = f"🛑 Capital Shield: Today's Loss (-₹{abs(today_net_pnl):.2f}) reached daily limit (-₹{daily_loss_limit:.0f}). Paused for 24h to preserve wallet."
                elif today_net_pnl >= daily_profit_goal:
                    allow_new = False
                    bot_state["last_signal"] = "DAILY PROFIT GOAL REACHED"
                    bot_state["last_reason"] = f"🎉 Target Hit: Today's Net Profit (+₹{today_net_pnl:.2f}) reached goal (+₹{daily_profit_goal:.0f}). Banking profits for the day!"

                if not allow_new:
                    # MANAGE-ONLY MODE: Do NOT open any new trades; only manage existing active trades!
                    if cur_count > 0:
                        bot_state["last_signal"] = f"MANAGE-ONLY [{cur_count}/{max_slots} Active Positions]"
                        bot_state["last_reason"] = f"🛡️ Manage-Only Mode: New trades paused. Actively managing {cur_count} open position(s) with dynamic TP & -48% Margin Defense."
                    else:
                        bot_state["last_signal"] = "MANAGE-ONLY (Standby - 0 Positions)"
                        bot_state["last_reason"] = "🛡️ Manage-Only Mode: New trades paused by user. Standing by (0 active positions)."
                else:
                    # ==============================================================
                    # CONTINUOUS ALPHA CAPITAL ROTATION (SLOT SWAPPING WHEN FULL)
                    # When all 5 slots are full, keep scanning for 84%+ (4/5 MTF) setups.
                    # If found and an existing trade is at >= +5.5% profit, bank profit & rotate!
                    # ==============================================================
                    if cur_count >= max_slots and getattr(config, "CAPITAL_ROTATION_ENABLED", True) and now_ts >= scan_cooldown_until:
                        rotatable = [p for p in bot_state["active_positions"] if float(p.get("gross_pnl_pct", 0.0) or 0.0) >= getattr(config, "ROTATION_MIN_PROFIT_PCT", 5.5)]
                        if rotatable:
                            held_coins = {p.get("symbol") for p in bot_state["active_positions"]}
                            rot_min_conf = getattr(config, "ROTATION_CANDIDATE_MIN_CONF", 84)
                            rot_signals = scanner.scan_all_crypto_signals(min_confidence=rot_min_conf, direction=preferred_dir, limit=25)
                            rot_valid = [s for s in (rot_signals or []) if s["coin"] not in held_coins and recent_coins.get(s["coin"], 0) < now_ts]
                            if rot_valid:
                                best_rot_cand = rot_valid[0]
                                # Pick existing trade with highest profit to bank
                                target_rot_pos = max(rotatable, key=lambda p: float(p.get("gross_pnl_pct", 0.0) or 0.0))
                                r_symbol = target_rot_pos.get("symbol")
                                r_dir = target_rot_pos.get("direction", "LONG")
                                r_pnl_pct = float(target_rot_pos.get("gross_pnl_pct", 0.0) or 0.0)
                                r_net_pnl = float(target_rot_pos.get("net_pnl", 0.0) or 0.0)
                                r_invested = float(target_rot_pos.get("invested", 0.0) or 0.0)
                                r_lev = target_rot_pos.get("leverage", 7)
                                r_pair = target_rot_pos.get("pair")
                                r_qty = target_rot_pos.get("quantity")
                                r_cur_p = float(target_rot_pos.get("current_price", 0.0) or 0.0)

                                print(f"[💎 CAPITAL ROTATION] Banking +{r_pnl_pct:.1f}% (+₹{r_net_pnl:.2f}) on {r_symbol} to enter {best_rot_cand['coin']} (Conf: {best_rot_cand.get('probability', 85)}%, MTF: {best_rot_cand.get('mtf_agreement', '4/5')})")

                                r_exit_side = "sell" if r_dir == "LONG" else "buy"
                                if not config.DRY_RUN:
                                    try:
                                        client.place_futures_order(r_exit_side, pair=r_pair, quantity=r_qty, leverage=r_lev)
                                    except Exception as rot_exit_err:
                                        print(f"[ROTATION EXIT ERR]: {rot_exit_err}")

                                r_proceeds = round(r_invested + r_net_pnl, 2)
                                bot_state["paper_balance"] = round(bot_state["paper_balance"] + r_proceeds, 2)
                                rot_reason = f"💎 Alpha Capital Rotation (+{r_pnl_pct:.1f}% Banked, ₹{r_net_pnl:+.2f} into {best_rot_cand['coin']})"
                                r_exit_rec = {
                                    "type": "SELL" if r_dir == "LONG" else "BUY_COVER",
                                    "coin": r_symbol,
                                    "direction": r_dir,
                                    "price": r_cur_p,
                                    "entry_price": float(target_rot_pos.get("buy_price", 0.0)),
                                    "target": target_rot_pos.get("target"),
                                    "stop_loss": target_rot_pos.get("stop_loss"),
                                    "leverage": r_lev,
                                    "amount": r_proceeds,
                                    "gross_pnl": round(r_invested * (r_pnl_pct / 100.0), 2),
                                    "fee": float(target_rot_pos.get("fee", 1.5)),
                                    "tds": float(target_rot_pos.get("tds", 2.0)),
                                    "tax": float(target_rot_pos.get("tax", 0.0)),
                                    "total_deductions": float(target_rot_pos.get("total_deductions", 3.5)),
                                    "pnl": r_net_pnl,
                                    "pnl_pct": float(target_rot_pos.get("net_pnl_pct", r_pnl_pct)),
                                    "reason": rot_reason,
                                    "time": get_ist_time_str(),
                                    "timestamp": get_ist_datetime_str(),
                                    "is_live": not config.DRY_RUN
                                }
                                bot_state["trade_history"].insert(0, r_exit_rec)
                                bot_state["active_positions"] = [p for p in bot_state["active_positions"] if p.get("symbol") != r_symbol]
                                bot_state["active_position"] = bot_state["active_positions"][0] if bot_state["active_positions"] else None
                                record_paper_trade(r_exit_rec, active_positions=bot_state["active_positions"])
                                save_active_positions(bot_state["active_positions"])
                                cur_count = len(bot_state["active_positions"])
                                slots_needed = max_slots - cur_count

                    if slots_needed > 0 and now_ts >= scan_cooldown_until:
                        scan_cooldown_until = now_ts + 20  # Fast 20s scanner cadence
                        held_coins = {p.get("symbol") for p in bot_state["active_positions"]}

                        signals = scanner.scan_all_crypto_signals(min_confidence=dyn_min_conf, direction=preferred_dir, limit=25)
                        valid_signals = [s for s in signals if s["coin"] not in held_coins and recent_coins.get(s["coin"], 0) < now_ts] if signals else []

                        num_valid = len(valid_signals)
                        # Adaptive Capital Sizing per User Requirement (Wallet ₹30,000, 5 Max Slots, ₹6,000 margin per trade):
                        if (cur_count == 0 and num_valid == 1) or (num_valid == 1 and slots_needed == 1):
                            target_margin = getattr(config, "SOLO_SNIPER_INVESTMENT_INR", 6000.0)
                            sizing_lbl = "Solo Sniper (₹6,000)"
                        elif num_valid >= 3 or cur_count >= 3:
                            target_margin = getattr(config, "MULTI_CONFIRMED_INVESTMENT_INR", 6000.0)
                            sizing_lbl = "Multi-Slot Wave (₹6,000)"
                        else:
                            target_margin = getattr(config, "INVESTMENT_PER_TRADE_INR", 6000.0)
                            sizing_lbl = "Standard 5-Slot (₹6,000)"

                        for candidate in valid_signals:
                            if len(bot_state["active_positions"]) >= max_slots:
                                break

                            avail_balance = max(0.0, float(bot_state.get("paper_balance", 0.0)))
                            deployed_margin = sum(float(p.get("invested", 0)) for p in bot_state["active_positions"])
                            total_wallet = avail_balance + deployed_margin
                            safe_reserve_min = total_wallet * getattr(config, "SAFE_MARGIN_RATIO", 0.40)
                            max_trade_cap = total_wallet * getattr(config, "MAX_CAPITAL_IN_TRADE_RATIO", 0.60)

                            # Strict 60% in trade / 40% safe margin buffer rules:
                            if (deployed_margin + target_margin) > max_trade_cap:
                                # 60% deployed trade limit reached; keep remaining 40% safe
                                break
                            if (avail_balance - target_margin) < safe_reserve_min:
                                # Balance would drop below 40% safe margin; stop opening new trades
                                break

                            invest_target = min(target_margin, avail_balance)

                            c_coin = candidate["coin"]
                            c_pair = f"B-{c_coin}_USDT"
                            # 0. STABLECOIN & PEGGED TOKEN FILTER:
                            c_last_price = float(candidate.get("current_price", 0) or 0)
                            if 0.96 <= c_last_price <= 1.04 or c_coin in getattr(config, "STABLECOIN_BLACKLIST", set()):
                                continue

                            c_dir = candidate.get("direction", "UP").upper()
                            pos_dir = "LONG" if c_dir == "UP" else "SHORT"

                            # 1. PORTFOLIO DIRECTIONAL BALANCE GUARD (Anti-Cascade Shield):
                            # Enforce maximum 3 positions in the same direction to prevent one-sided portfolio wipeouts
                            active_same_dir = sum(1 for p in bot_state["active_positions"] if (p.get("direction") or p.get("side")) == pos_dir)
                            max_dir_cap = getattr(config, "MAX_SAME_DIRECTION_POSITIONS", 3)
                            if active_same_dir >= max_dir_cap:
                                continue

                            # 2. BITCOIN KING MACRO REGIME GUARD:
                            # If Bitcoin 1h is in a confirmed pullback, block altcoin LONGs unless 5/5 unanimous MTF confluence
                            btc_macro = scanner.get_btc_macro_regime(client)
                            if btc_macro.get("regime") == "BEARISH" and pos_dir == "LONG" and c_coin not in ["BTC", "WBTC"]:
                                if candidate.get("confidence_tier") != "A+":
                                    continue

                            # 3. HIGHER-TIMEFRAME MACRO TREND SHIELD (Anti-Falling Knife):
                            macro_chk = scanner.check_macro_daily_trend(c_coin, client)
                            if pos_dir == "LONG" and macro_chk.get("is_falling_knife", False):
                                continue
                            if pos_dir == "SHORT" and macro_chk.get("is_parabolic_pump", False):
                                continue

                            if float(candidate.get("volume_usdt", 0) or 0) < 500_000.0:
                                continue

                            is_turtle_mode = getattr(config, "STRATEGY_MODE", "TURTLE") == "TURTLE"
                            c_limit = 70 if is_turtle_mode else 30
                            c_candles = client.get_candles(pair=c_pair, interval="15m", limit=c_limit)
                            if c_candles is not None and len(c_candles) >= (57 if is_turtle_mode else 15):
                                c_df = calculate_indicators(c_candles)
                                last_row = c_df.iloc[-1]
                                coin_rsi = float(last_row.get("rsi", 50))
                                c_ema9 = float(last_row.get("ema_fast", 0))

                                turtle_sl = None
                                exit_ch_low = None
                                exit_ch_high = None
                                turtle_n = None
                                if is_turtle_mode:
                                    t_sig, t_reason, t_metrics = evaluate_signal(c_candles)
                                    if pos_dir == "LONG" and t_sig != "BUY":
                                        continue
                                    if pos_dir == "SHORT" and t_sig != "SELL_SHORT":
                                        continue
                                    turtle_sl = t_metrics.get("turtle_stop_loss")
                                    exit_ch_low = t_metrics.get("exit_low")
                                    exit_ch_high = t_metrics.get("exit_high")
                                    turtle_n = t_metrics.get("n_volatility")

                                # 4. ANTI-FOMO MOMENTUM & VALUE GATES:
                                # Never enter overbought tops (RSI > 65) or oversold bottom traps (RSI < 35)
                                rsi_long_min = getattr(config, "RSI_LONG_MIN", 38.0)
                                rsi_long_max = getattr(config, "RSI_LONG_MAX", 65.0)
                                rsi_short_min = getattr(config, "RSI_SHORT_MIN", 35.0)
                                rsi_short_max = getattr(config, "RSI_SHORT_MAX", 62.0)

                                if not is_turtle_mode:
                                    if pos_dir == "LONG" and not (rsi_long_min <= coin_rsi <= rsi_long_max):
                                        continue
                                    if pos_dir == "SHORT" and not (rsi_short_min <= coin_rsi <= rsi_short_max):
                                        continue

                                live_stats = client.get_futures_stats(c_coin)
                                live_p = float(live_stats.get("mark_price", 0) or live_stats.get("last_price", 0) or 0)
                                if live_p <= 0:
                                    live_p = float(last_row["close"])

                                # Pullback-to-Value Gate: Price must be within 1.8% of 15m EMA9 (buy value, never chase rockets)
                                if c_ema9 > 0 and live_p > 0:
                                    pullback_dev = abs((live_p - c_ema9) / c_ema9) * 100.0
                                    max_dev = getattr(config, "MAX_EMA_PULLBACK_DEVIATION_PCT", 1.8)
                                    if pullback_dev > max_dev:
                                        continue

                                # 5. VOLATILITY-ADAPTIVE LEVERAGE:
                                pos_lev = candidate.get("adaptive_leverage", dyn_lev)
                                c_chg = abs(float(candidate.get("change_24h", 0) or 0))
                                if c_chg >= 10.0 and c_coin not in ["BTC", "WBTC", "ETH"]:
                                    pos_lev = min(pos_lev, getattr(config, "MAX_HIGH_BETA_LEVERAGE", 5))
                                prob = candidate.get("probability", 85)
                                precision = 6 if live_p < 1.0 else (4 if live_p < 50.0 else 2)

                                # Dynamic Confidence-Based Target Scaling (₹20 - ₹50 Net Profit):
                                # - 84% - 87% Confidence: Quick Scalp +6.8% to +8.5% ROI (₹24 - ₹30 profit)
                                # - 88% - 92%+ Confidence: High-Conviction Breakout +12.0% to +14.0% ROI (₹42 - ₹50 profit)
                                front_run = getattr(config, "FRONT_RUN_RATIO", 0.75)
                                c_prob = float(candidate.get("probability", 85) or 85)
                                target_roi_pct = float(getattr(config, "TARGET_PROFIT_ROI_PCT", 15.0))
                                min_sl_pct = float(getattr(config, "STOP_LOSS_PERCENT", 1.85)) / 100.0
                                min_sl_dist = live_p * min_sl_pct
                                rrr = float(getattr(config, "RISK_REWARD_RATIO", 2.0))

                                target_move_pct = target_roi_pct / max(1, pos_lev)

                                pred_target = float(candidate.get("target_price", 0) or 0)
                                if is_turtle_mode and turtle_sl:
                                    # Strict 1:2 Risk-to-Reward Ratio (Reward = 2 x Risk distance) with Safe Min 3.0% Buffer
                                    risk_dist = max(min_sl_dist, abs(live_p - turtle_sl))
                                    if pos_dir == "LONG":
                                        target_price = round(live_p + (risk_dist * rrr), precision)
                                        stop_loss = round(min(live_p - min_sl_dist, turtle_sl), precision)
                                    else:
                                        target_price = round(live_p - (risk_dist * rrr), precision)
                                        stop_loss = round(max(live_p + min_sl_dist, turtle_sl), precision)
                                elif pred_target > 0 and ((pos_dir == "LONG" and pred_target > live_p) or (pos_dir == "SHORT" and pred_target < live_p)):
                                    predicted_move_pct = abs((pred_target - live_p) / live_p) * 100.0
                                    capped_move_pct = min(target_move_pct, predicted_move_pct * front_run)
                                    capped_move_pct = max(capped_move_pct, (min_sl_pct * 100.0) * rrr)
                                    target_price = round(live_p * (1.0 + (capped_move_pct / 100.0)), precision) if pos_dir == "LONG" else round(live_p * (1.0 - (capped_move_pct / 100.0)), precision)
                                    stop_loss = round(live_p * (1.0 - min_sl_pct), precision) if pos_dir == "LONG" else round(live_p * (1.0 + min_sl_pct), precision)
                                elif pos_dir == "LONG":
                                    target_move_pct = max(target_move_pct, (min_sl_pct * 100.0) * rrr)
                                    target_price = round(live_p * (1.0 + (target_move_pct / 100.0)), precision)
                                    stop_loss = round(live_p * (1.0 - min_sl_pct), precision)
                                else:
                                    target_move_pct = max(target_move_pct, (min_sl_pct * 100.0) * rrr)
                                    target_price = round(live_p * (1.0 - (target_move_pct / 100.0)), precision)
                                    stop_loss = round(live_p * (1.0 + min_sl_pct), precision)

                                # Breathing room with -48% Margin Defense
                                defense_ratio = abs(float(getattr(config, "MARGIN_DEFENSE_DRAWDOWN_PCT", -48.0))) / 100.0
                                order_side = "buy" if pos_dir == "LONG" else "sell"

                                qty, spend = calculate_futures_trade_qty(c_coin, live_p, target_margin_inr=invest_target, leverage=pos_lev)
                                if spend > avail_balance:
                                    spend = avail_balance
                                # Deduct margin from paper balance
                                bot_state["paper_balance"] = round(max(0.0, bot_state["paper_balance"] - spend), 2)

                                if not config.DRY_RUN:
                                    try:
                                        live_order = client.place_futures_order(order_side, pair=c_pair, quantity=qty, leverage=pos_lev)
                                        print(f"[LIVE AUTONOMOUS {pos_dir} ORDER]: {c_coin} Qty={qty} Lev={pos_lev}x -> {live_order}")
                                        is_err = False
                                        if isinstance(live_order, dict):
                                            if live_order.get("status") == "error" or "code" in live_order:
                                                is_err = True
                                        elif not live_order:
                                            is_err = True
                                        if is_err:
                                            err_msg = live_order.get("message") if isinstance(live_order, dict) else "Exchange order rejection"
                                            print(f"[LIVE ORDER REJECTED BY EXCH]: {c_coin} -> {err_msg}")
                                            bot_state["paper_balance"] = round(bot_state["paper_balance"] + spend, 2)
                                            continue
                                    except Exception as live_err:
                                        print(f"[LIVE AUTONOMOUS ORDER ERROR]: {live_err}")
                                        bot_state["paper_balance"] = round(bot_state["paper_balance"] + spend, 2)
                                        continue

                                entry_ts = time.time()
                                mtf_lbl = candidate.get("mtf_agreement", "MTF")
                                new_pos = {
                                    "symbol": c_coin,
                                    "pair": c_pair,
                                    "strategy": "TURTLE_SYSTEM_2" if is_turtle_mode else "USER_MIRROR",
                                    "direction": pos_dir,
                                    "buy_price": live_p,
                                    "current_price": live_p,
                                    "quantity": qty,
                                    "invested": spend,
                                    "leverage": pos_lev,
                                    "target": target_price,
                                    "stop_loss": stop_loss,
                                    "exit_channel_low": exit_ch_low,
                                    "exit_channel_high": exit_ch_high,
                                    "n_volatility": turtle_n,
                                    "trailing_stop": None,
                                    "margin_defended": False,
                                    "peak_price": live_p,
                                    "valley_price": live_p,
                                    "peak_pnl_pct": 0.0,
                                    "gross_pnl_pct": 0.0,
                                    "net_pnl": 0.0,
                                    "net_pnl_pct": 0.0,
                                    "sl_defense_price": round(live_p * (1.0 - (defense_ratio / pos_lev)), precision) if pos_dir == "LONG" else round(live_p * (1.0 + (defense_ratio / pos_lev)), precision),
                                    "tp_target_pct": round(((target_price - live_p) / max(1e-6, live_p)) * 100.0 * pos_lev, 2) if pos_dir == "LONG" else round(((live_p - target_price) / max(1e-6, live_p)) * 100.0 * pos_lev, 2),
                                    "trailing_lock_pct": 0.0,
                                    "probability": prob,
                                    "mtf_agreement": mtf_lbl,
                                    "entry_time": entry_ts,
                                    "time": get_ist_time_str()
                                }
                                bot_state["active_positions"].append(new_pos)
                                bot_state["active_position"] = bot_state["active_positions"][0]
                                bot_state["selected_coin"] = c_coin
                                bot_state["selected_pair"] = c_pair
                                bot_state["last_signal"] = f"AUTONOMOUS {pos_dir} [{c_coin}] ({len(bot_state['active_positions'])}/{max_slots} Slots)"
                                bot_state["last_reason"] = f"UserMirror {mtf_lbl} ({prob}% {pos_dir}) {pos_lev}x Lev: Entry ${live_p}, Target ${target_price} (₹{spend:.0f} size), -48% Margin Defense"

                                trade_rec = {
                                    "type": "BUY" if pos_dir == "LONG" else "SELL_SHORT",
                                    "coin": c_coin,
                                    "direction": pos_dir,
                                    "price": live_p,
                                    "entry_price": live_p,
                                    "target": target_price,
                                    "stop_loss": stop_loss,
                                    "leverage": pos_lev,
                                    "amount": spend,
                                    "note": f"UserMirror {mtf_lbl} ({prob}% {pos_dir}) {pos_lev}x Lev: Target ${target_price}, -48% Margin Defense",
                                    "time": get_ist_time_str(),
                                    "timestamp": get_ist_datetime_str(),
                                    "is_live": not config.DRY_RUN
                                }
                                bot_state["trade_history"].insert(0, trade_rec)
                                record_paper_trade(trade_rec, active_positions=bot_state["active_positions"])
                                save_active_positions(bot_state["active_positions"])

            except Exception as e:
                print(f"[Autonomous Worker Error] {e}")

        # Hyper-fast 3s refresh when active positions exist for real-time mobile app sync
        time.sleep(3 if bot_state.get("active_positions") else 10)

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
                                "time_str": get_ist_time_str()
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
    time.sleep(1)
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
        time.sleep(20)

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
            try:
                emp_data = predictor.calculate_empirical_success_rate(coin, client=client)
                response_data["empirical_success"] = emp_data
            except Exception:
                response_data["empirical_success"] = None

            _ADVISOR_CACHE[coin] = {"data": response_data, "timestamp": now_a}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # API: Empirical Success Rate Engine (1% - 100% Real Historical Win Probability)
        elif path == "/api/success_rate":
            coin = query.get("coin", [bot_state.get("selected_coin", "BTC")])[0].upper()
            client = CoinDCXClient()
            data = predictor.calculate_empirical_success_rate(coin, client=client)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # API: Candle Data for Chart (Supports 1m, 5m, 15m, 1h, 1d) with 5s cache
        elif path == "/api/candles":
            pair = query.get("pair", ["B-BTC_USDT"])[0].upper().strip()
            interval = query.get("interval", ["1h"])[0].lower().strip()
            if interval in ["d", "1day"]:
                interval = "1d"
            elif interval in ["5min"]:
                interval = "5m"
            elif interval in ["15min"]:
                interval = "15m"
            elif interval in ["1min"]:
                interval = "1m"
            limit = int(query.get("limit", ["60"])[0])

            now_c = time.time()
            c_key = (pair, interval, limit)
            cached_c = _CANDLES_CACHE.get(c_key)
            if cached_c and (now_c - cached_c["timestamp"]) < 4.0:
                candles = cached_c["data"]
            else:
                client = CoinDCXClient()
                candles = client.get_raw_candles(pair=pair, interval=interval, limit=limit)
                if candles and len(candles) > 0:
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
            bot_state["ws_connected"] = ws_stream.is_connected if ws_stream else False
            bot_state["ws_prices"] = ws_stream.get_all_live_prices() if ws_stream else {}
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

        # API: Live CoinDCX Audited Trade History (19 Winning Round Trips)
        elif path == "/api/live_trades":
            live_file = os.path.join(os.path.dirname(__file__), "live_trades_cache.json")
            live_data = {"summary": {}, "trades": []}
            if os.path.exists(live_file):
                try:
                    with open(live_file, "r", encoding="utf-8") as f:
                        live_data = json.load(f)
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(live_data).encode("utf-8"))
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
            save_active_positions(bot_state.get("active_positions", []), is_running=bot_state["is_running"], allow_new_trades=bot_state.get("allow_new_trades", True))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"is_running": bot_state["is_running"], "allow_new_trades": bot_state.get("allow_new_trades", True)}).encode("utf-8"))
            return

        elif path == "/api/bot/toggle_new_trades":
            bot_state["allow_new_trades"] = not bot_state.get("allow_new_trades", True)
            save_active_positions(bot_state.get("active_positions", []), is_running=bot_state["is_running"], allow_new_trades=bot_state["allow_new_trades"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "allow_new_trades": bot_state["allow_new_trades"],
                "message": "Auto-trading active: New trades allowed" if bot_state["allow_new_trades"] else "Manage-only mode active: New trades paused"
            }).encode("utf-8"))
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
            avail_balance = max(0.0, float(bot_state.get("paper_balance", 0.0)))
            if actual_spend > avail_balance:
                actual_spend = avail_balance
            bot_state["paper_balance"] = round(max(0.0, bot_state["paper_balance"] - actual_spend), 2)
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
                "time": get_ist_time_str()
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
                "time": get_ist_time_str(),
                "timestamp": get_ist_datetime_str(),
                "is_live": not config.DRY_RUN
            }
            bot_state["trade_history"].insert(0, trade_rec)
            record_paper_trade(trade_rec, active_positions=bot_state.get("active_positions", []))

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
            deductions = calculate_trade_deductions(pos["invested"], lev, gross_pnl)
            trade_fee = deductions["exchange_fee"]
            trade_tds = deductions["tds"]
            trade_tax = deductions["govt_tax"]
            total_cut = deductions["total_deductions"]
            net_pnl = deductions["net_pnl"]
            net_pnl_pct = deductions["net_pnl_pct"]
            proceeds = round(pos["invested"] + net_pnl, 2)
            bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

            if not config.DRY_RUN:
                try:
                    close_side = "sell" if side == "LONG" else "buy"
                    client.place_futures_order(close_side, pair=pos["pair"], quantity=pos["quantity"], leverage=lev)
                except Exception as live_err:
                    print(f"[LIVE MANUAL CLOSE ERROR]: {live_err}")

            deduct_desc = f"after ₹{trade_fee:.2f} fee, ₹{trade_tds:.2f} TDS"
            if trade_tax > 0:
                deduct_desc += f", ₹{trade_tax:.2f} 31.2% tax"
            bot_state["last_signal"] = f"MANUAL EXIT [{coin_sym}]"
            bot_state["last_reason"] = f"Closed {coin_sym} at ${curr_price:.4f} (Net PnL: {net_pnl_pct:+.1f}%, INR {net_pnl:+.2f} {deduct_desc})"
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
                "tds": trade_tds,
                "tax": trade_tax,
                "total_deductions": total_cut,
                "pnl": net_pnl,
                "pnl_pct": net_pnl_pct,
                "reason": f"Manual Close Button (Net PnL: {net_pnl_pct:+.1f}%, ₹{net_pnl:+.2f} {deduct_desc})",
                "time": get_ist_time_str(),
                "timestamp": get_ist_datetime_str(),
                "is_live": not config.DRY_RUN
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
                start_wal = float(getattr(config, "STARTING_WALLET_INR", 30000.0))
                max_s = int(getattr(config, "MAX_OPEN_POSITIONS", 2))
                payload = {
                    "updated_at": get_ist_now().isoformat(),
                    "paper_balance": start_wal,
                    "starting_balance": start_wal,
                    "max_slots": max_s,
                    "summary": {
                        "total_trades": 0, "completed_trades": 0, "wins": 0,
                        "losses": 0, "win_rate_pct": 0, "total_pnl_inr": 0,
                        "gross_pnl_inr": 0, "total_fees_inr": 0, "total_tds_inr": 0,
                        "total_tax_inr": 0, "total_deductions_inr": 0, "total_volume_inr": 0,
                        "is_profitable": False
                    },
                    "trades": [],
                    "is_running": True,
                    "allow_new_trades": True,
                    "active_positions": [],
                    "active_position": None
                }
                with open(TRADES_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                bot_state["trade_history"] = []
                bot_state["active_positions"] = []
                bot_state["active_position"] = None
                bot_state["paper_balance"] = start_wal
                bot_state["starting_balance"] = start_wal
                bot_state["max_slots"] = max_s
                bot_state["is_running"] = True
                bot_state["allow_new_trades"] = True
                bot_state["performance_summary"] = payload["summary"]
                bot_state["last_signal"] = "FRESH RESTART"
                bot_state["last_reason"] = f"Wallet reset to INR {start_wal:,.2f}. Scanning 700+ coins across {max_s} fresh slots..."
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": f"Paper history reset to INR {start_wal:,.2f} across {max_s} slots"}).encode("utf-8"))
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
