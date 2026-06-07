import html
import json
import mimetypes
import time
import uuid
from dataclasses import dataclass

import requests

from config import FeishuConfig, NotificationConfig, TelegramConfig


@dataclass
class ChannelResult:
    channel: str
    success: bool
    message: str = ""


_FEISHU_TOKEN_CACHE = {"cache_key": "", "token": None, "expire_at": 0}


def get_proxy_dict(proxy_url: str = ""):
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def send_tweet_message(
    notifications: NotificationConfig,
    proxy_url: str,
    author: str,
    original_text: str,
    translated_text: str,
    link: str,
    images: list[str] | None = None,
) -> list[ChannelResult]:
    results: list[ChannelResult] = []
    if notifications.telegram.enabled:
        results.append(
            _send_telegram_message(
                notifications.telegram,
                proxy_url,
                author,
                original_text,
                translated_text,
                link,
                images=images,
            )
        )
    if notifications.feishu.enabled:
        results.append(
            _send_feishu_card_message(
                notifications.feishu,
                proxy_url,
                author,
                original_text,
                translated_text,
                link,
                images=images,
            )
        )
    if not results:
        results.append(ChannelResult("none", False, "没有启用通知渠道"))
    return results


def send_plain_message(
    notifications: NotificationConfig,
    proxy_url: str,
    text: str,
) -> list[ChannelResult]:
    results: list[ChannelResult] = []
    if notifications.telegram.enabled:
        results.append(_send_telegram_plain_message(notifications.telegram, proxy_url, text))
    if notifications.feishu.enabled:
        results.append(_send_feishu_plain_message(notifications.feishu, proxy_url, text))
    if not results:
        results.append(ChannelResult("none", False, "没有启用通知渠道"))
    return results


def successful_channels(results: list[ChannelResult]) -> list[str]:
    return [result.channel for result in results if result.success]


def _build_telegram_body(author: str, original_text: str, translated_text: str, link: str) -> str:
    safe_original = html.escape(original_text)
    safe_author = html.escape(author)
    header = f"📢 <b>{safe_author}</b>\n\n"
    content_parts = [header, f"<b>原文：</b>\n{safe_original}\n\n"]
    if translated_text:
        safe_translated = html.escape(translated_text)
        content_parts.append(f"<b>翻译：</b>\n{safe_translated}\n\n")
    content_parts.append(f"🔗 <a href='{html.escape(link, quote=True)}'>查看推文</a>")
    return "".join(content_parts)


def _send_telegram_message(
    config: TelegramConfig,
    proxy_url: str,
    author: str,
    original_text: str,
    translated_text: str,
    link: str,
    images: list[str] | None = None,
) -> ChannelResult:
    if not config.bot_token or not config.chat_id:
        return ChannelResult("telegram", False, "Telegram 配置缺失")

    body = _build_telegram_body(author, original_text, translated_text, link)
    method = "sendMessage"
    payload = {
        "chat_id": config.chat_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    if images:
        if len(body) <= 1000:
            method = "sendPhoto"
            payload["photo"] = images[0]
            payload["caption"] = body
            payload.pop("disable_web_page_preview", None)
        else:
            payload["text"] = body
    else:
        payload["text"] = body

    url = f"https://api.telegram.org/bot{config.bot_token}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=20, proxies=get_proxy_dict(proxy_url))
        response.raise_for_status()
        return ChannelResult("telegram", True, f"method={method}")
    except Exception as exc:
        if method == "sendPhoto":
            fallback = _send_telegram_text(config, proxy_url, body)
            if fallback.success:
                return ChannelResult("telegram", True, "sendPhoto 失败，已降级为 sendMessage")
            return ChannelResult("telegram", False, f"sendPhoto 失败且降级失败: {fallback.message}")
        return ChannelResult("telegram", False, str(exc))


def _send_telegram_text(config: TelegramConfig, proxy_url: str, body: str) -> ChannelResult:
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {
        "chat_id": config.chat_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "text": body,
    }
    try:
        response = requests.post(url, json=payload, timeout=20, proxies=get_proxy_dict(proxy_url))
        response.raise_for_status()
        return ChannelResult("telegram", True, "sendMessage")
    except Exception as exc:
        return ChannelResult("telegram", False, str(exc))


def _send_telegram_plain_message(
    config: TelegramConfig,
    proxy_url: str,
    text: str,
) -> ChannelResult:
    if not config.bot_token or not config.chat_id:
        return ChannelResult("telegram", False, "Telegram 配置缺失")
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {"chat_id": config.chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=20, proxies=get_proxy_dict(proxy_url))
        response.raise_for_status()
        return ChannelResult("telegram", True, "系统消息已发送")
    except Exception as exc:
        return ChannelResult("telegram", False, str(exc))


def _feishu_cache_key(config: FeishuConfig) -> str:
    return f"{config.api_base}|{config.app_id}|{config.app_secret}"


def _get_feishu_tenant_access_token(config: FeishuConfig, proxy_url: str) -> str:
    now = int(time.time())
    cache_key = _feishu_cache_key(config)
    cached = _FEISHU_TOKEN_CACHE.get("token")
    if (
        cached
        and _FEISHU_TOKEN_CACHE.get("cache_key") == cache_key
        and _FEISHU_TOKEN_CACHE.get("expire_at", 0) > now
    ):
        return str(cached)

    url = f"{config.api_base}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": config.app_id, "app_secret": config.app_secret}
    response = requests.post(url, json=payload, timeout=20, proxies=get_proxy_dict(proxy_url))
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        raise RuntimeError(f"获取飞书 tenant_access_token 失败: {result.get('msg', 'unknown error')}")

    token = result.get("tenant_access_token")
    expire = int(result.get("expire", 7200))
    _FEISHU_TOKEN_CACHE["cache_key"] = cache_key
    _FEISHU_TOKEN_CACHE["token"] = token
    _FEISHU_TOKEN_CACHE["expire_at"] = now + max(expire - 120, 60)
    return token


