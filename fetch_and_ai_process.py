import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# =================== 全局配置 ===================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 每次运行最大处理文章数（防止超时）
MAX_PROCESS_PER_RUN = 5 
HISTORY_FILE = "data/processed_history.json"

# 【关键修改】每个 RSS 源单独保留最近的 1000 条记录
# 40个源 x 1000条 = 4万条记录，文件仅约 4MB，非常安全且高效
MAX_HISTORY_PER_FEED = 1000 

FEEDS = [
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
    "https://www.lesswrong.com/feed.xml?view=curated-rss",
    "https://www.lesswrong.com/.rss",
    "https://www.scottaaronson.com/blog/?feed=rss2",
    "https://undark.org/feed/",
    "https://www.technologyreview.com/feed/",
    "https://longreads.com/feed/",
    "https://forum.effectivealtruism.org/.rss",
    "https://theconversation.com/global/feed",
    "https://daily.jstor.org/feed/",
    "https://www.bigthink.com/feed",
    "https://www.gwern.net/atom.xml",
    "https://www.alignmentforum.org/.rss",
    "https://sideways-view.com/feed/",
    "https://www.benkuhn.net/index.xml",
    "https://www.worksinprogress.news/feed",
    "https://www.noahpinion.blog/feed",
    "https://www.slowboring.com/feed",
    "https://ourworldindata.org/feed",
    "https://www.rootsofprogress.org/feed.xml",
    "https://maximumprogress.substack.com/feed",
    "https://ifp.org/feed/",
    "https://newsletter.safe.ai/feed",
    "https://thezvi.substack.com/feed",
    "https://matthewbarnett.substack.com/feed",
    "https://marginalrevolution.com/feed",
    "https://nav.al/rss",
    "https://www.lunarsociety.org/feed",
    "https://waitbutwhy.com/feed",
    "https://www.ribbonfarm.com/feed/",
]

TEXT_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash"
]

# =================== 历史记录模块（分源隔离版） ===================

def load_history():
    """
    加载历史记录，返回一个字典结构 {feed_url: [url1, url2...]}
    如果发现旧文件是列表格式（旧版本代码产生），则重置为空字典，实现平滑迁移
    """
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    print("⚠️ 检测到旧版历史记录格式，正在重置为分源隔离格式...")
                    return {} 
                return data
        except:
            return {}
    return {}

def save_history(history_dict):
    """保存历史记录到文件"""
    if not os.path.exists('data'): os.makedirs('data')
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_dict, f, ensure_ascii=False, indent=2)

def is_processed(feed_url, article_url, history_dict):
    """检查特定源下是否已存在该文章"""
    if feed_url not in history_dict:
        return False
    # 这里用 list 查找，1000条数据内性能极快，无需担心
    return article_url in history_dict[feed_url]

def add_to_history(feed_url, article_url, history_dict):
    """添加记录并执行分源截断"""
    if feed_url not in history_dict:
        history_dict[feed_url] = []
    
    # 避免单次运行重复添加
    if article_url not in history_dict[feed_url]:
        history_dict[feed_url].append(article_url)
    
    # 【核心防爆】只截断当前这个源的记录，保留最新的 1000 条
    if len(history_dict[feed_url]) > MAX_HISTORY_PER_FEED:
        history_dict[feed_url] = history_dict[feed_url][-MAX_HISTORY_PER_FEED:]

# =================== 工具函数 ===================

def get_picsum_cover_url(width=800, height=340):
    """极速获取高质量随机图"""
    return f"https://picsum.photos/{width}/{height}?random={int(time.time())}"

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
    return html_str.strip()

