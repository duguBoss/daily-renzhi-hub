import hashlib
import json
import os
import re
import time
from datetime import datetime
from html import unescape
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import requests

try:
    import feedparser  # type: ignore
except ImportError:
    feedparser = None


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

MAX_PROCESS_PER_RUN = 5
HISTORY_FILE = "data/processed_history.json"
MAX_HISTORY_PER_FEED = 1000
MAX_GLOBAL_FINGERPRINTS = 5000

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
    "gemini-2.5-flash",
]

URL_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "spm",
    "from",
    "source",
    "ref",
    "ref_src",
    "ref_url",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
}

SOURCE_BLOCKLIST = [
    "ycombinator.com/blog/feed",
]

CONTENT_BLOCK_PATTERNS = [
    r"\by\s*combinator\b",
    r"\byc\b",
    r"\bdemo day\b",
    r"\bstartup school\b",
    r"\bseed round\b",
    r"\bseries [abc]\b",
    r"\bpaul graham\b",
]

CN_STYLE_BLOCK_PATTERNS = [
    r"\byc\b",
    r"\by\s*combinator\b",
    r"\bdemo day\b",
    r"\bstartup school\b",
]


class SimpleFeedResult:
    def __init__(self, entries=None):
        self.entries = entries or []


def ensure_data_dir():
    if not os.path.exists("data"):
        os.makedirs("data")


def parse_feed(feed_url: str):
    if feedparser is not None:
        return feedparser.parse(feed_url)

    try:
        response = requests.get(feed_url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return SimpleFeedResult([])

    entries = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="") or ""
        link = item.findtext("link", default="") or ""
        entries.append({"title": title.strip(), "link": link.strip()})

    if not entries:
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//atom:entry", namespace):
            title = item.findtext("atom:title", default="", namespaces=namespace) or ""
            link = ""
            for link_node in item.findall("atom:link", namespace):
                href = link_node.attrib.get("href", "").strip()
                rel = link_node.attrib.get("rel", "alternate").strip()
                if href and rel in {"alternate", ""}:
                    link = href
                    break
            entries.append({"title": title.strip(), "link": link})

    return SimpleFeedResult(entries)