def _download_image_bytes(image_url: str, proxy_url: str):
    response = requests.get(image_url, timeout=20, proxies=get_proxy_dict(proxy_url))
    response.raise_for_status()
    image_bytes = response.content
    if not image_bytes:
        raise RuntimeError("图片内容为空")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise RuntimeError("图片超过 10MB 限制")
    content_type = response.headers.get("Content-Type", "")
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(image_url)
        content_type = guessed_type or "application/octet-stream"
    return image_bytes, content_type


def _upload_feishu_image(token: str, config: FeishuConfig, proxy_url: str, image_url: str) -> str:
    image_bytes, content_type = _download_image_bytes(image_url, proxy_url)
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".jpg"
    filename = f"tweet_image{ext}"
    url = f"{config.api_base}/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"image_type": "message"}
    files = {"image": (filename, image_bytes, content_type)}
    response = requests.post(
        url,
        headers=headers,
        data=data,
        files=files,
        timeout=30,
        proxies=get_proxy_dict(proxy_url),
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        raise RuntimeError(f"飞书图片上传失败: {result.get('msg', 'unknown error')}")
    image_key = (result.get("data") or {}).get("image_key")
    if not image_key:
        raise RuntimeError("飞书图片上传失败: 未返回 image_key")
    return image_key


def _build_feishu_card(
    author: str,
    original_text: str,
    translated_text: str,
    link: str,
    image_key: str | None = None,
) -> dict:
    elements = [{"tag": "markdown", "content": f"### **原文**\n{original_text}"}]
    if translated_text:
        elements.append({"tag": "markdown", "content": f"### **翻译**\n{translated_text}"})
    if image_key:
        elements.append(
            {
                "tag": "img",
                "img_key": image_key,
                "alt": {"tag": "plain_text", "content": "tweet image"},
            }
        )
    elements.append({"tag": "markdown", "content": f"[查看推文]({link})"})
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "fill"},
        "header": {
            "title": {"tag": "plain_text", "content": f"📢 {author}"},
            "template": "blue",
        },
        "body": {"elements": elements},
    }


def _send_feishu_card_message(
    config: FeishuConfig,
    proxy_url: str,
    author: str,
    original_text: str,
    translated_text: str,
    link: str,
    images: list[str] | None = None,
) -> ChannelResult:
    if not config.app_id or not config.app_secret or not config.receive_ids:
        return ChannelResult("feishu", False, "飞书配置缺失")
    try:
        token = _get_feishu_tenant_access_token(config, proxy_url)
    except Exception as exc:
        return ChannelResult("feishu", False, f"获取访问凭证失败: {exc}")

    image_key = None
    if images:
        try:
            image_key = _upload_feishu_image(token, config, proxy_url, images[0])
        except Exception as exc:
            print(f"飞书图片处理失败，继续发送无图卡片: {exc}")

    content = json.dumps(
        _build_feishu_card(author, original_text, translated_text, link, image_key=image_key),
        ensure_ascii=False,
    )
    url = f"{config.api_base}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    failures = []
    success_count = 0
    for receive_id in config.receive_ids:
        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": content,
            "uuid": str(uuid.uuid4()),
        }
        params = {"receive_id_type": config.receive_id_type}
        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20,
                proxies=get_proxy_dict(proxy_url),
            )
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                raise RuntimeError(result.get("msg", "unknown error"))
            success_count += 1
        except Exception as exc:
            failures.append(f"{receive_id}: {exc}")
    if success_count:
        suffix = f"，失败 {len(failures)} 个" if failures else ""
        return ChannelResult("feishu", True, f"成功 {success_count} 个接收者{suffix}")
    return ChannelResult("feishu", False, "; ".join(failures) or "飞书发送失败")


def _send_feishu_plain_message(config: FeishuConfig, proxy_url: str, text: str) -> ChannelResult:
    if not config.app_id or not config.app_secret or not config.receive_ids:
        return ChannelResult("feishu", False, "飞书配置缺失")
    try:
        token = _get_feishu_tenant_access_token(config, proxy_url)
    except Exception as exc:
        return ChannelResult("feishu", False, f"获取访问凭证失败: {exc}")

    url = f"{config.api_base}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    content = json.dumps({"text": text}, ensure_ascii=False)
    failures = []
    success_count = 0
    for receive_id in config.receive_ids:
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content,
            "uuid": str(uuid.uuid4()),
        }
        params = {"receive_id_type": config.receive_id_type}
        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20,
                proxies=get_proxy_dict(proxy_url),
            )
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                raise RuntimeError(result.get("msg", "unknown error"))
            success_count += 1
        except Exception as exc:
            failures.append(f"{receive_id}: {exc}")
    if success_count:
        suffix = f"，失败 {len(failures)} 个" if failures else ""
        return ChannelResult("feishu", True, f"成功 {success_count} 个接收者{suffix}")
    return ChannelResult("feishu", False, "; ".join(failures) or "飞书发送失败")


# 兼容旧函数名；新 Web 代码不使用它们。
def send_telegram_message(*args, **kwargs):
    raise RuntimeError("send_telegram_message 已迁移为 send_tweet_message，需要传入运行时通知配置。")

