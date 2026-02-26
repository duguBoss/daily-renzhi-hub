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

# 2. 备选模型矩阵 (默认首选 gemini-3-flash-preview)
MODELS =[
    "gemini-3-flash-preview",    
    "gemini-3.1-pro-preview",    
    "gemini-3-pro-preview"       
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =================== 图片处理模块 ===================

def crop_to_wechat_cover(img_data, output_path):
    """将生成的 16:9 图片智能居中裁剪为微信标准的 2.35:1 比例"""
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
        
    image.save(output_path, "JPEG", quality=90)

def generate_ai_cover_image(keyword, title):
    """召唤最新版 imagen-3.0 生图模型"""
    prompt = f"A highly aesthetic, cinematic, wide-angle illustration for an article titled '{title}'. Core visual concept: {keyword}. No text, no words, no letters in the image. Highly detailed, masterpiece."
    
    # 使用 Imagen 3 模型节点
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GEMINI_API_KEY}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "16:9" # 原生支持 16:9，由 Python 裁剪为 2.35:1
        }
    }
    
    try:
        res = requests.post(url, json=payload, timeout=60)
        res_json = res.json()
        
        # 解析 Base64 数据
        if 'predictions' in res_json and res_json['predictions']:
            b64 = res_json['predictions'][0].get('bytesBase64Encoded')
            if b64: return base64.b64decode(b64)
            
    except Exception as e:
        print(f"      [Image API Error]: {e}")
        
    return None

def get_picsum_cover_url(width=800, height=340):
    """兜底备用：获取 Picsum 近似 2.35:1 (800x340) 的静态高清配图"""
    req_url = f"https://picsum.photos/{width}/{height}?blur=2" # 稍微加点模糊增加高级感
    try:
        response = requests.get(req_url, allow_redirects=True, stream=True, timeout=10)
        final_url = response.url
        response.close()
        return final_url
    except: return req_url

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
    html_str = re.sub(r'\s{2,}', ' ', html_str)
    return html_str.strip()

