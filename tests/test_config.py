import unittest

from config import parse_rss_configs


class ConfigTests(unittest.TestCase):
    def test_parse_rss_configs_flags_and_defaults(self):
        configs = parse_rss_configs(
            "https://rsshub.app/twitter/user/elonmusk@T,"
            "https://rsshub.app/twitter/user/NASA@F,"
            "https://example.com/feed"
        )

        self.assertEqual(
            configs,
            [
                {"url": "https://rsshub.app/twitter/user/elonmusk", "translate_enabled": True},
                {"url": "https://rsshub.app/twitter/user/NASA", "translate_enabled": False},
                {"url": "https://example.com/feed", "translate_enabled": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()

