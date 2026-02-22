from google import genai
from google.genai import types
from openai import OpenAI
from config import GEMINI_API_KEY, GEMINI_BASE_URL, AI_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL
import time
import textwrap

gemini_client = None
openai_client = None

# 初始化客户端
if AI_PROVIDER == "gemini":
    if GEMINI_API_KEY:
        try:
            http_options = None
            if GEMINI_BASE_URL:
                # 如果配置了 Base URL，设置 base_url
                http_options = {'base_url': GEMINI_BASE_URL}
                print(f"使用自定义 Gemini Base URL: {GEMINI_BASE_URL}")
                
            gemini_client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_options)  # type: ignore
        except Exception as e:
            print(f"初始化 Gemini 客户端失败: {e}")
    else:
        print("警告: 选择了 gemini 接口，但未配置 GEMINI_API_KEY，无法进行翻译。")

elif AI_PROVIDER == "openai":
    if OPENAI_API_KEY:
        try:
            kwargs = {"api_key": OPENAI_API_KEY}
            if OPENAI_BASE_URL:
                kwargs["base_url"] = OPENAI_BASE_URL
                print(f"使用自定义 OpenAI Base URL: {OPENAI_BASE_URL}")
            openai_client = OpenAI(**kwargs)
        except Exception as e:
            print(f"初始化 OpenAI 客户端失败: {e}")
    else:
        print("警告: 选择了 openai 接口，但未配置 OPENAI_API_KEY，无法进行翻译。")
else:
    print(f"警告: 未知 AI_PROVIDER: {AI_PROVIDER}")

def translate_tweet(content):
    """
    使用 AI 翻译推文内容
    如果失败，最多重试 3 次
    """
    local_gemini_client = gemini_client
    local_openai_client = openai_client
    
    if AI_PROVIDER == "gemini" and not local_gemini_client:
        return "无法翻译 (缺少 Gemini API Key)"
    elif AI_PROVIDER == "openai" and not local_openai_client:
        return "无法翻译 (缺少 OpenAI API Key)"

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
            if AI_PROVIDER == "gemini" and local_gemini_client:
                # 使用 gemini-3-flash-preview 模型
                response = local_gemini_client.models.generate_content(
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
                
            elif AI_PROVIDER == "openai" and local_openai_client:
                response = local_openai_client.responses.create(
                    model="gpt-5.2",
                    reasoning={"effort": "medium"},
                    input=[
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ]
                )
                if not response.output_text:
                    raise ValueError("OpenAI 返回了空内容")
                return response.output_text.strip()
                
        except Exception as e:
            if attempt < max_retries:
                wait_time = base_wait_time * (attempt + 1)
                provider_name = "Gemini" if AI_PROVIDER == "gemini" else "OpenAI"
                print(f"{provider_name} 翻译失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                provider_name = "Gemini" if AI_PROVIDER == "gemini" else "OpenAI"
                print(f"{provider_name} 翻译最终失败: {e}")
                return f"翻译失败: {str(e)}"
    
    return "翻译失败 (未知错误)"
