import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 配置
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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def get_full_content(url):
    headers = {"Accept": "application/json"}
    try:
        # 使用 Jina Reader 获取正文
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=20)
        if response.status_code == 200:
            return response.json().get('data', {})
    except Exception as e:
        print(f"      [Jina Error]: {e}")
    return None

def extract_json_from_text(text):
    """从 AI 返回的文本中提取 JSON 部分"""
    try:
        # 尝试匹配 ```json ... ``` 块
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except:
        return None

def ai_process(content_text, title_en):
    if not content_text or not OPENROUTER_API_KEY:
        return None

    # 限制内容长度，防止超出模型窗口或导致 API 报错
    truncated_content = content_text[:3500] 

    prompt = f"""
    你是一个专业的内容审查和翻译官。请处理以下文章内容：
    
    1. **安全合规检查**：如果内容涉及血腥、暴力、色情、极端政治、宗教冲突，直接回复 "REJECT"。
    2. **任务**：翻译标题 "{title_en}" 并总结300字以内的中文摘要。
    3. **输出格式**：必须只返回一个 JSON 对象，格式如下：
    {{
      "status": "APPROVED",
      "title_cn": "中文标题",
      "summary_cn": "中文摘要"
    }}

    文章原文：
    {truncated_content}
    """
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/assistant-rss", # OpenRouter 建议携带
        "X-Title": "RSS AI Summary"
    }
    
    payload = {
        "model": "stepfun/step-3.5-flash:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            headers=headers, 
            json=payload, 
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"      [AI API Error]: Status {response.status_code} - {response.text}")
            return None

        res_json = response.json()
        if 'choices' not in res_json:
            print(f"      [AI API Unexpected Response]: {res_json}")
            return None

        raw_content = res_json['choices'][0]['message']['content'].strip()
        
        if "REJECT" in raw_content.upper() and "APPROVED" not in raw_content.upper():
            return {"status": "REJECT"}

        return extract_json_from_text(raw_content)

    except Exception as e:
        print(f"      [AI Process Exception]: {e}")
        return None

def main():
    if not os.path.exists('data'):
        os.makedirs('data')

    processed_articles = []
    print(f"Start processing at {datetime.now().isoformat()}")

    for feed_url in FEEDS:
        print(f"\nFeed: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        # 限制每个源处理 1-2 篇最新的，避免触发免费额度限制
        for entry in feed.entries[:2]:
            link = entry.get('link')
            title_en = entry.get('title')
            print(f"  - Article: {title_en}")
            
            # 1. 获取内容
            data = get_full_content(link)
            if not data or not data.get('content'):
                print("    >>> Failed to fetch content via Jina")
                continue
            
            # 2. AI 处理
            ai_result = ai_process(data.get('content'), title_en)
            
            if not ai_result:
                print("    >>> Skipped: AI process failed")
                continue
            
            if ai_result.get("status") == "REJECT":
                print("    >>> Skipped: Content filtered (REJECT)")
                continue

            # 3. 整合
            article_data = {
                "title_cn": ai_result.get("title_cn", "翻译失败"),
                "title_en": title_en,
                "url": link,
                "summary": ai_result.get("summary_cn", "总结失败"),
                "source": feed_url,
                "images": data.get('images', [])[:3], # 仅保留前3张图
                "publish_date": entry.get('published', ''),
                "processed_at": datetime.now().isoformat()
            }
            processed_articles.append(article_data)
            print("    >>> Successfully processed")
            
            # 延时防止触发 OpenRouter 的频率限制
            time.sleep(5)

    if processed_articles:
        file_path = f"data/summary_{datetime.now().strftime('%Y%m%d')}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(processed_articles, f, ensure_ascii=False, indent=2)
        print(f"\nDone! Saved {len(processed_articles)} articles.")
    else:
        print("\nNo articles were processed successfully.")

if __name__ == "__main__":
    main()
