import time
import schedule
import signal
import sys
from config import CHECK_INTERVAL
from rss_fetcher import fetch_new_tweets, save_last_link
from translator import translate_tweet
from notifier import send_telegram_message

def job():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始检查新推文...")
    try:
        new_tweets = fetch_new_tweets()
        
        if not new_tweets:
            print("没有新推文。")
            return

        print(f"发现 {len(new_tweets)} 条新推文，准备处理...")

        for i, tweet in enumerate(new_tweets, 1):
            print(f"--- 处理第 {i}/{len(new_tweets)} 条 ---")
            
            # 翻译
            print("正在翻译...")
            translated_content = translate_tweet(tweet['content'])
            
            # 发送
            print("正在推送...")
            send_telegram_message(tweet['content'], translated_content, tweet['link'])
            
            # 保存进度 (每成功一条就保存一条，防止中断后重复推送)
            save_last_link(tweet['link'])
            
            # 避免触发 API 限制
            time.sleep(3)

        print("所有新推文处理完成。")

    except Exception as e:
        print(f"任务执行出错: {e}")

def signal_handler(sig, frame):
    print('\n程序已停止。')
    sys.exit(0)

if __name__ == "__main__":
    # 注册退出信号
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"程序已启动。检查间隔: {CHECK_INTERVAL} 秒")
    
    # 立即运行一次
    job()

    # 设置定时任务
    schedule.every(CHECK_INTERVAL).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
