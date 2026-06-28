#!/usr/bin/env python3
"""
每日 AI & 科技新闻简报 - 抓取 + 推送飞书
运行于 GitHub Actions，每天中午 12:00 自动执行
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import feedparser

# ---------- 时区 ----------
TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")

# ---------- RSS 源 ----------
RSS_SOURCES = {
    # ----- 国内科技 -----
    "36氪": "https://36kr.com/feed",
    "虎嗅": "https://www.huxiu.com/rss/0.xml",
    "InfoQ 中文": "https://www.infoq.cn/feed",

    # ----- 国际科技媒体 -----
    "BBC Tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "CNN Tech": "https://rss.cnn.com/rss/cnn_tech.rss",
    "Reuters": "https://news.google.com/rss/search?q=site:reuters.com+technology+innovation+AI&hl=en-US&gl=US&ceid=US:en",
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Wired": "https://www.wired.com/feed/rss",
    "VentureBeat": "https://venturebeat.com/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",

    # ----- AI 专项 -----
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "MarkTechPost": "https://www.marktechpost.com/feed/",
    "arXiv cs.AI": "https://rss.arxiv.org/rss/cs.AI",

    # ----- 社区 & 产品 -----
    "HackerNews": "https://hnrss.org/frontpage",
    "Product Hunt": "https://www.producthunt.com/feed",
    "TLDR AI": "https://tldr.tech/api/rss/ai",
    "Ben's Bites": "https://bensbites.beehiiv.com/feed",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _parse_date(entry) -> Optional[datetime]:
    """尝试从 entry 中解析发布时间"""
    for attr in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, attr, None)
        if tp:
            try:
                return datetime(*tp[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


async def fetch_rss(session: aiohttp.ClientSession, name: str, url: str) -> list[dict]:
    """抓取单个 RSS 源，返回 [{title, summary, link, date}]"""
    items = []
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"  [!] {name} -> HTTP {resp.status}")
                return items
            text = await resp.text()
    except Exception as e:
        print(f"  [!] {name} -> {e}")
        return items

    try:
        feed = feedparser.parse(text)
    except Exception as e:
        print(f"  [!] {name} parse error -> {e}")
        return items

    for entry in feed.entries[:10]:
        published = _parse_date(entry)
        # 只取当天的
        if published and published.astimezone(TZ).strftime("%Y-%m-%d") != TODAY:
            continue
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()
        link = entry.get("link", "").strip()
        if not title:
            continue
        # 清理 HTML 标签
        summary = _strip_html(summary)[:200]
        items.append({
            "source": name,
            "title": title,
            "summary": summary,
            "link": link,
            "date": published.strftime("%H:%M") if published else "",
        })
    print(f"  [OK] {name} -> {len(items)} 条")
    return items


def _strip_html(text: str) -> str:
    """简单去掉 HTML 标签"""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def gather_news() -> list[dict]:
    """并发抓取所有 RSS 源"""
    print(f"📡 开始抓取新闻 ({TODAY})")
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_rss(session, name, url) for name, url in RSS_SOURCES.items()]
        results = await asyncio.gather(*tasks)
    all_items = []
    for items in results:
        all_items.extend(items)
    # 按时间排序（最新的在前）
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    print(f"\n✅ 共抓取 {len(all_items)} 条新闻")
    return all_items


def _has_chinese(text: str) -> bool:
    """检查文本是否包含中文字符"""
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def _looks_english(text: str) -> bool:
    """判断文本是否看起来是英文（需要翻译）"""
    if not text or len(text.strip()) < 3:
        return False
    # 已经包含中文则不翻译
    if _has_chinese(text):
        return False
    # 统计英文字母占比
    alpha = sum(1 for c in text if c.isascii() and c.isalpha())
    return alpha > 0 and (alpha / len(text.strip())) > 0.4


_translate_semaphore = asyncio.Semaphore(5)  # 最多 5 个并发翻译


async def translate_text(session: aiohttp.ClientSession, text: str) -> str:
    """使用 Google Translate 将英文翻译为中文"""
    text = text.strip()[:500]
    if not _looks_english(text):
        return text
    async with _translate_semaphore:
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": "en",
                "tl": "zh-CN",
                "dt": "t",
                "q": text,
            }
            async with session.get(url, params=params,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    translated = "".join(part[0] for part in data[0] if part[0])
                    return translated.strip() or text
                else:
                    print(f"  [!] 翻译接口返回 {resp.status}")
        except Exception as e:
            print(f"  [!] 翻译失败: {e}")
    return text


async def translate_news(items: list[dict]) -> list[dict]:
    """批量翻译英文新闻的标题和摘要"""
    print("\n🌐 翻译英文新闻...")
    async with aiohttp.ClientSession() as session:
        tasks = []
        for item in items:
            tasks.append(translate_text(session, item["title"]))
            tasks.append(translate_text(session, item["summary"]))
        results = await asyncio.gather(*tasks)
    # 结果交错：偶数索引是标题，奇数索引是摘要
    translated_count = 0
    for i, item in enumerate(items):
        new_title = results[i * 2]
        new_summary = results[i * 2 + 1]
        if new_title != item["title"]:
            translated_count += 1
        item["title"] = new_title
        item["summary"] = new_summary
    print(f"  ✅ 翻译了 {translated_count} 条新闻标题/摘要")
    return items


def format_feishu_message(items: list[dict]) -> dict:
    """格式化为飞书消息卡片"""
    if not items:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"📭 今日暂无新闻 ({TODAY})"},
                    "template": "blue",
                }
            }
        }

    # 分类
    CN_SOURCES = ("36氪", "虎嗅", "InfoQ 中文")
    AI_SOURCES = ("OpenAI", "Google AI", "Hugging Face", "MarkTechPost",
                  "arXiv cs.AI", "TLDR AI", "Ben's Bites")

    cn_items = [i for i in items if i["source"] in CN_SOURCES]
    ai_items = [i for i in items if i["source"] in AI_SOURCES]
    intl_items = [i for i in items if i["source"] not in CN_SOURCES and i["source"] not in AI_SOURCES]

    elements = []

    def make_elements(category_title, item_list, emoji, maxn=6):
        block = []
        block.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{emoji} {category_title}**"}
        })
        for idx, item in enumerate(item_list[:maxn], 1):
            title = item["title"][:60]
            summary = item["summary"][:80] if item["summary"] else ""
            content = f"{idx}. **[{title}]({item['link']})**"
            if summary:
                content += f"\n   {summary}"
            content += f"\n   `{item['source']}`"
            block.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": content}
            })
        return block

    if cn_items:
        elements.extend(make_elements("国内科技", cn_items, "🇨🇳"))

    if ai_items:
        elements.extend(make_elements("AI 前沿", ai_items, "🤖"))

    if intl_items:
        elements.extend(make_elements("国际科技", intl_items, "🌍"))

    # 底部信息
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": f"🕐 {TODAY} 12:00 | 星期六简报 · 喵老大专属 🤖"
        }]
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🤖 喵老大，今日 AI & 科技简报来了！"},
                "template": "blue",
            },
            "elements": elements,
        }
    }


async def send_to_feishu(webhook_url: str, payload: dict):
    """发送消息到飞书"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.text()
                print(f"📬 飞书推送状态: HTTP {resp.status}")
                if resp.status != 200:
                    print(f"  响应: {result[:200]}")
                return resp.status == 200
        except Exception as e:
            print(f"❌ 飞书推送失败: {e}")
            return False


async def main():
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("❌ 环境变量 FEISHU_WEBHOOK 未设置")
        sys.exit(1)

    print("=" * 50)
    print("  喵老大 AI & 科技新闻简报")
    print(f"  日期: {TODAY}")
    print("=" * 50)

    # 1. 抓新闻
    news = await gather_news()

    # 2. 翻译英文新闻为中文
    news = await translate_news(news)

    # 3. 格式化
    payload = format_feishu_message(news)
    print("\n📋 简报已整理，准备推送...")

    # 3. 推送
    ok = await send_to_feishu(webhook, payload)
    if ok:
        print("\n🎉 简报推送成功！")
    else:
        print("\n❌ 简报推送失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
