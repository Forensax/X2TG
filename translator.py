import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from openai import OpenAI

from config import AppSettings


@dataclass
class TranslationResult:
    text: str
    success: bool
    error: str = ""


def translate_tweet(content: str, settings: AppSettings) -> TranslationResult:
    """使用当前运行时设置翻译推文内容。"""
    provider = settings.ai_provider.lower()
    if provider == "gemini" and not settings.gemini_api_key:
        return TranslationResult("无法翻译 (缺少 Gemini API Key)", False, "missing_gemini_key")
    if provider == "openai" and not settings.openai_api_key:
        return TranslationResult("无法翻译 (缺少 OpenAI API Key)", False, "missing_openai_key")
    if provider not in {"gemini", "openai"}:
        return TranslationResult(f"无法翻译 (未知 AI Provider: {settings.ai_provider})", False, "unknown_provider")

    prompt = build_translation_prompt(content)
    max_retries = 3
    base_wait_time = 2

    for attempt in range(max_retries + 1):
        try:
            translated = _call_provider(prompt, settings)
            if not translated:
                raise ValueError("模型返回了空内容")
            return TranslationResult(translated.strip(), True)
        except Exception as exc:
            if attempt < max_retries:
                wait_time = base_wait_time * (attempt + 1)
                print(f"{provider} 翻译失败 (尝试 {attempt + 1}/{max_retries}): {exc}")
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            print(f"{provider} 翻译最终失败: {exc}")
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


def _call_provider(prompt: str, settings: AppSettings) -> str:
    if settings.ai_provider == "openai":
        return _call_openai(prompt, settings)
    return _call_gemini(prompt, settings)


def _call_gemini(prompt: str, settings: AppSettings) -> str:
    http_options = {"base_url": settings.gemini_base_url} if settings.gemini_base_url else None
    client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)  # type: ignore[arg-type]
    response = client.models.generate_content(
        model=settings.ai_model or "gemini-3-flash-preview",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.7, candidate_count=1),
    )
    return response.text or ""


def _call_openai(prompt: str, settings: AppSettings) -> str:
    kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**kwargs)
    response = client.responses.create(
        model=settings.ai_model or "gpt-5.5",
        reasoning={"effort": "medium"},
        input=[{"role": "user", "content": prompt}],
    )
    return response.output_text or ""

