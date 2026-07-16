#!/usr/bin/env python3
"""
喵老大 AI 早报 · 双人对话播客生成器

流程：
  1. 读取 news.json（由 fetch_news.py 产出）
  2. 生成双人对话文稿（小星 / 大伟）
  3. 用 edge-tts（微软免费中文语音，无需密钥）逐句合成
  4. ffmpeg 拼接成一期 MP3，并在句间插入静音
  5. 生成 / 累加 podcast RSS（保留最近 7 期）
  6. 清理过期音频，输出到 docs/ 由 GitHub Pages 托管

运行：python podcast.py
环境变量 PAGES_BASE 可选，默认 https://<owner>.github.io/<repo>
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")

# GitHub Pages 基础地址（音频与 RSS 的最终 URL）
PAGES_BASE = os.environ.get(
    "PAGES_BASE",
    "https://baiyihua590-glitch.github.io/daily-tech-news",
).rstrip("/")

DOCS_DIR = "docs"
AUDIO_DIR = os.path.join(DOCS_DIR, "audio")
FEED_PATH = os.path.join(DOCS_DIR, "feed.xml")
NEWS_PATH = "news.json"
KEEP_EPISODES = 7

# ---------- 双主播 ----------
HOSTS = {
    "A": {"name": "小星", "voice": "zh-CN-XiaoxiaoNeural"},   # 温柔女声
    "B": {"name": "大伟", "voice": "zh-CN-YunxiNeural"},     # 活力男声
}

# ---------- 对话素材 ----------
REACTIONS = {
    "AI大模型": [
        "大模型这波又卷起来了。",
        "各家在 AI 上的军备竞赛，看来是停不下来了。",
        "这个迭代速度，确实快得有点吓人。",
    ],
    "马斯克": [
        "马斯克又来搞事情了。",
        "说真的，这人真是一刻都闲不下来。",
        "马斯克这张牌，往往能搅动整个行业的风向。",
    ],
    "机器人": [
        "现在机器人进展是真快。",
        "人形机器人离进工厂、进家庭，又近了一步。",
        "这块要是跑通了，影响的可不只是一个行业。",
    ],
    "中美AI": [
        "中美在 AI 上的博弈，又添了一层。",
        "这事儿牵扯的，早就不只是技术了。",
        "看来自主可控这条路，还得接着坚定走下去。",
    ],
}
GENERIC_REACT = [
    "这条也挺有意思。",
    "确实值得咱们留意一下。",
    "这个趋势，我觉得还会延续下去。",
]
ELABORATE = {
    "AI大模型": "对咱们来说，这意味着手里的工具又要升级了。",
    "马斯克": "不管你关不关注他，他的动作都会影响整个市场。",
    "机器人": "以后工厂、仓库，甚至家里，可能都要变样。",
    "中美AI": "这直接关系到咱们能不能不被卡脖子。",
}


def build_script(items: list[dict]) -> list[tuple]:
    """返回 [(说话人 'A'/'B', 文本), ...] 的对话列表"""
    segs = []
    n = len(items)
    segs.append(("A", f"喵老大早上好，欢迎收听今天的 AI 早报，我是小星。"))
    segs.append(("B", f"我是大伟。今天咱们挑了 {n} 条最值得关注的消息，"
                      f"有 GPT、马斯克、机器人，还有中美 AI 的较量，咱们一条条聊。"))

    for idx, item in enumerate(items, 1):
        title = item.get("title", "").strip()
        summary = (item.get("summary") or "").strip()
        tags = item.get("tags", [])

        # 主播 A：播报本条
        lead = f"第 {idx} 条，{title}。"
        if summary:
            lead += f"{summary}"
        segs.append(("A", lead))

        # 主播 B：按话题选一句评论
        pool = []
        for t in tags:
            pool += REACTIONS.get(t, [])
        if not pool:
            pool = GENERIC_REACT
        segs.append(("B", pool[idx % len(pool)]))

        # 主播 A：有标签的重点新闻，补一句"为什么值得关注"
        if tags:
            elab_pool = [ELABORATE.get(t) for t in tags if ELABORATE.get(t)]
            if elab_pool:
                segs.append(("A", elab_pool[0]))

    segs.append(("A", "以上就是今天的 AI 早报。"))
    segs.append(("B", "喵老大开车路上慢慢听，咱们明天接着聊。"))
    segs.append(("A", "拜拜。"))
    segs.append(("B", "拜拜。"))
    return segs


def tts_to_mp3(segs: list[tuple], out_mp3: str) -> float:
    """逐句合成并拼接，返回音频时长（秒）"""
    import asyncio
    import edge_tts

    os.makedirs("tmp_seg", exist_ok=True)
    seg_files = []

    async def gen():
        for i, (spk, text) in enumerate(segs):
            voice = HOSTS[spk]["voice"]
            fp = os.path.join("tmp_seg", f"seg{i}.mp3")
            comm = edge_tts.Communicate(text, voice)
            await comm.save(fp)
            seg_files.append(fp)
            print(f"  🔊 [{HOSTS[spk]['name']}] {text[:24]}...")

    asyncio.run(gen())

    # 句间静音
    silent = os.path.join("tmp_seg", "silence.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", "0.35", "-q:a", "9", silent],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    mixed = []
    for fp in seg_files:
        mixed.append(fp)
        mixed.append(silent)

    list_file = os.path.join("tmp_seg", "list.txt")
    with open(list_file, "w") as f:
        for fp in mixed:
            f.write(f"file '{os.path.abspath(fp)}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c:a", "libmp3lame", "-q:a", "4", out_mp3],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    dur = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", out_mp3],
    ).decode().strip()
    return float(dur)


def parse_existing_feed(feed_path: str) -> list[dict]:
    """从已有 feed.xml 中解析出历史期数（用于累加）"""
    if not os.path.exists(feed_path):
        return []
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(feed_path)
        root = tree.getroot()
        items = []
        for it in root.iter("item"):
            title = it.findtext("title", "")
            enclosure = it.find("enclosure")
            url = enclosure.get("url") if enclosure is not None else ""
            pub = it.findtext("pubDate", "")
            dur = it.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration", "")
            items.append({"title": title, "url": url, "pubDate": pub, "duration": dur})
        return items
    except Exception as e:
        print(f"  [!] 解析旧 feed 失败: {e}")
        return []


def build_feed(new_item: dict, history: list[dict]) -> str:
    all_items = [new_item] + history
    all_items = all_items[:KEEP_EPISODES]

    item_xml = []
    for it in all_items:
        item_xml.append(f"""    <item>
      <title>{it['title']}</title>
      <description>{it['desc']}</description>
      <enclosure url="{it['url']}" type="audio/mpeg" />
      <guid isPermaLink="false">{it['url']}</guid>
      <pubDate>{it['pubDate']}</pubDate>
      <itunes:duration>{it['duration']}</itunes:duration>
    </item>""")

    pub = datetime.now(TZ).strftime("%a, %d %b %Y %H:%M:%S +0800")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>喵老大AI早报</title>
    <description>每日精选 AI 与科技热点，开车路上听新闻。由星期六自动生成。</description>
    <language>zh-CN</language>
    <link>{PAGES_BASE}/</link>
    <itunes:author>星期六</itunes:author>
    <itunes:category text="Technology" />
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(item_xml)}
  </channel>
</rss>
"""


