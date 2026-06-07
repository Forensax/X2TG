# X2TG Web

X2TG 是一个用于监控 Twitter/X RSSHub 订阅源、翻译推文并推送到 Telegram/飞书的私有 Web 管理项目。

当前版本已经从 `.env` 驱动的单进程脚本改造成单体 Web 服务：

- 在网页中配置 RSS 源、代理、大模型 API、Telegram、飞书。
- 后台自动定时检查 RSS，也支持手动检查。
- SQLite 持久化配置、RSS 进度、成功发送历史和运行日志。
- 单管理员密码登录保护管理页面。
- 首次启动会兼容导入旧 `.env` 和 `state.json`，不会删除原文件。

## 功能

- 多 RSS 源监控，每个源可单独启停和控制是否翻译。
- 支持 Gemini / OpenAI，并可配置模型名、API Key、Base URL。
- 支持 HTTP/HTTPS 代理。
- 支持 Telegram 和飞书应用机器人通知渠道。
- 历史页面只展示至少一个渠道发送成功的消息。
- 运维页面支持暂停/恢复后台监控、立即检查全部、单源检查、查看日志。
- 新增 RSS 源默认只标记最新内容为已读，避免首次配置时刷屏。

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

启动 Web 服务：

```bash
python main.py
```

或：

```bash
uvicorn app.web:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开：

```text
http://localhost:8000
```

首次访问会进入管理员初始化页面。也可以在首次启动前设置：

```bash
ADMIN_INIT_PASSWORD=change-me-now
```

默认数据库位置：

```text
data/x2tg.db
```

## Docker 运行

```bash
docker compose up -d --build
```

访问：

```text
http://localhost:8000
```

`docker-compose.yml` 默认挂载：

```text
./data:/app/data
```

如需首次导入旧 `.env`，可以临时取消 compose 中的 `.env` 挂载注释。导入完成后建议移除该挂载，改用网页配置。

## 旧配置迁移

启动时如果检测到项目根目录存在 `.env`，会导入这些字段：

- `RSS_URL`
- `AI_PROVIDER`
- `GEMINI_API_KEY`
- `GEMINI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `TG_BOT_TOKEN`
- `TG_CHAT_ID`
- `NOTIFY_CHANNELS`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_RECEIVE_ID_TYPE`
- `FEISHU_RECEIVE_IDS`
- `FEISHU_API_BASE`
- `CHECK_INTERVAL`
- `PROXY_URL`

如果检测到旧 `state.json`，会把每个 RSS URL 的最后处理链接合并到 SQLite。

迁移不会删除 `.env` 或 `state.json`。

## 现在 `.env` 还可以放什么

日常配置建议都在网页中完成。`.env` 只建议保留启动级配置：

```ini
DATABASE_URL=sqlite:///data/x2tg.db
ADMIN_INIT_PASSWORD=change-me-now
SECRET_KEY=replace-with-a-long-random-string
TZ=Asia/Shanghai
```

`ADMIN_INIT_PASSWORD` 只用于第一次创建管理员。管理员创建后建议删除。

## 项目结构

- `app/web.py`：FastAPI 路由、表单页面、应用启动入口。
- `app/db.py`：SQLite schema、迁移、配置和历史数据访问。
- `app/monitor.py`：后台定时检查、手动检查、暂停/恢复。
- `app/auth.py`：单管理员密码和签名 Cookie 登录。
- `app/templates/`：Jinja2 页面模板。
- `app/static/`：管理界面样式。
- `rss_fetcher.py`：RSS 获取与解析。
- `translator.py`：Gemini/OpenAI 翻译。
- `notifier.py`：Telegram/飞书发送。
- `main.py`：兼容入口，启动 Web 服务。

## 注意事项

- 公共 RSSHub 实例可能不稳定，建议使用自建或稳定 RSSHub。
- Telegram、Gemini、OpenAI 在中国大陆网络环境下通常需要代理。
- 当前登录保护按私有自用设计；公网部署建议放在 HTTPS 反向代理后面，并设置稳定的 `SECRET_KEY`。
- 成功发送至少一个通知渠道后才会推进 RSS 进度；全部渠道失败会保留进度，便于下次重试。

