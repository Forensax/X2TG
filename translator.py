import time
from dataclasses import dataclass

from openai import OpenAI

from config import AppSettings, DEFAULT_OPENAI_COMPAT_MODEL


@dataclass
class TranslationResult:
    text: str
    success: bool
    error: str = ""


def translate_tweet(content: str, settings: AppSettings) -> TranslationResult:
    """使用 OpenAI 兼容 Chat Completions 接口翻译推文内容。"""
    if not settings.openai_api_key:
        return TranslationResult("无法翻译 (缺少 OpenAI 兼容 API Key)", False, "missing_api_key")

    prompt = build_translation_prompt(content)
    max_retries = 3
    base_wait_time = 2

    for attempt in range(max_retries + 1):
        try:
            translated = call_openai_compatible(prompt, settings)
            if not translated:
                raise ValueError("模型返回了空内容")
            return TranslationResult(translated.strip(), True)
        except Exception as exc:
            if attempt < max_retries:
                wait_time = base_wait_time * (attempt + 1)
                print(f"OpenAI 兼容接口翻译失败 (尝试 {attempt + 1}/{max_retries}): {exc}")
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            print(f"OpenAI 兼容接口翻译最终失败: {exc}")
            return TranslationResult(f"翻译失败: {exc}", False, str(exc))

    return TranslationResult("翻译失败 (未知错误)", False, "unknown")


def build_translation_prompt(content: str) -> str:
    return f"""
请将以下推特推文内容翻译成流畅、自然的中文。

要求：
1. 保持原推文的语气和情感。
2. 不要直译，要符合中文阅读习惯。
3. 必须保留原文中的所有链接 (URL)、Hashtag (#标签) 和提及 (@用户)。
4. 只输出翻译后的中文内容，不要包含解释或其他文字。

推文内容：
{content}
"""


def call_openai_compatible(prompt: str, settings: AppSettings) -> str:
    client = build_openai_client(settings.openai_api_key, settings.openai_base_url)
    response = client.chat.completions.create(
        model=settings.ai_model or DEFAULT_OPENAI_COMPAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    if not response.choices:
        return ""
    message = response.choices[0].message
    return message.content or ""


def build_openai_client(api_key: str, base_url: str = "") -> OpenAI:
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)

