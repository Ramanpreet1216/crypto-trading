import os
import requests
import urllib.parse

# ==============================================================================
# TELEGRAM CREDENTIALS - OFFICIAL DEDICATED NOTIFICATION BOT
# Instant Push Notifications + Sound in Notification Bar
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8921375735:AAECpOFMgGSdRweEHwMY4MpHxcBNGhr0m3k")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "928958576")

# ==============================================================================
# WHATSAPP CREDENTIALS - SELF-HOSTED 100% FREE LOCAL GATEWAY
# Powered by Baileys on Oracle VM (http://127.0.0.1:5001/send)
# Zero subscription, zero third-party limits, instant delivery to your personal phone
# ==============================================================================
WHATSAPP_PHONE_NUMBER = os.getenv("WHATSAPP_PHONE_NUMBER", "919478551925").strip()
WHATSAPP_LOCAL_GATEWAY = os.getenv("WHATSAPP_LOCAL_GATEWAY", "http://127.0.0.1:5001/send")


def send_telegram_alert(message: str) -> bool:
    """Sends high-priority trading alert to Telegram."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN).strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID).strip()
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true"
        }
        res = requests.post(url, json=payload, timeout=4.0)
        if res.status_code == 200:
            return True
        # Robust fallback: send without HTML parsing if markdown or custom tags were used
        clean_plain = (
            message.replace("<b>", "").replace("</b>", "")
            .replace("<i>", "").replace("</i>", "")
            .replace("*", "")
        )
        res_plain = requests.post(
            url,
            json={"chat_id": chat_id, "text": clean_plain, "disable_web_page_preview": "true"},
            timeout=4.0
        )
        return res_plain.status_code == 200
    except Exception as e:
        print(f"[Telegram Alert Notice]: {e}")
        return False


def send_whatsapp_alert(message: str, phone: str = None) -> bool:
    """
    Sends real-time trading alert directly to personal WhatsApp via local self-hosted gateway.
    100% Free, unlimited, zero third-party subscription fees.
    """
    target_phone = phone or os.getenv("WHATSAPP_PHONE_NUMBER", WHATSAPP_PHONE_NUMBER).strip()
    clean_text = (
        message.replace("<b>", "*")
        .replace("</b>", "*")
        .replace("•", "-")
        .replace("<i>", "_")
        .replace("</i>", "_")
        .replace("<code>", "```")
        .replace("</code>", "```")
    )

    # 1. Primary: Self-Hosted Local Baileys Gateway on Oracle VM
    try:
        payload = {
            "number": target_phone,
            "message": clean_text
        }
        res = requests.post(WHATSAPP_LOCAL_GATEWAY, json=payload, timeout=5.0)
        if res.status_code == 200 and res.json().get("success"):
            return True
    except Exception as e:
        # If running locally outside Oracle VM, or service restarting
        pass

    # 2. Secondary Fallback: CallMeBot if API key is provided
    apikey = os.getenv("WHATSAPP_API_KEY", "").strip()
    if apikey:
        try:
            encoded_text = urllib.parse.quote(clean_text)
            url = f"https://api.callmebot.com/whatsapp.php?phone={target_phone}&text={encoded_text}&apikey={apikey}"
            res = requests.get(url, timeout=5.0)
            return res.status_code == 200
        except Exception:
            pass

    return False


def broadcast_alert(message: str):
    """Broadcasts simultaneously to WhatsApp and Telegram."""
    send_whatsapp_alert(message)
    send_telegram_alert(message)


def alert_regime_change(old_regime: str, new_regime: str, btc_price: float, rsi: float, trend_1h: str):
    """Alerts user when BTC macro regime shifts (e.g. BEARISH -> BULLISH)."""
    icon_map = {
        "STRONG_BEARISH": "🩸 STRONG BEARISH",
        "MILD_BEARISH": "🔻 BEARISH",
        "NEUTRAL": "⚖️ NEUTRAL",
        "MILD_BULLISH": "📈 BULLISH",
        "STRONG_BULLISH": "🚀 STRONG BULLISH"
    }
    new_lbl = icon_map.get(new_regime, new_regime)
    old_lbl = icon_map.get(old_regime, old_regime)
    msg = (
        f"🌐 *BTC MACRO REGIME SHIFT*\n\n"
        f"• Status: *{old_lbl}* ➔ *{new_lbl}*\n"
        f"• BTC Price: *${btc_price:,.2f}*\n"
        f"• 15m RSI: *{rsi:.1f}*\n"
        f"• 1-Hour Trend: *{trend_1h}*\n\n"
        f"🛡️ Bot strategy auto-aligns active risk limits and trade direction."
    )
    broadcast_alert(msg)


def alert_macro_news(title: str, impact: str, details: str):
    """Alerts user of high-impact crypto market news and sentiment shocks."""
    msg = (
        f"📰 *HIGH-IMPACT NEWS INTEL*\n\n"
        f"• Headline: *{title}*\n"
        f"• Impact: *{impact.upper()}*\n"
        f"• Summary: {details}\n\n"
        f"🤖 Bot 2 (AI Supervisor) auto-assessing token quarantine and risk filters."
    )
    broadcast_alert(msg)
