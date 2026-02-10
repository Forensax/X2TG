import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取配置
RSS_URL = os.getenv("RSS_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1800"))
PROXY_URL = os.getenv("PROXY_URL")

# 简单校验
if not all([RSS_URL, GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID]):
    print("错误: 请在 .env 文件中配置所有必要的环境变量 (RSS_URL, GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID)")
    # 这里不退出，方便用户先运行看看结构，但在 main.py 中会检查
