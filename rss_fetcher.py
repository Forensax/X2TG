import feedparser
import os
import json
import html2text
import requests
from config import RSS_URL, PROXY_URL

STATE_FILE = "state.json"

def get_proxy_dict():
    if PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return None

def load_last_link():
    """读取上次处理的最后一条推文链接"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_link")
        except Exception as e:
            print(f"读取状态文件出错: {e}")
    return None

def save_last_link(link):
    """保存最新处理的推文链接"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_link": link}, f)
        print(f"已更新处理进度，最后一条: {link}")
    except Exception as e:
        print(f"保存状态文件出错: {e}")

def fetch_new_tweets():
    """获取自上次检查以来的新推文"""
    if not RSS_URL:
        print("错误: RSS_URL 未配置")
        return []

    print(f"正在检查 RSS: {RSS_URL} ...")
    
    feed = None
    try:
        proxies = get_proxy_dict()
        response = requests.get(RSS_URL, proxies=proxies, timeout=20)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"请求 RSS 失败: {e}")
        try:
            print("尝试直接使用 feedparser...")
            feed = feedparser.parse(RSS_URL)
        except Exception:
            return []

    if not feed or not feed.entries:
        print("未获取到任何推文，请检查 RSSHub URL 是否有效。")
        return []

    last_link = load_last_link()
    new_tweets = []

    # 首次运行
    if last_link is None:
        print("首次运行，标记最新一条推文为已读，不进行推送。")
        if feed.entries:
            first_link = feed.entries[0].get('link', '')
            if first_link:
                save_last_link(first_link)
        return []

    # 遍历 RSS 条目
    for entry in feed.entries:
        current_link = entry.get('link', '')
        
        if current_link == last_link:
            break
        
        if not current_link:
            continue

        # 强制转换为字符串并清理
        description = str(entry.get('description', ''))
        h = html2text.HTML2Text()
        h.ignore_links = False 
        h.body_width = 0
        clean_content = h.handle(description).strip()
        
        # 安全获取作者，使用字典访问方式
        feed_data = feed.get('feed', {})
        feed_title = feed_data.get('title', 'Unknown') if isinstance(feed_data, dict) else 'Unknown'
        author = entry.get('author', feed_title)

        tweet_data = {
            "link": current_link,
            "author": author,
            "content": clean_content,
            "published": entry.get('published', '')
        }
        new_tweets.append(tweet_data)

    # 返回按时间正序排列的推文（旧 -> 新）
    # 注意：这里不再自动保存状态，由 main.py 决定何时保存
    return list(reversed(new_tweets))
