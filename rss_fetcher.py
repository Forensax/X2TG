import feedparser
import os
import json
import html2text
import requests
from config import PROXY_URL

STATE_FILE = "state.json"

def get_proxy_dict():
    if PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return None

def load_state():
    """加载整个状态字典"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 简单的格式校验，确保是字典
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"读取状态文件出错: {e}")
    return {}

def save_state(state):
    """保存整个状态字典"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存状态文件出错: {e}")

def load_last_link(rss_url):
    """读取指定 RSS URL 的最后一条推文链接"""
    state = load_state()
    return state.get(rss_url)

def save_last_link(rss_url, link):
    """保存指定 RSS URL 的最新处理推文链接"""
    state = load_state()
    state[rss_url] = link
    save_state(state)
    print(f"[{rss_url[:30]}...] 进度已更新")

def fetch_new_tweets(rss_url):
    """获取指定 RSS URL 自上次检查以来的新推文"""
    if not rss_url:
        print("错误: 传入的 RSS URL 为空")
        return []

    print(f"正在检查 RSS: {rss_url} ...")
    
    feed = None
    try:
        proxies = get_proxy_dict()
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

    last_link = load_last_link(rss_url)
    new_tweets = []

    # 首次运行针对该 URL
    if last_link is None:
        print(f"[{rss_url}] 首次运行，标记最新一条推文为已读，不进行推送。")
        if feed.entries:
            first_link = feed.entries[0].get('link', '')
            if first_link:
                save_last_link(rss_url, first_link)
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
        
        # 安全获取作者
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

    return list(reversed(new_tweets))
