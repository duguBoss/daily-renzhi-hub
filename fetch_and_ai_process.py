import feedparser
import json
import os
import requests
import time
from datetime import datetime

# 1. 配置
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

# 指定模型
MODEL_NAME = "gemini-3-flash-preview" 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_full_content(url):
    """通过 Jina 获取全文和图片"""
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except:
        return None
    return None

def ai_process_wechat_article(content_text, title_en):
    """调用 Gemini 3 生成公众号爆款文章"""
    if not content_text or not GEMINI_API_KEY:
        return None

    # 限制长度防止溢出
    text_input = content_text[:10000]

    prompt = f"""
    你是一个拥有百万粉丝的中文公众号“硬核主编”，擅长将枯燥的深度长文改写为让人欲罢不能的爆款文章。
    
    【任务指令】
    1. 安全审查：若内容涉及血腥、黄色、敏感政治、极端宗教、暴力或文化歧视，必须仅输出: {{"status": "REJECT"}}。
    2. 爆款标题：基于原标题 "{title_en}"，创作一个极具吸引力、引发好奇心或共鸣的中文标题（拒绝翻译腔）。
    3. 内容重构：
       - 用“通俗易懂”的语言改写，保留原意但降低理解门槛。
       - 使用模块化排版（分段明确，每段配有形象的 Emoji）。
       - 包含：【核心观点速览】、富有逻辑的【正文拆解】、以及一段引发互动的【主编点评】。
       - 适当加入“金句”。
    4. 视觉描述：提供一个与文章主题高度相关的英文单词作为 image_keyword。

    【输出格式】
    必须输出严格的 JSON 字符串，包含以下字段：
    - status: "APPROVED" 或 "REJECT"
    - viral_title: "爆款标题"
    - article_content: "公众号风格正文内容"
    - one_sentence_summary: "一句话金句摘要"
    - image_keyword: "用于配图的英文关键词"

    文章原文：
    {text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.8 # 提高随机性，增加文采
        }
    }

    try:
        res = requests.post(url, json=payload, timeout=90)
        res_data = res.json()
        # 提取生成的文本
        raw_output = res_data['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_output)
    except Exception as e:
        print(f"      [AI Error]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results = []

    for feed_url in FEEDS:
        print(f"\nScanning Feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:2]: # 每天每个源只取最新的2篇
            original_title = entry.get('title')
            link = entry.get('link')
            print(f"  - Processing: {original_title}")

            # 1. 深度抓取
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'):
                print("    >>> Jina Fetch Failed")
                continue

            # 2. AI 创作
            article_res = ai_process_wechat_article(web_data['content'], original_title)
            
            if not article_res or article_res.get("status") == "REJECT":
                print("    >>> Skipped (Safety Filter or Error)")
                continue

            # 3. 视觉处理
            # 优先用原图，没原图用 Unsplash 补位
            raw_imgs = web_data.get('images', [])
            final_images = []
            
            # 过滤并提取原图链接
            if isinstance(raw_imgs, list):
                final_images = [img for img in raw_imgs if isinstance(img, str) and img.startswith('http')][:2]
            
            # 如果原图失效，使用关键词从 Unsplash 获取动态图
            kw = article_res.get('image_keyword', 'abstract')
            cover_url = final_images[0] if final_images else f"https://images.unsplash.com/photo-1506744038136-46273834b3fb?q=80&w=800&auto=format&fit=crop&sig={kw}"
            # 注意：unsplash 的动态搜索接口
            placeholder_img = f"https://source.unsplash.com/800x450/?{kw}"

            # 4. 封装数据
            item = {
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": link,
                "summary": article_res.get("one_sentence_summary"),
                "wechat_content": article_res.get("article_content"),
                "cover": placeholder_img, # 动态获取的主题图
                "source_images": final_images,
                "author_source": feed_url,
                "publish_date": entry.get('published', datetime.now().strftime("%Y-%m-%d")),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            final_results.append(item)
            print("    >>> Successfully curated")
            time.sleep(5) # 保护 API 频率限制

    # 5. 保存结果
    if final_results:
        today_str = datetime.now().strftime('%Y%m%d')
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        print(f"\nMission Complete: {len(final_results)} articles saved to {output_file}")

if __name__ == "__main__":
    main()
