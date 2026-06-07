import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.db import Repository
from config import RssSource
from notifier import send_plain_message, send_tweet_message, successful_channels
from rss_fetcher import fetch_latest_link, fetch_new_tweets
from translator import translate_tweet


@dataclass
class MonitorSnapshot:
    status: str
    paused: bool
    checking: bool
    last_run_at: str
    next_run_at: str
    last_error: str


class Monitor:
    def __init__(self, repo: Repository):
        self.repo = repo
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self.paused = False
        self.checking = False
        self.last_run_at = ""
        self.next_run_at = ""
        self.last_error = ""
        self._lock = asyncio.Lock()

    @property
    def status(self) -> str:
        if self.checking:
            return "checking"
        if self.last_error:
            return "error"
        if self.paused:
            return "paused"
        return "running"

    def snapshot(self) -> MonitorSnapshot:
        return MonitorSnapshot(
            status=self.status,
            paused=self.paused,
            checking=self.checking,
            last_run_at=self.last_run_at,
            next_run_at=self.next_run_at,
            last_error=self.last_error,
        )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        self.repo.add_event("info", "monitor", "后台监控任务已启动。")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task

    def pause(self) -> None:
        self.paused = True
        self.repo.add_event("info", "monitor", "后台监控已暂停。")

    def resume(self) -> None:
        self.paused = False
        self.last_error = ""
        self.repo.add_event("info", "monitor", "后台监控已恢复。")

    def config_reloaded(self) -> None:
        self.last_error = ""
        self.repo.add_event("info", "monitor", "运行配置已重载。")

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                config = self.repo.get_runtime_config()
                interval = max(config.settings.check_interval, 10)
                self.next_run_at = (datetime.now() + timedelta(seconds=interval)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    pass
                if not self.paused:
                    await self.check_all(manual=False)
            except Exception as exc:
                self.last_error = str(exc)
                self.repo.add_event("error", "monitor", f"后台监控循环异常: {exc}")
                await asyncio.sleep(5)

    async def check_all(self, manual: bool = True) -> None:
        async with self._lock:
            self.checking = True
            self.last_error = ""
            self.repo.add_event(
                "info",
                "manual_check" if manual else "scheduled_check",
                "开始手动检查所有启用 RSS 源。" if manual else "开始定时检查所有启用 RSS 源。",
            )
            try:
                sources = self.repo.list_sources(enabled_only=True)
                if not sources:
                    self.repo.add_event("info", "check", "没有启用的 RSS 源。")
                    return
                for source in sources:
                    await self.check_source(source.id, manual=manual, within_lock=True)
                self.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:
                self.last_error = str(exc)
                self.repo.add_event("error", "check", f"检查任务异常: {exc}")
            finally:
                self.checking = False

    async def check_source(
        self,
        source_id: Optional[int],
        manual: bool = True,
        within_lock: bool = False,
    ) -> None:
        if within_lock:
            await self._check_source_inner(source_id, manual)
            return
        async with self._lock:
            self.checking = True
            try:
                await self._check_source_inner(source_id, manual)
                self.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            finally:
                self.checking = False

    async def _check_source_inner(self, source_id: Optional[int], manual: bool) -> None:
        if source_id is None:
            return
        source = self.repo.get_source(source_id)
        if not source:
            self.repo.add_event("error", "check", f"RSS 源不存在: {source_id}")
            return
        config = self.repo.get_runtime_config()
        settings = config.settings
        notifications = config.notifications

        try:
            if not source.last_link:
                latest = await asyncio.to_thread(fetch_latest_link, source.url, settings.proxy_url)
                if latest:
                    self.repo.update_source_last_link(source.id, latest)
                    self.repo.add_event(
                        "info",
                        "source_init",
                        f"RSS 源首次检查已标记最新链接为已读: {source.url}",
                        {"link": latest},
                    )
                else:
                    self.repo.add_event("warning", "source_init", f"RSS 源首次检查未获取到内容: {source.url}")
                return

            tweets = await asyncio.to_thread(
                fetch_new_tweets,
                source.url,
                source.last_link,
                settings.proxy_url,
                False,
            )
            if not tweets:
                self.repo.add_event("info", "check", f"没有新内容: {source.url}")
                return
            self.repo.add_event(
                "info",
                "check",
                f"发现 {len(tweets)} 条新内容: {source.url}",
            )
            for tweet in tweets:
                await self._process_tweet(source, tweet, settings, notifications)
                await asyncio.sleep(2)
        except Exception as exc:
            self.last_error = str(exc)
            self.repo.add_event("error", "rss", f"RSS 源处理失败: {source.url}", {"error": str(exc)})

    async def send_latest_source(self, source_id: int) -> bool:
        async with self._lock:
            self.checking = True
            try:
                source = self.repo.get_source(source_id)
                if not source:
                    self.repo.add_event("error", "send_latest", f"RSS 源不存在: {source_id}")
                    return False

                config = self.repo.get_runtime_config()
                tweets = await asyncio.to_thread(
                    fetch_new_tweets,
                    source.url,
                    "",
                    config.settings.proxy_url,
                    True,
                )
                if not tweets:
                    self.repo.add_event("warning", "send_latest", f"未获取到最新推文: {source.url}")
                    return False

                tweet = tweets[-1]
                sent = await self._process_tweet(
                    source,
                    tweet,
                    config.settings,
                    config.notifications,
                    event_type="send_latest",
                )
                self.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return sent
            except Exception as exc:
                self.last_error = str(exc)
                self.repo.add_event(
                    "error",
                    "send_latest",
                    f"发送最新推文失败: {exc}",
                    {"source_id": source_id},
                )
                return False
            finally:
                self.checking = False

    async def _process_tweet(
        self,
        source: RssSource,
        tweet: dict,
        settings,
        notifications,
        event_type: str = "send",
    ) -> bool:
        translated_text = ""
        if source.translate_enabled:
            result = await asyncio.to_thread(translate_tweet, tweet.get("content", ""), settings)
            translated_text = result.text
            if not result.success:
                self.repo.add_event(
                    "error",
                    "translation",
                    f"翻译失败但将继续发送: {tweet.get('link', '')}",
                    {"error": result.error},
                )

        results = await asyncio.to_thread(
            send_tweet_message,
            notifications,
            settings.proxy_url,
            tweet.get("author", ""),
            tweet.get("content", ""),
            translated_text,
            tweet.get("link", ""),
            tweet.get("images", []),
        )
        channels = successful_channels(results)
        if channels:
            self.repo.add_sent_message(source, tweet, translated_text, channels)
            self.repo.update_source_last_link(source.id, tweet.get("link", ""))
            self.repo.add_event(
                "info",
                event_type,
                f"消息发送成功: {tweet.get('link', '')}",
                {"channels": channels},
            )
            return True
        else:
            self.repo.add_event(
                "error",
                event_type,
                f"所有通知渠道发送失败，不推进 RSS 进度: {tweet.get('link', '')}",
                {"results": [result.__dict__ for result in results]},
            )
            return False

    async def send_startup_message(self) -> None:
        config = self.repo.get_runtime_config()
        lines = [
            "🤖 X2TG Web 服务已启动",
            f"⏱️ 检查间隔: {config.settings.check_interval} 秒",
            f"🧠 翻译模型: {config.settings.ai_provider.upper()} / {config.settings.ai_model}",
            f"📢 通知渠道: {', '.join(config.notifications.enabled_channels) or '无'}",
            f"📋 启用 RSS 源: {len([s for s in config.sources if s.enabled])}",
        ]
        results = await asyncio.to_thread(
            send_plain_message,
            config.notifications,
            config.settings.proxy_url,
            "\n".join(lines),
        )
        channels = successful_channels(results)
        if channels:
            self.repo.add_event("info", "startup", "启动通知已发送。", {"channels": channels})
        else:
            self.repo.add_event(
                "warning",
                "startup",
                "启动通知未发送成功。",
                {"results": [result.__dict__ for result in results]},
            )

