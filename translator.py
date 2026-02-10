from google import genai
from google.genai import types
from config import GEMINI_API_KEY
import time
import textwrap

# 初始化客户端
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("警告: 未配置 GEMINI_API_KEY，无法进行翻译。")
    client = None

def translate_tweet(content):
    """
    使用 Gemini 翻译推文内容 (使用 google-genai SDK)
    如果失败，最多重试 3 次
    """
    if not client:
        return "无法翻译 (缺少 API Key)"

    max_retries = 3
    base_wait_time = 2  # 初始等待时间 2秒

    prompt = f"""
    请将以下推特推文内容翻译成流畅、自然的中文。
    
    要求：
    1. 保持原推文的语气和情感。
    2. 不要直译，要符合中文阅读习惯。
    3. 必须保留原文中的所有链接 (URL)、Hashtag (#标签) 和提及 (@用户)。
    4. 只输出翻译后的中文内容，不要包含解释或其他文字。

    推文内容：
    {content}
    """

    for attempt in range(max_retries + 1):
        try:
            # 使用新版 SDK 调用
            # 使用 gemini-3-flash-preview 模型
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7, 
                    candidate_count=1
                )
            )
            if not response.text:
                raise ValueError("Gemini 返回了空内容")
            return response.text.strip()
        except Exception as e:
            if attempt < max_retries:
                wait_time = base_wait_time * (attempt + 1)
                print(f"Gemini 翻译失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"Gemini 翻译最终失败: {e}")
                return f"翻译失败: {str(e)}"
    
    return "翻译失败 (未知错误)"
