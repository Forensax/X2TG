import html
import json
import mimetypes
import time
import uuid

import requests

from config import (
    ENABLED_CHANNELS,
    FEISHU_API_BASE,
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_RECEIVE_IDS,
    FEISHU_RECEIVE_ID_TYPE,
    PROXY_URL,
    TG_BOT_TOKEN,
    TG_CHAT_ID,
)


_FEISHU_TOKEN_CACHE = {"token": None, "expire_at": 0}


def get_proxy_dict():
    if PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return None


def _build_telegram_body(author, original_text, translated_text, link):
    safe_original = html.escape(original_text)
    safe_author = html.escape(author)

    header = f"📢 <b>{safe_author}</b>\n\n"
    content_parts = [header, f"<b>原文：</b>\n{safe_original}\n\n"]

    if translated_text:
        safe_translated = html.escape(translated_text)
        content_parts.append(f"<b>翻译：</b>\n{safe_translated}\n\n")

    content_parts.append(f"🔗 <a href='{link}'>查看推文</a>")
    return "".join(content_parts)


def _send_telegram_message(author, original_text, translated_text, link, images=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，跳过 Telegram 发送。")
        return

    body = _build_telegram_body(author, original_text, translated_text, link)

    method = "sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    if images and len(images) > 0:
        if len(body) <= 1000:
            method = "sendPhoto"
            payload["photo"] = images[0]
            payload["caption"] = body
            if "disable_web_page_preview" in payload:
                del payload["disable_web_page_preview"]
        else:
            print("内容过长，Telegram 跳过图片发送，改用链接预览。")
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

        if method == "sendPhoto":
            print("Telegram 尝试降级为纯文本发送...")
            try:
                if "photo" in payload:
                    del payload["photo"]
                if "caption" in payload:
                    del payload["caption"]

                payload["text"] = body
                payload["disable_web_page_preview"] = False

                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                response = requests.post(url, json=payload, timeout=20, proxies=proxies)
                response.raise_for_status()
                print(f"Telegram 降级发送成功: {link}")
            except Exception as e2:
                print(f"Telegram 降级发送也失败: {e2}")


def _send_telegram_plain_message(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，跳过 Telegram 发送。")
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    proxies = get_proxy_dict()
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=payload, timeout=20, proxies=proxies)
        response.raise_for_status()
        print(f"系统消息已发送到 Telegram: {text}")
    except Exception as e:
        print(f"发送系统消息到 Telegram 失败: {e}")


def _get_feishu_tenant_access_token():
    now = int(time.time())
    cached = _FEISHU_TOKEN_CACHE.get("token")
    if cached and _FEISHU_TOKEN_CACHE.get("expire_at", 0) > now:
        return cached

    url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}

    response = requests.post(url, json=payload, timeout=20, proxies=get_proxy_dict())
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 0:
        raise RuntimeError(f"获取飞书 tenant_access_token 失败: {result.get('msg', 'unknown error')}")

    token = result.get("tenant_access_token")
    expire = int(result.get("expire", 7200))
    _FEISHU_TOKEN_CACHE["token"] = token
    _FEISHU_TOKEN_CACHE["expire_at"] = now + max(expire - 120, 60)
    return token


def _download_image_bytes(image_url):
    response = requests.get(image_url, timeout=20, proxies=get_proxy_dict())
    response.raise_for_status()

    image_bytes = response.content
    if not image_bytes:
        raise RuntimeError("图片内容为空")

    max_size = 10 * 1024 * 1024
    if len(image_bytes) > max_size:
        raise RuntimeError("图片超过 10MB 限制")

    content_type = response.headers.get("Content-Type", "")
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(image_url)
        content_type = guessed_type or "application/octet-stream"

    return image_bytes, content_type


