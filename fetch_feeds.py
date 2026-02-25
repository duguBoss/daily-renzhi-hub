import feedparser
import json
import os
from datetime import datetime

# 订阅列表
FEEDS = [
    "https://www.lesswrong.com/feed",
    "https://astralcodexten.substack.com/feed",
    "https://gwern.net/atom.xml",
    "https://dynomight.net/feed.xml",
    "https://putanumonit.com/feed/",
    "https://meltingasphalt.com/feed/",
    "https://www.experimental-history.com/feed",
    "https://www.clearerthinking.org/feed",
    "https://www.overcomingbias.com/feed",
    "https://mindlevelup.wordpress.com/feed/",
    "https://www.quantamagazine.org/feed/",
    "https://knowablemagazine.org/feed"
]

def fetch_and_save():
    # 确保 data 目录存在
    if not os.path.exists('data'):
        os.makedirs('data')

    for url in FEEDS:
        print(f"Fetching: {url}")
        feed = feedparser.parse(url)
        
        # 提取有用的信息
        feed_data = {
            "title": feed.feed.get('title', 'Unknown Title'),
            "link": feed.feed.get('link', url),
            "updated": datetime.now().isoformat(),
            "entries": []
        }

        for entry in feed.entries:
            feed_data["entries"].append({
                "title": entry.get('title'),
                "link": entry.get('link'),
                "published": entry.get('published', entry.get('updated')),
                "summary": entry.get('summary', '')[:500]  # 限制摘要长度
            })

        # 生成文件名（将 URL 转换为合法文件名）
        filename = url.replace('https://', '').replace('/', '_').replace('.', '_') + '.json'
        filepath = os.path.join('data', filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved: {filepath}")

if __name__ == "__main__":
    fetch_and_save()
