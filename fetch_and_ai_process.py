import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 1. 核心配置：高质量 Feed 矩阵
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

# 2. 备选模型矩阵 (默认首选 gemini-3-flash-preview，触发限流时自动向下瀑布流切换)
MODELS =[
    "gemini-3-flash-preview",    # 默认首选：速度最快，额度最高
    "gemini-3.1-pro-preview",    # 备胎 1：3.1 Pro 增强版
    "gemini-3-pro-preview"       # 备胎 2：3.0 Pro 兜底
]

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

    如果你判定文章安全、积极、有深度，请继续执行以下【创作任务】。

    【创作任务】
    你是一个拥有百万粉丝的“顶流知识播客主理人”和“专栏作家”。你的受众是一群聪明、渴望认知升级但讨厌被生硬说教的人。
    请根据原文，写一篇既适合口播录音，又完美适配图文阅读的深度爆款文案。
    
    【核心写作要求】
    1. **去AI化与反八股**：绝对禁止使用“总之、综上所述、首先其次最后、这意味着、探索、见证、维度、赋予”等机器味词汇。拒绝123分点式说教。
    2. **人设与语感**：像一个知识渊博的老朋友在喝咖啡时与读者进行深度对谈。语气要松弛、犀利、有亲和力，多用反问和生活化类比。
    3. **长尾长青（Evergreen）**：切勿使用“今天”、“最近”、“昨晚”等带有当前时间局限性的词汇，确保文章在任何时候被翻阅都不过时。
    4. **叙事流**：用“引子（抛出痛点） -> 深度拆解（不仅说是什么，更挖为什么） -> 认知破局（对普通人做事有什么启发） -> 留白思考”的流式结构。
    5. **字数硬指标**：哪怕是闲聊也要聊透，字数必须达到 1000-1500 字，多加一点你自己的“主观洞察”。

    【HTML 样式组件】
    - 全文 margin:0; padding:0;
    - 图片：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:15px 0;">
    - 正文段落：<section style="font-size:16px;line-height:1.8;margin-bottom:20px;text-align:justify;color:#333;">[内容]</section>
    - 强调观点：<section style="font-size:19px;font-weight:bold;color:#111;margin-bottom:12px;letter-spacing:1px;">[别具一格的短句标题]</section>
    - 扎心金句：<section style="text-align:center;margin:30px 0;padding:20px 0;color:#b77a56;font-size:20px;font-weight:600;line-height:1.5;">“[一句话扎心]”</section>

    【输出 JSON 格式（审核通过时）】
    {{
      "status": "APPROVED",
      "viral_title": "极简但极具吸引力的中文标题",
      "script_text": "此处是1000字以上的纯文字播客/推文脚本...",
      "article_html": "<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:0;'><!-- 正文流 -->[CONTENT]</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>"
    }}

    待分享原文（原标题: {title_en}）:
    {text_input}
    """

    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.8} 
    }

    # 瀑布流：优先使用默认的 gemini-3-flash-preview，受限则向下切换
    for current_model in MODELS:
        print(f"      [AI] 正在召唤模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            res = requests.post(url, json=payload, timeout=120)
            
            # 捕获 HTTP 429 限流
            if res.status_code == 429:
                print(f"      [Rate Limit 429]: {current_model} 频率超限，正在切换备用模型...")
                time.sleep(2) # 缓冲避免瞬间并发轰炸
                continue 
                
            res_json = res.json()
            
            # 捕获 Quota 额度耗尽等错误
            if 'error' in res_json:
                err_msg = res_json['error'].get('message', 'Unknown Error')
                if 'Quota exceeded' in err_msg or 'exhausted' in err_msg.lower():
                    print(f"      [Quota Error]: {current_model} 免费额度耗尽！自动切换备用模型...")
                    time.sleep(2)
                    continue 
                elif 'not found' in err_msg.lower() or 'not supported' in err_msg.lower():
                    print(f"      [Model Invalid]: {current_model} 不可用或无权限，跳过...")
                    continue
                else:
                    print(f"      [API Error]: {err_msg} ({current_model})，尝试切换...")
                    continue
                
            # 安全拦截是针对内容本身的，不用换模型，直接结束
            if 'candidates' not in res_json:
                if 'promptFeedback' in res_json:
                    print(f"      [API Blocked]: 触碰 API 官方安全底线被拦截")
                return None
                
            # 提取文本并解析
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
            try:
                return json.loads(clean_json_string(raw_output))
            except json.JSONDecodeError:
                print(f"      [Parse Error]: {current_model} 吐出的 JSON 损坏，尝试下一个模型救场...")
                continue
                
        except requests.exceptions.Timeout:
            print(f"      [Timeout]: {current_model} 响应超时 (120s)，切换备用模型...")
            continue
        except Exception as e:
            print(f"      [Network Exception]: {current_model} 异常 -> {e}，尝试切换...")
            continue

    print("      ❌ 警告：所有模型均已超限或瘫痪，此篇文章暂时放弃。")
    return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 开始扫描 {len(FEEDS)} 个内容节点，默认模型为 {MODELS[0]} (瀑布流防封控已开启)...\n")

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
            print(f"  📝 查阅: {original_title[:50]}...")
            
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): 
                print("    >>> ⚠️ 识别跳过: 抓取不到正文，可能遭遇反爬。")
                continue

            article_res = ai_process_wechat_article(web_data['content'], original_title)
            
            if not article_res:
                print("    >>> ❌ 识别失败: 所有 Gemini 3 模型皆尝试完毕并超限。")
                continue
                
            if article_res.get("status") == "REJECT":
                print(f"    >>> 🚫 审查过滤: {article_res.get('reason', '触碰内容过滤底线')}")
                continue

            # 处理封面与排版
            cover_url = get_picsum_cover_url(800, 600)
            raw_html = article_res.get("article_html", "")
            final_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            compressed_html = minify_html(final_html)
            
            # 加入结果列表
            final_results.append({
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": link,
                "cover": cover_url,
                "script_text": article_res.get("script_text"),
                "wechat_html": compressed_html,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # 实时覆盖保存，绝不丢数据
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)
            
            print(f"    >>> ✅ 创作并实时保存成功！(字数: {len(article_res.get('script_text', ''))} 字)")
            
            # 保底休眠时间，即便有多模型，也尽量保持风控安全距离
            time.sleep(15) 

    # =============== 运行结束，打印汇总报告 ===============
    print("\n" + "="*50)
    if final_results:
        print(f"🎉 任务完成！共成功处理并保存了 {len(final_results)} 篇优质内容。")
        print(f"📂 数据已安全保存至: {output_file}\n")
        print("👇 成功文章列表：")
        for idx, res in enumerate(final_results, 1):
            print(f"[{idx}] 《{res['title']}》")
    else:
        print("⚠️ 任务结束，所有内容均被过滤或获取失败。")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