def _upload_feishu_image(token, image_url):
    image_bytes, content_type = _download_image_bytes(image_url)
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".jpg"
    filename = f"tweet_image{ext}"

    url = f"{FEISHU_API_BASE}/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"image_type": "message"}
    files = {"image": (filename, image_bytes, content_type)}

    response = requests.post(url, headers=headers, data=data, files=files, timeout=30, proxies=get_proxy_dict())
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 0:
        raise RuntimeError(f"飞书图片上传失败: {result.get('msg', 'unknown error')}")

    image_key = (result.get("data") or {}).get("image_key")
    if not image_key:
        raise RuntimeError("飞书图片上传失败: 未返回 image_key")
    return image_key


def _build_feishu_card(author, original_text, translated_text, link, image_key=None):
    elements = [
        {
            "tag": "markdown",
            "content": f"### **原文**\n{original_text}",
        }
    ]

    if translated_text:
        elements.append(
            {
                "tag": "markdown",
                "content": f"### **翻译**\n{translated_text}",
            }
        )

    if image_key:
        elements.append(
            {
                "tag": "img",
                "img_key": image_key,
                "alt": {"tag": "plain_text", "content": "tweet image"},
            }
        )

    elements.append(
        {
            "tag": "markdown",
            "content": f"[查看推文]({link})",
        }
    )

    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "fill"},
        "header": {
            "title": {"tag": "plain_text", "content": f"📢 {author}"},
            "template": "blue",
        },
        "body": {"elements": elements},
    }


def _send_feishu_card_message(author, original_text, translated_text, link, images=None):
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET or not FEISHU_RECEIVE_IDS:
        print("飞书配置缺失，跳过飞书发送。")
        return

    try:
        token = _get_feishu_tenant_access_token()
    except Exception as e:
        print(f"获取飞书访问凭证失败: {e}")
        return

    image_key = None
    if images and len(images) > 0:
        try:
            image_key = _upload_feishu_image(token, images[0])
        except Exception as e:
            print(f"飞书图片处理失败，继续发送无图卡片: {e}")

    content = json.dumps(
        _build_feishu_card(author, original_text, translated_text, link, image_key=image_key),
        ensure_ascii=False,
    )

    url = f"{FEISHU_API_BASE}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    for receive_id in FEISHU_RECEIVE_IDS:
        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": content,
            "uuid": str(uuid.uuid4()),
        }
        params = {"receive_id_type": FEISHU_RECEIVE_ID_TYPE}

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20,
                proxies=get_proxy_dict(),
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                raise RuntimeError(result.get("msg", "unknown error"))

            print(f"成功推送到飞书: {link} (receive_id={receive_id})")
        except Exception as e:
            print(f"推送到飞书失败 (receive_id={receive_id}): {e}")


def _send_feishu_plain_message(text):
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET or not FEISHU_RECEIVE_IDS:
        print("飞书配置缺失，跳过飞书发送。")
        return

    try:
        token = _get_feishu_tenant_access_token()
    except Exception as e:
        print(f"获取飞书访问凭证失败: {e}")
        return

    url = f"{FEISHU_API_BASE}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    content = json.dumps({"text": text}, ensure_ascii=False)

    for receive_id in FEISHU_RECEIVE_IDS:
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content,
            "uuid": str(uuid.uuid4()),
        }
        params = {"receive_id_type": FEISHU_RECEIVE_ID_TYPE}

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20,
                proxies=get_proxy_dict(),
            )
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                raise RuntimeError(result.get("msg", "unknown error"))

            print(f"系统消息已发送到飞书 (receive_id={receive_id}): {text}")
        except Exception as e:
            print(f"发送系统消息到飞书失败 (receive_id={receive_id}): {e}")


def send_telegram_message(author, original_text, translated_text, link, images=None):
    """
    兼容旧函数名：按配置分发到多个通知渠道。
    """
    if "telegram" in ENABLED_CHANNELS:
        _send_telegram_message(author, original_text, translated_text, link, images=images)

    if "feishu" in ENABLED_CHANNELS:
        _send_feishu_card_message(author, original_text, translated_text, link, images=images)


def send_plain_message(text):
    """
    兼容旧函数名：按配置分发到多个通知渠道。
    """
    if "telegram" in ENABLED_CHANNELS:
        _send_telegram_plain_message(text)

    if "feishu" in ENABLED_CHANNELS:
        _send_feishu_plain_message(text)
