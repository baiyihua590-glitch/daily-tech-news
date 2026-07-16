# 喵老大 AI 早报 · 每日科技播客

每天自动抓取 AI & 科技新闻 → 按你的关注点筛选 → 生成**双人对话语音播客** → 发布成 RSS → 在小宇宙（车机）订阅收听。

## 功能
- 📰 **21 个新闻源**：国内（36氪/虎嗅/InfoQ）+ 国际（BBC/CNN/Reuters/TechCrunch/Verge/Wired 等）+ AI 专项（OpenAI/Google AI/HuggingFace/arXiv 等）
- 🔥 **重点聚焦**：自动打标签 —— AI大模型 / 马斯克 / 机器人 / 中美AI
- 🌐 **英文自动翻译**为中文
- 🎙️ **双人对话播报**（小星 + 大伟），微软 edge-tts 免费中文语音，无需密钥
- 🚗 **小宇宙订阅**：RSS 托管在 GitHub Pages，车机小宇宙导入一次即可

## 架构
```
GitHub Actions（每天 UTC 01:00 跑，时间不敏感）
  ├─ fetch_news.py   抓取 + 翻译 + 打标签 → news.json
  ├─ podcast.py       生成对话文稿 → edge-tts 合成 → ffmpeg 拼接 → docs/audio/YYYY-MM-DD.mp3
  │                   → 累加 podcast RSS（保留最近 7 期）→ docs/feed.xml
  └─ 提交 docs/  →  GitHub Pages 托管
小宇宙 App → 导入 RSS 链接 → 每天自动出现新一期
```

## 小宇宙订阅步骤
1. 打开小宇宙 App → 「我的」→「设置」→「导入节目」
2. 选择「通过 RSS 链接导入」
3. 填入本仓库的 feed.xml 地址：
   ```
   https://baiyihua590-glitch.github.io/daily-tech-news/feed.xml
   ```
4. 确认订阅，之后每天新车机打开小宇宙就能看到新一期。

## 文件
| 文件 | 作用 |
|------|------|
| `fetch_news.py` | 抓取/翻译/打标签，输出 news.json |
| `podcast.py` | 对话文稿 + 语音合成 + RSS 生成 |
| `requirements.txt` | Python 依赖 |
| `.github/workflows/daily-podcast.yml` | 每日自动运行 |
| `docs/` | GitHub Pages 托管的音频与 RSS（自动生成） |