def ai_process_wechat_article(content_text, title_en):
    if not content_text or not GEMINI_API_KEY: return None
    text_input = content_text[:18000] 

    prompt = f"""
    【最高指令：内容安全审查】
    审查原文内容。如果涉及：1.政治争端/敏感历史；2.宗教宣扬/贬低；3.残暴血腥；4.色情低俗；5.极端性别或文化对立。
    直接且仅返回：{{"status": "REJECT", "reason": "涉及[敏感类型]"}}，不要生成其他内容！

    如果判定文章安全，请执行【创作任务】。

    【创作任务】
    你是一个拥有百万粉丝的“顶流知识播客主理人”。请写一篇深度爆款文案。
    
    1. **去AI化与反八股**：严禁使用“总之、综上所述、首先其次最后”等词。
    2. **语感**：像老朋友喝咖啡时深度对谈，多用反问和类比。
    3. **长尾长青**：切勿使用“今天、最近”等带有时间局限性的词汇。
    4. **结构与配图（硬性要求）**：引子痛点 -> 深度拆解 -> 认知破局。**必须**在正文中间自然过渡的地方，插入图片占位符 `<img src="[COVER_IMG_URL]" ...>`！
    5. **零边距排版**：所有文字必须零边距，占满屏幕。

    【HTML 样式组件（必须严格复制 style）】
    - 外部容器：<section style="margin:0;padding:0;width:100%;box-sizing:border-box;background-color:#fff;">
    - 正文配图（请务必在正文中间插入一次）：<img src="[COVER_IMG_URL]" style="width:100%;display:block;margin:25px 0;padding:0;">
    - 正文文字（零边距全宽）：<section style="font-size:16px;line-height:1.8;margin:0 0 20px 0;padding:0;text-align:justify;color:#333;width:100%;box-sizing:border-box;">[内容]</section>
    - 强调标题：<section style="font-size:19px;font-weight:bold;color:#111;margin:0 0 12px 0;padding:0;letter-spacing:1px;width:100%;">[短句标题]</section>
    - 扎心金句：<section style="text-align:center;margin:30px 0;padding:25px 0;color:#b77a56;font-size:20px;font-weight:600;line-height:1.5;border-top:1px solid #f0f0f0;border-bottom:1px solid #f0f0f0;width:100%;box-sizing:border-box;">“[一句话扎心]”</section>

    【输出 JSON 格式（必须严格遵守）】
    {{
      "status": "APPROVED",
      "viral_title": "极简极具吸引力的中文标题",
      "image_keyword": "用于生成配图的【纯英文】提示词（画面核心元素，无文字描述）",
      "script_text": "此处是1000字以上的纯文字推文脚本...",
      "article_html": "<section style='margin:0;padding:0;width:100%;box-sizing:border-box;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;margin:0;padding:0;'><section style='margin:0;padding:0;width:100%;box-sizing:border-box;'><!-- 正文流，务必在此处插入 [COVER_IMG_URL] 占位符 -->[CONTENT]</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;margin:0;padding:0;'></section>"
    }}

    待分享原文（原标题: {title_en}）:
    {text_input}
    """

    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.8} 
    }

    for current_model in MODELS:
        print(f"      [AI] 召唤文本大模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            res = requests.post(url, json=payload, timeout=120)
            if res.status_code == 429:
                print(f"      [Rate Limit 429]: 频率超限，切换备用模型...")
                time.sleep(2)
                continue 
                
            res_json = res.json()
            if 'error' in res_json:
                print(f"      [API Error]: {res_json['error'].get('message')}，尝试切换...")
                continue
                
            if 'candidates' not in res_json:
                if 'promptFeedback' in res_json: print(f"      [API Blocked]: 安全底线被拦截")
                return None
                
            raw_output = res_json['candidates'][0]['content']['parts'][0]['text']
            try:
                return json.loads(clean_json_string(raw_output))
            except json.JSONDecodeError:
                print(f"      [Parse Error]: JSON 解析失败，尝试下一个模型...")
                continue
                
        except Exception as e:
            print(f"      [Exception]: 异常 -> {e}，尝试切换...")
            continue

    return None

# =================== 主程序流程 ===================

def main():
    if not os.path.exists('data'): os.makedirs('data')
    if not os.path.exists('images'): os.makedirs('images')
    
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 开始扫描 {len(FEEDS)} 个内容节点 (全屏零边距 + 强制配图模式)...\n")

    for feed_url in FEEDS:
        print(f"\n[{feed_url}]")
        try: feed = feedparser.parse(feed_url)
        except: continue
        
        for entry in feed.entries[:3]:
            original_title = entry.get('title', 'Untitled')
            link = entry.get('link', '')
            print(f"  📝 查阅: {original_title[:50]}...")
            
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'): continue

            # 1. 生成文章内容
            article_res = ai_process_wechat_article(web_data['content'], original_title)
            if not article_res or article_res.get("status") == "REJECT": continue

            # 2. 生成并处理专属 AI 封面/正文配图
            print("    >>> 🎨 正在召唤 Imagen 3 生成专属配图...")
            keyword = article_res.get("image_keyword", "abstract minimalist philosophy")
            img_bytes = generate_ai_cover_image(keyword, article_res.get("viral_title", original_title))
            
            if img_bytes:
                safe_title = re.sub(r'[\\/*?:"<>|]', "", article_res.get("viral_title", "cover")).strip()
                filename = f"{today_str}_{safe_title[:15]}_{int(time.time())}.jpg"
                filepath = os.path.join("images", filename)
                
                try:
                    # 裁剪为微信 2.35:1 比例
                    crop_to_wechat_cover(img_bytes, filepath)
                    
                    # 组装 GitHub Actions 自动化 raw 图床链接
                    repo = os.getenv("GITHUB_REPOSITORY")
                    branch = os.getenv("GITHUB_REF_NAME", "main")
                    if repo:
                        filepath_url = filepath.replace('\\', '/')
                        cover_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{filepath_url}"
                    else:
                        # 兜底：如果没跑在 Github 里，直接返回公共的 Picsum 链接，确保微信能粘贴显示
                        cover_url = get_picsum_cover_url(800, 340) 
                    print("    >>> 🖼️ AI 配图生成与 2.35:1 裁切成功！")
                except Exception as e:
                    print(f"      [Image Crop Error]: 裁切失败 -> {e}")
                    cover_url = get_picsum_cover_url(800, 340)
            else:
                print("    >>> ⚠️ AI 生图受限，自动切换至高清备用配图。")
                cover_url = get_picsum_cover_url(800, 340)

            # 3. HTML 排版：强制插入图片防漏机制 + 变量替换
            raw_html = article_res.get("article_html", "")
            
            # 【双保险防漏机制】：如果大模型忘记放入[COVER_IMG_URL]，我们强行在文章顶部 GIF 后注入配图！
            if "[COVER_IMG_URL]" not in raw_html:
                img_tag = f"<img src='{cover_url}' style='width:100%;display:block;margin:20px 0;padding:0;'>"
                # 寻找第一个正文区的开头并插入
                raw_html = raw_html.replace("<!-- 正文流 -->", f"<!-- 正文流 -->{img_tag}")
            else:
                raw_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
                
            compressed_html = minify_html(raw_html)
            
            # 4. 数据留存
            final_results.append({
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": link,
                "cover": cover_url,
                "script_text": article_res.get("script_text"),
                "wechat_html": compressed_html,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)
            
            print(f"    >>> ✅ 创作并实时保存成功！")
            time.sleep(15) 

    print("\n" + "="*50)
    if final_results:
        print(f"🎉 任务完成！共成功处理并保存了 {len(final_results)} 篇全屏排版的优质内容。")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