def ai_process_wechat_article(content_text, title_en):
    if not content_text or not GEMINI_API_KEY: return None
    
    # 截取前 25000 字符，足够覆盖绝大多数深度长文
    text_input = content_text[:25000] 
    
    prompt = f"""
    【角色】你是一家顶级中文商业与深度知识媒体（如虎嗅、36氪）的金牌主编。你最擅长将枯燥的英文长文改写为符合中国读者阅读习惯的爆款文章。
    
    【任务一：优胜劣汰】
    通读原文。如果文章内容过于狭隘、是单纯的个人碎碎念、或者涉及极其冷门的国外政治，请直接输出 JSON `"status": "REJECTED"`，并简述理由。
    只有包含普适性认知、科技趋势、商业洞察或思维模型的文章，才输出 `"status": "APPROVED"`。

    【任务二：深度改写（仅 APPROVED 时执行）】
    1. **标题重塑**：必须使用新媒体爆款标题公式（反常识、痛点放大、悬念、高阶信息差）。例：“为什么极度聪明的人，都在偷偷做减法？”。
    2. **开头钩子**：第一段必须用扎心的场景、犀利的提问或颠覆性的数据抓住眼球，严禁平铺直叙。
    3. **去 AI 味**：严禁使用“综上所述”、“总而言之”、“在这个快速变化的时代”。口语化，像专家在聊天。
    4. **结构排版**：使用下方的 HTML 标签进行排版，两侧 0 留白，段落间距大，呼吸感强。
    5. **图片位**：在开头（钩子段落后）插入一次 `[COVER_IMG_URL]`。

    【HTML组件库（严格遵守）】
    - 正文段落：`<p style="margin:0 0 24px 0; line-height:2; color:#2c3e50; font-size:16px; letter-spacing:0.8px; text-align:justify;">...</p>`
    - 金句/引用：`<section style="margin:35px 0; padding:15px 0 15px 20px; border-left:3px solid #111; background-color:#FAFAFA; color:#555; font-size:15px; line-height:1.9;">...</section>`
    - 小标题：`<section style="margin:50px 0 25px 0; border-bottom:1px solid #E5E5E5; padding-bottom:12px; display:flex; align-items:center;"><span style="display:inline-block; width:5px; height:18px; background-color:#111; margin-right:12px;"></span><strong style="font-size:19px; color:#111; letter-spacing:1.5px;">...</strong></section>`
    - 强调：`<strong style="color:#000; font-weight:bold;">...</strong>`

    【输出 JSON】
    {{
      "status": "APPROVED 或 REJECTED",
      "reject_reason": "中文理由",
      "viral_title": "爆款标题",
      "seo_tags":["标签1", "标签2"],
      "article_html": "HTML内容"
    }}

    原文标题: {title_en}
    原文内容:
    {text_input}
    """

    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.75}
    }

    for current_model in TEXT_MODELS:
        print(f"      [Text AI] 调用模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, json=payload, timeout=120)
            res_json = res.json()
            if 'candidates' in res_json:
                return json.loads(clean_json_string(res_json['candidates'][0]['content']['parts'][0]['text']))
            elif 'error' in res_json:
                print(f"      [API Error]: {res_json['error'].get('message')}")
        except Exception as e:
            print(f"      [Text API Exception]: {e}")
            continue
    return None

# =================== 主程序流程 ===================

def main():
    if not os.path.exists('data'): os.makedirs('data')
    
    # 1. 加载分源隔离的历史记录
    history_dict = load_history()
    
    final_results = []
    success_count = 0
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 启动任务 | 限制生成数: {MAX_PROCESS_PER_RUN} | 历史记录模式: 分源隔离 (1000条/源)")

    for feed_url in FEEDS:
        if success_count >= MAX_PROCESS_PER_RUN:
            print(f"\n🛑 已达到单次运行上限 ({MAX_PROCESS_PER_RUN} 篇)，结束抓取。")
            break

        print(f"\n🔍 扫描源: {feed_url}")
        try: 
            feed = feedparser.parse(feed_url)
        except: 
            print("   -> 解析失败，跳过")
            continue
            
        for entry in feed.entries[:6]: 
            if success_count >= MAX_PROCESS_PER_RUN: break

            title = entry.get('title', 'Untitled')
            link = entry.get('link', '')

            # 2. 分源查重：只检查当前 feed_url 对应的 1000 条记录
            if is_processed(feed_url, link, history_dict):
                print(f"  ⏭️ [跳过] 历史记录已存在: {title[:20]}...")
                continue

            print(f"  📝 [处理] 新发现: {title[:30]}...")
            
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): continue
            
            # 3. AI 改写
            article_res = ai_process_wechat_article(web_data['content'], title)
            if not article_res: continue
            
            # 4. 无论是否通过，都加入历史记录，防止下次重复消耗 Token
            add_to_history(feed_url, link, history_dict)
            
            if article_res.get("status") == "REJECTED":
                print(f"    >>> 🚫 拒稿: {article_res.get('reject_reason')}")
                save_history(history_dict) # 拒稿后立即保存历史记录，防止程序意外中断导致记录丢失
                continue
            
            print(f"    >>> ✨ 标题: {article_res.get('viral_title')}")
            
            # 获取静态/随机图
            cover_url = get_picsum_cover_url()

            raw_html = article_res.get("article_html", "")
            # 替换占位符
            if "[COVER_IMG_URL]" in raw_html:
                content_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            else:
                content_html = f"<img peitu='true' src='{cover_url}' style='width:100%;display:block;margin:30px 0;'>{raw_html}"
            
            # 组装 Tag
            tags_html = ""
            if article_res.get("seo_tags"):
                tags_spans = "".join([f"<span style='display:inline-block;margin:0 10px 10px 0;padding:4px 12px;border:1px solid #DCDFE6;color:#606266;font-size:12px;'>{t}</span>" for t in article_res.get("seo_tags")])
                tags_html = f"""
                <section style='margin:45px 0 20px 0;padding-top:20px;border-top:1px solid #E5E5E5;'>
                    <section style='font-size:13px;color:#999;margin-bottom:12px;text-transform:uppercase;'>TAGS</section>
                    <section>{tags_spans}</section>
                </section>
                """

            final_wechat_html = f"""
            <section style='margin:0;padding:0;background-color:#fff;'>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
                <section style='padding:0;'>{content_html}{tags_html}</section>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
            </section>
            """
            
            final_results.append({
                "title": article_res.get("viral_title"),
                "url": link,
                "cover": cover_url,
                "wechat_html": minify_html(final_wechat_html),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # 保存历史记录
            save_history(history_dict)
            success_count += 1
            
            # 保存文章数据（追加模式）
            existing_data = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except: pass
            
            existing_data.extend(final_results)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            final_results = []
            print(f"    >>> 💾 已保存")
            time.sleep(2) 

    print(f"\n🎉 任务完成，本轮生成 {success_count} 篇。")

if __name__ == "__main__":
    main()
