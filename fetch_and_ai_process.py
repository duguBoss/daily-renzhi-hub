import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 配置订阅列表
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_full_content(url):
    """使用 Jina Reader 获取网页结构化内容"""
    headers = {"Accept": "application/json"}
    try:
        # Jina 不需要 Key，直接请求
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except Exception as e:
        print(f"      [Jina Error]: {e}")
    return None

def ai_process_gemini(content_text, title_en):
    """使用 Google Gemini 1.5 Flash 进行过滤、翻译和总结"""
    if not content_text or not GEMINI_API_KEY:
        return None

    # Gemini 1.5 Flash 支持超长上下文，这里取前 10000 字以保效率
    truncated_content = content_text[:10000]

    prompt = f"""
    你是一个专业的内容审查和翻译官。请处理以下文章：
    
    任务：
    1. **合规检查**：如果内容涉及血腥、暴力、色情(NSFW)、极端政治或宗教冲突，必须输出: {{"status": "REJECT"}}。
    2. **中文化处理**：将文章标题 "{title_en}" 翻译为中文。
    3. **总结内容**：用中文写一段200-300字的摘要，提取文章核心洞见。
    4. **严格输出格式**：只返回一个有效的 JSON 对象，不得包含任何 Markdown 代码块标签（如 ```json）。

    待处理内容：
    {truncated_content}
    """

    # Gemini API 结构
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json", # 强制 JSON 输出
            "temperature": 0.2
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=60)
        res_json = response.json()
        
        # 解析 Gemini 返回的结构
        if 'candidates' in res_json:
            raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text)
        else:
            print(f"      [Gemini API Error]: {res_json}")
            return None
    except Exception as e:
        print(f"      [AI Exception]: {e}")
        return None

def main():
    if not os.path.exists('data'):
        os.makedirs('data')

    processed_articles = []
    print(f"Task started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for feed_url in FEEDS:
        print(f"\nFeed: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        # 每次每个源取最新的 2 篇
        for entry in feed.entries[:2]:
            link = entry.get('link')
            title_en = entry.get('title')
            print(f"  - Article: {title_en}")
            
            # 1. Jina 抓取
            data = get_full_content(link)
            if not data or not data.get('content'):
                print("    >>> Jina fetch failed")
                continue
            
            # 2. Gemini 处理
            ai_result = ai_process_gemini(data.get('content'), title_en)
            
            if not ai_result or ai_result.get("status") == "REJECT":
                print("    >>> Skipped (Filtered or AI Error)")
                continue

            # 3. 整合
            article_data = {
                "title_cn": ai_result.get("title_cn"),
                "title_en": title_en,
                "url": link,
                "summary": ai_result.get("summary_cn"),
                "source": feed_url,
                "images": data.get('images', [])[:3], # 提取前3张图片
                "publish_date": entry.get('published', ''),
                "processed_at": datetime.now().isoformat()
            }
            processed_articles.append(article_data)
            print("    >>> Successfully processed")
            
            # Gemini 免费版有 RPM 限制（每分钟约 15 次），建议停顿
            time.sleep(4)

    # 4. 保存
    if processed_articles:
        today = datetime.now().strftime('%Y%m%d')
        file_path = f"data/news_{today}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(processed_articles, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(processed_articles)} articles to {file_path}")

if __name__ == "__main__":
    main()
