import feedparser
import json
import os
import requests
import time
import re
from datetime import datetime

# 1. 配置
FEEDS =[
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

# 指定模型，推荐使用 gemini-1.5-flash 处理长文本和结构化输出
MODEL_NAME = "gemini-1.5-flash" 

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
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()

def minify_html(html_str):
    """将 HTML 压缩为一行，去除换行和多余空格"""
    if not html_str:
        return ""
    # 移除换行符和制表符
    html_str = html_str.replace('\n', '').replace('\r', '').replace('\t', '')
    # 移除 HTML 标签之间的多余空格 (例如 </div> <div> 变成 </div><div>)
    html_str = re.sub(r'>\s+<', '><', html_str)
    # 移除标签内或文本中连续的多余空格
    html_str = re.sub(r'\s{2,}', ' ', html_str)
    return html_str.strip()

def get_picsum_cover_url(width=800, height=600):
    """请求 picsum.photos 获得随机 4:3 横屏图片，并返回跳转后的真实最终地址"""
    req_url = f"https://picsum.photos/{width}/{height}"
    try:
        # stream=True 避免下载整个图片实体，只需要拿到 headers 和跳转后的 url 即可
        response = requests.get(req_url, allow_redirects=True, stream=True, timeout=10)
        final_url = response.url
        response.close()
        return final_url
    except Exception as e:
        print(f"      [Image Fetch Error]: {e}")
        return req_url # 失败则降级返回原始请求链接

def ai_process_wechat_article(content_text, title_en):
    """调用 Gemini 生成自由口播风格的公众号内容及直接可用的HTML排版"""
    if not content_text or not GEMINI_API_KEY:
        return None

    text_input = content_text[:12000] # 限制长度防止溢出

    prompt = f"""
    你是一个拥有百万粉丝的中文“播客/口播型知识博主”。擅长将枯燥的深度长文，转化为让人欲罢不能的爆款文章。
    你的文风特点是：直接、犀利、情绪饱满、像在跟好朋友面对面聊天一样自然（多用设问、短句、留白，少用生僻词）。
    
    【核心任务指令】
    1. 拒绝八股文和死板的结构！请按你最舒服、最引人入胜的口播节奏自由发挥，让文章像流水一样自然。不要让读者看出任何“AI模块化格式”的痕迹。
    2. 基于原标题 "{title_en}"，创作一个极具吸引力、直击痛点的中文口播标题。
    3. 提取核心图片关键词（英文）。
    4. 【重点】在 `article_html` 字段中，直接输出完整的微信公众号排版 HTML 代码。
    
    【HTML排版与写作要求】
    请以我提供的以下 HTML 样式作为你的“排版组件库”。在自由写文章时，根据文字的情绪节奏，自然地应用这些 HTML 标签：

    <section style="margin:0;padding:0;background-color:#fff;font-family:-apple-system-font,BlinkMacSystemFont,'Helvetica Neue','PingFang SC',sans-serif;letter-spacing:1.5px;color:#333;text-align:justify;">
    <!-- 顶部动图 (必须保留在代码最顶部) -->
    <img src="https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif" style="width:100%;display:block;vertical-align:top;margin:0;padding-bottom:15px;">
    
    <!-- 开篇引入 (仅在开头使用一次，分离出首个汉字用作放大) -->
    <section style="display:block;padding:0 0 15px;overflow:hidden;">
        <section style="float:left;font-size:48px;line-height:0.9;margin-top:4px;padding-right:8px;font-weight:bold;color:#b77a56;font-family:Georgia,serif;">[首]</section>
        <section style="font-size:16px;line-height:1.8;">[紧接首字的自然开篇叙述，迅速拉升听众代入感...]</section>
    </section>

    <!-- 普通口播段落 (主要篇幅，像聊天一样，可多次使用) -->
    <section style="display:block;font-size:16px;line-height:1.8;padding-bottom:15px;">[你的自由行文...]</section>

    <!-- 犀利观点/小标题 (用于内容转折或升华时) -->
    <section style="display:block;font-size:20px;font-weight:bold;color:#111;line-height:1.4;padding-bottom:8px;">[小标题或惊人观点]</section>

    <!-- 插入图片位置 (请在文中合适的转折处或重点处，原样插入此占位符代码，稍后系统会自动替换配图) -->
    <img src="[COVER_IMG_URL]" style="width:100%;display:block;vertical-align:top;padding-bottom:15px;background-color:#f5f5f5;min-height:200px;" alt="情绪配图">

    <!-- 金句划重点 (全篇使用1-2次即可，提取最具穿透力的一句话) -->
    <section style="display:block;text-align:center;padding:15px 0;">
        <svg width="100%" height="1" style="display:block;background:#f0f0f0;"></svg>
        <section style="padding:10px 0;line-height:1.6;font-size:18px;font-weight:bold;color:#b77a56;">“[扎心金句]”</section>
        <svg width="100%" height="1" style="display:block;background:#f0f0f0;"></svg>
    </section>

    <!-- 结尾互动与标签 (文章尾部使用) -->
    <section style="display:block;text-align:center;font-size:14px;color:#999;line-height:1.8;font-style:italic;padding:15px 0;">[向听众抛出一个开放式问题，留有余味]</section>
    <section style="display:block;text-align:center;font-size:14px;color:#b77a56;line-height:1.6;padding-bottom:20px;letter-spacing:1px;font-weight:500;">[#提供3到5个带#号的关键词]</section>
    <section style="display:block;text-align:center;font-size:10px;color:#ccc;letter-spacing:2px;margin-bottom:5px;">END / 硬核主编</section>
    
    <!-- 底部动图 (必须保留在代码最底部) -->
    <img src="https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif" style="width:100%;display:block;vertical-align:top;padding-top:0px;">
    </section>

    【输出格式要求】
    必须输出严格的 JSON 字符串，包含以下字段：
    - status: "APPROVED" 或 "REJECT" （若含黄暴敏则REJECT）
    - viral_title: "爆款标题"
    - image_keyword: "用于搜索配图的单个英文单词"
    - article_html: "包含完整微信排版代码的文章正文（将你的文章写在上述HTML标签内）"

    文章原文：
    {text_input}
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
        
    payload = {
        "contents":[{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.85 # 增强口播行文的网感和流畅度
        }
    }

    try:
        res = requests.post(url, json=payload, timeout=90)
        res_data = res.json()
        raw_output = res_data['candidates'][0]['content']['parts'][0]['text']
        clean_json = clean_json_string(raw_output)
        return json.loads(clean_json)
    except Exception as e:
        print(f"      [AI Error]: {e}")
        return None

def main():
    if not os.path.exists('data'): os.makedirs('data')
    
    final_results =[]
    today_str = datetime.now().strftime('%Y%m%d')

    for feed_url in FEEDS:
        print(f"\nScanning Feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:2]: # 每天每个源只取最新的2篇
            original_title = entry.get('title')
            link = entry.get('link')
            print(f"  - Processing: {original_title}")

            # 1. 深度抓取
            web_data = get_full_content(link)
            if not web_data or not web_data.get('content'):
                print("    >>> Jina Fetch Failed")
                continue

            # 2. AI 创作 (输出包含 HTML 排版的内容)
            article_res = ai_process_wechat_article(web_data['content'], original_title)
            
            if not article_res or article_res.get("status") == "REJECT":
                print("    >>> Skipped (Safety Filter or Error)")
                continue

            # 3. 视觉处理：提取真实图片替换占位符
            raw_imgs = web_data.get('images',[])
            final_images =[img for img in raw_imgs if isinstance(img, str) and img.startswith('http')][:2] if isinstance(raw_imgs, list) else[]
            
            # 优先使用原文图片，没有则使用 picsum 获取 4:3 (800x600) 横屏图的真实地址
            if final_images:
                cover_url = final_images[0]
            else:
                cover_url = get_picsum_cover_url(800, 600)
                print(f"    >>> Fetched Picsum Cover: {cover_url}")
            
            # 4. 提取生成的 HTML 并进行【变量替换】与【极度压缩】
            raw_html = article_res.get("article_html", "")
            final_html = raw_html.replace("[COVER_IMG_URL]", cover_url) # 注入带有真实静态链接的图片
            compressed_html = minify_html(final_html) # 压缩成单行无缝代码
            
            # 5. 封装最终数据到 JSON 字典
            item = {
                "title": article_res.get("viral_title"),
                "original_title": original_title,
                "url": link,
                "cover": cover_url, # 保存跳转后的静态图片链接到 JSON
                "publish_date": entry.get('published', datetime.now().strftime("%Y-%m-%d")),
                "wechat_html": compressed_html  # 直接存入压缩好的完整微信代码
            }
            final_results.append(item)
            
            print(f"    >>> Successfully processed and compressed HTML")
            time.sleep(5) # 保护 API 频率限制

    # 6. 保存所有的最终数据到单个 JSON 文件
    if final_results:
        output_file = f"data/wechat_ready_{today_str}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            # indent=2 保证外部 JSON 结构可读，但 wechat_html 字段内的值是干净的一行字符串
            json.dump(final_results, f, ensure_ascii=False, indent=2)
            
        print(f"\n✅ 任务完成！共处理 {len(final_results)} 篇文章。")
        print(f"💡 数据已统一保存到: {output_file}")
        print("💡 您可以直接读取 JSON 中 `wechat_html` 字段的数据（它已经去除了所有空格、换行，非常适合通过 API 发送）。")

if __name__ == "__main__":
    main()
