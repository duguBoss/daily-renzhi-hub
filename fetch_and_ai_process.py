import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 1. 配置（23个高质量深度内容源）
FEEDS =[
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
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', {})
    except: return None
    return None

def clean_json_string(raw_text):
    text = raw_text.strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
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
    text_input = content_text[:18000] 

    prompt = f"""
    你是一个深夜电台/播客博主。你的听众是一群聪明但讨厌被说教的人。
    请根据以下内容写一个分享稿。
    
    【关键指令：去AI化】
    1. **禁词列表**（用了就会死鱼味）：总之、综上所述、首先/其次/最后、这意味着、不仅如此、探索、见证、维度、赋予、深远意义。
    2. **人设**：你是在和朋友深夜喝酒聊天，语气要松弛、偶尔带点情绪（惊讶、感叹、自嘲）。
    3. **叙事逻辑**：不要分1、2、3条。要用“引子 -> 一个奇怪的发现 -> 细思极恐的细节 -> 咱们普通人该怎么办 -> 留白”这种流式结构。
    4. **字数硬指标**：哪怕是闲聊也要聊透，字数必须达到 1000-1500 字，多写写你对这件事的“主观感受”和“生活类比”。
    
    【HTML 样式组件】
    - 全文 margin:0; padding:0; 不要任何边距。
    - 图片：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:15px 0;">
    - 正文段落：<section style="font-size:16px;line-height:1.8;margin-bottom:20px;text-align:justify;color:#333;">[内容]</section>
    - 强调观点：<section style="font-size:19px;font-weight:bold;color:#111;margin-bottom:12px;letter-spacing:1px;">[别具一格的短句标题]</section>
    - 扎心金句：<section style="text-align:center;margin:30px 0;padding:20px 0;color:#b77a56;font-size:20px;font-weight:600;line-height:1.5;">“[一句话扎心]”</section>

    【输出 JSON】
    {{
      "status": "APPROVED",
      "viral_title": "像朋友圈或者播客那种极简但吸引人的标题",
      "script_text": "此处是1000字以上的纯文字聊天脚本...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:0;'><!-- 正文流 -->[CONTENT]</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>"
    }}

    待分享内容（原标题: {title_en}）:
    {text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.85}
    }

    try:
        res = requests.post(url, json=payload, timeout=120)
        res_json = res.json()
        
        # 1. 深度拦截 API 真实报错原因
        if 'candidates' not in res_json:
            if 'error' in res_json:
                print(f"      [API Error Detail]: {res_json['error'].get('message', 'Unknown API Error')}")
            elif 'promptFeedback' in res_json:
                print(f"      [API Blocked]: 触发了安全机制被拦截 -> {res_json['promptFeedback']}")
            else:
                print(f"      [API Unknown Response]: {res_json}")
            return None
            
        # 2. 正常提取文本
        raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
        
        # 3. 拦截 AI 生成的非法 JSON
        try:
            return json.loads(clean_json_string(raw_output))
        except json.JSONDecodeError as e:
            print(f"      [JSON Parse Error]: AI 生成了非法的 JSON 格式。")
            return None
            
    except requests.exceptions.Timeout:
        print("      [Request Timeout]: 请求 Gemini API 超时 (120s)")
        return None
    except Exception as e:
        print(f"      [Request Exception]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')

    print(f"🚀 开始扫描 RSS 节点，当前模型: {MODEL_NAME}...\n")

    for feed_url in FEEDS:
        print(f"[{feed_url}]")
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:3]:
            original_title = entry.get('title')
            link = entry.get('link')
            print(f"  📝 Reading: {original_title[:50]}...")
            
            # 获取全文
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): 
                print("    >>> ⚠️ 跳过 (Jina 抓取不到原文或遭遇反爬)")
                continue

            # AI 处理
            article_res = ai_process_wechat_article(web_data['content'], original_title)
            
            if not article_res:
                print("    >>> ❌ 跳过 (AI 接口返回错误或超时，请查看上方报错日志)")
                continue
            if article_res.get("status") == "REJECT":
                print("    >>> ❌ 跳过 (AI 拒绝改写该文章内容，可能触发内置规则)")
                continue

            # 处理封面与排版
            cover_url = get_picsum_cover_url(800, 600)
            raw_html = article_res.get("article_html", "")
            final_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            compressed_html = minify_html(final_html)
            
            final_results.append({
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": link,
                "cover": cover_url,
                "script_text": article_res.get("script_text"),
                "wechat_html": compressed_html,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            print(f"    >>> ✅ 识别并保存成功！(生成字数: {len(article_res.get('script_text', ''))}字)")
            time.sleep(4)
            
        print("-" * 40)

    # =============== 运行结束，打印汇总报告 ===============
    print("\n" + "="*50)
    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
            
        print(f"🎉 任务完成！共成功处理并保存了 {len(final_results)} 篇文章。")
        print(f"📂 数据已保存至: {output_file}\n")
        print("👇 成功文章列表：")
        for idx, res in enumerate(final_results, 1):
            print(f"  [{idx}] {res['original_title']}  =>  《{res['title']}》")
    else:
        print("⚠️ 任务结束，本次未成功生成任何文章。请检查上述打印的错误原因。")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