def normalize_url(raw_url: str) -> str:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""

    parts = urlsplit(raw_url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = re.sub(r"/+", "/", parts.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in URL_TRACKING_PARAMS:
            continue
        query_items.append((key, value))

    query_items.sort()
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = text.replace("\u200b", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def article_fingerprint(title: str, content: str) -> str:
    normalized_title = normalize_text(title).lower()
    normalized_content = normalize_text(content).lower()
    normalized_content = re.sub(r"https?://\S+", " ", normalized_content)
    normalized_content = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized_content)
    normalized_content = re.sub(r"\s+", " ", normalized_content).strip()
    base = f"{normalized_title}\n{normalized_content[:1800]}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def load_history():
    ensure_data_dir()
    default_data = {"version": 2, "feeds": {}, "fingerprints": []}

    if not os.path.exists(HISTORY_FILE):
        return default_data

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default_data

    if isinstance(data, list):
        return default_data

    if "feeds" in data or "fingerprints" in data:
        feeds = data.get("feeds", {})
        fingerprints = data.get("fingerprints", [])
        if not isinstance(feeds, dict):
            feeds = {}
        if not isinstance(fingerprints, list):
            fingerprints = []
        return {"version": 2, "feeds": feeds, "fingerprints": fingerprints}

    if isinstance(data, dict):
        migrated = {}
        for feed_url, url_list in data.items():
            if not isinstance(url_list, list):
                continue
            migrated[feed_url] = [normalize_url(url) for url in url_list if normalize_url(url)]
        return {"version": 2, "feeds": migrated, "fingerprints": []}

    return default_data


def save_history(history):
    ensure_data_dir()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def is_processed(feed_url: str, article_url: str, fingerprint: str, history: dict) -> bool:
    feeds = history.get("feeds", {})
    normalized = normalize_url(article_url)
    if normalized and normalized in feeds.get(feed_url, []):
        return True
    if fingerprint and fingerprint in history.get("fingerprints", []):
        return True
    return False


def add_to_history(feed_url: str, article_url: str, fingerprint: str, history: dict):
    feeds = history.setdefault("feeds", {})
    normalized = normalize_url(article_url)

    if feed_url not in feeds:
        feeds[feed_url] = []

    if normalized and normalized not in feeds[feed_url]:
        feeds[feed_url].append(normalized)

    if len(feeds[feed_url]) > MAX_HISTORY_PER_FEED:
        feeds[feed_url] = feeds[feed_url][-MAX_HISTORY_PER_FEED:]

    fingerprints = history.setdefault("fingerprints", [])
    if fingerprint and fingerprint not in fingerprints:
        fingerprints.append(fingerprint)

    if len(fingerprints) > MAX_GLOBAL_FINGERPRINTS:
        history["fingerprints"] = fingerprints[-MAX_GLOBAL_FINGERPRINTS:]


def get_picsum_cover_url(width=800, height=340):
    return f"https://picsum.photos/{width}/{height}?random={int(time.time())}"


def get_full_content(url):
    headers = {"Accept": "application/json"}
    target_url = normalize_url(url)
    try:
        response = requests.get(f"https://r.jina.ai/http://{target_url.split('://', 1)[1]}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get("data", {})
    except Exception:
        return None
    return None


def clean_json_string(raw_text):
    text = (raw_text or "").strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def minify_html(html_str):
    if not html_str:
        return ""
    html_str = html_str.replace("\n", "").replace("\r", "").replace("\t", "")
    html_str = re.sub(r">\s+<", "><", html_str)
    return html_str.strip()


def matches_any_pattern(text: str, patterns: List[str]) -> bool:
    haystack = (text or "").lower()
    return any(re.search(pattern, haystack, flags=re.I) for pattern in patterns)


def should_skip_feed(feed_url: str) -> bool:
    normalized = normalize_url(feed_url)
    return any(blocked in normalized for blocked in SOURCE_BLOCKLIST)


def should_filter_article(title: str, content_text: str, source_url: str) -> Tuple[bool, str]:
    combined = " ".join([title or "", content_text or "", source_url or ""])
    if matches_any_pattern(combined, CONTENT_BLOCK_PATTERNS):
        return True, "内容偏美国创业圈/YC 语境，不适合中文科技日报"
    return False, ""


def validate_cn_output(article_res: dict) -> Tuple[bool, str]:
    viral_title = article_res.get("viral_title", "")
    article_html = article_res.get("article_html", "")
    seo_tags = " ".join(article_res.get("seo_tags", []) or [])
    combined = " ".join([viral_title, article_html, seo_tags])
    if matches_any_pattern(combined, CN_STYLE_BLOCK_PATTERNS):
        return False, "改写结果仍残留 YC/硅谷创业黑话"
    return True, ""


def ai_process_wechat_article(content_text, title_en, source_url=""):
    if not content_text or not GEMINI_API_KEY:
        return None

    text_input = normalize_text(content_text)[:25000]
    prompt = f"""
你是一家顶级中文科技与商业媒体的主编，负责把英文长文改写成适合中国读者在微信公众号阅读的深度文章。

必须遵守以下规则：
1. 先判断是否值得写。若文章主题过于私人化、过于冷门、强依赖美国本土语境，或主要围绕 YC、Demo Day、硅谷融资八卦、美国创业圈黑话，直接返回 REJECTED。
2. 只有包含普适认知、科技趋势、商业洞察、社会观察、思维模型的内容，才返回 APPROVED。
3. APPROVED 时，全文必须“中文化”处理：
   - 用简体中文自然表达，不能保留英文写作腔。
   - 国外机构、人名、概念首次出现时，要给出面向中国读者的简短解释。
   - 不要把 YC、Demo Day、Paul Graham、硅谷黑话当作默认背景知识。
   - 如果原文例子太美国化，要主动替换成中国读者能理解的解释方式；无法替换时，弱化细节，保留核心观点。
4. 不要输出“YC”“Y Combinator”“Demo Day”“Startup School”等词；如果文章离不开这些词，应该直接 REJECTED。
5. 标题必须是中文新媒体标题，但不能低质夸张。
6. 开头第一段要有钩子，然后插入一次 [COVER_IMG_URL]。
7. 只允许输出 JSON，不要输出解释。

HTML 组件库：
- 正文段落：<p style="margin:0 0 24px 0; line-height:2; color:#2c3e50; font-size:16px; letter-spacing:0.8px; text-align:justify;">...</p>
- 金句/引用：<section style="margin:35px 0; padding:15px 0 15px 20px; border-left:3px solid #111; background-color:#FAFAFA; color:#555; font-size:15px; line-height:1.9;">...</section>
- 小标题：<section style="margin:50px 0 25px 0; border-bottom:1px solid #E5E5E5; padding-bottom:12px; display:flex; align-items:center;"><span style="display:inline-block; width:5px; height:18px; background-color:#111; margin-right:12px;"></span><strong style="font-size:19px; color:#111; letter-spacing:1.5px;">...</strong></section>
- 强调：<strong style="color:#000; font-weight:bold;">...</strong>

输出 JSON 格式：
{{
  "status": "APPROVED 或 REJECTED",
  "reject_reason": "中文理由",
  "viral_title": "中文标题",
  "seo_tags": ["标签1", "标签2"],
  "article_html": "HTML内容"
}}

原文链接: {source_url}
原文标题: {title_en}
原文内容:
{text_input}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.75,
        },
    }

    for current_model in TEXT_MODELS:
        print(f"      [Text AI] 调用模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, json=payload, timeout=120)
            res_json = res.json()
            if "candidates" in res_json:
                data = json.loads(clean_json_string(res_json["candidates"][0]["content"]["parts"][0]["text"]))
                return data
            if "error" in res_json:
                print(f"      [API Error]: {res_json['error'].get('message')}")
        except Exception as e:
            print(f"      [Text API Exception]: {e}")
    return None


def append_output(output_file: str, article: dict):
    existing_data = []
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    existing_data.append(article)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)


def main():
    ensure_data_dir()
    history = load_history()
    success_count = 0
    today_str = datetime.now().strftime("%Y%m%d")
    output_file = f"data/wechat_ready_{today_str}.json"

    print(f"🚀 启动任务 | 限制生成数: {MAX_PROCESS_PER_RUN} | 历史记录: URL规范化 + 内容指纹去重")

    for feed_url in FEEDS:
        if success_count >= MAX_PROCESS_PER_RUN:
            print(f"\n🛑 已达到单次运行上限 ({MAX_PROCESS_PER_RUN} 篇)，结束抓取。")
            break

        if should_skip_feed(feed_url):
            print(f"\n⛔ 跳过源: {feed_url} | 原因: 源本身偏 YC/美国创业圈")
            continue

        print(f"\n🔍 扫描源: {feed_url}")
        try:
            feed = parse_feed(feed_url)
        except Exception:
            print("   -> 解析失败，跳过")
            continue

        for entry in feed.entries[:6]:
            if success_count >= MAX_PROCESS_PER_RUN:
                break

            title = entry.get("title", "Untitled")
            raw_link = entry.get("link", "")
            link = normalize_url(raw_link)
            if not link:
                continue

            web_data = get_full_content(link)
            if not web_data or not web_data.get("content"):
                continue

            content_text = web_data.get("content", "")
            fingerprint = article_fingerprint(title, content_text)

            if is_processed(feed_url, link, fingerprint, history):
                print(f"  ⏭️ [跳过] URL或内容已处理: {title[:24]}...")
                continue

            should_filter, reason = should_filter_article(title, content_text, link)
            if should_filter:
                print(f"  🚫 [过滤] {title[:24]}... | {reason}")
                add_to_history(feed_url, link, fingerprint, history)
                save_history(history)
                continue

            print(f"  📝 [处理] 新发现: {title[:30]}...")
            article_res = ai_process_wechat_article(content_text, title, link)
            if not article_res:
                continue

            add_to_history(feed_url, link, fingerprint, history)

            if article_res.get("status") == "REJECTED":
                print(f"    >>> 🚫 拒稿: {article_res.get('reject_reason')}")
                save_history(history)
                continue

            is_valid_output, output_reason = validate_cn_output(article_res)
            if not is_valid_output:
                print(f"    >>> 🚫 放弃: {output_reason}")
                save_history(history)
                continue

            print(f"    >>> ✨ 标题: {article_res.get('viral_title')}")
            cover_url = get_picsum_cover_url()

            raw_html = article_res.get("article_html", "")
            if "[COVER_IMG_URL]" in raw_html:
                content_html = raw_html.replace("[COVER_IMG_URL]", cover_url)
            else:
                content_html = f"<img peitu='true' src='{cover_url}' style='width:100%;display:block;margin:30px 0;'>{raw_html}"

            tags_html = ""
            seo_tags = article_res.get("seo_tags") or []
            if seo_tags:
                tags_spans = "".join(
                    [
                        f"<span style='display:inline-block;margin:0 10px 10px 0;padding:4px 12px;border:1px solid #DCDFE6;color:#606266;font-size:12px;'>{tag}</span>"
                        for tag in seo_tags
                    ]
                )
                tags_html = (
                    "<section style='margin:45px 0 20px 0;padding-top:20px;border-top:1px solid #E5E5E5;'>"
                    "<section style='font-size:13px;color:#999;margin-bottom:12px;text-transform:uppercase;'>TAGS</section>"
                    f"<section>{tags_spans}</section>"
                    "</section>"
                )

            final_wechat_html = f"""
            <section style='margin:0;padding:0;background-color:#fff;'>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
                <section style='padding:0;'>{content_html}{tags_html}</section>
                <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
            </section>
            """

            article = {
                "title": article_res.get("viral_title"),
                "url": link,
                "cover": cover_url,
                "wechat_html": minify_html(final_wechat_html),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            append_output(output_file, article)
            save_history(history)
            success_count += 1
            print("    >>> 💾 已保存")
            time.sleep(2)

    print(f"\n🎉 任务完成，本轮生成 {success_count} 篇。")


if __name__ == "__main__":
    main()
