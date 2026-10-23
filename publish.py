# -*- coding: utf-8 -*-
"""
发布脚本：抓取 -> 生成 -> 索引 -> 推送 gh-pages。

为什么单独成文件：GitHub Actions 的 `run: |` 里写 heredoc 极易被网页编辑器的
自动缩进破坏，而且报错信息藏在日志深处。本脚本把全部逻辑集中一处，
工作流只保留一行 `python publish.py`，任何问题都会直接打印在本步骤输出里。

环境变量（Actions 自动注入）：
  GITHUB_TOKEN      推送凭据
  GITHUB_REPOSITORY owner/repo
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.abspath(__file__))


def sh(cmd, cwd=None, hide=None):
    shown = [hide if hide and hide in c else c for c in cmd]
    print("+ " + " ".join(shown), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True)


def main():
    os.chdir(ROOT)
    os.makedirs("data", exist_ok=True)

    print("=== 1/4 抓取行情 ===", flush=True)
    try:
        sh([sys.executable, "fetch_market.py", "data"])
    except subprocess.CalledProcessError:
        print("!! 抓取脚本非零退出，仍尝试生成（数据可能不完整）", flush=True)

    mp = "data/market.json"
    if not os.path.exists(mp):
        print("!! 没有生成 market.json，无法继续", flush=True)
        return 1

    with open(mp, encoding="utf-8") as f:
        d = json.load(f)
    trade = d.get("trade_date")
    today = datetime.now(CST).date().isoformat()
    ix = d.get("indexes") or {}
    pf = d.get("portfolio") or {}
    print("### 北京时间  :", today)
    print("### 行情日期  :", trade, "| is_trading_day =", d.get("is_trading_day"))
    print("### 指数数量  :", len(ix), "| 上证收盘 =",
          (ix.get("000001") or {}).get("close"))
    print("### 持仓数量  :", len([v for v in pf.values() if v.get("close")]))
    print("### 触发      :", d.get("triggered_count"), "/", d.get("trigger_total"))

    print("=== 2/4 生成 HTML ===", flush=True)
    name = trade or today
    os.makedirs("site", exist_ok=True)
    try:
        sh([sys.executable, "generate_report.py", mp, "site/%s.html" % name])
    except subprocess.CalledProcessError as e:
        print("!! 生成失败：", e, flush=True)
        return 1
    shutil.copy("site/%s.html" % name, "site/latest.html")

    print("=== 3/4 更新索引 ===", flush=True)
    sh([sys.executable, "update_index.py", "site"])
    shutil.copy(mp, "site/market.json")
    if os.path.exists("fetch.log"):
        shutil.copy("fetch.log", "site/fetch.log")

    print("=== 4/4 推送 gh-pages ===", flush=True)
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("!! 本地运行：无 GITHUB_TOKEN，跳过推送（正常）")
        return 0
    sh(["git", "config", "user.name", "github-actions[bot]"], cwd="site")
    sh(["git", "config", "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com"], cwd="site")
    if not os.path.isdir(os.path.join("site", ".git")):
        sh(["git", "init", "-q"], cwd="site")
    sh(["git", "checkout", "-q", "-B", "gh-pages"], cwd="site")
    sh(["git", "add", "-A"], cwd="site")
    sh(["git", "commit", "-q", "-m", "review %s" % today], cwd="site")
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    sh(["git", "push", "-q", "-f", url, "gh-pages"],
       cwd="site", hide=token)
    print("### 已推送到 gh-pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())