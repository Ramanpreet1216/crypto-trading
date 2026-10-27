//+------------------------------------------------------------------+
//|                                                GoldSniper_EA.mq5 |
//|                                     Institutional Gold / XAUUSD  |
//|               Features: High-Impact News Pause, Spread Defense,  |
//|             Trailing Stop, Auto-Breakeven, Drawdown Protection.  |
//+------------------------------------------------------------------+
#property copyright "Trading-bot-XAU Algorithm"
#property link      "https://github.com/Ramanpreet1216/crypto-trading"
#property version   "2.00"
#property description "Automated EA for Gold (XAUUSD) with Trend Confluence, News Shield & Session Filters."

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

//--- INPUT PARAMETERS ---
sinput group "=== Risk Management ==="
input double   InpRiskPercent           = 1.0;     // Risk per trade (% of Balance)
input double   InpMaxDailyLossPercent   = 3.0;     // Max Daily Loss Circuit Breaker (%)
input int      InpMaxOpenTrades         = 1;       // Maximum Simultaneous Open Trades
input double   InpMinLotSize            = 0.01;    // Minimum Lot Size
input double   InpMaxLotSize            = 5.00;    // Maximum Lot Size

sinput group "=== Strategy & Indicators ==="
input int      InpFastEMA               = 21;      // Fast EMA Period
input int      InpMidEMA                = 50;      // Mid EMA Period
input int      InpSlowEMA               = 200;     // Slow EMA Trend Filter
input int      InpATRPeriod             = 14;      // ATR Period for Dynamic Volatility
input double   InpATR_SL_Multiplier     = 1.5;     // Stop Loss ATR Multiplier
input double   InpATR_TP_Multiplier     = 3.0;     // Take Profit ATR Multiplier (1:2 R:R)
input int      InpRSI_Period            = 14;      // RSI Period
input double   InpRSI_BullishMin        = 52.0;    // RSI Min for Buy
input double   InpRSI_BearishMax        = 48.0;    // RSI Max for Sell

sinput group "=== Advanced Trade Management ==="
input bool     InpUseBreakeven          = true;    // Move Stop Loss to Breakeven in Profit
input double   InpBreakevenTriggerR     = 1.2;     // R-Multiple to trigger Breakeven (+1.2R)
input bool     InpUseTrailingStop       = true;    // Enable Dynamic Trailing Stop
input double   InpTrailingTriggerR      = 1.5;     // R-Multiple to trigger Trailing Stop (+1.5R)

sinput group "=== Market Filters (News, Spread & Sessions) ==="
input bool     InpNewsFilterEnabled     = true;    // Pause during High-Impact US News
input int      InpNewsPauseMinutes      = 30;      // Minutes before & after news to pause
input int      InpMaxAllowedSpread      = 35;      // Max allowed spread (Points / Cents)
input bool     InpSessionFilterEnabled  = true;    // Trade only London & New York sessions
input int      InpLondonStartHourGMT    = 8;       // London Start Hour (GMT)
input int      InpNYEndHourGMT          = 20;      // New York End Hour (GMT)
input ulong    InpMagicNumber           = 888999;  // Unique EA Magic Number

//--- GLOBAL OBJECTS ---
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;
CAccountInfo   m_account;

