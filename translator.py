from google import genai
from google.genai import types
from config import GEMINI_API_KEY
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
    """
    if not client:
        return "无法翻译 (缺少 API Key)"

    try:
        # 使用新版 SDK 调用
        # model="gemini-2.0-flash" 是目前比较推荐的快速模型
        # 如果你有权限使用 gemini-3-flash-preview 或其他模型，请在这里修改
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"""
            请将以下推特推文内容翻译成流畅、自然的中文。
            
            要求：
            1. 保持原推文的语气和情感。
            2. 不要直译，要符合中文阅读习惯。
            3. 必须保留原文中的所有链接 (URL)、Hashtag (#标签) 和提及 (@用户)。
            4. 只输出翻译后的中文内容，不要包含解释或其他文字。

            推文内容：
            {content}
            """,
            config=types.GenerateContentConfig(
                temperature=0.7, # 控制创造性，0.7 适合翻译
                candidate_count=1
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini 翻译失败: {e}")
        return f"翻译失败: {str(e)}"
