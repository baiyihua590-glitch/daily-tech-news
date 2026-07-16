#!/usr/bin/env python3
"""用 cron-job.org 的免费精确定时器，每天 09:00(北京) 触发 GitHub Actions dispatch。

为什么需要它：
  GitHub Actions 自带的 schedule 是 best-effort，会被排队延后数小时，
  导致新闻总在 12:10 左右才发。改用外部精确定时器来踢 GitHub 的
  workflow_dispatch 接口，即可锁定 09:00 准时发送。

使用方法（需要两个环境变量，不要写死在脚本里）：
  export CRONJOB_API_KEY="你的 cron-job.org API Key"
  export GH_TOKEN="具备 workflow 作用域的 GitHub PAT（建议用本仓库专用的细粒度 token）"
  python3 setup_cronjob.py

安全提示：
  - 本仓库是 PUBLIC，切勿把真实 token 写进此文件再提交。
  - GH_TOKEN 会被写入 cron-job.org 的任务配置中（用于调用 GitHub API），
    因此建议用「细粒度 PAT」：仅授权 daily-tech-news 这一个仓库的
    Actions: Read and Write，不要把全权限的主 PAT 暴露给第三方。
"""
import os
import sys
import json
import urllib.request
import urllib.error

CRONJOB_API_KEY = os.environ.get("CRONJOB_API_KEY")
GH_TOKEN = os.environ.get("GH_TOKEN")

if not CRONJOB_API_KEY or not GH_TOKEN:
    print("❌ 缺少环境变量：需要 CRONJOB_API_KEY 和 GH_TOKEN")
    sys.exit(1)

REPO = "baiyihua590-glitch/daily-tech-news"
WORKFLOW_ID = 303462284
DISPATCH_URL = (
    f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_ID}/dispatches"
)

# 每天 01:00 UTC = 北京 09:00
job = {
    "job": {
        "url": DISPATCH_URL,
        "enabled": True,
        "saveResponses": True,
        "schedule": {
            "timezone": "UTC",
            "expiresAt": 0,
            "hours": [1],
            "minutes": [0],
            "mdays": [-1],
            "months": [-1],
            "wdays": [-1],
        },
        "requestMethod": 1,  # 1 = POST
        "extendedData": {
            "headers": {
                "Authorization": f"token {GH_TOKEN}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            "body": json.dumps({"ref": "main"}),
        },
    }
}

req = urllib.request.Request(
    "https://api.cron-job.org/jobs",
    data=json.dumps(job).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {CRONJOB_API_KEY}",
        "Content-Type": "application/json",
    },
    method="PUT",
)

try:
    resp = urllib.request.urlopen(req)
    print("✅ cron-job.org 任务创建成功:", resp.read().decode())
except urllib.error.HTTPError as e:
    print(f"❌ 创建失败 ({e.code}):", e.read().decode())
    sys.exit(1)
