import time
import schedule
import signal
import sys
from config import CHECK_INTERVAL, RSS_CONFIGS, ENABLED_CHANNELS, AI_PROVIDER, PROXY_URL
from rss_fetcher import fetch_new_tweets, save_last_link
from translator import translate_tweet
from notifier import send_telegram_message, send_plain_message

def process_rss_config(config, only_latest=False):
    """处理单个 RSS 配置
    only_latest: True=启动时仅获取最新一条且不更新进度
    """
    rss_url = config['url']
    need_translate = config['translate']
    
    mode_msg = "[启动检查]" if only_latest else "[常规检查]"
    print(f"\n--- {mode_msg} 正在处理 RSS: {rss_url} (翻译: {need_translate}) ---")
    try:
        new_tweets = fetch_new_tweets(rss_url, only_latest=only_latest)
        
        if not new_tweets:
            print("没有新推文。")
            return

        print(f"发现 {len(new_tweets)} 条推文，准备处理...")

        for i, tweet in enumerate(new_tweets, 1):
            print(f"--- 处理第 {i}/{len(new_tweets)} 条 ({tweet['author']}) ---")
            
            # 翻译
            translated_content = ""
            if need_translate:
                print("正在翻译...")
                translated_content = translate_tweet(tweet['content'])
            else:
                print("跳过翻译...")
            
            # 发送
            print("正在推送...")
            send_telegram_message(
                author=tweet['author'],
                original_text=tweet['content'], 
                translated_text=translated_content, 
                link=tweet['link'],
                images=tweet.get('images', [])
            )
            
            # 保存进度 (每成功一条就保存一条)
            save_last_link(rss_url, tweet['link'])
            
            # 避免触发 API 限制
            time.sleep(3)
            
    except Exception as e:
        print(f"处理 RSS 出错 [{rss_url}]: {e}")


def job():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始本轮检查...")
    
    if not RSS_CONFIGS:
        print("未配置任何 RSS URL。")
        return

    for config in RSS_CONFIGS:
        process_rss_config(config)
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
    print(f"已配置监控 {len(RSS_CONFIGS)} 个 RSS 源")
    print(f"已启用通知渠道: {', '.join(ENABLED_CHANNELS) if ENABLED_CHANNELS else '无'}")
    
    # --- 启动通知流程 ---
    print("正在发送启动通知...")
    
    # 构建详细的启动消息
    startup_msg_lines = [
        "🤖 Twitter 监控机器人已启动\n",
        f"⏱️ 启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"🔄 检查间隔: {CHECK_INTERVAL} 秒",
        f"🧠 翻译模型: {AI_PROVIDER.upper()}",
        f"📢 通知渠道: {', '.join(ENABLED_CHANNELS) if ENABLED_CHANNELS else '无'}"
    ]
    if PROXY_URL:
        startup_msg_lines.append(f"🌐 网络代理: 已配置")
        
    startup_msg_lines.append(f"\n📋 监控列表 ({len(RSS_CONFIGS)} 个):")
    for i, config in enumerate(RSS_CONFIGS, 1):
        url = config['url']
        url_parts = [p for p in url.split('/') if p]
        username = url
        if len(url_parts) >= 2:
            username = url_parts[-2] if url_parts[-1] == 'rss' else url_parts[-1]
            
        translate_status = "✅ 翻译" if config['translate'] else "❌ 不翻译"
        startup_msg_lines.append(f"  {i}. {username} [{translate_status}]")
        
    send_plain_message("\n".join(startup_msg_lines))

    print("\n[启动检查] 获取所有关注用户的最新推文...")
    for config in RSS_CONFIGS:
        # 使用 only_latest=True 模式，仅发送最新一条且不更新进度
        process_rss_config(config, only_latest=True)
        time.sleep(2)
        
    send_plain_message("✅ 消息获取测试成功，开始进入常规监控循环")
    print("--- 启动通知流程结束 ---\n")
    # --------------------

    # 立即运行一次常规检查 (补齐遗漏的历史推文)
    job()

    # 设置定时任务
    schedule.every(CHECK_INTERVAL).seconds.do(job)

    while True:

        schedule.run_pending()
        time.sleep(1)
