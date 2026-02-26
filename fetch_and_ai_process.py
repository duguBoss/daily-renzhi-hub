import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 1. 配置（已去重整合）
FEEDS = [
    "https://www.lesswrong.com/feed",
    "https://nautil.us/feed",
    "https://aeon.co/feed",
    "https://aeon.co/essays/feed",
    "https://aeon.co/ideas/feed",
    "https://waitbutwhy.com/feed",
    "https://www.astralcodexten.com/feed",
    "https://www.quantamagazine.org/feed/",
    "https://psyche.co/feed",
    "https://www.themarginalian.org/feed/",
    "https://worksinprogress.co/feed/",
    "https://www.noemamag.com/feed/",
    "https://www.palladiummag.com/feed/",
    "https://knowablemagazine.org/feed",
    "https://gwern.net/atom.xml",
    "https://dynomight.net/feed.xml",
    "https://putanumonit.com/feed/",
    "https://meltingasphalt.com/feed/",
    "https://www.ribbonfarm.com/feed/",
    "https://www.experimental-history.com/feed",
    "https://www.clearerthinking.org/feed",
    "https://www.overcomingbias.com/feed",
    "https://mindlevelup.wordpress.com/feed/"
]

MODEL_NAME = "gemini-3-flash-preview" 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_full_content(url):
    """通过 Jina 获取全文"""
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
    """极简压缩，去掉所有边距"""
    if not html_str: return ""
    html_str = html_str.replace('\n', '').replace('\r', '').replace('\t', '')
    html_str = re.sub(r'>\s+<', '><', html_str)
    html_str = re.sub(r'\s{2,}', ' ', html_str)
    return html_str.strip()

def get_picsum_cover_url(width=800, height=600):
    """获取 4:3 静态配图"""
    req_url = f"https://picsum.photos/{width}/{height}"
    try:
        response = requests.get(req_url, allow_redirects=True, stream=True, timeout=10)
        final_url = response.url
        response.close()
        return final_url
    except: return req_url

def ai_process_wechat_article(content_text, title_en):
    """调用 Gemini-3 生成长文"""
    if not content_text or not GEMINI_API_KEY: return None
    # 尽可能多地传入原文，保证 AI 有素材写长
    text_input = content_text[:16000] 

    prompt = f"""
    你是一个拥有百万粉丝的中文公众号“硬核主编”。你现在的任务是将一篇深度长文改写为极具吸引力、字数充足、逻辑完整的口播风格爆款文案。
    
    【核心要求】
    1. **长度控制**：全文（script_text 和 article_html）必须达到 1000-1500 字。严禁虎头蛇尾，严禁草草收场。
    2. **内容结构**：
       - **黄金开头**：用极具冲突感、扎心的场景切入，不要直接讲道理。
       - **现象拆解**：描述这种现象在当下的普遍性，拉起读者共鸣。
       - **硬核硬控**：深入分析背后的底层逻辑/科学机制，这是文章的灵魂。
       - **警示/反思**：如果不了解这个逻辑，会付出什么代价？
       - **行动指南**：给出具体、可执行的思维模型或生活建议。
       - **情感升华/结尾**：用一段充满后劲的话收尾，并抛出一个开放性话题。
    3. **文风**：口播风，多用“你敢信吗”、“咱说实话”、“深呼吸”、“听好了”等口语，段落要长短结合。

    【HTML 组件库】
    - 整体外边距清零 (margin:0; padding:0)。
    - 使用提供的顶部/底部 GIF 图。
    - 首字放大：<section style="float:left;font-size:48px;line-height:0.9;margin-top:4px;padding-right:8px;font-weight:bold;color:#b77a56;">[首]</section>
    - 正文段落：<section style="font-size:16px;line-height:1.8;margin-bottom:20px;text-align:justify;color:#333;">[文字]</section>
    - 犀利标题：<section style="font-size:20px;font-weight:bold;color:#111;margin-bottom:12px;">[核心洞察]</section>
    - 中间配图：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:25px 0;">
    - 原创金句：<section style="text-align:center;margin:25px 0;border-top:1px solid #eee;border-bottom:1px solid #eee;padding:20px 0;color:#b77a56;font-size:19px;font-weight:bold;">“[金句]”</section>

    【输出 JSON】
    {{
      "status": "APPROVED",
      "viral_title": "爆款标题",
      "script_text": "此处填写 1000 字以上的纯文字口播脚本...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:0;'><!-- 正文 --></section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>"
    }}

    待处理原文：
    {text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.82}
    }

    try:
        res = requests.post(url, json=payload, timeout=120)
        res_json = res.json()
        raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
        return json.loads(clean_json_string(raw_output))
    except Exception as e:
        print(f"      [API Error]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results = []
    today_str = datetime.now().strftime('%Y%m%d')

    for feed_url in FEEDS:
        print(f"\nScanning: {feed_url}")
        feed = feedparser.parse(feed_url)
        # 深度策略：每次每个源只选 1 篇最值得写的，保证 AI 算力集中在长文生成上
        for entry in feed.entries[:3]:
            original_title = entry.get('title')
            print(f"  - Processing: {original_title}")
            
            web_data = get_full_content(entry.get('link'))
            if not web_data or not web_data.get('content'): continue

            article_res = ai_process_wechat_article(web_data['content'], original_title)
            if not article_res or article_res.get("status") == "REJECT":
                print("    >>> Failed/Rejected")
                continue

            # 获取静态 4:3 封面
            cover_url = get_picsum_cover_url(800, 600)
            
            # HTML 处理：替换图片占位符并压缩
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
            # 打印字数统计以便监控
            script_len = len(article_res.get('script_text', ''))
            print(f"    >>> Success! Script Length: {script_len} chars.")
            time.sleep(10) # 延长间隔，防止触发 API 速率限制

    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        print(f"\nMission Complete: {len(final_results)} articles saved to {output_file}")

if __name__ == "__main__":
    main()
