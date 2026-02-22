import os
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
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1800"))
PROXY_URL = os.getenv("PROXY_URL")


def parse_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


# 通知渠道配置，默认开启多个渠道
NOTIFY_CHANNELS = [
    channel.lower() for channel in parse_csv(os.getenv("NOTIFY_CHANNELS", "telegram,feishu"))
]

# 飞书应用机器人配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_RECEIVE_ID_TYPE = os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id")
FEISHU_RECEIVE_IDS = parse_csv(os.getenv("FEISHU_RECEIVE_IDS", ""))
FEISHU_API_BASE = os.getenv("FEISHU_API_BASE", "https://open.feishu.cn/open-apis")


def build_enabled_channels():
    enabled = []
    requested = []

    for channel in NOTIFY_CHANNELS:
        if channel not in ("telegram", "feishu"):
            print(f"警告: 不支持的通知渠道 '{channel}'，已忽略")
            continue

        if channel in requested:
            continue
        requested.append(channel)

    for channel in requested:
        if channel == "telegram":
            if TG_BOT_TOKEN and TG_CHAT_ID:
                enabled.append(channel)
            else:
                print("警告: Telegram 渠道未完整配置，已跳过 (需 TG_BOT_TOKEN + TG_CHAT_ID)")
        elif channel == "feishu":
            if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_RECEIVE_IDS:
                enabled.append(channel)
            else:
                print(
                    "警告: 飞书渠道未完整配置，已跳过 "
                    "(需 FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_RECEIVE_IDS)"
                )

    return enabled


ENABLED_CHANNELS = build_enabled_channels()

# 简单校验
if not RSS_CONFIGS:
    print("错误: 请在 .env 文件中配置 RSS_URL (格式: URL@T,URL@F)")
if any(config["translate"] for config in RSS_CONFIGS):
    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        print("错误: 检测到开启翻译的 RSS 源，由于使用 gemini 模型，但未配置 GEMINI_API_KEY")
    elif AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        print("错误: 检测到开启翻译的 RSS 源，由于使用 openai 模型，但未配置 OPENAI_API_KEY")

if not ENABLED_CHANNELS:
    print("错误: 没有可用的通知渠道，请检查 NOTIFY_CHANNELS 及对应配置")
