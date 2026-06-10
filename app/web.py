import os
import time
from pathlib import Path
from typing import Optional

import requests
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import AuthService, generate_secret_key
from app.db import Repository
from app.monitor import Monitor
from config import (
    DEFAULT_DATABASE_URL,
    DEFAULT_FEISHU_API_BASE,
    DEFAULT_OPENAI_COMPAT_MODEL,
    AppSettings,
    FeishuConfig,
    NotificationConfig,
    SECRET_PLACEHOLDER,
    TelegramConfig,
    parse_bool,
    parse_csv,
)
from notifier import send_plain_message, successful_channels
from rss_fetcher import fetch_latest_link
from translator import build_openai_client


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

repo = Repository(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
repo.initialize()
repo.migrate_legacy_files(str(PROJECT_DIR / ".env"), str(PROJECT_DIR / "state.json"))

auth = AuthService(repo, os.getenv("SECRET_KEY", generate_secret_key()))
monitor = Monitor(repo)

app = FastAPI(title="X2TG Web")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
async def startup() -> None:
    init_password = os.getenv("ADMIN_INIT_PASSWORD", "")
    if init_password and not repo.has_admin():
        auth.create_admin("admin", init_password)
        repo.add_event("info", "auth", "已使用 ADMIN_INIT_PASSWORD 初始化管理员。")
    await monitor.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await monitor.stop()


def require_auth(request: Request) -> Optional[RedirectResponse]:
    if not repo.has_admin() and request.url.path != "/setup":
        return RedirectResponse("/setup", status_code=303)
    if request.url.path in {"/login", "/setup"}:
        return None
    if not auth.is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return None


def context(request: Request, **extra):
    data = {
        "request": request,
        "monitor": monitor.snapshot(),
        "has_admin": repo.has_admin(),
        "path": request.url.path,
        "flash": request.query_params.get("flash", ""),
        "error": request.query_params.get("error", ""),
        "secret_placeholder": SECRET_PLACEHOLDER,
    }
    data.update(extra)
    return data


def valid_password_length(password: str) -> bool:
    return len(password.encode("utf-8")) <= 72


def proxy_dict(proxy_url: str) -> Optional[dict]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def render(request: Request, template: str, **extra):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=context(request, **extra),
    )


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if repo.has_admin():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context=context(request),
    )


@app.post("/setup")
async def setup_admin(
    request: Request,
    username: str = Form("admin"),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    if repo.has_admin():
        return RedirectResponse("/login", status_code=303)
    if len(password) < 8:
        return RedirectResponse("/setup?error=密码至少需要 8 位", status_code=303)
    if not valid_password_length(password):
        return RedirectResponse("/setup?error=密码不能超过 72 字节", status_code=303)
    if password != password_confirm:
        return RedirectResponse("/setup?error=两次输入的密码不一致", status_code=303)
    auth.create_admin(username.strip() or "admin", password)
    return auth.login_response("/")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not repo.has_admin():
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=context(request),
    )


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if auth.authenticate(username.strip(), password):
        return auth.login_response("/")
    return RedirectResponse("/login?error=用户名或密码错误", status_code=303)


