import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取配置
# 支持多个 RSS URL，使用逗号分隔
# 格式: URL@T (翻译) 或 URL@F (不翻译)，默认开启翻译
rss_env = os.getenv("RSS_URL", "")
RSS_CONFIGS = []

for item in rss_env.split(","):
    item = item.strip()
    if not item:
        continue
    
    # 按照 @ 分割 URL 和 标记
    parts = item.split("@")
    url = parts[0].strip()
    
    # 默认开启翻译
    translate_flag = True 
    if len(parts) > 1:
        flag = parts[1].strip().upper()
        if flag == 'F':
            translate_flag = False
            
    if url:
        RSS_CONFIGS.append({
            "url": url,
            "translate": translate_flag
        })

# 兼容旧代码引用 (只取 URL 列表)
RSS_URLS = [c["url"] for c in RSS_CONFIGS]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1800"))
PROXY_URL = os.getenv("PROXY_URL")

# 简单校验
if not RSS_CONFIGS:
    print("错误: 请在 .env 文件中配置 RSS_URL (格式: URL@T,URL@F)")
if not all([GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID]):
    print("错误: 请在 .env 文件中配置必要的环境变量 (GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID)")
