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

# 2. 文本模型矩阵 (自动轮询兜底)
TEXT_MODELS =[
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-flash"
]

# 3. 图像模型矩阵 (自动轮询兜底)
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
            # 图片太高，上下裁剪
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            bottom = top + new_h
            image = image.crop((0, top, w, bottom))
        elif current_ratio > target_ratio:
            # 图片太宽，左右裁剪
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
    """
    使用 Gemini API 生成配图 (支持多模型轮询兜底)
    """
    if not GEMINI_API_KEY: return None

    prompt = f"Generate a high-quality, photorealistic image. Concept: {keyword}. Context: {title}. Style: Cinematic lighting, 8k resolution, highly detailed, aesthetic. No text."
    
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents":[{
            "parts":[
                {"text": prompt}
            ]
        }]
    }
    
    for current_model in IMAGE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            print(f"      [Image API] 尝试调用图像模型: {current_model} ...")
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res_json = res.json()
            
            if "candidates" in res_json and res_json["candidates"]:
                parts = res_json["candidates"][0].get("content", {}).get("parts",[])
                for part in parts:
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    if inline_data:
                        b64_data = inline_data.get("data")
                        if b64_data:
                            return base64.b64decode(b64_data)
            
            print(f"      [Image API Fail]: 模型 {current_model} 未返回合法图片. 响应: {str(res_json)[:150]}")

        except Exception as e:
            print(f"[Image API Exception]: 模型 {current_model} 发生异常: {e}")
            
        if current_model != IMAGE_MODELS[-1]:
             print(f"      ⚠️ 尝试切换下一个备用图像模型...")
        
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
    
    text_input = content_text[:20000]
    
    prompt = f"""
    【角色】你是一个拥有百万读者的深度知识类公众号主理人及高级排版大师。
    【任务】将以下文章改写为一篇深度的中文推文，并附带极具视觉冲击力的高级排版。
    
    【核心要求】
    1. **拒绝AI味**：不要用“综上所述”、“总之”等词。像老朋友聊天一样自然，有洞察力。
    2. **结构**：[引子痛点] -> [核心认知拆解] ->[行动/思维破局]。
    3. **不需要开头标题**：排版中绝对不要生成开头的大标题（因为外层已有标题），开头直接进入引子正文。
    4. **高级排版（视觉冲击）**：必须使用丰富的 HTML 样式，避免大段枯燥的纯文本。灵活组合以下提供的排版模板。
    5. **图片占位**：必须在引子之后、核心正文之前，插入且仅插入一次图片占位符 `[COVER_IMG_URL]`。
    6. **标签提取**：提取 3-5 个用于 SEO 的精准中文关键词。
    
    【HTML 排版规范（必须严格组合使用这些组件！）】
    - **全局容器**：`<section style="padding:15px;line-height:1.8;color:#333;font-size:16px;letter-spacing:1px;text-align:justify;">`
    - **痛点/金句引用块**：`<section style="padding:16px 20px;margin:20px 0;background-color:#F5F7FA;border-left:4px solid #2C4CE0;border-radius:0 8px 8px 0;color:#555;font-size:15px;">`
    - **精美小标题**：`<section style="margin:35px 0 20px 0;"><section style="display:inline-block;padding:6px 16px;background:linear-gradient(90deg, #2C4CE0 0%, #506DF0 100%);color:#fff;border-radius:20px;font-weight:bold;font-size:16px;box-shadow:0 4px 10px rgba(44,76,224,0.2);">01 / 小标题内容</section></section>`
    - **重点文字划线/高亮**：`<span style="color:#2C4CE0;font-weight:bold;">重点文字</span>` 或 `<span style="border-bottom:2px solid #2C4CE0;padding-bottom:2px;">划线文字</span>`
    - **图片格式（注意带有 peitu 属性）**：`<img peitu="true" src="[COVER_IMG_URL]" style="width:100%;display:block;margin:30px 0;border-radius:8px;box-shadow:0 4px 15px rgba(0,0,0,0.08);">`
    
    【输出 JSON 格式】
    {{
      "status": "APPROVED",
      "viral_title": "中文主标题(用于推文标题字段)",
      "image_keyword": "English keywords for image generation",
      "script_text": "推文纯文本摘要...",
      "seo_tags":["认知", "破局", "AI未来"],
      "article_html": "不包含主标题、但富含高级排版的完整 HTML 正文"
    }}

    原文标题: {title_en}
    原文内容:
    {text_input}
    """

    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.7}
    }

    for current_model in TEXT_MODELS:
        print(f"[Text AI] 正在调用文本模型: {current_model} ...")
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
            print(f"[Text API Exception]: {e}")
            continue

    return None