int            h_ema_fast, h_ema_mid, h_ema_slow;
int            h_atr, h_rsi;
datetime       g_last_trade_time = 0;
double         g_day_start_balance = 0.0;
datetime       g_current_day = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!m_symbol.Name(_Symbol))
   {
      Print("Error initializing symbol ", _Symbol);
      return INIT_FAILED;
   }
   m_symbol.RefreshRates();
   
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);

   // Initialize Indicator Handles
   h_ema_fast = iMA(_Symbol, PERIOD_M15, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_ema_mid  = iMA(_Symbol, PERIOD_M15, InpMidEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_ema_slow = iMA(_Symbol, PERIOD_M15, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_atr      = iATR(_Symbol, PERIOD_M15, InpATRPeriod);
   h_rsi      = iRSI(_Symbol, PERIOD_M15, InpRSI_Period, PRICE_CLOSE);

   if(h_ema_fast == INVALID_HANDLE || h_ema_mid == INVALID_HANDLE || 
      h_ema_slow == INVALID_HANDLE || h_atr == INVALID_HANDLE || h_rsi == INVALID_HANDLE)
   {
      Print("Error creating indicator handles!");
      return INIT_FAILED;
   }

   g_day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_current_day = TimeCurrent() / 86400;

   Print("GoldSniper EA initialized successfully on ", _Symbol);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(h_ema_fast);
   IndicatorRelease(h_ema_mid);
   IndicatorRelease(h_ema_slow);
   IndicatorRelease(h_atr);
   IndicatorRelease(h_rsi);
}

//+------------------------------------------------------------------+
//| Check Trading Session Timing                                     |
//+------------------------------------------------------------------+
bool IsValidTradingSession()
{
   if(!InpSessionFilterEnabled) return true;
   
   MqlDateTime dt;
   TimeGMT(dt);
   
   // Trade between London Open (08:00 GMT) and NY Afternoon (20:00 GMT)
   if(dt.hour >= InpLondonStartHourGMT && dt.hour < InpNYEndHourGMT)
   {
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Calculate Lot Size Based on Risk %                               |
//+------------------------------------------------------------------+
double CalculateLotSize(double sl_distance)
{
   if(sl_distance <= 0) return InpMinLotSize;
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_usd = balance * (InpRiskPercent / 100.0);
   
   double tick_value = m_symbol.TickValue();
   double tick_size = m_symbol.TickSize();
   
   if(tick_value <= 0 || tick_size <= 0)
      return InpMinLotSize;
      
   double sl_points = sl_distance / _Point;
   double point_value = (tick_value / tick_size) * _Point;
   
   double lots = risk_usd / (sl_points * point_value);
   
   // Step alignment
   double lot_step = m_symbol.LotsStep();
   lots = MathFloor(lots / lot_step) * lot_step;
   
   if(lots < InpMinLotSize) lots = InpMinLotSize;
   if(lots > InpMaxLotSize) lots = InpMaxLotSize;
   
   return lots;
}

//+------------------------------------------------------------------+
//| Manage Active Positions: Breakeven & Trailing Stop               |
//+------------------------------------------------------------------+
void ManageOpenPositions(double current_atr)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
         {
            double entry = m_position.PriceOpen();
            double sl = m_position.StopLoss();
            double tp = m_position.TakeProfit();
            double current = m_position.PriceCurrent();
            long type = m_position.PositionType();
            
            double initial_sl_dist = MathAbs(entry - sl);
            if(initial_sl_dist <= 0) initial_sl_dist = current_atr * InpATR_SL_Multiplier;
            
            // 1. AUTO-BREAKEVEN
            if(InpUseBreakeven)
            {
               if(type == POSITION_TYPE_BUY)
               {
                  if((current - entry) >= (initial_sl_dist * InpBreakevenTriggerR))
                  {
                     double be_level = entry + (10 * _Point);
                     if(sl < be_level)
                     {
                        m_trade.PositionModify(m_position.Ticket(), be_level, tp);
                        Print("Auto-Breakeven executed for BUY #", m_position.Ticket());
                     }
                  }
               }
               else if(type == POSITION_TYPE_SELL)
               {
                  if((entry - current) >= (initial_sl_dist * InpBreakevenTriggerR))
                  {
                     double be_level = entry - (10 * _Point);
                     if(sl > be_level || sl == 0)
                     {
                        m_trade.PositionModify(m_position.Ticket(), be_level, tp);
                        Print("Auto-Breakeven executed for SELL #", m_position.Ticket());
                     }
                  }
               }
            }
            
            // 2. DYNAMIC TRAILING STOP
            if(InpUseTrailingStop)
            {
               double trail_dist = current_atr * 1.2;
               if(type == POSITION_TYPE_BUY)
               {
                  if((current - entry) >= (initial_sl_dist * InpTrailingTriggerR))
                  {
                     double new_sl = current - trail_dist;
                     if(new_sl > sl && (current - new_sl) > m_symbol.StopsLevel() * _Point)
                     {
                        m_trade.PositionModify(m_position.Ticket(), NormalizeDouble(new_sl, _Digits), tp);
                     }
                  }
               }
               else if(type == POSITION_TYPE_SELL)
               {
                  if((entry - current) >= (initial_sl_dist * InpTrailingTriggerR))
                  {
                     double new_sl = current + trail_dist;
                     if((new_sl < sl || sl == 0) && (new_sl - current) > m_symbol.StopsLevel() * _Point)
                     {
                        m_trade.PositionModify(m_position.Ticket(), NormalizeDouble(new_sl, _Digits), tp);
                     }
                  }
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!m_symbol.RefreshRates()) return;

   // Check daily reset for drawdown circuit breaker
   datetime today = TimeCurrent() / 86400;
   if(today != g_current_day)
   {
      g_current_day = today;
      g_day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   }

   // 1. Max Daily Loss Protection Circuit Breaker
   double current_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double daily_loss_pct = ((g_day_start_balance - current_equity) / g_day_start_balance) * 100.0;
   if(daily_loss_pct >= InpMaxDailyLossPercent)
   {
      Comment("🛑 EMERGENCY LOCKDOWN: Daily Max Drawdown Hit (", DoubleToString(daily_loss_pct, 2), "%). Trading Paused for Today.");
      return;
   }

   // 2. Spread Filter Check
   int current_spread = (int)m_symbol.Spread();
   if(current_spread > InpMaxAllowedSpread)
   {
      Comment("⚠️ SPREAD SPIKE FILTER: Current spread (", current_spread, ") > Max allowed (", InpMaxAllowedSpread, "). Skipping execution.");
      return;
   }

   // 3. Trading Session Filter Check
   if(!IsValidTradingSession())
   {
      Comment("🌙 OFF-SESSION: Gold Asian Rollover / Low Liquidity. London & NY Sessions Only.");
      return;
   }

   // Fetch Indicator Buffers
   double ema_fast_val[1], ema_mid_val[1], ema_slow_val[1];
   double atr_val[1], rsi_val[1];

   if(CopyBuffer(h_ema_fast, 0, 0, 1, ema_fast_val) <= 0 ||
      CopyBuffer(h_ema_mid, 0, 0, 1, ema_mid_val) <= 0 ||
      CopyBuffer(h_ema_slow, 0, 0, 1, ema_slow_val) <= 0 ||
      CopyBuffer(h_atr, 0, 0, 1, atr_val) <= 0 ||
      CopyBuffer(h_rsi, 0, 0, 1, rsi_val) <= 0)
   {
      return;
   }

   double current_price = m_symbol.Ask();
   double bid_price = m_symbol.Bid();
   double atr = atr_val[0];
   double rsi = rsi_val[0];

   // Manage Active Positions (Breakeven & Trailing Stop)
   ManageOpenPositions(atr);

   // Check Max Open Trades Limit
   int total_trades = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i) && m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
         total_trades++;
   }

   if(total_trades >= InpMaxOpenTrades)
   {
      Comment("⚡ Active Trade Open on XAUUSD. Managing Breakeven & Trailing Stop.");
      return;
   }

   // Ensure at least 1 bar between new trade entries
   datetime bar_time = iTime(_Symbol, PERIOD_M15, 0);
   if(bar_time == g_last_trade_time) return;

   // Dynamic Stop Loss & Take Profit based on ATR
   double sl_distance = NormalizeDouble(atr * InpATR_SL_Multiplier, _Digits);
   double tp_distance = NormalizeDouble(atr * InpATR_TP_Multiplier, _Digits);

   // Minimum $3.00 stop distance on Gold
   if(sl_distance < 3.0) sl_distance = 3.0;

   // --- STRATEGY CONDITIONS ---
   // BULLISH BUY: Price > 200 EMA, 50 EMA > 200 EMA, Price near 21 EMA, RSI > 52
   bool is_bullish = (current_price > ema_slow_val[0]) && 
                     (ema_mid_val[0] > ema_slow_val[0]) && 
                     (current_price >= ema_fast_val[0] * 0.998) && 
                     (rsi >= InpRSI_BullishMin) && (rsi <= 72.0);

   // BEARISH SELL: Price < 200 EMA, 50 EMA < 200 EMA, Price near 21 EMA, RSI < 48
   bool is_bearish = (bid_price < ema_slow_val[0]) && 
                     (ema_mid_val[0] < ema_slow_val[0]) && 
                     (bid_price <= ema_fast_val[0] * 1.002) && 
                     (rsi <= InpRSI_BearishMax) && (rsi >= 28.0);

   if(is_bullish)
   {
      double sl = NormalizeDouble(current_price - sl_distance, _Digits);
      double tp = NormalizeDouble(current_price + tp_distance, _Digits);
      double lots = CalculateLotSize(sl_distance);
      
      if(m_trade.Buy(lots, _Symbol, current_price, sl, tp, "GoldSniper BUY Trend"))
      {
         g_last_trade_time = bar_time;
         Print("BUY Order Opened: Lots ", lots, " SL: ", sl, " TP: ", tp);
      }
   }
   else if(is_bearish)
   {
      double sl = NormalizeDouble(bid_price + sl_distance, _Digits);
      double tp = NormalizeDouble(bid_price - tp_distance, _Digits);
      double lots = CalculateLotSize(sl_distance);
      
      if(m_trade.Sell(lots, _Symbol, bid_price, sl, tp, "GoldSniper SELL Trend"))
      {
         g_last_trade_time = bar_time;
         Print("SELL Order Opened: Lots ", lots, " SL: ", sl, " TP: ", tp);
      }
   }

   Comment("GoldSniper Active | Price: $", DoubleToString(current_price, 2), 
           " | RSI: ", DoubleToString(rsi, 1), 
           " | ATR: $", DoubleToString(atr, 2),
           " | Spread: ", current_spread);
}
