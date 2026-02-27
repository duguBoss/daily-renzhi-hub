import feedparser
import json
import os
import requests
import time
import re
import base64
import io
from PIL import Image
from datetime import datetime

# ==========================================
# ⚠️ 必须安装依赖: pip install requests feedparser Pillow
# ==========================================

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

# 2. 文本模型矩阵 (⚠️已将 3.1-pro 设为首选)
TEXT_MODELS =[
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash"
]

# 3. 图像模型矩阵
IMAGE_MODELS =[
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image"
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =================== 图片处理模块 ===================

def crop_to_wechat_cover(img_data, output_path):
    """将生成的图片智能居中裁剪为微信标准的 2.35:1 比例"""
    try:
        image = Image.open(io.BytesIO(img_data))
        w, h = image.size
        
        target_ratio = 2.35
        current_ratio = w / h
        
        if current_ratio < target_ratio:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            bottom = top + new_h
            image = image.crop((0, top, w, bottom))
        elif current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            right = left + new_w
            image = image.crop((left, 0, right, h))
            
        image.save(output_path, "JPEG", quality=95)
        return True
    except Exception as e:
        print(f"      [Crop Error]: {e}")
        return False

def generate_ai_cover_image(keyword, title):
    if not GEMINI_API_KEY: return None

    prompt = f"Generate a high-quality, photorealistic image. Concept: {keyword}. Context: {title}. Style: Editorial photography, highly detailed, minimalist, authoritative, premium. No text."
    
    headers = {"Content-Type": "application/json"}
    payload = {"contents":[{"parts":[{"text": prompt}]}]}
    
    for current_model in IMAGE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            print(f"[Image AI] 尝试调用: {current_model} ...")
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res_json = res.json()
            
            if "candidates" in res_json and res_json["candidates"]:
                parts = res_json["candidates"][0].get("content", {}).get("parts",[])
                for part in parts:
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    if inline_data and inline_data.get("data"):
                        return base64.b64decode(inline_data.get("data"))
                        
        except Exception as e:
             pass
        if current_model != IMAGE_MODELS[-1]:
             print(f"      ⚠️ 尝试切换备用图像模型...")
             
    return None

def get_picsum_cover_url(width=800, height=340):
    return f"https://picsum.photos/{width}/{height}?random={int(time.time())}"

# =================== 文本处理模块 ===================

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
    
    text_input = content_text[:25000] # 稍微扩大上下文截取
    
    prompt = f"""
    【角色】你是一家顶级中文商业与深度知识媒体（如虎嗅、三联生活周刊、经济学人）的金牌主编和排版视觉总监。
    
    【前置过滤任务：优胜劣汰】
    作为主编，请先通读提供的英文原文。如果文章充斥着极其冷门的国外政治、难以理解的国外文化梗，或对中国受众毫无启发、没有阅读价值，请直接在 JSON 输出 `"status": "REJECTED"`，并给出简短拒绝理由（如"受众不匹配"）。
    只有当文章包含普适性的认知、科技趋势、商业洞察或优秀的自我提升方法论时，才输出 `"status": "APPROVED"` 并执行以下改写任务。
    
    【核心改写要求（仅在 APPROVED 时）】
    1. **本土化降维打击**：不要逐字翻译！将其彻底改写为符合中国微信读者口味的爆款深度文。用中国读者熟悉的逻辑、商业词汇或生活比喻重新表述。
    2. **摒弃AI味**：严禁出现“综上所述”、“总之”、“这是一篇关于…”等机械词汇。语气要客观、专业、有洞察力，像资深行业专家在分享。
    3. **结构设计**：直接进入痛点/引子（不生成大标题，文章已有） -> 核心认知深度拆解 -> 升华与行动指南。
    4. **图片占位**：必须在引子之后、核心正文之前，插入且仅插入一次图片占位符 `[COVER_IMG_URL]`。
    
    【顶级权威排版规范（必须严格组合使用，不可擅自改变）】
    要求：两侧 0 留白，极强段落呼吸感，配色克制（黑/白/深灰/细线），充满专业权威感。
    
    - **全局正文段落（最重要的呼吸感）**：千万不要生成大段粘连的文字！每一段文字必须使用 `<p style="margin:0 0 24px 0; line-height:2; color:#2c3e50; font-size:16px; letter-spacing:0.8px; text-align:justify;">段落内容...</p>` 包裹。
    - **专家引用/核心洞察框（极简克制）**：`<section style="margin:35px 0; padding:15px 0 15px 20px; border-left:3px solid #111; background-color:#FAFAFA; color:#555; font-size:15px; line-height:1.9;">引用或核心洞察...</section>`
    - **权威感小标题（去渐变，用纯粹的质感）**：`<section style="margin:50px 0 25px 0; border-bottom:1px solid #E5E5E5; padding-bottom:12px; display:flex; align-items:center;"><span style="display:inline-block; width:5px; height:18px; background-color:#111; margin-right:12px;"></span><strong style="font-size:19px; color:#111; letter-spacing:1.5px;">此处为小标题</strong></section>`
    - **专业词汇强调**：`<strong style="color:#000; font-weight:bold;">重点词</strong>` 或 `<span style="border-bottom:1px solid #111; padding-bottom:1px;">重点概念</span>`
    - **配图（带专属属性，两边顶格不留白）**：`<img peitu="true" src="[COVER_IMG_URL]" style="width:100%; display:block; margin:40px 0;">`
    
    【输出 JSON 格式（严格遵守）】
    {{
      "status": "APPROVED 或 REJECTED",
      "reject_reason": "如果被拒绝，用中文简述原因，如'中国读者缺乏背景认知'",
      "viral_title": "令人无法拒绝的深度中文主标题",
      "image_keyword": "English keywords for image generation (Minimalist, cinematic)",
      "seo_tags":["洞察", "思维模型", "破局"],
      "article_html": "不包含主标题，必须由上述 HTML 组件拼装而成的全文（注意两侧不要留任何 margin/padding，段落必须用带 marginBottom 的 p 标签包裹）"
    }}

    原文标题: {title_en}
    原文内容:
    {text_input}
    """

    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.6}
    }

    for current_model in TEXT_MODELS:
        print(f"      [Text AI] 调用模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            res = requests.post(url, json=payload, timeout=120)
            res_json = res.json()
            
            if 'candidates' in res_json:
                raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
                return json.loads(clean_json_string(raw_output))
            elif 'error' in res_json:
                 print(f"      [API Error]: {res_json['error'].get('message')}")
            
        except Exception as e:
            print(f"      [Text API Exception]: {e}")
            continue

    return None

# =================== 主程序流程 ===================

def main():
    if not os.path.exists('data'): os.makedirs('data')
    if not os.path.exists('images'): os.makedirs('images')
    
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 启动任务 | 文本首选: {TEXT_MODELS[0]} | 图像首选: {IMAGE_MODELS[0]}")

    for feed_url in FEEDS:
        print(f"\n🔍 扫描源: {feed_url}")
        try: 
            feed = feedparser.parse(feed_url)
        except: 
            print("   -> 解析失败，跳过")
            continue
            
        # ⚠️ 增大遍历范围，交给 AI 主编去优胜劣汰过滤不适合的文章
        for entry in feed.entries[:6]: 
            title = entry.get('title', 'Untitled')
            link = entry.get('link', '')
            print(f"  📝 处理: {title[:40]}...")
            
            # 1. 获取内容
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): continue
            
            # 2. 文本生成与 AI 预审
            article_res = ai_process_wechat_article(web_data['content'], title)
            if not article_res: continue
            
            # 拦截被 AI 主编判断为不符合中国读者口味的文章
            if article_res.get("status") == "REJECTED":
                print(f"    >>> 🚫 AI 拒稿: {article_res.get('reject_reason', '受众不匹配')}")
                continue
            
            # 3. 图像生成
            print("    >>> 🎨 请求 AI 生成高质量配图...")
            keyword = article_res.get("image_keyword", "minimalist editorial design")
            img_bytes = generate_ai_cover_image(keyword, article_res.get("viral_title"))
            
            cover_url = ""
            if img_bytes:
                safe_title = re.sub(r'[\\/*?:"<>|]', "", article_res.get("viral_title", "cover"))[:10]
                filename = f"{today_str}_{int(time.time())}_{safe_title}.jpg"
                filepath = os.path.join("images", filename)
                
                if crop_to_wechat_cover(img_bytes, filepath):
                    repo = os.getenv("GITHUB_REPOSITORY")
                    branch = os.getenv("GITHUB_REF_NAME", "main")
                    if repo:
                        file_url_path = filepath.replace('\\', '/')
                        cover_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_url_path}"
                    else:
                        cover_url = get_picsum_cover_url()
                    print("    >>> ✅ 配图生成与裁剪成功")
                else:
                    cover_url = get_picsum_cover_url()
            else:
                cover_url = get_picsum_cover_url()

            # 4. 组装极致专业 HTML
            raw_html = article_res.get("article_html", "")
            if "[COVER_IMG_URL]" in raw_html:
                content_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            else:
                content_html = f"<img peitu='true' src='{cover_url}' style='width:100%;display:block;margin:30px 0;'>{raw_html}"
            
            # SEO 标签优化 (极简黑框，国际化质感)
            seo_tags = article_res.get("seo_tags",[])
            tags_html = ""
            if seo_tags:
                tags_spans = "".join([f"<span style='display:inline-block;margin:0 10px 10px 0;padding:4px 12px;border:1px solid #DCDFE6;color:#606266;font-size:12px;letter-spacing:1px;'>{tag}</span>" for tag in seo_tags])
                tags_html = f"""
                <section style='margin:45px 0 20px 0;padding-top:20px;border-top:1px solid #E5E5E5;'>
                    <section style='font-size:13px;color:#999;margin-bottom:12px;text-transform:uppercase;letter-spacing:2px;'>TAGS / 标签</section>
                    <section>{tags_spans}</section>
                </section>
                """

            # 绝对 0 padding，完全撑满两侧的容器组装
            final_wechat_html = f"""
            <section style='margin:0;padding:0;background-color:#fff;width:100%;box-sizing:border-box;'>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;margin:0;padding:0;'>
                
                <!-- 核心正文容器，零边距，依靠 P 标签自身的属性支撑版面 -->
                <section style='padding:0;margin:0;'>
                    {content_html}
                    {tags_html}
                </section>
                
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;margin:0;padding:0;'>
            </section>
            """
            
            # 5. 保存结果
            final_results.append({
                "title": article_res.get("viral_title"),
                "url": link,
                "cover": cover_url,
                "wechat_html": minify_html(final_wechat_html),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)
            
            print(f"    >>> 💾 数据已保存 ({len(final_results)} 篇)")
            time.sleep(5) 

    print(f"\n🎉 任务圆满完成，共筛选并生成 {len(final_results)} 篇爆款深度文章。")

if __name__ == "__main__":
    main()
