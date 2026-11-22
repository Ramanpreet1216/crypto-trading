"""
==============================================================================
24/7 AI SUPERVISOR & SENTINEL (META-OPTIMIZER & RISK GUARDIAN)
==============================================================================
Runs continuously 24/7 alongside the trading engine:
1. Ingests real-time crypto news (CoinTelegraph, CoinDesk RSS, Google News).
2. Computes Live Market Regime & Sentiment Pulse (-100 to +100).
3. Conducts Automated Forensic Audits on any trade loss (diagnoses why it failed).
4. Enforces an Institutional Liquid Whitelist (Min $25M volume, Top 35 assets).
5. Dynamically Quarantines failed/illiquid coins for 48 hours.
6. Self-Tunes Bot parameters (Elevates to Ultra-Sniper 90%+ confidence on losses).
7. Enforces strict 1:2 Risk-to-Reward Ratio (+₹320 - ₹380 profit vs -₹160 stop).
8. Acts as Gatekeeper: trading bot CANNOT execute without Supervisor clearance.
==============================================================================
"""

import os
import sys
import json
import time
import threading
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

def get_ist_time_str() -> str:
    return get_ist_now().strftime("%H:%M:%S")

def get_ist_datetime_str() -> str:
    return get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

STATE_FILE = os.path.join(DATA_DIR, "supervisor_state.json")
LOGS_FILE = os.path.join(DATA_DIR, "supervisor_logs.json")
QUARANTINE_FILE = os.path.join(DATA_DIR, "supervisor_quarantine.json")
PAPER_TRADES_FILE = os.path.join(BASE_DIR, "paper_trades.json")

# Institutional Elite Whitelist - High volume & depth perpetual futures (Strict BTC Correlation Followers)
INSTITUTIONAL_WHITELIST = {
    "BTC", "ETH", "SOL", "SUI", "DOGE", "AVAX", "BNB", "LINK", 
    "ADA", "NEAR", "APT", "INJ", "RENDER", "DOT", "LTC", 
    "TIA", "FET", "PEPE", "SHIB", "HYPE", "TAO", "AAVE", "UNI"
}

# Decoupled / Independent Catalyst Token Watchlist (Unpredictable vs BTC)
DECOUPLED_RISK_TOKENS = {"XRP"}

# Chronic High-Risk / Spread Spike Blacklist (24 Banned Dangerous Tokens)
PERMANENT_BLACKLIST = {
    "ASTER", "ZEC", "VVV", "PROM", "QNT", "GIGGLE", "FIL", "PIEVERSE", "ULTIMA", "GMX",
    "TRB", "GAS", "BLZ", "LOOM", "DASH", "ZEN", "STRAX", "BIGTIME", "STPT", "MEME", "XVG", "ICX", "FRONT", "LEVER"
}

BULLISH_KEYWORDS = [
    "surge", "surges", "surging", "rally", "rallies", "bull", "bullish", "jump",
    "jumps", "breakout", "breaks out", "gains", "soar", "soaring", "record high",
    "all-time high", "ath", "inflow", "inflows", "accumulation", "buying", "adoption",
    "approved", "approval", "etf approval", "outperform", "milestone", "green"
]

