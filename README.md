# Twitter/X to Telegram 自动翻译推送机器人

这是一个基于 Python 的自动化机器人，能够监控指定 Twitter/X 用户的 RSSHub 订阅源，使用 Google Gemini 大模型将推文自动翻译成中文，并实时推送到 Telegram 频道或群组。

## ✨ 功能特性

*   **多账号监控**: 支持同时监控多个 Twitter 账号，只需在配置中用逗号分隔多个 RSS URL。
*   **翻译控制**: 支持为每个账号单独配置是否开启翻译。使用 `@T`（开启，默认）或 `@F`（关闭）后缀。
    *   例如：`https://rsshub.app/twitter/user/elonmusk@T,https://rsshub.app/twitter/user/NASA@F`
*   **AI 翻译**: 集成 Google Gemini Pro/Flash 模型，提供流畅、自然的中文翻译（默认为 `gemini-3-flash-preview`）。
*   **智能重试**: 翻译失败自动重试机制（最多 3 次），并支持指数退避，确保服务稳定性。
*   **格式保留**: 翻译过程中自动保留原文链接、Hashtag (#标签) 和用户提及 (@用户)。
*   **智能去重**: 本地分别记录每个 RSS 源已处理的推文，避免重复推送（重启程序后依然有效）。
*   **防封禁**: 内置请求间隔和错误重试机制，防止触发 API 速率限制。
*   **代理支持**: 支持配置 HTTP/HTTPS 代理，方便国内网络环境使用。
*   **自定义 Base URL**: 支持自定义 Gemini API 端点（`GEMINI_BASE_URL`），便于对接反向代理。

## 🛠️ 前置要求

*   Python 3.8+
*   [Google Gemini API Key](https://aistudio.google.com/)
*   [Telegram Bot Token](https://t.me/BotFather)
*   有效的 RSSHub 订阅链接 (例如: `https://rsshub.app/twitter/user/elonmusk`)

## 🚀 安装步骤

1.  **克隆项目**
    ```bash
    git clone https://github.com/your-repo/rss-gemini-tg-bot.git
    cd rss-gemini-tg-bot
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置环境变量**
    复制配置文件模板并重命名为 `.env`：
    ```bash
    cp .env.example .env
    ```
    
    使用文本编辑器打开 `.env` 文件并填入以下信息：
    ```ini
    # RSSHub 订阅地址 (支持多个，用逗号分隔)
    # 格式: URL@T (翻译) 或 URL@F (不翻译)
    RSS_URL=https://rsshub.app/twitter/user/elonmusk@T,https://rsshub.app/twitter/user/NASA@F
    
    # Google Gemini API Key
    GEMINI_API_KEY=your_gemini_api_key_here

    # (可选) 自定义 Gemini API Base URL (例如使用反向代理时)
    # GEMINI_BASE_URL=https://generativelanguage.googleapis.com
    
    # Telegram Bot Token
    TG_BOT_TOKEN=your_telegram_bot_token
    
    # 接收消息的 Chat ID (用户 ID 或 频道 ID)
    TG_CHAT_ID=your_chat_id
    
    # 检查间隔 (秒)，默认 30 分钟
    CHECK_INTERVAL=1800
    
    # (可选) 代理设置
    # PROXY_URL=http://127.0.0.1:7890
    ```

## 🏃‍♂️ 运行

在配置完成后，直接运行主程序：

```bash
python main.py
```

程序启动后：
1.  **首次运行**：会自动标记所有配置账号的最新一条推文为"已读"，**不会**推送历史消息（防止刷屏）。
2.  之后每隔 `CHECK_INTERVAL` 秒检查一次新推文。
3.  发现新推文后，会自动翻译并推送到 Telegram。

## 📂 项目结构

*   `main.py`: 程序入口，负责多任务调度和主循环。
*   `config.py`: 配置加载模块，支持解析多 RSS URL 及翻译标记。
*   `rss_fetcher.py`: 负责从 RSSHub 获取并解析数据，独立管理每个源的状态。
*   `translator.py`: 调用 Google Gemini API 进行翻译，包含重试逻辑。
*   `notifier.py`: 调用 Telegram Bot API 发送消息。
*   `state.json`: (自动生成) 存储每个 RSS 源最后处理的推文链接。

## ⚠️ 注意事项

*   **RSSHub 稳定性**: 公共的 RSSHub 实例（如 rsshub.app）可能会因为反爬虫限制而无法获取 Twitter 内容。建议自建 RSSHub 或使用其他可靠的 RSS 源。
*   **Gemini 配额**: 请留意 Google Gemini API 的免费额度限制（通常每分钟请求次数有限制），默认的 30 分钟检查间隔通常是安全的。
*   **网络问题**: 如果在中国大陆使用，请务必配置 `.env` 中的 `PROXY_URL`。

## 📝 License

MIT License
