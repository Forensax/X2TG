import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import dotenv_values, load_dotenv
except ImportError:  # pragma: no cover - exercised only in minimal runtimes
    dotenv_values = None

    def load_dotenv(*args, **kwargs):
        return False


load_dotenv()

DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/x2tg.db")
DEFAULT_FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
DEFAULT_OPENAI_COMPAT_MODEL = "gpt-4o-mini"
SECRET_PLACEHOLDER = "********"


def parse_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def parse_rss_configs(raw_value: Optional[str]) -> list[dict]:
    configs = []
    for item in parse_csv(raw_value):
        parts = item.rsplit("@", 1)
        url = parts[0].strip()
        translate_enabled = True
        if len(parts) > 1 and parts[1].strip().upper() == "F":
            translate_enabled = False
        if url:
            configs.append({"url": url, "translate_enabled": translate_enabled})
    return configs


@dataclass
class AppSettings:
    check_interval: int = 1800
    proxy_url: str = ""
    ai_model: str = DEFAULT_OPENAI_COMPAT_MODEL
    openai_api_key: str = ""
    openai_base_url: str = ""

    @property
    def active_api_key(self) -> str:
        return self.openai_api_key

    @property
    def active_base_url(self) -> str:
        return self.openai_base_url


@dataclass
class RssSource:
    id: Optional[int] = None
    url: str = ""
    display_name: str = ""
    translate_enabled: bool = True
    enabled: bool = True
    last_link: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class FeishuConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    receive_id_type: str = "chat_id"
    receive_ids: list[str] = field(default_factory=list)
    api_base: str = DEFAULT_FEISHU_API_BASE


@dataclass
class NotificationConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)

    @property
    def enabled_channels(self) -> list[str]:
        channels = []
        if self.telegram.enabled and self.telegram.bot_token and self.telegram.chat_id:
            channels.append("telegram")
        if (
            self.feishu.enabled
            and self.feishu.app_id
            and self.feishu.app_secret
            and self.feishu.receive_ids
        ):
            channels.append("feishu")
        return channels


@dataclass
class RuntimeConfig:
    settings: AppSettings = field(default_factory=AppSettings)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    sources: list[RssSource] = field(default_factory=list)


def get_database_path(database_url: str = DEFAULT_DATABASE_URL) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "", 1)
    return database_url


def load_legacy_env(env_path: str = ".env") -> dict:
    values = {}
    if os.path.exists(env_path):
        if dotenv_values:
            values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
        else:
            values.update(_read_env_file(env_path))
    for key in (
        "RSS_URL",
        "AI_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "TG_BOT_TOKEN",
        "TG_CHAT_ID",
        "NOTIFY_CHANNELS",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_RECEIVE_ID_TYPE",
        "FEISHU_RECEIVE_IDS",
        "FEISHU_API_BASE",
        "CHECK_INTERVAL",
        "PROXY_URL",
    ):
        if key not in values and os.getenv(key):
            values[key] = os.getenv(key, "")
    return values


def _read_env_file(env_path: str) -> dict:
    values = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            values[key.strip()] = value
    return values


def settings_from_legacy_env(values: dict) -> AppSettings:
    try:
        interval = int(values.get("CHECK_INTERVAL") or 1800)
    except ValueError:
        interval = 1800
    return AppSettings(
        check_interval=max(interval, 10),
        proxy_url=values.get("PROXY_URL", ""),
        ai_model=values.get("AI_MODEL", DEFAULT_OPENAI_COMPAT_MODEL),
        openai_api_key=values.get("OPENAI_API_KEY", ""),
        openai_base_url=values.get("OPENAI_BASE_URL", ""),
    )


def notifications_from_legacy_env(values: dict) -> NotificationConfig:
    requested = {channel.lower() for channel in parse_csv(values.get("NOTIFY_CHANNELS", ""))}
    if not requested:
        requested = {"telegram", "feishu"}
    telegram = TelegramConfig(
        enabled="telegram" in requested,
        bot_token=values.get("TG_BOT_TOKEN", ""),
        chat_id=values.get("TG_CHAT_ID", ""),
    )
    feishu = FeishuConfig(
        enabled="feishu" in requested,
        app_id=values.get("FEISHU_APP_ID", ""),
        app_secret=values.get("FEISHU_APP_SECRET", ""),
        receive_id_type=values.get("FEISHU_RECEIVE_ID_TYPE", "chat_id"),
        receive_ids=parse_csv(values.get("FEISHU_RECEIVE_IDS", "")),
        api_base=values.get("FEISHU_API_BASE", DEFAULT_FEISHU_API_BASE),
    )
    return NotificationConfig(telegram=telegram, feishu=feishu)
