import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from config import (
    DEFAULT_FEISHU_API_BASE,
    AppSettings,
    FeishuConfig,
    NotificationConfig,
    RssSource,
    TelegramConfig,
    get_database_path,
    load_legacy_env,
    notifications_from_legacy_env,
    parse_bool,
    parse_csv,
    parse_rss_configs,
    settings_from_legacy_env,
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Repository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.path = Path(get_database_path(database_url))
        if self.path.parent and str(self.path.parent) not in {"", "."}:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            self._create_schema(conn)
            self._ensure_defaults(conn)

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                check_interval INTEGER NOT NULL DEFAULT 1800,
                proxy_url TEXT NOT NULL DEFAULT '',
                ai_provider TEXT NOT NULL DEFAULT 'gemini',
                ai_model TEXT NOT NULL DEFAULT 'gemini-3-flash-preview',
                gemini_api_key TEXT NOT NULL DEFAULT '',
                gemini_base_url TEXT NOT NULL DEFAULT '',
                openai_api_key TEXT NOT NULL DEFAULT '',
                openai_base_url TEXT NOT NULL DEFAULT '',
                legacy_env_imported INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rss_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL DEFAULT '',
                translate_enabled INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_link TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_channels (
                name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                source_url TEXT NOT NULL,
                author TEXT NOT NULL,
                original_text TEXT NOT NULL,
                translated_text TEXT NOT NULL DEFAULT '',
                link TEXT NOT NULL UNIQUE,
                images_json TEXT NOT NULL DEFAULT '[]',
                published_at TEXT NOT NULL DEFAULT '',
                sent_at TEXT NOT NULL,
                successful_channels TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY (source_id) REFERENCES rss_sources(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sent_messages_sent_at ON sent_messages(sent_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sent_messages_source_id ON sent_messages(source_id);
            CREATE INDEX IF NOT EXISTS idx_sent_messages_author ON sent_messages(author);

            CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL DEFAULT 'info',
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_run_events_created_at ON run_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_run_events_level ON run_events(level);

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def _ensure_defaults(self, conn: sqlite3.Connection) -> None:
        now = utc_now()
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (
                id, check_interval, proxy_url, ai_provider, ai_model,
                gemini_api_key, gemini_base_url, openai_api_key, openai_base_url,
                updated_at
            ) VALUES (1, 1800, '', 'gemini', 'gemini-3-flash-preview', '', '', '', '', ?)
            """,
            (now,),
        )
        for name, config in (
            ("telegram", {"bot_token": "", "chat_id": ""}),
            (
                "feishu",
                {
                    "app_id": "",
                    "app_secret": "",
                    "receive_id_type": "chat_id",
                    "receive_ids": [],
                    "api_base": DEFAULT_FEISHU_API_BASE,
                },
            ),
        ):
            conn.execute(
                """
                INSERT OR IGNORE INTO notification_channels (name, enabled, config_json, updated_at)
                VALUES (?, 0, ?, ?)
                """,
                (name, json.dumps(config, ensure_ascii=False), now),
            )

    def migrate_legacy_files(self, env_path: str = ".env", state_path: str = "state.json") -> None:
        values = load_legacy_env(env_path)
        state = self._load_state_file(state_path)
        if not values and not state:
            return

        with self.connect() as conn:
            settings = conn.execute("SELECT legacy_env_imported FROM settings WHERE id = 1").fetchone()
            already_imported = bool(settings and settings["legacy_env_imported"])

            if values and not already_imported:
                self._import_env(conn, values)
                conn.execute(
                    "UPDATE settings SET legacy_env_imported = 1, updated_at = ? WHERE id = 1",
                    (utc_now(),),
                )
                self._add_event_conn(
                    conn,
                    "info",
                    "migration",
                    "已从 .env 导入初始配置，原文件已保留。",
                    {"env_path": env_path},
                )

            if state:
                imported = self._import_state(conn, state)
                if imported:
                    self._add_event_conn(
                        conn,
                        "info",
                        "migration",
                        "已从 state.json 合并 RSS 进度，原文件已保留。",
                        {"state_path": state_path, "count": imported},
                    )

    def _load_state_file(self, state_path: str) -> dict:
        if not os.path.exists(state_path):
            return {}
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _import_env(self, conn: sqlite3.Connection, values: dict) -> None:
        settings = settings_from_legacy_env(values)
        self._update_settings_conn(conn, settings)
        notifications = notifications_from_legacy_env(values)
        self._save_notifications_conn(conn, notifications)
        for source in parse_rss_configs(values.get("RSS_URL", "")):
            self._upsert_source_conn(
                conn,
                url=source["url"],
                display_name="",
                translate_enabled=source["translate_enabled"],
                enabled=True,
                preserve_last_link=True,
            )

    def _import_state(self, conn: sqlite3.Connection, state: dict) -> int:
        count = 0
        for url, last_link in state.items():
            if not url or not last_link:
                continue
            row = conn.execute("SELECT id FROM rss_sources WHERE url = ?", (url,)).fetchone()
            if not row:
                self._upsert_source_conn(
                    conn,
                    url=url,
                    display_name="",
                    translate_enabled=True,
                    enabled=True,
                    preserve_last_link=True,
                )
            conn.execute(
                "UPDATE rss_sources SET last_link = ?, updated_at = ? WHERE url = ?",
                (str(last_link), utc_now(), url),
            )
            count += 1
        return count

    def get_settings(self) -> AppSettings:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
            return self._settings_from_row(row)

    def save_settings(self, settings: AppSettings, keep_blank_secrets: bool = True) -> None:
        with self.connect() as conn:
            if keep_blank_secrets:
                existing = self._settings_from_row(
                    conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
                )
                if not settings.gemini_api_key:
                    settings.gemini_api_key = existing.gemini_api_key
                if not settings.openai_api_key:
                    settings.openai_api_key = existing.openai_api_key
            self._update_settings_conn(conn, settings)
            self._add_event_conn(conn, "info", "settings", "系统设置已保存。")

    def _update_settings_conn(self, conn: sqlite3.Connection, settings: AppSettings) -> None:
        ai_provider = settings.ai_provider if settings.ai_provider in {"gemini", "openai"} else "gemini"
        check_interval = max(int(settings.check_interval or 1800), 10)
        model = settings.ai_model.strip() or (
            "gpt-5.5" if ai_provider == "openai" else "gemini-3-flash-preview"
        )
        conn.execute(
            """
            UPDATE settings SET
                check_interval = ?,
                proxy_url = ?,
                ai_provider = ?,
                ai_model = ?,
                gemini_api_key = ?,
                gemini_base_url = ?,
                openai_api_key = ?,
                openai_base_url = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                check_interval,
                settings.proxy_url.strip(),
                ai_provider,
                model,
                settings.gemini_api_key.strip(),
                settings.gemini_base_url.strip(),
                settings.openai_api_key.strip(),
                settings.openai_base_url.strip(),
                utc_now(),
            ),
        )

    def _settings_from_row(self, row: sqlite3.Row) -> AppSettings:
        return AppSettings(
            check_interval=int(row["check_interval"]),
            proxy_url=row["proxy_url"] or "",
            ai_provider=row["ai_provider"] or "gemini",
            ai_model=row["ai_model"] or "gemini-3-flash-preview",
            gemini_api_key=row["gemini_api_key"] or "",
            gemini_base_url=row["gemini_base_url"] or "",
            openai_api_key=row["openai_api_key"] or "",
            openai_base_url=row["openai_base_url"] or "",
        )

    def get_notifications(self) -> NotificationConfig:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM notification_channels").fetchall()
            data = {row["name"]: row for row in rows}
        telegram_config = json.loads(data["telegram"]["config_json"]) if "telegram" in data else {}
        feishu_config = json.loads(data["feishu"]["config_json"]) if "feishu" in data else {}
        telegram_row = data.get("telegram")
        feishu_row = data.get("feishu")
        return NotificationConfig(
            telegram=TelegramConfig(
                enabled=parse_bool(telegram_row["enabled"] if telegram_row else False),
                bot_token=telegram_config.get("bot_token", ""),
                chat_id=telegram_config.get("chat_id", ""),
            ),
            feishu=FeishuConfig(
                enabled=parse_bool(feishu_row["enabled"] if feishu_row else False),
                app_id=feishu_config.get("app_id", ""),
                app_secret=feishu_config.get("app_secret", ""),
                receive_id_type=feishu_config.get("receive_id_type", "chat_id"),
                receive_ids=parse_csv(feishu_config.get("receive_ids", ""))
                if isinstance(feishu_config.get("receive_ids"), str)
                else list(feishu_config.get("receive_ids", [])),
                api_base=feishu_config.get("api_base", DEFAULT_FEISHU_API_BASE),
            ),
        )

    def save_notifications(self, notifications: NotificationConfig, keep_blank_secrets: bool = True) -> None:
        with self.connect() as conn:
            if keep_blank_secrets:
                existing = self.get_notifications()
                if not notifications.telegram.bot_token:
                    notifications.telegram.bot_token = existing.telegram.bot_token
                if not notifications.feishu.app_secret:
                    notifications.feishu.app_secret = existing.feishu.app_secret
            self._save_notifications_conn(conn, notifications)
            self._add_event_conn(conn, "info", "settings", "通知渠道设置已保存。")

    def _save_notifications_conn(
        self, conn: sqlite3.Connection, notifications: NotificationConfig
    ) -> None:
        now = utc_now()
        conn.execute(
            """
            INSERT INTO notification_channels (name, enabled, config_json, updated_at)
            VALUES ('telegram', ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                enabled = excluded.enabled,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (
                1 if notifications.telegram.enabled else 0,
                json.dumps(
                    {
                        "bot_token": notifications.telegram.bot_token,
                        "chat_id": notifications.telegram.chat_id,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO notification_channels (name, enabled, config_json, updated_at)
            VALUES ('feishu', ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                enabled = excluded.enabled,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (
                1 if notifications.feishu.enabled else 0,
                json.dumps(
                    {
                        "app_id": notifications.feishu.app_id,
                        "app_secret": notifications.feishu.app_secret,
                        "receive_id_type": notifications.feishu.receive_id_type,
                        "receive_ids": notifications.feishu.receive_ids,
                        "api_base": notifications.feishu.api_base,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )

    def get_runtime_config(self) -> Any:
        from config import RuntimeConfig

        return RuntimeConfig(
            settings=self.get_settings(),
            notifications=self.get_notifications(),
            sources=self.list_sources(enabled_only=False),
        )

    def list_sources(self, enabled_only: bool = False) -> list[RssSource]:
        sql = "SELECT * FROM rss_sources"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY id ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._source_from_row(row) for row in rows]

    def get_source(self, source_id: int) -> Optional[RssSource]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rss_sources WHERE id = ?", (source_id,)).fetchone()
            return self._source_from_row(row) if row else None

    def get_source_by_url(self, url: str) -> Optional[RssSource]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rss_sources WHERE url = ?", (url,)).fetchone()
            return self._source_from_row(row) if row else None

    def save_source(
        self,
        url: str,
        display_name: str,
        translate_enabled: bool,
        enabled: bool,
        source_id: Optional[int] = None,
    ) -> int:
        with self.connect() as conn:
            if source_id:
                conn.execute(
                    """
                    UPDATE rss_sources SET
                        url = ?,
                        display_name = ?,
                        translate_enabled = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        url.strip(),
                        display_name.strip(),
                        1 if translate_enabled else 0,
                        1 if enabled else 0,
                        utc_now(),
                        source_id,
                    ),
                )
                saved_id = source_id
                self._add_event_conn(conn, "info", "source", f"RSS 源已更新: {url}")
            else:
                saved_id = self._upsert_source_conn(
                    conn,
                    url=url,
                    display_name=display_name,
                    translate_enabled=translate_enabled,
                    enabled=enabled,
                    preserve_last_link=True,
                )
                self._add_event_conn(conn, "info", "source", f"RSS 源已添加: {url}")
            return saved_id

    def _upsert_source_conn(
        self,
        conn: sqlite3.Connection,
        url: str,
        display_name: str,
        translate_enabled: bool,
        enabled: bool,
        preserve_last_link: bool,
    ) -> int:
        now = utc_now()
        existing = conn.execute("SELECT id FROM rss_sources WHERE url = ?", (url.strip(),)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE rss_sources SET
                    display_name = CASE WHEN ? != '' THEN ? ELSE display_name END,
                    translate_enabled = ?,
                    enabled = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    display_name.strip(),
                    display_name.strip(),
                    1 if translate_enabled else 0,
                    1 if enabled else 0,
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO rss_sources (
                url, display_name, translate_enabled, enabled, last_link, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '', ?, ?)
            """,
            (
                url.strip(),
                display_name.strip(),
                1 if translate_enabled else 0,
                1 if enabled else 0,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)

    def delete_source(self, source_id: int) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT url FROM rss_sources WHERE id = ?", (source_id,)).fetchone()
            conn.execute("DELETE FROM rss_sources WHERE id = ?", (source_id,))
            if row:
                self._add_event_conn(conn, "info", "source", f"RSS 源已删除: {row['url']}")

    def update_source_last_link(self, source_id: int, link: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rss_sources SET last_link = ?, updated_at = ? WHERE id = ?",
                (link, utc_now(), source_id),
            )

    def _source_from_row(self, row: sqlite3.Row) -> RssSource:
        return RssSource(
            id=int(row["id"]),
            url=row["url"],
            display_name=row["display_name"] or "",
            translate_enabled=bool(row["translate_enabled"]),
            enabled=bool(row["enabled"]),
            last_link=row["last_link"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_sent_message(
        self,
        source: RssSource,
        tweet: dict,
        translated_text: str,
        successful_channels: Iterable[str],
    ) -> None:
        channels = list(successful_channels)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sent_messages (
                    source_id, source_url, author, original_text, translated_text,
                    link, images_json, published_at, sent_at, successful_channels
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.url,
                    tweet.get("author", ""),
                    tweet.get("content", ""),
                    translated_text or "",
                    tweet.get("link", ""),
                    json.dumps(tweet.get("images", []), ensure_ascii=False),
                    tweet.get("published", ""),
                    utc_now(),
                    json.dumps(channels, ensure_ascii=False),
                ),
            )

    def list_sent_messages(
        self,
        source_id: str = "",
        author: str = "",
        channel: str = "",
        keyword: str = "",
        start: str = "",
        end: str = "",
        limit: int = 100,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if source_id:
            clauses.append("source_id = ?")
            params.append(int(source_id))
        if author:
            clauses.append("author LIKE ?")
            params.append(f"%{author}%")
        if channel:
            clauses.append("successful_channels LIKE ?")
            params.append(f"%{channel}%")
        if keyword:
            clauses.append("(original_text LIKE ? OR translated_text LIKE ? OR link LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if start:
            clauses.append("sent_at >= ?")
            params.append(start)
        if end:
            clauses.append("sent_at <= ?")
            params.append(end)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT sent_messages.*, rss_sources.display_name
                FROM sent_messages
                LEFT JOIN rss_sources ON sent_messages.source_id = rss_sources.id
                {where}
                ORDER BY sent_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._message_dict(row) for row in rows]

    def recent_sent_messages(self, limit: int = 5) -> list[dict]:
        return self.list_sent_messages(limit=limit)

    def _message_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "source_id": row["source_id"],
            "source_url": row["source_url"],
            "source_name": row["display_name"] or row["source_url"],
            "author": row["author"],
            "original_text": row["original_text"],
            "translated_text": row["translated_text"],
            "link": row["link"],
            "images": json.loads(row["images_json"] or "[]"),
            "published_at": row["published_at"],
            "sent_at": row["sent_at"],
            "successful_channels": json.loads(row["successful_channels"] or "[]"),
        }

    def add_event(
        self,
        level: str,
        event_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        with self.connect() as conn:
            self._add_event_conn(conn, level, event_type, message, details)

    def _add_event_conn(
        self,
        conn: sqlite3.Connection,
        level: str,
        event_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO run_events (level, event_type, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                level,
                event_type,
                message,
                json.dumps(details or {}, ensure_ascii=False),
                utc_now(),
            ),
        )

    def list_events(self, limit: int = 100, level: str = "") -> list[dict]:
        clauses = []
        params: list[Any] = []
        if level:
            clauses.append("level = ?")
            params.append(level)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM run_events {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "level": row["level"],
                    "event_type": row["event_type"],
                    "message": row["message"],
                    "details": json.loads(row["details_json"] or "{}"),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def recent_errors(self, limit: int = 5) -> list[dict]:
        return self.list_events(limit=limit, level="error")

    def has_admin(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM admin_users WHERE id = 1").fetchone()
            return bool(row)

    def create_or_update_admin(self, username: str, password_hash: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_users (id, username, password_hash, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username = excluded.username,
                    password_hash = excluded.password_hash,
                    updated_at = excluded.updated_at
                """,
                (username, password_hash, now, now),
            )
            self._add_event_conn(conn, "info", "auth", "管理员账号已初始化或更新。")

    def get_admin(self) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM admin_users WHERE id = 1").fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "username": row["username"],
                "password_hash": row["password_hash"],
            }

    def counts(self) -> dict:
        with self.connect() as conn:
            return {
                "sources": conn.execute("SELECT COUNT(*) FROM rss_sources").fetchone()[0],
                "enabled_sources": conn.execute(
                    "SELECT COUNT(*) FROM rss_sources WHERE enabled = 1"
                ).fetchone()[0],
                "sent_messages": conn.execute("SELECT COUNT(*) FROM sent_messages").fetchone()[0],
                "errors": conn.execute("SELECT COUNT(*) FROM run_events WHERE level = 'error'").fetchone()[0],
            }
