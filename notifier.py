import requests
import html
from config import TG_BOT_TOKEN, TG_CHAT_ID

def send_telegram_message(original_text, translated_text, link):
    """
    发送消息到 Telegram
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，无法发送消息。")
        return

    # 对文本进行 HTML 转义，防止 HTML 注入导致解析错误
    safe_original = html.escape(original_text)
    safe_translated = html.escape(translated_text)
    
    # 构建消息内容
    message = (
        f"<b>原文：</b>\n{safe_original}\n\n"
        f"<b>翻译：</b>\n{safe_translated}\n\n"
        f"🔗 <a href='{link}'>查看推文</a>"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True # 可选，禁用预览以保持整洁
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"成功推送到 Telegram: {link}")
    except Exception as e:
        print(f"推送到 Telegram 失败: {e}")
