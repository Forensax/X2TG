import feedparser
import os
import json
import html2text
import requests
from urllib.parse import urlparse
import ipaddress
from bs4 import BeautifulSoup
from config import PROXY_URL

STATE_FILE = "state.json"


def get_proxy_dict():
    if PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return None

def is_private_url(url):
    """检查 URL 是否指向私有 IP 地址 (内网)"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # 常见本地标识
        if hostname.lower() == 'localhost':
            return True
            
        # 尝试判断是否为 IP 地址
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private
        except ValueError:
            # 不是 IP 地址 (可能是域名)，暂不视为私有地址
            return False
    except Exception:
        return False

def load_state():
    """加载整个状态字典"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
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

def fetch_new_tweets(rss_url, only_latest=False):
    """获取指定 RSS URL 自上次检查以来的新推文
    only_latest=True: 仅获取最新的一条推文（用于启动检查）
    """
    if not rss_url:

        print("错误: 传入的 RSS URL 为空")
        return []

    print(f"正在检查 RSS: {rss_url} ...")
    
    feed = None
    try:
        proxies = get_proxy_dict()
        
        # 如果是内网地址，强制不使用代理
        if is_private_url(rss_url):
            # print(f"检测到内网地址 {rss_url}，跳过代理配置")
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
        print(f"[{rss_url}] 启动检查，仅获取最新一条推文。")
        entries_to_process = [feed.entries[0]]
    else:
        last_link = load_last_link(rss_url)
        entries_to_process = []
        
        # 遍历所有推文，直到找到上次处理的链接
        # 如果 last_link 为 None (首次运行/新Feed)，则会处理 Feed 中的所有条目
        # 这对于追溯历史或初始化状态是合理的
        for entry in feed.entries:
            current_link = entry.get('link', '')
            if current_link == last_link:
                break
            if not current_link:
                continue
            entries_to_process.append(entry)

    new_tweets = []

    
    # 遍历需要处理的条目
    for entry in entries_to_process:
        current_link = entry.get('link', '')
        
        # 强制转换为字符串
        description = str(entry.get('description', ''))
        
        # 1. 提取图片
        images = []
        try:
            soup = BeautifulSoup(description, 'html.parser')
            for img in soup.find_all('img'):
                # 确保 img 是 Tag 对象
                if hasattr(img, 'get'):
                    src = img.get('src')
                    if src:
                        # 过滤掉一些特定的跟踪像素或小图标（可选）
                        images.append(src)
        except Exception as e:
            print(f"解析图片出错: {e}")

        # 2. 清理文本
        h = html2text.HTML2Text()
        h.ignore_links = False 
        h.body_width = 0
        h.ignore_images = True # 忽略原HTML中的图片标签，因为我们已经提取了
        clean_content = h.handle(description).strip()
        
        # 安全获取作者
        feed_data = feed.get('feed', {})
        feed_title = feed_data.get('title', 'Unknown') if isinstance(feed_data, dict) else 'Unknown'
        author = entry.get('author', feed_title)

        tweet_data = {
            "link": current_link,
            "author": author,
            "content": clean_content,
            "published": entry.get('published', ''),
            "images": images
        }
        new_tweets.append(tweet_data)

    # 返回按时间正序排列的推文（旧 -> 新）
    # 对于首次运行只有一条，reversed 也没影响
    return list(reversed(new_tweets))
