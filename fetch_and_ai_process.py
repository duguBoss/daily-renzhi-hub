import feedparser
import json
import os
import requests
import time
import random
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_full_content(url):
    """通过 Jina 提取正文"""
    try:
        headers = {"Accept": "application/json"}
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except:
        return None
    return None

def get_fallback_image(keyword):
    """如果没有原图，从 Unsplash 获取一张相关图片"""
    return f"https://source.unsplash.com/featured/800x450?{keyword}"

def ai_process_wechat_style(content_text, title_en):
    """调用 Gemini 生成公众号风格文章"""
    if not content_text or not GEMINI_API_KEY:
        return None

    # 截取前 8000 字，防止超出限制
    text_input = content_text[:8000]

    prompt = f"""
    你是一个拥有百万粉丝的中文公众号大主编，擅长编写引人入胜、通俗易懂的科普/深度文章。
    请阅读以下英文文章内容，完成以下任务：

    1. **安全过滤**：如果内容涉及血腥、色情、敏感政治、暴力，输出: {{"status": "REJECT"}}。
    2. **爆款标题**：将文章标题 "{title_en}" 重新翻译并创作为富有吸引力、让人想点击的中文标题。
    3. **内容创作**：
       - 用大众能理解的语言重新解构文章核心观点。
       - 使用“总-分-总”结构，多使用表情符号（Emoji）增加趣味性。
       - 适当加入“金句”和“深度思考”。
       - 字数控制在 500-800 字。
    4. **关键词提取**：提取 1 个描述文章主题的英文单词（用于配图搜索）。

    输出格式必须是严格的 JSON 对象：
    {{
      "status": "APPROVED",
      "title_cn": "爆款标题",
      "article_body": "公众号排版风格的正文内容",
      "summary": "一句话核心摘要",
      "image_keyword": "theme keyword in english"
    }}

    文章原文：
    {text_input}
    """

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.7
        }
    }

    try:
        res = requests.post(api_url, json=payload, timeout=60)
        res_data = res.json()
        raw_json = res_data['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_json)
    except Exception as e:
        print(f"      [AI Error]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    results = []

    for feed_url in FEEDS:
        print(f"Fetching: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:2]: # 限制每个源2篇
            link = entry.get('link')
            print(f"  - Article: {entry.get('title')}")

            # 1. 抓取正文
            full_data = get_full_content(link)
            if not full_data or not full_data.get('content'): continue

            # 2. AI 创作
            ai_res = ai_process_wechat_style(full_data['content'], entry.get('title'))
            
            if not ai_res or ai_res.get("status") == "REJECT":
                print("    >>> Filtered or Failed")
                continue

            # 3. 处理配图
            # 优先从原文中找图，如果没图或图太少，用 Unsplash 补充
            original_images = full_data.get('images', [])
            images = []
            if isinstance(original_images, list) and len(original_images) > 0:
                images = original_images[:2] # 取前两张原图
            
            if len(images) == 0:
                # 使用 AI 提供的关键词生成 fallback 图片
                kw = ai_res.get('image_keyword', 'knowledge')
                images.append(get_fallback_image(kw))

            # 4. 组装结果
            results.append({
                "title": ai_res.get("title_cn"),
                "original_title": entry.get('title'),
                "url": link,
                "summary": ai_res.get("summary"),
                "content": ai_res.get("article_body"),
                "cover_image": images[0] if images else "",
                "all_images": images,
                "source": feed_url,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            print("    >>> Success")
            time.sleep(3) # 减缓频率

    # 5. 保存
    if results:
        file_name = f"data/wechat_style_{datetime.now().strftime('%Y%m%d')}.json"
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(results)} articles.")

if __name__ == "__main__":
    main()
