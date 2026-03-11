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

MAX_PROCESS_PER_RUN = 4
CANDIDATE_POOL_TARGET = 10
MAX_ENTRIES_PER_FEED = 8
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
        response = requests.get(
            f"https://r.jina.ai/http://{target_url.split('://', 1)[1]}",
            headers=headers,
            timeout=30,
        )
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
        return True, "内容偏美国创业圈/YC语境，不适合中文科技日报"
    return False, ""


def validate_cn_output(article_res: dict) -> Tuple[bool, str]:
    viral_title = article_res.get("viral_title", "")
    article_html = article_res.get("article_html", "")
    seo_tags = " ".join(article_res.get("seo_tags", []) or [])
    combined = " ".join([viral_title, article_html, seo_tags])
    if matches_any_pattern(combined, CN_STYLE_BLOCK_PATTERNS):
        return False, "改写结果仍残留YC/硅谷创业黑话"
    return True, ""


def call_gemini_json(prompt: str, temperature: float = 0.75):
    if not GEMINI_API_KEY:
        return None

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": temperature,
        },
    }

    for current_model in TEXT_MODELS:
        print(f"      [Text AI] 调用模型: {current_model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, json=payload, timeout=120)
            res_json = res.json()
            if "candidates" in res_json:
                return json.loads(clean_json_string(res_json["candidates"][0]["content"]["parts"][0]["text"]))
            if "error" in res_json:
                print(f"      [API Error]: {res_json['error'].get('message')}")
        except Exception as e:
            print(f"      [Text API Exception]: {e}")
    return None


def build_selection_candidates(candidates: List[dict]) -> List[dict]:
    items = []
    for index, item in enumerate(candidates):
        items.append(
            {
                "id": index,
                "title": item["title"],
                "url": item["url"],
                "feed_url": item["feed_url"],
                "summary": normalize_text(item["content"])[:600],
                "content_preview": normalize_text(item["content"])[:2200],
            }
        )
    return items


def ai_select_daily_featured(candidates: List[dict]) -> List[dict]:
    if not candidates:
        return []

    if not GEMINI_API_KEY:
        return candidates[:MAX_PROCESS_PER_RUN]

    prompt = f"""
你是中文科技日报的总编。你的任务不是改写，而是从候选文章里精选出“今日最值得发的4篇”。

筛选原则：
1. 只看文章本身内容，不看来源名气，不看标题包装。
2. 优先选择对中文读者有信息增量的内容：科技趋势、商业洞察、社会观察、认知模型、方法论。
3. 优先选择有细节、有冲突、有对比、有反常识的内容，不要选空泛概念文。
4. 避免4篇都挤在同一个话题，尽量让题材分散。
5. 过滤强美国本土语境、硅谷创业圈黑话、私人碎碎念、冷门到无法转译的内容。
6. 如果两篇很像，只保留信息密度更高的一篇。

判断时参考这些可执行技巧：
- 开头是否自带一个具体观察、瞬间、场景。
- 文章是否先抓住情绪，再能落到一个清晰论点。
- 文中是否存在冲突、反差、代价、误区，而不是抽象正确话。
- 是否能让中文读者自然代入，而不是只能站在美国创业圈内部自嗨。

只返回JSON：
{{
  "selected_ids": [0, 1, 2, 3],
  "selection_reason": "中文总结，说明这4篇为什么值得发"
}}

候选文章：
{json.dumps(build_selection_candidates(candidates), ensure_ascii=False)}
"""

    result = call_gemini_json(prompt, temperature=0.35)
    if not isinstance(result, dict):
        return candidates[:MAX_PROCESS_PER_RUN]

    selected_ids = result.get("selected_ids", [])
    chosen = []
    seen = set()

    for item_id in selected_ids:
        if not isinstance(item_id, int):
            continue
        if item_id < 0 or item_id >= len(candidates):
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        chosen.append(candidates[item_id])
        if len(chosen) >= MAX_PROCESS_PER_RUN:
            break

    return chosen or candidates[:MAX_PROCESS_PER_RUN]


def ai_process_wechat_article(content_text, title_en, source_url=""):
    if not content_text or not GEMINI_API_KEY:
        return None

    text_input = normalize_text(content_text)[:25000]
    prompt = f"""
你是一家中文科技深度媒体的主编，要把英文文章改写成适合微信公众号发布的“每日精选”稿件。

先判断值不值得写：
1. 如果文章过于私人化、太冷门、强依赖美国本土语境，或主要围绕YC、Demo Day、美国创业圈黑话，直接返回REJECTED。
2. 只有包含普适认知、科技趋势、商业洞察、社会观察、思维模型的内容，才返回APPROVED。

APPROVED时必须遵守这些改写原则：
1. 立足原文内容本身，不要硬凹观点，不要为了爆款牺牲准确性。
2. 做彻底中国化表达：
   - 用简体中文自然表达，不能保留英文写作腔。
   - 国外机构、人名、概念首次出现时，要给出中国读者能秒懂的短解释。
   - 如果原文例子太美国化，要改写成中国读者能理解的解释方式；不能硬替换时，就弱化细节、保留核心道理。
3. 吸收这些写作技巧：
   - 开头优先“观察型开场”，直接写具体场景、反差或扎心瞬间，不要空话起手。
   - 先抓情绪核心，再点出智识论点；让读者先有画面，再明白道理。
   - 多用冲突、对比、反常识、细节，少用抽象总结。
   - 镜头朝向读者，让读者感觉“这事和我有关”。
   - 结尾要锋利，点破代价、误区或真正值得记住的一句话。
4. 去AI味：
   - 禁用这些词和表达：此外、至关重要、格局、关键、充满活力、深入探讨、值得注意的是。
   - 尽量避免这些句式：不仅...而且、不仅仅是...而是、与其说...不如说、三段排比。
   - 语言要像真人编辑聊天，口语化，但不要油腻。
5. 不要输出“YC”“Y Combinator”“Demo Day”“Startup School”等词；如果离不开这些词，应该直接REJECTED。
6. 标题必须是高点击中文标题，但不能标题党。
7. 开头钩子段落后插入一次[COVER_IMG_URL]。
8. 生成初稿后，先自检：开头是否具体，正文是否有冲突和细节，结尾是否锋利，全文是否有明显AI腔；任一不满足，就在内部重写后再输出。

HTML组件库：
- 正文段落：<p style="margin:0 0 24px 0; line-height:2; color:#2c3e50; font-size:16px; letter-spacing:0.8px; text-align:justify;">...</p>
- 金句/引用：<section style="margin:35px 0; padding:15px 0 15px 20px; border-left:3px solid #111; background-color:#FAFAFA; color:#555; font-size:15px; line-height:1.9;">...</section>
- 小标题：<section style="margin:50px 0 25px 0; border-bottom:1px solid #E5E5E5; padding-bottom:12px; display:flex; align-items:center;"><span style="display:inline-block; width:5px; height:18px; background-color:#111; margin-right:12px;"></span><strong style="font-size:19px; color:#111; letter-spacing:1.5px;">...</strong></section>
- 强调：<strong style="color:#000; font-weight:bold;">...</strong>

只返回JSON：
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
    return call_gemini_json(prompt, temperature=0.75)


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


def write_output(output_file: str, articles: List[dict]):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def build_final_article(article_res: dict, original_url: str) -> dict:
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

    return {
        "title": article_res.get("viral_title"),
        "url": original_url,
        "cover": cover_url,
        "wechat_html": minify_html(final_wechat_html),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_daily_featured": True,
    }


def main():
    ensure_data_dir()
    history = load_history()
    today_str = datetime.now().strftime("%Y%m%d")
    output_file = f"data/wechat_ready_{today_str}.json"
    daily_featured_file = "data/daily-news.json"
    candidate_pool = []
    generated_count = 0
    daily_featured_articles = []

    print(
        f"🚀 启动任务 | 候选池目标: {CANDIDATE_POOL_TARGET} | 每日精选: {MAX_PROCESS_PER_RUN} | 历史记录: URL规范化 + 内容指纹去重"
    )

    for feed_url in FEEDS:
        if len(candidate_pool) >= CANDIDATE_POOL_TARGET:
            print(f"\n🛑 候选池已足够 ({len(candidate_pool)} 篇)，停止继续抓取。")
            break

        if should_skip_feed(feed_url):
            print(f"\n⛔ 跳过源: {feed_url} | 原因: 源本身偏YC/美国创业圈")
            continue

        print(f"\n🔍 扫描源: {feed_url}")
        try:
            feed = parse_feed(feed_url)
        except Exception:
            print("   -> 解析失败，跳过")
            continue

        for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
            if len(candidate_pool) >= CANDIDATE_POOL_TARGET:
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

            candidate_pool.append(
                {
                    "feed_url": feed_url,
                    "title": title,
                    "url": link,
                    "content": content_text,
                    "fingerprint": fingerprint,
                }
            )
            print(f"  📥 [入池] 候选文章: {title[:30]}...")

    if not candidate_pool:
        print("\n🫥 没有可用候选文章，本轮结束。")
        return

    print(f"\n🧠 开始从 {len(candidate_pool)} 篇候选中筛选每日精选 {MAX_PROCESS_PER_RUN} 篇...")
    selected_candidates = ai_select_daily_featured(candidate_pool)

    for candidate in candidate_pool:
        add_to_history(candidate["feed_url"], candidate["url"], candidate["fingerprint"], history)
    save_history(history)

    for candidate in selected_candidates:
        print(f"\n📝 [生成] 精选文章: {candidate['title'][:36]}...")
        article_res = ai_process_wechat_article(candidate["content"], candidate["title"], candidate["url"])
        if not article_res:
            continue

        if article_res.get("status") == "REJECTED":
            print(f"    >>> 🚫 拒稿: {article_res.get('reject_reason')}")
            continue

        is_valid_output, output_reason = validate_cn_output(article_res)
        if not is_valid_output:
            print(f"    >>> 🚫 放弃: {output_reason}")
            continue

        article = build_final_article(article_res, candidate["url"])
        append_output(output_file, article)
        daily_featured_articles.append(article)
        generated_count += 1
        print(f"    >>> ✨ 标题: {article_res.get('viral_title')}")
        print("    >>> 💾 已保存")
        time.sleep(2)

    write_output(daily_featured_file, daily_featured_articles)
    print(f"\n📦 今日精选文件已更新: {daily_featured_file}")

    print(
        f"\n🎉 任务完成 | 候选入池 {len(candidate_pool)} 篇 | AI精选四篇候选 {len(selected_candidates)} 篇 | 实际生成 {generated_count} 篇。"
    )


if __name__ == "__main__":
    main()