# =================== 主程序流程 ===================

def main():
    if not os.path.exists('data'): os.makedirs('data')
    if not os.path.exists('images'): os.makedirs('images')
    
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 启动任务 | 文本模型矩阵: {TEXT_MODELS} | 图像模型矩阵: {IMAGE_MODELS}")

    for feed_url in FEEDS:
        print(f"\n🔍 扫描源: {feed_url}")
        try: 
            feed = feedparser.parse(feed_url)
        except: 
            print("   -> 解析失败，跳过")
            continue
            
        for entry in feed.entries[:2]: 
            title = entry.get('title', 'Untitled')
            link = entry.get('link', '')
            print(f"  📝 处理: {title[:40]}...")
            
            # 1. 获取内容
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): continue
            
            # 2. 文本生成
            article_res = ai_process_wechat_article(web_data['content'], title)
            if not article_res or article_res.get("status") != "APPROVED": continue
            
            # 3. 图像生成
            print("    >>> 🎨 请求 AI 生成配图...")
            keyword = article_res.get("image_keyword", "abstract art")
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
                print("    >>> ⚠️ 图像模型矩阵全线失败，使用静态兜底图")
                cover_url = get_picsum_cover_url()

            # 4. 组装高级排版 HTML
            
            # 4.1 注入主图片 (注意这里的 img 标签也加上了 peitu 属性，做容错处理)
            raw_html = article_res.get("article_html", "")
            if "[COVER_IMG_URL]" in raw_html:
                content_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            else:
                # 容错：如果 AI 没有按格式输出，我们手动在最前插入带有 peitu 属性的图片
                content_html = f"<img peitu='true' src='{cover_url}' style='width:100%;display:block;margin:20px 0;border-radius:8px;box-shadow:0 4px 15px rgba(0,0,0,0.08);'>{raw_html}"
            
            # 4.2 构建底部 SEO 标签区域
            seo_tags = article_res.get("seo_tags",[])
            tags_html = ""
            if seo_tags:
                tags_spans = "".join([f"<span style='display:inline-block;margin-right:12px;margin-bottom:10px;padding:5px 14px;background-color:#F0F2F5;color:#555;border-radius:20px;font-size:13px;letter-spacing:1px;'>#{tag}</span>" for tag in seo_tags])
                tags_html = f"""
                <section style='margin:40px 15px 20px 15px;padding-top:25px;border-top:1px dashed #E4E7ED;'>
                    <section style='font-size:14px;color:#909399;margin-bottom:15px;font-weight:bold;'>🏷️ 文章标签</section>
                    <section>{tags_spans}</section>
                </section>
                """

            # 4.3 包装固定的顶部/底部动态 GIF 及全文容器
            # 这里的顶部和底部 img 标签 *没有* peitu 属性，以做区分
            final_wechat_html = f"""
            <section style='margin:0;padding:0;background-color:#fff;'>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
                <section style='padding:0;'>
                    {content_html}
                    {tags_html}
                </section>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
            </section>
            """
            
            # 5. 保存
            final_results.append({
                "title": article_res.get("viral_title"),
                "url": link,
                "cover": cover_url,
                "wechat_html": minify_html(final_wechat_html),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)
            
            print("    >>> 💾 数据已保存")
            time.sleep(5) 

    print(f"\n🎉 所有任务完成，共生成 {len(final_results)} 篇文章。")

if __name__ == "__main__":
    main()
