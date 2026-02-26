import feedparser
import json
import os
import requests
import time
import re
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

MODEL_NAME = "gemini-3-flash-preview" 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_full_content(url):
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except: return None
    return None

def clean_json_string(raw_text):
    text = raw_text.strip()
    if text.startswith('```json'): text = text[7:]
    elif text.startswith('```'): text = text[3:]
    if text.endswith('```'): text = text[:-3]
    return text.strip()

def minify_html(html_str):
    if not html_str: return ""
    html_str = html_str.replace('\n', '').replace('\r', '').replace('\t', '')
    html_str = re.sub(r'>\s+<', '><', html_str)
    html_str = re.sub(r'\s{2,}', ' ', html_str)
    return html_str.strip()

def get_picsum_cover_url(width=800, height=600):
    req_url = f"https://picsum.photos/{width}/{height}"
    try:
        response = requests.get(req_url, allow_redirects=True, stream=True, timeout=10)
        final_url = response.url
        response.close()
        return final_url
    except: return req_url

def ai_process_wechat_article(content_text, title_en):
    if not content_text or not GEMINI_API_KEY: return None
    text_input = content_text[:15000] # 增加输入长度以获取更多细节

    prompt = f"""
    你是一个拥有百万粉丝的中文公众号“硬核主编”，也是一名顶级播客博主。你的文字风格极其犀利、充满情绪张力、像老朋友喝酒聊天。
    
    【核心任务】
    基于提供的文章内容，创作一篇深度、爆款的口播风格长文。
    1. 字数要求：全文必须在 1000 字以上。严禁三言两语结束，要深入挖掘。
    2. 结构要求：必须有完整的【Hook引子】、【现象拆解】、【底层逻辑剖析】、【金句升华】、【实操建议】、【开放式结尾】。
    
    【内容要求】
    - viral_title: 极其吸引眼球的中文标题。
    - script_text: 1000字以上的纯文字口播稿，语气要像在B站做深度视频。
    - article_html: 微信排版HTML。
    
    【HTML 样式规范】
    - 整体 margin:0; padding:0; 不要留白。
    - 开篇首字放大效果。
    - 必须包含提供的顶部/底部 GIF 图。
    - 正文使用 <section style="font-size:16px;line-height:1.8;margin-bottom:20px;text-align:justify;">，每段文字要饱满，不要太碎。
    - 在文章中间位置自然地插入一个 <img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:20px 0;">。
    - 必须包含一个原创的金句模块。

    【JSON输出格式】
    {{
      "status": "APPROVED",
      "viral_title": "爆款标题",
      "script_text": "此处是1000字以上的详细口播稿...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px 0;'><!-- 此处填充正文 --></section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>"
    }}

    原文内容：{text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.85}
    }

    try:
        res = requests.post(url, json=payload, timeout=120)
        raw_output = res.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(clean_json_string(raw_output))
    except Exception as e:
        print(f"      [AI Error]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results = []
    today_str = datetime.now().strftime('%Y%m%d')

    for feed_url in FEEDS:
        print(f"\nScanning: {feed_url}")
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:1]: # 增加深度，减少篇数
            original_title = entry.get('title')
            print(f"  - Processing: {original_title}")
            
            web_data = get_full_content(entry.get('link'))
            if not web_data: continue

            article_res = ai_process_wechat_article(web_data.get('content'), original_title)
            if not article_res or article_res.get("status") == "REJECT": continue

            cover_url = get_picsum_cover_url(800, 600)
            raw_html = article_res.get("article_html", "")
            final_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            compressed_html = minify_html(final_html)
            
            final_results.append({
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": entry.get('link'),
                "cover": cover_url,
                "script_text": article_res.get("script_text"),
                "wechat_html": compressed_html,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"    >>> Success ({len(article_res.get('script_text', ''))} chars)")
            time.sleep(5)

    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        print(f"\nMission Complete: {len(final_results)} articles saved.")

if __name__ == "__main__":
    main()
