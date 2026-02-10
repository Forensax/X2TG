import google.generativeai as genai
from config import GEMINI_API_KEY
import textwrap

# 配置 API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("警告: 未配置 GEMINI_API_KEY，无法进行翻译。")

def translate_tweet(content):
    """
    使用 Gemini 翻译推文内容
    """
    if not GEMINI_API_KEY:
        return "无法翻译 (缺少 API Key)"

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
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
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini 翻译失败: {e}")
        return f"翻译失败: {str(e)}"
