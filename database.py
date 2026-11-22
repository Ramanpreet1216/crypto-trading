"""
========================================================================================
🗄️ UNIFIED 4-BOT PRODUCTION DATABASE LAYER (SQLite & PostgreSQL Compatible)
========================================================================================
- Stores trades, wallet balances, taxes, and strategies for all 4 bots:
  * Bot 1: Momentum Breakout Scanner
  * Bot 2: 1:2 Asymmetric R:R Sentinel
  * Bot 3: Turtle Trading Trend Follower (System 2)
  * Bot 4: High Win Rate (~80%) Anti-Wick Breakeven Sniper & Strategy Generator
- Automatically works locally on SQLite (data/trading_master.db) and on Oracle Cloud
  with PostgreSQL (via DATABASE_URL).
========================================================================================
"""

import os
import sqlite3
import json
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

SQLITE_PATH = os.path.join(DATA_DIR, "trading_master.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

class MasterDatabase:
    def __init__(self, db_path=SQLITE_PATH, pg_url=DATABASE_URL):
        self.db_path = db_path
        self.pg_url = pg_url if pg_url and pg_url.startswith("postgresql://") else None
        self.is_pg = bool(self.pg_url)
        self.init_schema()

    def get_connection(self):
        if self.is_pg:
            import psycopg2
            return psycopg2.connect(self.pg_url)
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def init_schema(self):
        conn = self.get_connection()
        cur = conn.cursor()

        # 1. Bot Wallets & State
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_wallets (
            bot_id TEXT PRIMARY KEY,
            starting_capital REAL,
            current_wallet_balance REAL,
            total_gross_wins REAL,
            total_gross_losses REAL,
            total_fees REAL,
            total_tds REAL,
            total_tax_115bbh REAL,
            net_in_pocket REAL,
            win_rate_pct REAL,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            target_achieved INTEGER,
            updated_at TEXT
        );
        """)

        # 2. Master Trade Logs (All 4 Bots)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            symbol TEXT,
            side TEXT,
            entry_time TEXT,
            exit_time TEXT,
            entry_price REAL,
            exit_price REAL,
            margin REAL,
            leverage REAL,
            gross_pnl REAL,
            coindcx_fee REAL,
            tds_deducted REAL,
            wallet_net_pnl REAL,
            tax_115bbh REAL,
            net_in_pocket REAL,
            exit_reason TEXT,
            created_at TEXT
        );
        """)

        # 3. Strategy Optimization Store (Bot 4 Autonomous Strategies)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS generated_strategies (
            strategy_id TEXT PRIMARY KEY,
            name TEXT,
            bot_id TEXT,
            params_json TEXT,
            win_rate_pct REAL,
            wallet_profit REAL,
            tax_115bbh REAL,
            net_in_pocket REAL,
            achieved_120k INTEGER,
            created_at TEXT
        );
        """)

        # 4. Open Active Positions
        cur.execute("""
        CREATE TABLE IF NOT EXISTS active_positions (
            position_id TEXT PRIMARY KEY,
            bot_id TEXT,
            symbol TEXT,
            side TEXT,
            entry_time TEXT,
            entry_price REAL,
            current_price REAL,
            sl_price REAL,
            tp_price REAL,
            margin REAL,
            leverage REAL,
            unrealized_pnl REAL,
            status TEXT,
            updated_at TEXT
        );
        """)

        # Initialize Default State for all 4 Bots if not present
        bots = [
            ("bot1", 30000.0),
            ("bot2", 30000.0),
            ("bot3", 30000.0),
            ("bot4", 30000.0)
        ]
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for b_id, cap in bots:
            cur.execute("SELECT COUNT(*) FROM bot_wallets WHERE bot_id = ?;", (b_id,))
            if cur.fetchone()[0] == 0:
                cur.execute("""
                INSERT INTO bot_wallets (
                    bot_id, starting_capital, current_wallet_balance, total_gross_wins,
                    total_gross_losses, total_fees, total_tds, total_tax_115bbh,
                    net_in_pocket, win_rate_pct, total_trades, winning_trades,
                    losing_trades, target_achieved, updated_at
                ) VALUES (?, ?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, ?);
                """, (b_id, cap, cap, now_str))

        conn.commit()
        conn.close()

    def get_bot_wallet(self, bot_id="bot4"):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bot_wallets WHERE bot_id = ?;", (bot_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_bot_wallet(self, bot_id, w_dict):
        conn = self.get_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        UPDATE bot_wallets SET
            current_wallet_balance = ?,
            total_gross_wins = ?,
            total_gross_losses = ?,
            total_fees = ?,
            total_tds = ?,
            total_tax_115bbh = ?,
            net_in_pocket = ?,
            win_rate_pct = ?,
            total_trades = ?,
            winning_trades = ?,
            losing_trades = ?,
            target_achieved = ?,
            updated_at = ?
        WHERE bot_id = ?;
        """, (
            w_dict["current_wallet_balance"],
            w_dict["total_gross_wins"],
            w_dict["total_gross_losses"],
            w_dict["total_fees"],
            w_dict["total_tds"],
            w_dict["total_tax_115bbh"],
            w_dict["net_in_pocket"],
            w_dict["win_rate_pct"],
            w_dict["total_trades"],
            w_dict["winning_trades"],
            w_dict["losing_trades"],
            1 if w_dict["net_in_pocket"] >= 120000.0 else 0,
            now_str,
            bot_id
        ))
        conn.commit()
        conn.close()

    def log_trade(self, t):
        conn = self.get_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        INSERT INTO trade_history (
            bot_id, symbol, side, entry_time, exit_time, entry_price, exit_price,
            margin, leverage, gross_pnl, coindcx_fee, tds_deducted,
            wallet_net_pnl, tax_115bbh, net_in_pocket, exit_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            t.get("bot_id", "bot4"), t["symbol"], t["side"], t["entry_time"], t["exit_time"],
            t["entry_price"], t["exit_price"], t["margin"], t["leverage"],
            t["gross_pnl"], t["fee"], t["tds"], t["wallet_net"],
            t["tax_115bbh"], t["net_in_pocket"], t["exit_reason"], now_str
        ))
        conn.commit()
        conn.close()

    def get_recent_trades(self, bot_id=None, limit=20):
        conn = self.get_connection()
        cur = conn.cursor()
        if bot_id:
            cur.execute("SELECT * FROM trade_history WHERE bot_id = ? ORDER BY trade_id DESC LIMIT ?;", (bot_id, limit))
        else:
            cur.execute("SELECT * FROM trade_history ORDER BY trade_id DESC LIMIT ?;", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def record_strategy(self, strat):
        conn = self.get_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        INSERT OR REPLACE INTO generated_strategies (
            strategy_id, name, bot_id, params_json, win_rate_pct,
            wallet_profit, tax_115bbh, net_in_pocket, achieved_120k, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            strat["strategy_id"], strat["name"], strat.get("bot_id", "bot4"),
            json.dumps(strat.get("params", {})), strat["win_rate_pct"],
            strat["wallet_profit"], strat["tax_115bbh"], strat["net_in_pocket"],
            1 if strat["net_in_pocket"] >= 120000.0 else 0, now_str
        ))
        conn.commit()
        conn.close()

    def get_top_strategies(self, limit=10):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM generated_strategies ORDER BY net_in_pocket DESC LIMIT ?;", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

master_db = MasterDatabase()