@app.post("/logout")
async def logout():
    return auth.logout_response()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    counts = repo.counts()
    settings = repo.get_settings()
    notifications = repo.get_notifications()
    return render(
        request,
        "dashboard.html",
        counts=counts,
        settings=settings,
        notifications=notifications,
        recent_messages=repo.recent_sent_messages(6),
        recent_errors=repo.recent_errors(6),
        events=repo.list_events(limit=8),
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return render(request, "settings.html", settings=repo.get_settings())


@app.post("/settings")
async def save_settings(
    request: Request,
    check_interval: int = Form(1800),
    proxy_url: str = Form(""),
    ai_model: str = Form(""),
    openai_api_key: str = Form(""),
    openai_base_url: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    repo.save_settings(
        AppSettings(
            check_interval=check_interval,
            proxy_url=proxy_url,
            ai_model=ai_model,
            openai_api_key="" if openai_api_key == SECRET_PLACEHOLDER else openai_api_key,
            openai_base_url=openai_base_url,
        ),
        keep_blank_secrets=True,
    )
    monitor.config_reloaded()
    return RedirectResponse("/settings?flash=系统设置已保存", status_code=303)


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request, edit: str = "", new: str = ""):
    editing = repo.get_source(int(edit)) if edit.isdigit() else None
    return render(
        request,
        "sources.html",
        sources=repo.list_sources(),
        editing=editing,
        adding=parse_bool(new),
    )


@app.post("/sources")
async def save_source(
    request: Request,
    background_tasks: BackgroundTasks,
    source_id: str = Form(""),
    url: str = Form(...),
    display_name: str = Form(""),
    translate_enabled: str = Form(""),
    enabled: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    saved_id = repo.save_source(
        url=url,
        display_name=display_name,
        translate_enabled=parse_bool(translate_enabled),
        enabled=parse_bool(enabled),
        source_id=int(source_id) if source_id else None,
    )
    source = repo.get_source(saved_id)
    if source and not source.last_link:
        settings = repo.get_settings()
        background_tasks.add_task(initialize_source_latest, saved_id, source.url, settings.proxy_url)
    monitor.config_reloaded()
    return RedirectResponse("/sources?flash=RSS 源已保存", status_code=303)


def initialize_source_latest(source_id: int, url: str, proxy_url: str) -> None:
    latest = fetch_latest_link(url, proxy_url)
    if latest:
        repo.update_source_last_link(source_id, latest)
        repo.add_event("info", "source_init", f"新增 RSS 源已标记最新内容为已读: {url}", {"link": latest})
    else:
        repo.add_event("warning", "source_init", f"新增 RSS 源初始化未获取到内容: {url}")


@app.post("/sources/{source_id}/delete")
async def delete_source(request: Request, source_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    repo.delete_source(source_id)
    monitor.config_reloaded()
    return RedirectResponse("/sources?flash=RSS 源已删除", status_code=303)


@app.post("/sources/{source_id}/check")
async def check_source(request: Request, source_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    await monitor.check_source(source_id, manual=True)
    return RedirectResponse("/ops?flash=单个 RSS 源检查完成", status_code=303)


@app.post("/sources/{source_id}/send-latest")
async def send_latest_source(request: Request, source_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    sent = await monitor.send_latest_source(source_id)
    if sent:
        return RedirectResponse("/sources?flash=最新一条推文已发送", status_code=303)
    return RedirectResponse("/sources?error=最新一条推文发送失败，请查看运维日志", status_code=303)


@app.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    return render(request, "channels.html", notifications=repo.get_notifications())


@app.post("/channels")
async def save_channels(
    request: Request,
    telegram_enabled: str = Form(""),
    tg_bot_token: str = Form(""),
    tg_chat_id: str = Form(""),
    feishu_enabled: str = Form(""),
    feishu_app_id: str = Form(""),
    feishu_app_secret: str = Form(""),
    feishu_receive_id_type: str = Form("chat_id"),
    feishu_receive_ids: str = Form(""),
    feishu_api_base: str = Form(DEFAULT_FEISHU_API_BASE),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    repo.save_notifications(
        NotificationConfig(
            telegram=TelegramConfig(
                enabled=parse_bool(telegram_enabled),
                bot_token="" if tg_bot_token == SECRET_PLACEHOLDER else tg_bot_token,
                chat_id=tg_chat_id,
            ),
            feishu=FeishuConfig(
                enabled=parse_bool(feishu_enabled),
                app_id=feishu_app_id,
                app_secret="" if feishu_app_secret == SECRET_PLACEHOLDER else feishu_app_secret,
                receive_id_type=feishu_receive_id_type,
                receive_ids=parse_csv(feishu_receive_ids),
                api_base=feishu_api_base or DEFAULT_FEISHU_API_BASE,
            ),
        ),
        keep_blank_secrets=True,
    )
    monitor.config_reloaded()
    return RedirectResponse("/channels?flash=通知渠道已保存", status_code=303)


@app.post("/channels/test/{channel}")
async def test_channel(request: Request, channel: str):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if channel not in {"telegram", "feishu"}:
        return RedirectResponse("/channels?error=不支持的通知渠道", status_code=303)

    config = repo.get_runtime_config()
    if channel == "telegram":
        notifications = NotificationConfig(
            telegram=config.notifications.telegram,
            feishu=FeishuConfig(enabled=False),
        )
        label = "Telegram"
    else:
        notifications = NotificationConfig(
            telegram=TelegramConfig(enabled=False),
            feishu=config.notifications.feishu,
        )
        label = "飞书"

    results = send_plain_message(
        notifications,
        config.settings.proxy_url,
        f"✅ X2TG Web {label} 通知渠道测试成功",
    )
    channels = successful_channels(results)
    if channels:
        repo.add_event("info", "test_message", f"{label} 通知渠道测试成功。", {"channels": channels})
        return RedirectResponse(f"/channels?flash={label} 测试消息已发送", status_code=303)
    repo.add_event(
        "error",
        "test_message",
        f"{label} 通知渠道测试失败。",
        {"results": [r.__dict__ for r in results]},
    )
    return RedirectResponse(f"/channels?error={label} 测试消息发送失败，请查看运维日志", status_code=303)


@app.get("/messages", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    source_id: str = "",
    author: str = "",
    channel: str = "",
    keyword: str = "",
    start: str = "",
    end: str = "",
):
    return render(
        request,
        "messages.html",
        messages=repo.list_sent_messages(
            source_id=source_id,
            author=author,
            channel=channel,
            keyword=keyword,
            start=start,
            end=end,
            limit=200,
        ),
        sources=repo.list_sources(),
        filters={
            "source_id": source_id,
            "author": author,
            "channel": channel,
            "keyword": keyword,
            "start": start,
            "end": end,
        },
    )


@app.get("/ops", response_class=HTMLResponse)
async def ops_page(request: Request, level: str = ""):
    return render(
        request,
        "ops.html",
        sources=repo.list_sources(),
        events=repo.list_events(limit=150, level=level),
        selected_level=level,
    )


@app.post("/ops/pause")
async def pause_monitor(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    monitor.pause()
    return RedirectResponse("/ops?flash=后台监控已暂停", status_code=303)


@app.post("/ops/resume")
async def resume_monitor(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    monitor.resume()
    return RedirectResponse("/ops?flash=后台监控已恢复", status_code=303)


@app.post("/ops/check")
async def check_all(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    await monitor.check_all(manual=True)
    return RedirectResponse("/ops?flash=手动检查完成", status_code=303)


@app.get("/api/status")
async def api_status(request: Request):
    redirect = require_auth(request)
    if redirect:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {
        "monitor": monitor.snapshot().__dict__,
        "counts": repo.counts(),
    }


@app.post("/api/test-proxy")
async def api_test_proxy(request: Request):
    redirect = require_auth(request)
    if redirect:
        return JSONResponse({"ok": False, "message": "未登录"}, status_code=401)

    payload = await request.json()
    proxy_url = str(payload.get("proxy_url", "")).strip()
    notifications = repo.get_notifications()
    token = notifications.telegram.bot_token
    if not token:
        return JSONResponse(
            {
                "ok": False,
                "message": "请先在通知渠道中配置 Telegram Bot Token。",
            },
            status_code=400,
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    started = time.perf_counter()
    try:
        response = requests.get(
            url,
            timeout=12,
            proxies=proxy_dict(proxy_url),
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "status_code": response.status_code,
            "message": f"代理测试完成，延迟 {latency_ms} ms，HTTP {response.status_code}。",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return JSONResponse(
            {
                "ok": False,
                "latency_ms": latency_ms,
                "message": f"代理测试失败，耗时 {latency_ms} ms：{exc}",
            },
            status_code=200,
        )


@app.post("/api/test-ai")
async def api_test_ai(request: Request):
    redirect = require_auth(request)
    if redirect:
        return JSONResponse({"ok": False, "message": "未登录"}, status_code=401)

    payload = await request.json()
    existing = repo.get_settings()
    api_key = str(payload.get("api_key", "")).strip()
    if not api_key or api_key == SECRET_PLACEHOLDER:
        api_key = existing.openai_api_key
    base_url = str(payload.get("base_url", "")).strip()
    model = str(payload.get("model", "")).strip() or DEFAULT_OPENAI_COMPAT_MODEL

    if not api_key:
        return JSONResponse(
            {"ok": False, "message": "请先填写或保存 OpenAI 兼容 API Key。"},
            status_code=400,
        )

    started = time.perf_counter()
    try:
        client = build_openai_client(api_key, base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "message": f"接口测试完成，延迟 {latency_ms} ms，模型返回：{content.strip() or '空内容'}。",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return JSONResponse(
            {
                "ok": False,
                "latency_ms": latency_ms,
                "message": f"接口测试失败，耗时 {latency_ms} ms：{exc}",
            },
            status_code=200,
        )


def main() -> None:
    uvicorn.run("app.web:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)


if __name__ == "__main__":
    main()
