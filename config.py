import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取配置
# 支持多个 RSS URL，使用逗号分隔
rss_env = os.getenv("RSS_URL", "")
RSS_URLS = [url.strip() for url in rss_env.split(",") if url.strip()]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1800"))
PROXY_URL = os.getenv("PROXY_URL")

# 简单校验
if not RSS_URLS:
    print("错误: 请在 .env 文件中配置 RSS_URL (多个地址用逗号分隔)")
if not all([GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID]):
    print("错误: 请在 .env 文件中配置必要的环境变量 (GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID)")
