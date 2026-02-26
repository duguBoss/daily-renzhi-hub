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

def clean_json_string(raw_text):
    """清理大模型可能返回的 Markdown JSON 格式"""
    text = raw_text.strip()
    if text.startswith('```json'): text = text[7:]
    elif text.startswith('```'): text = text[3:]
    if text.endswith('```'): text = text[:-3]
    return text.strip()

def minify_html(html_str):
    """极简压缩：将 HTML 压缩为单 line，移除所有标签间的留白，确保两边边距为 0"""
    if not html_str: return ""
    # 移除换行和制表符
    html_str = html_str.replace('\n', '').replace('\r', '').replace('\t', '')
    # 移除标签间的空格
    html_str = re.sub(r'>\s+<', '><', html_str)
    # 压缩多余空格
    html_str = re.sub(r'\s{2,}', ' ', html_str)
    return html_str.strip()

def get_picsum_cover_url(width=800, height=600):
    """获取 Picsum 真实跳转后的 4:3 静态图地址"""
    req_url = f"https://picsum.photos/{width}/{height}"
    try:
        response = requests.get(req_url, allow_redirects=True, stream=True, timeout=10)
        final_url = response.url
        response.close()
        return final_url
    except:
        return req_url

def ai_process_wechat_article(content_text, title_en):
    """调用 Gemini 生成口播风格内容，包含 HTML 和纯文字原稿"""
    if not content_text or not GEMINI_API_KEY: return None

    text_input = content_text[:12000] 

    prompt = f"""
    你是一个拥有百万粉丝的中文“播客博主”。风格：直接、犀利、像老朋友面对面聊天。
    
    【任务】
    1. 基于 "{title_en}" 创作一个爆款中文标题。
    2. 将原文改写为口播风格：
       - `script_text`: 纯文字版口播稿，不要任何 HTML 标签，适合语音阅读。
       - `article_html`: 微信公众号排版代码。
    
    【HTML 样式规范】
    - 整体外边距和内边距设为 0（margin:0; padding:0），不要在两边留白。
    - 必须包含提供的顶部/底部 GIF 图。
    - 样式组件参考：
      - 开篇：<section style="display:block;overflow:hidden;margin-bottom:15px;"><section style="float:left;font-size:48px;line-height:0.9;margin-top:4px;padding-right:8px;font-weight:bold;color:#b77a56;">[首字]</section><section style="font-size:16px;line-height:1.8;">[正文]</section></section>
      - 段落：<section style="font-size:16px;line-height:1.8;margin-bottom:15px;text-align:justify;">[文字]</section>
      - 标题：<section style="font-size:20px;font-weight:bold;color:#111;margin-bottom:10px;">[观点]</section>
      - 配图占位符：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin-bottom:15px;margin-left:0;margin-right:0;">
      - 金句：<section style="text-align:center;margin:20px 0;border-top:1px solid #f0f0f0;border-bottom:1px solid #f0f0f0;padding:15px 0;color:#b77a56;font-size:18px;font-weight:bold;">“[金句]”</section>

    【JSON输出】
    {{
      "status": "APPROVED",
      "viral_title": "爆款标题",
      "script_text": "此处是纯文字版本的口播稿原稿...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;margin-bottom:15px;'>[正文内容及组件]<img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;margin-top:15px;'></section>"
    }}

    原文内容：{text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.8}
    }

    try:
        res = requests.post(url, json=payload, timeout=90)
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
        for entry in feed.entries[:2]:
            original_title = entry.get('title')
            print(f"  - Processing: {original_title}")
            
            web_data = get_full_content(entry.get('link'))
            if not web_data: continue

            article_res = ai_process_wechat_article(web_data.get('content'), original_title)
            if not article_res or article_res.get("status") == "REJECT": continue

            # 获取 4:3 静态图地址
            cover_url = get_picsum_cover_url(800, 600)
            
            # HTML 替换与全屏化压缩
            raw_html = article_res.get("article_html", "")
            final_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            compressed_html = minify_html(final_html)
            
            # 存储数据
            final_results.append({
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": entry.get('link'),
                "cover": cover_url,
                "script_text": article_res.get("script_text"), # 纯文字口播稿
                "wechat_html": compressed_html,              # 压缩后的微信 HTML
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"    >>> Success")
            time.sleep(2)

    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        print(f"\nMission Complete: {len(final_results)} articles saved to {output_file}")

if __name__ == "__main__":
    main()