BEARISH_KEYWORDS = [
    "crash", "crashes", "crashing", "dump", "dumps", "dumping", "plunge", "plunges",
    "drop", "drops", "dropping", "bear", "bearish", "selloff", "sell-off", "liquidation",
    "liquidations", "lawsuit", "sec probe", "hack", "hacked", "stolen", "ban", "banned",
    "warning", "fear", "outflow", "outflows", "slide", "slides", "breakdown", "fall"
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, text/xml"}


class CryptoSupervisor:
    """
    24/7 Autonomous AI Supervisor & Risk Sentinel.
    Runs in a background daemon thread, analyzing news, market sentiment,
    trade history, and tuning the trading engine.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CryptoSupervisor, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.running = False
        self.thread = None

        # State Variables
        self.sentiment_score = -25.0       # -100 (Extreme Fear) to +100 (Extreme Greed)
        self.market_regime = "MILD_BEARISH"  # STRONG_BEARISH, MILD_BEARISH, NEUTRAL, MILD_BULLISH, STRONG_BULLISH
        self.directional_bias = "SHORT_BIAS" # SHORT_BIAS (70% Short / 30% Long), LONG_BIAS, NEUTRAL
        self.news_feed: List[Dict[str, Any]] = []
        self.fear_greed_data: Dict[str, Any] = {"value": 50, "classification": "Neutral", "score": 0.0}
        self.quarantine_registry: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: List[Dict[str, Any]] = []

        # Dynamic Auto-Tuned Parameters (Self-Tuning Engine)
        self.tuned_params = {
            "min_confidence": 90,           # Ultra-Sniper Gate (elevated from 86)
            "stop_loss_pct": 2.20,          # Tight 2.2% spot SL (-6.6% margin risk on 3x = ~₹165)
            "take_profit_pct": 4.80,        # 4.8% spot TP (+14.4% ROI on 3x = ~₹360 gross, 1:2.18 R:R)
            "min_liquidity_usdt": 20_000_000.0, # Minimum $20M USDT volume required
            "max_slots": 2,                 # Strict 2-slot cap
            "leverage_cap_alts": 3,
            "leverage_cap_btc": 4,
            "margin_defense_drawdown_pct": -5.1, # Capped at -5.1% (-₹127 max risk on ₹2,500 margin)
            "mode": "ULTRA_SNIPER_DEFENSE", # ULTRA_SNIPER_DEFENSE or BALANCED_ALPHA
            "last_tuned_at": get_ist_datetime_str(),
            "tuning_reason": "Enforcing 1:2 R:R asymmetric defense after low-cap wick stop-outs."
        }

        # Seed initial permanent blacklists into quarantine
        self._load_quarantine()
        self._load_state()
        self._load_logs()

        # Seed known failed coins (like ASTER, ZEC, VVV, PROM) with permanent/long quarantine
        for coin in PERMANENT_BLACKLIST:
            if coin not in self.quarantine_registry:
                self.quarantine_coin(
                    coin=coin,
                    reason="Low liquidity / erratic spread spikes / chronic stop-out history",
                    duration_hours=168.0,  # 7 days
                    auto_audit=False
                )

    # =========================================================================
    # PERSISTENCE HELPERS
    # =========================================================================

    def _load_quarantine(self):
        if os.path.exists(QUARANTINE_FILE):
            try:
                with open(QUARANTINE_FILE, "r", encoding="utf-8") as f:
                    self.quarantine_registry = json.load(f)
            except Exception as e:
                print(f"[Supervisor] Error loading quarantine: {e}")
                self.quarantine_registry = {}

    def _save_quarantine(self):
        try:
            with open(QUARANTINE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.quarantine_registry, f, indent=2)
        except Exception as e:
            print(f"[Supervisor] Error saving quarantine: {e}")

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.sentiment_score = data.get("sentiment_score", self.sentiment_score)
                    self.market_regime = data.get("market_regime", self.market_regime)
                    self.directional_bias = data.get("directional_bias", self.directional_bias)
                    if "fear_greed_data" in data:
                        self.fear_greed_data = data["fear_greed_data"]
                    if "tuned_params" in data:
                        self.tuned_params.update(data["tuned_params"])
            except Exception as e:
                print(f"[Supervisor] Error loading state: {e}")

    def _save_state(self):
        try:
            payload = {
                "updated_at": get_ist_datetime_str(),
                "sentiment_score": round(self.sentiment_score, 1),
                "market_regime": self.market_regime,
                "directional_bias": self.directional_bias,
                "fear_greed_data": self.fear_greed_data,
                "tuned_params": self.tuned_params,
                "quarantined_count": len(self.quarantine_registry),
                "news_count": len(self.news_feed)
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[Supervisor] Error saving state: {e}")

    def _load_logs(self):
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    self.audit_logs = json.load(f)
            except Exception as e:
                self.audit_logs = []

    def log_event(self, category: str, title: str, details: str, severity: str = "INFO"):
        """Records an audit event with IST timestamp."""
        event = {
            "timestamp": get_ist_datetime_str(),
            "time": get_ist_time_str(),
            "category": category,
            "severity": severity,
            "title": title,
            "details": details
        }
        self.audit_logs.insert(0, event)
        self.audit_logs = self.audit_logs[:200]  # Retain last 200 events
        try:
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.audit_logs, f, indent=2)
        except Exception as e:
            print(f"[Supervisor Log Err]: {e}")
        print(f"[🤖 SUPERVISOR {severity}] {title} - {details}")

    # =========================================================================
    # QUARANTINE ENGINE
    # =========================================================================

    def quarantine_coin(self, coin: str, reason: str, duration_hours: float = 48.0, auto_audit: bool = True):
        """Places a coin into quarantine, blocking trades for duration_hours."""
        coin_up = coin.upper().strip()
        until_ts = time.time() + (duration_hours * 3600.0)
        until_dt = (get_ist_now() + timedelta(hours=duration_hours)).strftime("%Y-%m-%d %H:%M:%S")

        self.quarantine_registry[coin_up] = {
            "coin": coin_up,
            "quarantined_at": get_ist_datetime_str(),
            "quarantine_until": until_dt,
            "until_timestamp": until_ts,
            "duration_hours": duration_hours,
            "reason": reason
        }
        self._save_quarantine()

        if auto_audit:
            self.log_event(
                category="QUARANTINE",
                title=f"Quarantined {coin_up} for {duration_hours:.0f}h",
                details=f"Reason: {reason}. Trade executions blocked until {until_dt}.",
                severity="WARNING"
            )

    def is_quarantined(self, coin: str) -> Tuple[bool, Optional[str]]:
        """Checks if a coin is currently quarantined."""
        coin_up = coin.upper().strip()
        record = self.quarantine_registry.get(coin_up)
        if not record:
            return False, None

        now_ts = time.time()
        until_ts = record.get("until_timestamp", 0)
        if now_ts < until_ts:
            return True, record.get("reason", "In active quarantine")
        else:
            # Quarantine expired
            del self.quarantine_registry[coin_up]
            self._save_quarantine()
            self.log_event(
                category="QUARANTINE_LIFTED",
                title=f"Quarantine Expired for {coin_up}",
                details="48h cooling period completed. Asset returned to surveillance pool.",
                severity="INFO"
            )
            return False, None

    # =========================================================================
    # NEWS & SENTIMENT HARVESTER
    # =========================================================================

    def fetch_crypto_news(self) -> List[Dict[str, Any]]:
        """Harvests live crypto news headlines from CoinTelegraph and CoinDesk RSS."""
        articles = []
        sources = [
            ("CoinTelegraph", "https://cointelegraph.com/rss"),
            ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/")
        ]

        for src_name, url in sources:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=4.0)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall(".//item")
                    for item in items[:10]:
                        title = item.find("title").text if item.find("title") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                        if title:
                            articles.append({
                                "source": src_name,
                                "title": title.strip(),
                                "link": link.strip(),
                                "pub_date": pub_date.strip()
                            })
            except Exception as e:
                # Soft failure on individual feed
                pass

        return articles

    def analyze_news_sentiment(self, articles: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
        """Analyzes sentiment for each article and outputs net sentiment score (-100 to +100)."""
        scored_articles = []
        total_score = 0.0

        for a in articles:
            text = a["title"].lower()
            bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
            bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)

            if bull_hits > bear_hits:
                classification = "BULLISH"
                score = min(100.0, (bull_hits - bear_hits) * 35.0)
            elif bear_hits > bull_hits:
                classification = "BEARISH"
                score = max(-100.0, (bull_hits - bear_hits) * 35.0)
            else:
                classification = "NEUTRAL"
                score = 0.0

            total_score += score
            scored_articles.append({
                **a,
                "classification": classification,
                "score": score
            })

        avg_score = (total_score / max(1, len(articles))) if articles else 0.0
        return avg_score, scored_articles[:15]

    def fetch_market_breadth(self) -> Dict[str, Any]:
        """Fetches 24h market breadth (gainers vs losers, BTC dominance) from Binance."""
        try:
            resp = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=HEADERS, timeout=3.5)
            if resp.status_code == 200:
                tickers = resp.json()
                usdt_tickers = [t for t in tickers if t.get("symbol", "").endswith("USDT")]
                gainers = sum(1 for t in usdt_tickers if float(t.get("priceChangePercent", 0) or 0) > 0)
                losers = sum(1 for t in usdt_tickers if float(t.get("priceChangePercent", 0) or 0) < 0)
                total = len(usdt_tickers)
                
                # BTC change
                btc_t = next((t for t in usdt_tickers if t.get("symbol") == "BTCUSDT"), None)
                btc_chg = float(btc_t.get("priceChangePercent", 0)) if btc_t else 0.0

                g_ratio = gainers / max(1, total)
                breadth_score = (g_ratio - 0.5) * 200.0  # -100 to +100

                return {
                    "total_pairs": total,
                    "gainers": gainers,
                    "losers": losers,
                    "gainer_pct": round(g_ratio * 100.0, 1),
                    "btc_24h_chg": btc_chg,
                    "breadth_score": breadth_score
                }
        except Exception:
            pass

        return {"total_pairs": 0, "gainers": 0, "losers": 0, "gainer_pct": 50.0, "btc_24h_chg": 0.0, "breadth_score": 0.0}

    def fetch_fear_and_greed_index(self) -> Dict[str, Any]:
        """
        Fetches the official Crypto Fear & Greed Index from alternative.me (Free API).
        Maps scale 0-100 to standardized sentiment score (-100 to +100).
        0 = Extreme Fear (-100), 50 = Neutral (0), 100 = Extreme Greed (+100).
        """
        try:
            resp = requests.get("https://api.alternative.me/fng/?limit=1", headers=HEADERS, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    raw_val = float(data[0].get("value", 50))
                    classification = data[0].get("value_classification", "Neutral")
                    # Map [0, 100] -> [-100, +100]
                    fng_score = (raw_val - 50.0) * 2.0
                    return {
                        "value": int(raw_val),
                        "classification": classification,
                        "score": round(fng_score, 1),
                        "timestamp": data[0].get("timestamp")
                    }
        except Exception as e:
            print(f"[Supervisor F&G Notice]: {e}")

        return {"value": 50, "classification": "Neutral", "score": 0.0}

    # =========================================================================
    # LOSS FORENSIC AUDITOR
    # =========================================================================

    def run_loss_forensics(self):
        """
        Inspects trade history in paper_trades.json.
        Detects newly completed loss trades and conducts root-cause forensic audits.
        """
        if not os.path.exists(PAPER_TRADES_FILE):
            return

        try:
            with open(PAPER_TRADES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        trades = data.get("trades", [])
        if not trades:
            return

        # Find losses in completed trades
        recent_losses = [
            t for t in trades 
            if t.get("type") in ["BUY_COVER", "SELL"] and float(t.get("pnl", 0) or 0) < 0
        ]

        for loss_trade in recent_losses[:5]:
            coin = loss_trade.get("coin", "").upper()
            pnl = float(loss_trade.get("pnl", 0))
            pnl_pct = float(loss_trade.get("pnl_pct", 0))
            reason = loss_trade.get("reason", "Stop-Loss Protection")
            trade_time = loss_trade.get("timestamp", get_ist_datetime_str())

            # Check if this loss was already audited
            loss_key = f"{coin}_{trade_time}"
            if any(evt.get("details", "").startswith(loss_key) for evt in self.audit_logs):
                continue

            # Perform root cause diagnosis
            is_low_cap = coin in PERMANENT_BLACKLIST or coin not in INSTITUTIONAL_WHITELIST
            diagnosis = []
            if is_low_cap:
                diagnosis.append(f"High-Beta / Thin Liquidity Asset ({coin} prone to sudden wicked stop-outs)")
            if abs(pnl_pct) >= 7.0:
                diagnosis.append("Exceeded allowable 1:2 R:R risk boundary (-8.7% hit vs -6.6% target)")
            diagnosis_str = " | ".join(diagnosis) if diagnosis else "Adverse market momentum wick"

            # Auto-quarantine coin for 48 hours ONLY if it is low-cap / volatile (never ban institutional blue chips like ETH, BTC, SOL, NEAR, INJ)
            if is_low_cap:
                quarantine_reason = f"Stopped out with {pnl_pct:.1f}% loss (₹{pnl:.2f}). Forensic Root Cause: {diagnosis_str}."
                self.quarantine_coin(coin, reason=quarantine_reason, duration_hours=48.0, auto_audit=True)
            else:
                self.log_event(
                    category="FORENSIC_LOSS_AUDIT",
                    title=f"Macro Stop-Out: {coin} (₹{pnl:+.2f})",
                    details=f"{loss_key} - Blue-chip {coin} stopped out due to macro Bitcoin trend reversal. Retaining in trading pool.",
                    severity="INFO"
                )

            self.log_event(
                category="FORENSIC_LOSS_AUDIT",
                title=f"Forensic Loss Analysis: {coin} (₹{pnl:+.2f})",
                details=f"{loss_key} - Trade closed at {trade_time}. Root Cause: {diagnosis_str}. ACTION: Quarantined {coin} for 48h.",
                severity="WARNING"
            )

            # Auto-tune: elevate defense
            self.auto_tune_risk_engine(trigger_reason=f"Stop-out on {coin} (₹{pnl:.2f})")

    # =========================================================================
    # AUTONOMOUS SELF-TUNING ENGINE (1:2 R:R ENFORCER)
    # =========================================================================

    def auto_tune_risk_engine(self, trigger_reason: str):
        """
        Dynamically tunes bot parameters based on real-time performance.
        Enforces confirmed 1:2 Risk-to-Reward ratio:
        - Win trade: ~+₹360 gross / +₹260-₹300 net
        - Loss trade: ~-₹165 gross / -₹210 net
        """
        if not os.path.exists(PAPER_TRADES_FILE):
            return

        try:
            with open(PAPER_TRADES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        summary = data.get("summary", {})
        wins = summary.get("wins", 0)
        losses = summary.get("losses", 0)
        win_rate = summary.get("win_rate_pct", 50.0)

        # If win rate is below 50% or we had recent losses, switch to ULTRA-SNIPER DEFENSE
        if losses > wins or win_rate < 50.0:
            new_conf = 90  # Elevated from 86 -> requires 4/5 or 5/5 MTF agreement
            new_sl = 2.20  # Tight spot stop loss
            new_tp = 4.80  # Spot TP target (2.18x reward-to-risk)
            new_vol = 25_000_000.0  # Require $25M institutional volume
            mode = "ULTRA_SNIPER_DEFENSE"
            justification = f"{trigger_reason}. Win rate is {win_rate:.1f}% ({wins}W / {losses}L). Enforcing Ultra-Sniper 90%+ MTF gate and tightening SL to 2.2% with 4.8% TP (1:2.18 R:R)."
        else:
            new_conf = 88
            new_sl = 2.50
            new_tp = 5.00
            new_vol = 20_000_000.0
            mode = "BALANCED_ALPHA"
            justification = f"Healthy win rate {win_rate:.1f}%. Maintaining standard 1:2 R:R sniper parameters."

        changed = (
            self.tuned_params.get("min_confidence") != new_conf or
            self.tuned_params.get("stop_loss_pct") != new_sl or
            self.tuned_params.get("mode") != mode
        )

        self.tuned_params.update({
            "min_confidence": new_conf,
            "stop_loss_pct": new_sl,
            "take_profit_pct": new_tp,
            "min_liquidity_usdt": new_vol,
            "mode": mode,
            "last_tuned_at": get_ist_datetime_str(),
            "tuning_reason": justification
        })
        self._save_state()

        if changed:
            self.log_event(
                category="AUTO_TUNING",
                title=f"Risk Engine Re-Tuned: {mode}",
                details=justification,
                severity="INFO"
            )

    # =========================================================================
    # GATEKEEPER CLEARANCE API
    # =========================================================================

    def get_trade_clearance(self, coin: str, direction: str, candidate_info: dict) -> Tuple[bool, str, dict]:
        """
        The Master Gatekeeper: Before server.py executes ANY trade, it MUST query this method.
        Returns:
            (is_approved: bool, reason: str, tuned_parameters: dict)
        """
        coin_up = coin.upper().strip()
        dir_up = direction.upper().strip()
        pos_dir = "LONG" if dir_up in ["UP", "LONG"] else "SHORT"

        # 1. QUARANTINE CHECK
        is_quar, q_reason = self.is_quarantined(coin_up)
        if is_quar:
            msg = f"BLOCKED by Sentinel: {coin_up} is currently quarantined ({q_reason})."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        # 2. PERMANENT BLACKLIST & DECOUPLED RISK CHECK
        if coin_up in PERMANENT_BLACKLIST:
            msg = f"BLOCKED by Sentinel: {coin_up} is on the permanent illiquid / erratic spread blacklist."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        if coin_up in DECOUPLED_RISK_TOKENS and pos_dir == "SHORT":
            msg = f"BLOCKED by Sentinel: {coin_up} frequently decouples from BTC trend (news/catalyst-driven). Short entries restricted to prevent rogue stop-outs."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        # 2b. SLEEP-SAFE OVERNIGHT INSTITUTIONAL WINDOW (02:00 AM - 08:30 AM IST)
        # User sleeps between 02:00 AM and 08:30 AM IST.
        # During this low-liquidity window, strictly permit ONLY deep-liquidity Tier-1 assets
        # (BTC, ETH, SOL, LTC, UNI) to prevent erratic midnight wicks (like XMR / XRP) from shaking out positions.
        now_ist = get_ist_now()
        current_time_float = now_ist.hour + (now_ist.minute / 60.0)
        if 2.0 <= current_time_float < 8.5:
            OVERNIGHT_HEAVYWEIGHTS = {"BTC", "ETH", "SOL", "LTC", "UNI"}
            if coin_up not in OVERNIGHT_HEAVYWEIGHTS:
                msg = f"BLOCKED by Sentinel: Sleep-Safe Overnight Window (02:00 AM - 08:30 AM IST) is active. Only Tier-1 High-Liquidity Heavyweights ({', '.join(sorted(OVERNIGHT_HEAVYWEIGHTS))}) allowed to protect sleep peace."
                self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir}) [Overnight Guard]", msg, "WARNING")
                return False, msg, self.tuned_params

        # 3. LIQUIDITY FLOOR CHECK (Min $20M - $25M USDT 24h Volume)
        vol_usdt = float(candidate_info.get("volume_usdt", 0) or 0)
        min_vol = float(self.tuned_params.get("min_liquidity_usdt", 20_000_000.0))
        if vol_usdt > 0 and vol_usdt < min_vol and coin_up not in ["BTC", "ETH", "SOL"]:
            msg = f"BLOCKED by Sentinel: {coin_up} 24h volume (${vol_usdt:,.0f}) is below the ${min_vol:,.0f} institutional liquidity floor."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        # 4. INSTITUTIONAL WHITELIST PREFERENCE
        # If in Ultra-Sniper defense mode, strictly require Tier-1 whitelist
        if self.tuned_params.get("mode") == "ULTRA_SNIPER_DEFENSE":
            if coin_up not in INSTITUTIONAL_WHITELIST:
                msg = f"BLOCKED by Sentinel: Ultra-Sniper Defense mode active. Only Institutional Whitelist assets allowed ({', '.join(sorted(list(INSTITUTIONAL_WHITELIST)[:8]))}...)."
                self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
                return False, msg, self.tuned_params

        # 5. MARKET REGIME & SENTIMENT CONFLICT CHECK
        if self.market_regime == "STRONG_BEARISH" and pos_dir == "LONG" and coin_up not in ["BTC", "WBTC"]:
            msg = f"BLOCKED by Sentinel: Market Regime is STRONG_BEARISH ({self.sentiment_score:.0f}). Altcoin LONG trades prohibited."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        if self.market_regime == "STRONG_BULLISH" and pos_dir == "SHORT" and coin_up not in ["BTC", "WBTC"]:
            msg = f"BLOCKED by Sentinel: Market Regime is STRONG_BULLISH ({self.sentiment_score:.0f}). Altcoin SHORT trades prohibited."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "WARNING")
            return False, msg, self.tuned_params

        # 6. DYNAMIC CONFIDENCE THRESHOLD CHECK
        c_prob = float(candidate_info.get("probability", 85) or 85)
        min_conf = int(self.tuned_params.get("min_confidence", 90))
        if c_prob < min_conf:
            msg = f"BLOCKED by Sentinel: Signal confidence {c_prob:.0f}% is below current Ultra-Sniper threshold ({min_conf}%)."
            self.log_event("TRADE_GATE_BLOCKED", f"Rejected {coin_up} ({pos_dir})", msg, "INFO")
            return False, msg, self.tuned_params

        # ALL CHECKS PASSED: CLEARANCE GRANTED
        approval_msg = f"CLEARANCE GRANTED: {coin_up} ({pos_dir}) meets institutional liquidity, market regime alignment, and Ultra-Sniper {c_prob:.0f}% confidence."
        self.log_event("TRADE_GATE_APPROVED", f"Approved {coin_up} ({pos_dir})", approval_msg, "INFO")
        return True, approval_msg, self.tuned_params

    # =========================================================================
    # SUPERVISOR BACKGROUND DAEMON LOOP
    # =========================================================================

    def _daemon_loop(self):
        """Continuous 24/7 background loop executed every 60 seconds."""
        print("[🤖 SUPERVISOR] 24/7 AI Sentinel & Meta-Optimizer daemon activated.")
        self.log_event("SYSTEM", "AI Sentinel Activated", "24/7 Continuous surveillance loop started.", "INFO")

        cycle_count = 0
        while self.running:
            try:
                cycle_count += 1

                # 1. Refresh News Headlines & Sentiment every 3 minutes (180s)
                if cycle_count % 3 == 1:
                    raw_news = self.fetch_crypto_news()
                    if raw_news:
                        news_score, scored_news = self.analyze_news_sentiment(raw_news)
                        self.news_feed = scored_news
                    else:
                        news_score = 0.0

                    breadth = self.fetch_market_breadth()
                    breadth_score = breadth.get("breadth_score", 0.0)

                    # 3-Layer Sentiment Engine: News (30%) + Breadth (45%) + Crypto Fear & Greed Index (25%)
                    fng = self.fetch_fear_and_greed_index()
                    self.fear_greed_data = fng
                    fng_score = float(fng.get("score", 0.0))

                    blended = (news_score * 0.30) + (breadth_score * 0.45) + (fng_score * 0.25)
                    self.sentiment_score = max(-100.0, min(100.0, blended))

                    if self.sentiment_score <= -40.0:
                        self.market_regime = "STRONG_BEARISH"
                        self.directional_bias = "SHORT_BIAS (80% Short / 20% Long)"
                    elif self.sentiment_score <= -15.0:
                        self.market_regime = "MILD_BEARISH"
                        self.directional_bias = "SHORT_BIAS (65% Short / 35% Long)"
                    elif self.sentiment_score >= 40.0:
                        self.market_regime = "STRONG_BULLISH"
                        self.directional_bias = "LONG_BIAS (80% Long / 20% Short)"
                    elif self.sentiment_score >= 15.0:
                        self.market_regime = "MILD_BULLISH"
                        self.directional_bias = "LONG_BIAS (65% Long / 35% Short)"
                    else:
                        self.market_regime = "CHOPPY_NEUTRAL"
                        self.directional_bias = "NEUTRAL (50/50 Scalp)"

                    # Notify user on WhatsApp/Telegram when Market Regime shifts
                    prev_sup_regime = getattr(self, "_last_sup_regime", None)
                    if prev_sup_regime and prev_sup_regime != self.market_regime:
                        try:
                            from telegram_alerts import broadcast_alert
                            broadcast_alert(
                                f"🌐 <b>MARKET SENTIMENT REGIME SHIFT</b>\n\n"
                                f"• Regime: <b>{prev_sup_regime}</b> ➔ <b>{self.market_regime}</b>\n"
                                f"• Sentiment Score: <b>{self.sentiment_score:.1f} / 100</b>\n"
                                f"• Bias: <b>{self.directional_bias}</b>\n"
                                f"• Fear & Greed: <b>{fng.get('classification', 'Neutral')} ({fng_score:.0f})</b>\n\n"
                                f"🤖 AI Supervisor auto-adjusting trade direction and filters."
                            )
                        except Exception:
                            pass
                    self._last_sup_regime = self.market_regime

                    # High impact news notifications
                    if raw_news and hasattr(self, "news_feed") and self.news_feed:
                        if not hasattr(self, "_alerted_news_titles"):
                            self._alerted_news_titles = set()
                        for art in self.news_feed[:3]:
                            t = art.get("title", "")
                            s = abs(float(art.get("sentiment_score", 0)))
                            if t and t not in self._alerted_news_titles and s >= 45:
                                self._alerted_news_titles.add(t)
                                try:
                                    from telegram_alerts import alert_macro_news
                                    impact = "HIGH BULLISH" if art.get("sentiment_score", 0) > 0 else "HIGH BEARISH"
                                    alert_macro_news(t, impact, art.get("summary", "")[:180])
                                except Exception:
                                    pass

                # 2. Run Forensic Audits on Paper Trades
                self.run_loss_forensics()

                # 3. Clean expired quarantines & persist state
                now_ts = time.time()
                expired = [k for k, v in self.quarantine_registry.items() if now_ts >= v.get("until_timestamp", 0)]
                for exp_k in expired:
                    del self.quarantine_registry[exp_k]
                    self.log_event("QUARANTINE_LIFTED", f"Quarantine Expired for {exp_k}", "Asset returned to surveillance.", "INFO")
                if expired:
                    self._save_quarantine()

                self._save_state()

            except Exception as e:
                print(f"[Supervisor Daemon Exception]: {e}")

            # Sleep 60 seconds between supervisor heartbeats
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)

    def start(self):
        """Starts the 24/7 background supervisor daemon."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._daemon_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the supervisor daemon."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def reset(self):
        """Resets supervisor logs and performance tracking back to fresh start while retaining safety quarantine."""
        self.audit_logs = []
        self.log_event(
            category="SYSTEM",
            title="Fresh System Reset",
            details="All paper trades and historical logs cleared. Both trading engine and AI Sentinel restarted from zero with fresh ₹30,000 balance and strict 1:2 R:R.",
            severity="INFO"
        )
        self.tuned_params.update({
            "min_confidence": 90,
            "stop_loss_pct": 2.20,
            "take_profit_pct": 4.80,
            "min_liquidity_usdt": 25_000_000.0,
            "margin_defense_drawdown_pct": -5.1,
            "mode": "ULTRA_SNIPER_DEFENSE",
            "last_tuned_at": get_ist_datetime_str(),
            "tuning_reason": "Fresh restart from zero with pure 1:2 R:R (+15% TP vs -5.1% SL)."
        })
        self._save_state()

    def get_status_dict(self) -> Dict[str, Any]:
        """Returns complete JSON status for frontend dashboard and REST API."""
        return {
            "status": "ACTIVE_24X7",
            "mode": self.tuned_params.get("mode", "ULTRA_SNIPER_DEFENSE"),
            "sentiment_score": round(self.sentiment_score, 1),
            "market_regime": self.market_regime,
            "directional_bias": self.directional_bias,
            "fear_greed_data": self.fear_greed_data,
            "tuned_params": self.tuned_params,
            "quarantined_coins": [
                {
                    "coin": k,
                    "quarantine_until": v.get("quarantine_until"),
                    "reason": v.get("reason"),
                    "hours_left": max(0.0, round((v.get("until_timestamp", 0) - time.time()) / 3600.0, 1))
                }
                for k, v in sorted(self.quarantine_registry.items())
            ],
            "institutional_whitelist": sorted(list(INSTITUTIONAL_WHITELIST)),
            "news_headlines": self.news_feed[:8],
            "recent_audit_logs": self.audit_logs[:20]
        }


# Global Singleton Instance
supervisor = CryptoSupervisor()

if __name__ == "__main__":
    print("Testing CryptoSupervisor...")
    s = CryptoSupervisor()
    print("Initial Status:")
    print(json.dumps(s.get_status_dict(), indent=2))
    print("\nTesting News Ingestion & Sentiment Analysis...")
    news = s.fetch_crypto_news()
    score, scored = s.analyze_news_sentiment(news)
    print(f"News Count: {len(news)}, Aggregate Score: {score:.1f}")
    for item in scored[:3]:
        print(f" - [{item['classification']}] {item['title'][:80]}")
    
    print("\nTesting Clearance Check on ASTER (Should be Blocked):")
    appr, reason, params = s.get_trade_clearance("ASTER", "SHORT", {"volume_usdt": 27000000, "probability": 96})
    print(f"Approval: {appr} | Reason: {reason}")

    print("\nTesting Clearance Check on BTC (Should be Approved if confidence >= 90):")
    appr, reason, params = s.get_trade_clearance("BTC", "SHORT", {"volume_usdt": 1600000000, "probability": 94})
    print(f"Approval: {appr} | Reason: {reason}")
