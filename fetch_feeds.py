import feedparser
import json
import os
import requests
import time
from datetime import datetime, timedelta

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

# 仅需要 OpenRouter 的 Key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def get_full_content(url):
    """
    使用 Jina Reader 提取内容。
    即使没有 API Key，通过设置 Accept: application/json 也可以获得结构化数据
    """
    headers = {
        "Accept": "application/json",
        "X-No-Cache": "true"
    }
    try:
        # Jina Reader 免费接口
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except Exception as e:
        print(f"Jina error for {url}: {e}")
    return None

def ai_process(content_text, title_en):
    """使用 OpenRouter 调用 stepfun/step-3.5-flash:free 进行过滤、翻译和摘要"""
    if not content_text:
        return None

    prompt = f"""
    你是一个专业的内容审查和翻译官。请处理以下文章内容：
    
    1. **安全合规检查**：如果内容涉及血腥、暴力、色情(儿童不宜)、极端政治、宗教冲突或严重的文化歧视，请直接回复"REJECT"。
    2. **翻译标题**：将文章原标题 "{title_en}" 翻译为中文。
    3. **内容总结**：提取文章核心观点，写一段200-300字的中文摘要。
    4. **输出格式**：请严格按以下 JSON 格式输出（不要包含 Markdown 代码块符号）：
    {{
      "status": "APPROVED",
      "title_cn": "中文标题",
      "summary_cn": "中文摘要"
    }}

    文章原文（部分）：
    {content_text[:4000]}
    """
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "stepfun/step-3.5-flash:free",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": { "type": "json_object" } # 强制 JSON 输出
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                                 headers=headers, json=payload, timeout=60)
        res_json = response.json()
        content = res_json['choices'][0]['message']['content'].strip()
        return json.loads(content)
    except Exception as e:
        print(f"AI Process error: {e}")
        return None

def main():
    if not os.path.exists('data'):
        os.makedirs('data')

    processed_articles = []
    
    for feed_url in FEEDS:
        print(f"Processing Feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        # 限制每个源处理最新的 2 篇，避免免费模型频率限制或任务超时
        for entry in feed.entries[:2]:
            link = entry.get('link')
            title_en = entry.get('title')
            
            print(f"  - Article: {title_en}")
            
            # 1. 使用 Jina 获取正文和图片
            data = get_full_content(link)
            if not data:
                continue
            
            full_text = data.get('content', '')
            # 提取图片链接列表（Jina 返回的 images 字段）
            images = data.get('images', [])
            if isinstance(images, dict): # 有时是字典形式
                images = list(images.values())

            # 2. AI 过滤、翻译、摘要
            ai_result = ai_process(full_text, title_en)
            
            if not ai_result or ai_result.get("status") == "REJECT":
                print(f"    >>> Skipped (Filtered by AI or Error)")
                continue

            # 3. 整合数据
            article_data = {
                "title_cn": ai_result.get("title_cn"),
                "title_en": title_en,
                "url": link,
                "summary": ai_result.get("summary_cn"),
                "source": feed_url,
                "images": images[:5], # 保留前5张图片
                "publish_date": entry.get('published', datetime.now().strftime("%Y-%m-%d")),
                "processed_at": datetime.now().isoformat()
            }
            processed_articles.append(article_data)
            
            # 免费 API 建议稍作延迟
            time.sleep(2)

    # 保存到以日期命名的文件
    if processed_articles:
        file_path = f"data/summary_{datetime.now().strftime('%Y%m%d')}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(processed_articles, f, ensure_ascii=False, indent=2)
        print(f"\nSuccess: Saved {len(processed_articles)} articles to {file_path}")

if __name__ == "__main__":
    main()
