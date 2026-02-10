import time
import schedule
import signal
import sys
from config import CHECK_INTERVAL, RSS_URLS
from rss_fetcher import fetch_new_tweets, save_last_link
from translator import translate_tweet
from notifier import send_telegram_message

def process_rss_url(rss_url):
    """处理单个 RSS URL"""
    print(f"\n--- 正在处理 RSS: {rss_url} ---")
    try:
        new_tweets = fetch_new_tweets(rss_url)
        
        if not new_tweets:
            print("没有新推文。")
            return

        print(f"发现 {len(new_tweets)} 条新推文，准备处理...")

        for i, tweet in enumerate(new_tweets, 1):
            print(f"--- 处理第 {i}/{len(new_tweets)} 条 ({tweet['author']}) ---")
            
            # 翻译
            print("正在翻译...")
            translated_content = translate_tweet(tweet['content'])
            
            # 发送
            print("正在推送...")
            send_telegram_message(tweet['content'], translated_content, tweet['link'])
            
            # 保存进度 (每成功一条就保存一条)
            save_last_link(rss_url, tweet['link'])
            
            # 避免触发 API 限制
            time.sleep(3)
            
    except Exception as e:
        print(f"处理 RSS 出错 [{rss_url}]: {e}")

def job():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始本轮检查...")
    
    if not RSS_URLS:
        print("未配置任何 RSS URL。")
        return

    for url in RSS_URLS:
        process_rss_url(url)
        # 每个 RSS 源处理完后休息一下
        time.sleep(2)
        
    print("\n本轮检查结束。")

def signal_handler(sig, frame):
    print('\n程序已停止。')
    sys.exit(0)

if __name__ == "__main__":
    # 注册退出信号
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"程序已启动。检查间隔: {CHECK_INTERVAL} 秒")
    print(f"已配置监控 {len(RSS_URLS)} 个 RSS 源")
    
    # 立即运行一次
    job()

    # 设置定时任务
    schedule.every(CHECK_INTERVAL).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
