"""
News Filter & Economic Calendar Shield for Gold (XAUUSD) Trading Bot.
Safeguards the bot against violent news spikes caused by US High-Impact releases:
- CPI (Consumer Price Index)
- NFP (Non-Farm Payrolls)
- FOMC / Federal Reserve Interest Rate Decisions & Press Conferences
- PPI (Producer Price Index)
- Retail Sales, GDP, Core PCE

Mechanisms:
1. Economic Calendar Pre-News / Post-News Blackout
2. Dynamic Spread Spike Protection (Emergency Circuit Breaker for unannounced news)
3. Volatility Surge Protection (ATR Multiplier)
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "calendar_cache.json")
CACHE_DURATION_HOURS = 2

class NewsShield:
    def __init__(
        self,
        pre_news_minutes: int = 30,
        post_news_minutes: int = 30,
        filter_impacts: Tuple[str, ...] = ("High",),
        filter_currencies: Tuple[str, ...] = ("USD",),
        max_spread_pips: float = 4.0,           # e.g., $0.40 on gold
        atr_spike_threshold: float = 2.5        # 2.5x normal 1m/5m ATR
    ):
        self.pre_news_minutes = pre_news_minutes
        self.post_news_minutes = post_news_minutes
        self.filter_impacts = filter_impacts
        self.filter_currencies = filter_currencies
        self.max_spread_pips = max_spread_pips
        self.atr_spike_threshold = atr_spike_threshold
        self._cached_events: List[Dict] = []
        self._last_fetch_time: float = 0.0

    def fetch_calendar(self, force: bool = False) -> List[Dict]:
        """Fetch economic calendar events with local disk caching."""
        now = time.time()
        if not force and self._cached_events and (now - self._last_fetch_time < CACHE_DURATION_HOURS * 3600):
            return self._cached_events

        # Check disk cache
        if not force and os.path.exists(CACHE_FILE):
            try:
                mtime = os.path.getmtime(CACHE_FILE)
                if now - mtime < CACHE_DURATION_HOURS * 3600:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list) and len(data) > 0:
                            self._cached_events = data
                            self._last_fetch_time = now
                            return self._cached_events
            except Exception:
                pass

        # Fetch from remote ForexFactory JSON feed
        try:
            headers = {"User-Agent": "TradingBot-XAU-Shield/1.0"}
            resp = requests.get(CALENDAR_URL, headers=headers, timeout=12)
            if resp.status_code == 200:
                raw_events = resp.json()
                parsed = []
                for ev in raw_events:
                    country = ev.get("country", "").upper()
                    impact = ev.get("impact", "").capitalize()
                    
                    # Filter for target currency and impact
                    if country in self.filter_currencies and impact in self.filter_impacts:
                        dt_str = ev.get("date", "")
                        try:
                            # Format: "2026-10-22T08:30:00-04:00"
                            ev_time = datetime.fromisoformat(dt_str)
                            # Convert to UTC timestamp
                            ev_ts = ev_time.astimezone(timezone.utc).timestamp()
                            parsed.append({
                                "title": ev.get("title", "Economic Event"),
                                "country": country,
                                "impact": impact,
                                "timestamp": ev_ts,
                                "iso_date": dt_str,
                                "forecast": ev.get("forecast", ""),
                                "previous": ev.get("previous", "")
                            })
                        except Exception:
                            continue

                self._cached_events = parsed
                self._last_fetch_time = now
                try:
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(parsed, f, indent=2)
                except Exception:
                    pass
                return self._cached_events
        except Exception as e:
            # If network error but we have disk cache, fallback to disk cache
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        self._cached_events = json.load(f)
                        return self._cached_events
                except Exception:
                    pass
            print(f"[NewsShield] Warning: Unable to fetch calendar feed ({e})")

        return self._cached_events

    def evaluate_news_status(self) -> Dict:
        """
        Check whether the bot is currently in a Pre-News or Post-News blackout window.
        Returns a dict with:
          - is_locked: bool (True = DO NOT TRADE)
          - lock_reason: str
          - next_event: dict | None
          - minutes_to_next: float | None
          - recent_event: dict | None
          - upcoming_events: list of events within next 24 hours
        """
        events = self.fetch_calendar()
        now_ts = datetime.now(timezone.utc).timestamp()

        is_locked = False
        lock_reason = ""
        next_event = None
        minutes_to_next = None
        recent_event = None
        upcoming_24h = []

        pre_sec = self.pre_news_minutes * 60
        post_sec = self.post_news_minutes * 60

        for ev in sorted(events, key=lambda x: x["timestamp"]):
            ev_ts = ev["timestamp"]
            diff = ev_ts - now_ts  # positive if in future, negative if in past

            # Collect upcoming events in next 24 hours
            if 0 <= diff <= 86400:
                ev_copy = dict(ev)
                ev_copy["minutes_away"] = round(diff / 60, 1)
                upcoming_24h.append(ev_copy)

            # Check PRE-NEWS window (e.g. within 30 min before news)
            if 0 <= diff <= pre_sec:
                is_locked = True
                lock_reason = f"🚨 PRE-NEWS LOCKDOWN: [{ev['country']}] {ev['title']} in {round(diff / 60)}m (Paused {self.pre_news_minutes}m before)"
                next_event = ev
                minutes_to_next = round(diff / 60, 1)
                break

            # Check POST-NEWS window (e.g. within 30 min after news)
            if -post_sec <= diff < 0:
                is_locked = True
                lock_reason = f"⚠️ POST-NEWS SETTLING: [{ev['country']}] {ev['title']} released {round(abs(diff) / 60)}m ago (Cooling off {self.post_news_minutes}m)"
                recent_event = ev

            # Identify the closest future event
            if diff > 0 and next_event is None:
                next_event = ev
                minutes_to_next = round(diff / 60, 1)

        return {
            "is_locked": is_locked,
            "lock_reason": lock_reason,
            "next_event": next_event,
            "minutes_to_next": minutes_to_next,
            "recent_event": recent_event,
            "upcoming_events": upcoming_24h[:10],
            "total_events_loaded": len(events)
        }

    def check_spread_protection(self, current_spread_pips: float) -> Tuple[bool, str]:
        """
        Emergency shield against unannounced news, flash crashes, or low-liquidity rollover.
        If spread blows out above max threshold, block trading immediately.
        """
        if current_spread_pips > self.max_spread_pips:
            return False, f"Spread too wide ({current_spread_pips:.2f} pips > {self.max_spread_pips:.2f} max allowed) - possible market shock or illiquidity"
        return True, "Spread OK"

    def check_volatility_spike(self, current_candle_range: float, avg_atr: float) -> Tuple[bool, str]:
        """
        Circuit breaker: detects violent anomalous candles (e.g. breaking geopolitical news).
        """
        if avg_atr > 0 and (current_candle_range / avg_atr) >= self.atr_spike_threshold:
            return False, f"Violent volatility spike detected ({current_candle_range:.2f} range vs {avg_atr:.2f} ATR, {current_candle_range/avg_atr:.1f}x) - halting for safety"
        return True, "Volatility OK"


if __name__ == "__main__":
    shield = NewsShield(pre_news_minutes=30, post_news_minutes=30, filter_impacts=("High", "Medium"))
    status = shield.evaluate_news_status()
    print("News Shield Test:")
    print("Is Locked:", status["is_locked"])
    print("Reason:", status["lock_reason"] or "All Clear")
    if status["next_event"]:
        print(f"Next Event: {status['next_event']['title']} in {status['minutes_to_next']} min")
    print(f"Upcoming Events (24h): {len(status['upcoming_events'])}")
    for ev in status["upcoming_events"][:3]:
        print(f"  - [{ev['impact']}] {ev['country']} {ev['title']} in {ev['minutes_away']}m")
