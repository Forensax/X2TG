import json
import tempfile
import unittest
from pathlib import Path

from app.db import Repository
from config import AppSettings


class RepositoryTests(unittest.TestCase):
    def test_legacy_env_and_state_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            state_path = tmp_path / "state.json"
            db_path = tmp_path / "x2tg.db"

            env_path.write_text(
                "\n".join(
                    [
                        "RSS_URL=https://rsshub.app/twitter/user/elonmusk@T,https://rsshub.app/twitter/user/NASA@F",
                        "AI_MODEL=gpt-test",
                        "OPENAI_API_KEY=sk-test",
                        "OPENAI_BASE_URL=https://example.test/v1",
                        "TG_BOT_TOKEN=tg-token",
                        "TG_CHAT_ID=123",
                        "NOTIFY_CHANNELS=telegram",
                        "CHECK_INTERVAL=120",
                        "PROXY_URL=http://127.0.0.1:7890",
                    ]
                ),
                encoding="utf-8",
            )
            state_path.write_text(
                json.dumps({"https://rsshub.app/twitter/user/elonmusk": "https://x.com/status/1"}),
                encoding="utf-8",
            )

            repo = Repository(f"sqlite:///{db_path}")
            repo.initialize()
            repo.migrate_legacy_files(str(env_path), str(state_path))

            settings = repo.get_settings()
            notifications = repo.get_notifications()
            sources = repo.list_sources()

            self.assertEqual(settings.ai_model, "gpt-test")
            self.assertEqual(settings.openai_api_key, "sk-test")
            self.assertEqual(settings.openai_base_url, "https://example.test/v1")
            self.assertEqual(settings.proxy_url, "http://127.0.0.1:7890")
            self.assertEqual(settings.check_interval, 120)
            self.assertTrue(notifications.telegram.enabled)
            self.assertEqual(notifications.telegram.bot_token, "tg-token")
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0].last_link, "https://x.com/status/1")
            self.assertFalse(sources[1].translate_enabled)

    def test_blank_secret_update_preserves_existing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repository(f"sqlite:///{Path(tmp) / 'x2tg.db'}")
            repo.initialize()
            repo.save_settings(AppSettings(openai_api_key="first-key"), keep_blank_secrets=False)

            repo.save_settings(AppSettings(check_interval=60, openai_api_key=""), keep_blank_secrets=True)

            settings = repo.get_settings()
            self.assertEqual(settings.openai_api_key, "first-key")
            self.assertEqual(settings.check_interval, 60)

    def test_sent_message_is_inserted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repository(f"sqlite:///{Path(tmp) / 'x2tg.db'}")
            repo.initialize()
            source_id = repo.save_source("https://example.com/feed", "Example", True, True)
            source = repo.get_source(source_id)

            tweet = {
                "author": "A",
                "content": "hello",
                "link": "https://x.com/status/1",
                "published": "today",
                "images": ["https://example.com/1.jpg"],
            }
            repo.add_sent_message(source, tweet, "你好", ["telegram"])
            repo.add_sent_message(source, tweet, "你好", ["telegram"])

            messages = repo.list_sent_messages()
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["successful_channels"], ["telegram"])
            self.assertEqual(messages[0]["images"], ["https://example.com/1.jpg"])


if __name__ == "__main__":
    unittest.main()

