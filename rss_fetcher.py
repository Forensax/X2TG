import ipaddress
import json
import os
from urllib.parse import urlparse

import feedparser
import html2text
import requests
from bs4 import BeautifulSoup


def get_proxy_dict(proxy_url: str = ""):
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def is_private_url(url: str) -> bool:
    """检查 URL 是否指向本机或内网地址。"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() == "localhost":
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private
        except ValueError:
            return False
    except Exception:
        return False


def fetch_new_tweets(
    rss_url: str,
    last_link: str = "",
    proxy_url: str = "",
    only_latest: bool = False,
) -> list[dict]:
    """获取指定 RSS URL 自 last_link 以来的新推文。"""
    if not rss_url:
        print("错误: 传入的 RSS URL 为空")
        return []

    print(f"正在检查 RSS: {rss_url} ...")
    feed = None
    try:
        proxies = get_proxy_dict(proxy_url)
        if is_private_url(rss_url):
            proxies = None
        response = requests.get(rss_url, proxies=proxies, timeout=20)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"请求 RSS 失败: {e}")
        try:
            print("尝试直接使用 feedparser...")
            feed = feedparser.parse(rss_url)
        except Exception:
            return []

    if not feed or not feed.entries:
        print(f"未获取到任何推文: {rss_url}")
        return []

    if only_latest:
        entries_to_process = [feed.entries[0]]
    else:
        entries_to_process = []
        for entry in feed.entries:
            current_link = entry.get("link", "")
            if current_link == last_link:
                break
            if current_link:
                entries_to_process.append(entry)

    tweets = []
    for entry in entries_to_process:
        current_link = entry.get("link", "")
        description = str(entry.get("description", ""))
        images = extract_images(description)
        clean_content = clean_description(description)
        feed_data = feed.get("feed", {})
        feed_title = feed_data.get("title", "Unknown") if isinstance(feed_data, dict) else "Unknown"
        author = entry.get("author", feed_title)
        tweets.append(
            {
                "link": current_link,
                "author": author,
                "content": clean_content,
                "published": entry.get("published", ""),
                "images": images,
            }
        )

    return list(reversed(tweets))


def fetch_latest_link(rss_url: str, proxy_url: str = "") -> str:
    tweets = fetch_new_tweets(rss_url, proxy_url=proxy_url, only_latest=True)
    return tweets[0]["link"] if tweets else ""


def extract_images(description: str) -> list[str]:
    images = []
    try:
        soup = BeautifulSoup(description, "html.parser")
        for img in soup.find_all("img"):
            if hasattr(img, "get"):
                src = img.get("src")
                if src:
                    images.append(src)
    except Exception as e:
        print(f"解析图片出错: {e}")
    return images


def clean_description(description: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    h.ignore_images = True
    return h.handle(description).strip()


# 旧脚本兼容 helpers。Web 版本不再依赖它们。
STATE_FILE = os.getenv("STATE_FILE", "state.json")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"读取状态文件出错: {e}")
    return {}


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存状态文件出错: {e}")


def load_last_link(rss_url: str) -> str:
    return load_state().get(rss_url, "")


def save_last_link(rss_url: str, link: str) -> None:
    state = load_state()
    state[rss_url] = link
    save_state(state)

