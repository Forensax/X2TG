import requests
import html
from config import TG_BOT_TOKEN, TG_CHAT_ID, PROXY_URL

def get_proxy_dict():
    if PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return None

def send_telegram_message(author, original_text, translated_text, link, images=None):
    """
    发送消息到 Telegram
    支持发送图片
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，无法发送消息。")
        return

    safe_original = html.escape(original_text)
    safe_author = html.escape(author)
    
    header = f"📢 <b>{safe_author}</b>\n\n"
    
    # 动态构建内容
    content_parts = [header, f"<b>原文：</b>\n{safe_original}\n\n"]
    
    # 只有当翻译文本存在时才添加
    if translated_text:
        safe_translated = html.escape(translated_text)
        content_parts.append(f"<b>翻译：</b>\n{safe_translated}\n\n")
        
    content_parts.append(f"🔗 <a href='{link}'>查看推文</a>")
    
    body = "".join(content_parts)

    # 默认配置 (sendMessage)
    method = "sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "parse_mode": "HTML",
        # 如果是纯文本发送，开启预览可以让 TG 自动抓取推文图片
        # 如果后面决定用 sendPhoto，这个参数会被移除
        "disable_web_page_preview": False 
    }

    # 如果有图片，尝试使用 sendPhoto
    if images and len(images) > 0:
        # Telegram Caption 限制 1024 字符
        # HTML 标签也会占用字符数，粗略判断
        if len(body) <= 1000:
            method = "sendPhoto"
            payload["photo"] = images[0]
            payload["caption"] = body
            # sendPhoto 不支持 disable_web_page_preview
            if "disable_web_page_preview" in payload:
                del payload["disable_web_page_preview"]
        else:
            # 如果超长，回退到 sendMessage
            print("内容过长，跳过图片发送，改用链接预览。")
            payload["text"] = body
    else:
        payload["text"] = body

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    proxies = get_proxy_dict()

    try:
        response = requests.post(url, json=payload, timeout=20, proxies=proxies)
        response.raise_for_status()
        print(f"成功推送到 Telegram: {link} (method={method})")
    except Exception as e:
        print(f"推送到 Telegram 失败 ({method}): {e}")
        
        # 如果 sendPhoto 失败（比如图片 URL 无效），降级重试 sendMessage
        if method == "sendPhoto":
            print("尝试降级为纯文本发送...")
            try:
                # 清理 payload，转为 sendMessage 格式
                if "photo" in payload: del payload["photo"]
                if "caption" in payload: del payload["caption"]
                
                payload["text"] = body
                payload["disable_web_page_preview"] = False
                
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                response = requests.post(url, json=payload, timeout=20, proxies=proxies)
                response.raise_for_status()
                print(f"降级发送成功: {link}")
            except Exception as e2:
                print(f"降级发送也失败: {e2}")

def send_plain_message(text):
    """
    发送纯文本消息到 Telegram
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，无法发送消息。")
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    proxies = get_proxy_dict()
    
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=20, proxies=proxies)
        response.raise_for_status()
        print(f"系统消息已发送: {text}")
    except Exception as e:
        print(f"发送系统消息失败: {e}")