def prune_old_audio():
    """只保留最近 KEEP_EPISODES 个音频文件"""
    if not os.path.isdir(AUDIO_DIR):
        return
    files = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR)
              if f.endswith(".mp3")]
    files.sort()  # 按日期文件名升序
    excess = files[:-KEEP_EPISODES] if len(files) > KEEP_EPISODES else []
    for fp in excess:
        os.remove(fp)
        print(f"  🗑️  清理旧音频: {os.path.basename(fp)}")


def main():
    if not os.path.exists(NEWS_PATH):
        print(f"❌ 找不到 {NEWS_PATH}，请先运行 fetch_news.py")
        sys.exit(1)

    with open(NEWS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])
    if not items:
        print("⚠️  今天没有抓到新闻，跳过生成")
        return

    print(f"🎙️  生成双人对话文稿（{len(items)} 条新闻）")
    segs = build_script(items)

    os.makedirs(AUDIO_DIR, exist_ok=True)
    mp3_path = os.path.join(AUDIO_DIR, f"{TODAY}.mp3")
    print(f"🔊 合成语音 -> {mp3_path}")
    duration = tts_to_mp3(segs, mp3_path)
    print(f"  ✅ 音频时长: {duration:.0f} 秒")

    mp3_url = f"{PAGES_BASE}/audio/{TODAY}.mp3"
    desc = "\n".join(f"{i+1}. {it['title']}（{it['source']}）"
                     for i, it in enumerate(items))
    new_item = {
        "title": f"AI早报 {TODAY}",
        "desc": desc,
        "url": mp3_url,
        "pubDate": datetime.now(TZ).strftime("%a, %d %b %Y %H:%M:%S +0800"),
        "duration": int(duration),
    }

    history = parse_existing_feed(FEED_PATH)
    feed_xml = build_feed(new_item, history)
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    print(f"📰 RSS 已更新（含历史共 {len([new_item]+history[:KEEP_EPISODES-1])} 期）")

    prune_old_audio()
    print("\n🎉 播客生成完成！")


if __name__ == "__main__":
    main()
