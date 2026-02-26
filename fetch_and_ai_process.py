import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 1. 核心配置：高质量 Feed 矩阵 (涵盖利他、创业、搞钱、深度认知)
FEEDS =[
    "https://80000hours.org/feed/",
    "https://blog.givewell.org/feed/",
    "https://www.ycombinator.com/blog/feed",
    "https://seths.blog/feed/",
    "https://fs.blog/feed/",
    "https://nautil.us/feed",
    "https://aeon.co/feed",
    "https://www.astralcodexten.com/feed",
    "https://www.quantamagazine.org/feed/",
    "https://psyche.co/feed",
    "https://www.themarginalian.org/feed/",
    "https://www.noemamag.com/feed/",
    "https://dynomight.net/feed.xml",
    "https://www.experimental-history.com/feed",
    "https://www.overcomingbias.com/feed",
    "https://www.lesswrong.com/.rss",
    "https://www.scottaaronson.com/blog/?feed=rss2",
    "https://undark.org/feed/",
    "https://www.technologyreview.com/feed/",
    "https://longreads.com/feed/",
    "https://forum.effectivealtruism.org/.rss",
    "https://theconversation.com/global/feed",
    "https://daily.jstor.org/feed/",
    "https://www.bigthink.com/feed"
]

MODEL_NAME = "gemini-2.5-flash" 
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
    【最高指令：内容安全审查】
    在进行任何处理前，你必须严格审查以下原文内容。如果原文的主题、暗含意思或主要情节涉及以下任何一项：
    1. 政治（如国际争端、政党、政府批判、敏感历史事件等）；
    2. 宗教（宣扬、探讨或贬低特定宗教信仰）；
    3. 残暴暴力、血腥犯罪、自残；
    4. 色情、低俗、黄色内容；
    5. 极端思想、性别对立、文化歧视等不符合大众主流价值和极具争议性的内容。
    如果你判定文章触犯以上任何一条，请直接且仅返回：{{"status": "REJECT", "reason": "涉及[具体敏感类型]"}}，不要生成任何其他内容！

    如果你判定文章安全、积极、有深度（特别是利他、创业、搞钱思维、科学、哲学等），请继续执行以下【创作任务】。

    【创作任务】
    你是一个拥有百万粉丝的“顶流知识播客主理人”，同时也是“爆款专栏作家”。你的受众是一群聪明、渴望认知升级但讨厌被生硬说教的人。
    请根据原文，写一篇既适合口播录音，又完美适配微信图文阅读的深度爆款文案。
    
    【核心写作要求】
    1. **去AI化与反八股**：绝对禁止使用“总之、综上所述、首先其次最后、这意味着、探索、见证、维度、赋予、深远意义”等机器味词汇。拒绝123分点式说教。
    2. **人设与语感**：像一个知识渊博的老朋友在喝咖啡时与读者进行深度对谈。语气要松弛、犀利、有亲和力，多用反问和生活化类比。既要有口语的流畅感，也要有文字的穿透力。
    3. **长尾长青（Evergreen）**：切勿使用“今天”、“最近”、“昨晚”等带有强烈当前时间局限性的词汇，确保文章在任何时候被翻阅都不过时、具有长期的适应能力。
    4. **叙事流**：用“引子（抛出反常识或痛点） -> 深度拆解（不仅说是什么，更挖为什么） -> 认知破局（对咱们普通人搞钱、做事有什么启发） -> 留白思考”的流式结构。
    5. **字数硬指标**：哪怕是闲聊也要聊透，字数必须达到 1000-1500 字，多加一点你自己的“主观洞察”和“现实生活案例”。

    【HTML 样式组件】
    - 全文 margin:0; padding:0;
    - 图片：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:15px 0;">
    - 正文段落：<section style="font-size:16px;line-height:1.8;margin-bottom:20px;text-align:justify;color:#333;">[内容]</section>
    - 强调观点：<section style="font-size:19px;font-weight:bold;color:#111;margin-bottom:12px;letter-spacing:1px;">[别具一格的短句标题]</section>
    - 扎心金句：<section style="text-align:center;margin:30px 0;padding:20px 0;color:#b77a56;font-size:20px;font-weight:600;line-height:1.5;">“[一句话扎心]”</section>

    【输出 JSON 格式（审核通过时）】
    {{
      "status": "APPROVED",
      "viral_title": "极简但极具吸引力的中文标题（适合公众号和播客）",
      "script_text": "此处是1000字以上的纯文字播客/推文脚本...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:0;'><!-- 正文流 -->[CONTENT]</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>"
    }}

    待分享原文（原标题: {title_en}）:
    {text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents":[{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.82} # 稍微下调一点点温度，保证大逻辑更严密
    }

    try:
        res = requests.post(url, json=payload, timeout=120)
        res_json = res.json()
        
        # 1. API 层面的拦截
        if 'candidates' not in res_json:
            if 'error' in res_json:
                print(f"      [API Error]: {res_json['error'].get('message', 'Unknown Error')}")
            elif 'promptFeedback' in res_json:
                print(f"[API Blocked]: 触碰 API 官方底线拦截 -> {res_json['promptFeedback']}")
            return None
            
        # 2. 提取文本
        raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
        
        # 3. 解析 JSON
        try:
            return json.loads(clean_json_string(raw_output))
        except json.JSONDecodeError:
            print(f"      [Parse Error]: 生成内容无法被解析为 JSON。")
            return None
            
    except Exception as e:
        print(f"      [Network Exception]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')

    print(f"🚀 开始扫描 {len(FEEDS)} 个内容节点，安全审查与 Evergreen 模式已开启...\n")

    for feed_url in FEEDS:
        print(f"\n[{feed_url}]")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"  ❌ RSS 解析失败: {e}")
            continue
        
        for entry in feed.entries[:3]:
            original_title = entry.get('title', 'Untitled')
            link = entry.get('link', '')
            print(f"  📝 查阅文章: {original_title[:60]}...")
            
            # 获取全文
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): 
                print("    >>> ⚠️ 识别跳过: 抓取不到正文，可能遭遇反爬或链接失效。")
                continue

            # AI 处理与审核
            article_res = ai_process_wechat_article(web_data['content'], original_title)
            
            if not article_res:
                print("    >>> ❌ 识别失败: AI 请求无响应或异常返回。")
                continue
                
            # 捕获我们在 Prompt 中设置的 REJECT 规则
            if article_res.get("status") == "REJECT":
                reason = article_res.get("reason", "触碰内容过滤底线")
                print(f"    >>> 🚫 审查不通过，已过滤: {reason}")
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
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 仅在元数据记录获取时间
            })
            
            print(f"    >>> ✅ 创作成功！(字数: {len(article_res.get('script_text', ''))} 字)")
            time.sleep(4) # 防止 API 频率限制

    # =============== 运行结束，打印汇总报告 ===============
    print("\n" + "="*50)
    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
            
        print(f"🎉 任务完成！共成功处理并保存了 {len(final_results)} 篇优质内容。")
        print(f"📂 数据已保存至: {output_file}\n")
        print("👇 成功文章列表：")
        for idx, res in enumerate(final_results, 1):
            print(f"[{idx}] 《{res['title']}》")
    else:
        print("⚠️ 任务结束，所有内容均被过滤或获取失败。")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
