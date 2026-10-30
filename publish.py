# -*- coding: utf-8 -*-
"""
发布脚本：抓取 -> 生成 -> 索引 -> 推送 gh-pages。

为什么单独成文件：GitHub Actions 的 `run: |` 里写 heredoc 极易被网页编辑器的
自动缩进破坏，而且报错信息藏在日志深处。本脚本把全部逻辑集中一处，
工作流只保留一行 `python publish.py`，任何问题都会直接打印在本步骤输出里。

设计原则（踩过的坑总结）：
  1. 绝不静默跳过。GitHub Actions 不会自动注入 GITHUB_TOKEN / GITHUB_REPOSITORY，
     必须在 workflow 里用 env: 显式传入，否则任务会"全绿"但什么都没推。
  2. 失败也要推，但**不能顶掉上一次的报告**。2026-10-30 云端因 generate_report.py
     里一个未定义变量（sec2 的 flow_ok）炸了，旧写法把错误页写成 site/latest.html
     再 force push → 线上站点整站被错误页顶掉，昨天能看的报告也没了。
     现在改成：先把上一次的 gh-pages 内容拉下来当基底，失败时把错误页写到
     site/error.html，latest.html 保持上一次的好报告。
  3. 推送段独立于生成段。抓取/生成/索引任何一步炸掉，都不影响最后把 gh-pages 建出来。
  4. 基底顺带让历史报告累积：update_index.py 一直支持"扫描 site/ 下所有
     YYYY-MM-DD.html、保留最近 30 篇"，之前因为 site/ 每天被清空而用不上。

环境变量（需在 workflow 中显式传入）：
  GITHUB_TOKEN      推送凭据
  GITHUB_REPOSITORY owner/repo
"""
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone, timedelta
import html as html_mod

CST = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.abspath(__file__))


def sh(cmd, cwd=None, hide=None):
    shown = [hide if hide and hide in c else c for c in cmd]
    print("+ " + " ".join(shown), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True)


def write_error_page(err, detail_lines):
    """把失败原因写成一个页面。

    ⚠️ 2026-10-30 起写到 site/error.html，**不再覆盖 site/latest.html**：
    上一次的好报告要留在 latest.html，失败不能把站点顶掉。
    """
    body = "".join("<li>%s</li>" % html_mod.escape(str(x)) for x in detail_lines)
    with open("site/error.html", "w", encoding="utf-8") as f:
        f.write(
            "<!DOCTYPE html><html lang=zh-CN><meta charset=utf-8>"
            "<title>复盘生成失败</title>"
            "<body style='background:#0d1117;color:#c9d1d9;"
            "font-family:system-ui,-apple-system,Segoe UI,sans-serif;padding:32px'>"
            "<h2 style='color:#f85149;margin:0 0 18px'>复盘生成失败</h2>"
            "<p style='color:#8b949e'>时间 %s ｜ 仓库 %s ｜ "
            "<a style='color:#58a6ff' href='latest.html'>← 回到上一份完好的报告</a></p>"
            "<h3 style='color:#58a6ff;font-size:15px'>现场信息</h3>"
            "<ul style='line-height:1.9'>%s</ul>"
            "<h3 style='color:#58a6ff;font-size:15px'>异常堆栈</h3>"
            "<pre style='white-space:pre-wrap;background:#161b22;padding:16px;"
            "border-radius:8px;border:1px solid #30363d'>%s</pre>"
            "<p style='color:#8b949e'>原始数据：<a style='color:#58a6ff' "
            "href='market.json'>market.json</a> ｜ "
            "抓取日志：<a style='color:#58a6ff' href='fetch.log'>fetch.log</a></p>"
            "</body></html>"
            % (datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST"),
               os.environ.get("GITHUB_REPOSITORY", "?"), body,
               html_mod.escape(err))
        )


def overlay_site(src_dir):
    """把 src_dir 里的站点文件铺到 site/ 下（已存在的不覆盖）。"""
    for name in os.listdir(src_dir):
        if name.startswith("."):
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join("site", name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif not os.path.exists(dst):
            shutil.copy2(src, dst)


def fetch_previous_site(token, repo):
    """把上一次的 gh-pages 内容拉下来，作为本次 site/ 的基底。

    目的：
      ① 生成失败时不至于把上一次能看的报告整站顶掉（2026-10-30 真实发生过）
      ② 顺带让历史报告累积 —— update_index.py 一直支持"保留最近 30 篇"
    失败不致命：拿不到就按老路走（site/ 只有本轮内容）。
    """
    if not (token and repo):
        return False
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    tmp = "_prev_site"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        sh(["git", "clone", "-q", "--depth", "1", "--branch", "gh-pages",
            url, tmp], hide=token)
    except Exception as e:
        print("!! 上一次站点内容拉取失败（不影响本次发布）：%s" % e, flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    try:
        overlay_site(tmp)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push_gh_pages(today):
    """只负责把 site/ 推到 gh-pages。任何异常都向上抛，由调用方决定怎么处理。"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        # 关键：绝不能静默跳过，否则任务显示"成功"但什么都没推。
        print("!! 缺少 GITHUB_TOKEN / GITHUB_REPOSITORY 环境变量，无法推送 gh-pages")
        print("!! 请在工作流的该步骤加上：")
        print("!!   env:")
        print("!!     GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}")
        print("!!     GITHUB_REPOSITORY: ${{ github.repository }}")
        return False

    if not os.path.isdir(os.path.join("site", ".git")):
        sh(["git", "init", "-q"], cwd="site")
    sh(["git", "config", "user.name", "github-actions[bot]"], cwd="site")
    sh(["git", "config", "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com"], cwd="site")
    sh(["git", "checkout", "-q", "-B", "gh-pages"], cwd="site")
    sh(["git", "add", "-A"], cwd="site")
    # 内容与上次完全一致时 `git commit` 会返回 1 并抛 CalledProcessError，
    # 让任务变红但站点其实没问题。先看有没有变更再决定要不要提交。
    st = subprocess.run(["git", "status", "--porcelain"], cwd="site",
                        capture_output=True, text=True)
    if st.stdout.strip():
        sh(["git", "commit", "-q", "-m", "review %s" % today], cwd="site")
    else:
        print("### 内容与上次一致，跳过提交", flush=True)
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    sh(["git", "push", "-q", "-f", url, "gh-pages"], cwd="site", hide=token)
    print("### 已推送到 gh-pages")
    print("### 站点地址：https://%s.github.io/%s/" % tuple(repo.split("/")),
          flush=True)
    return True


def main():
    os.chdir(ROOT)
    today = datetime.now(CST).date().isoformat()
    os.makedirs("data", exist_ok=True)
    os.makedirs("site", exist_ok=True)
    gen_ok = True
    info = []

    # 先把上一次的站点内容拉下来当基底：
    #   · 生成失败时 latest.html 仍是上一次的好报告（不再整站被错误页顶掉）
    #   · 历史报告自然累积，index.html 能列出多天
    _tok = os.environ.get("GITHUB_TOKEN")
    _repo = os.environ.get("GITHUB_REPOSITORY")
    if _tok and _repo and fetch_previous_site(_tok, _repo):
        print("### 已把上一次的站点内容作为基底（历史报告保留）", flush=True)

    try:
        print("=== 1/4 抓取行情 ===", flush=True)
        try:
            sh([sys.executable, "fetch_market.py", "data"])
        except subprocess.CalledProcessError:
            print("!! 抓取脚本非零退出，仍尝试生成（数据可能不完整）", flush=True)

        mp = "data/market.json"
        if not os.path.exists(mp):
            raise RuntimeError("抓取结束后没有产出 data/market.json")

        with open(mp, encoding="utf-8") as f:
            d = json.load(f)
        trade = d.get("trade_date")
        ix = d.get("indexes") or {}
        pf = d.get("portfolio") or {}
        info = ["北京时间：%s" % today,
                "行情日期：%s ｜ is_trading_day=%s"
                % (trade, d.get("is_trading_day")),
                "指数数量：%d ｜ 上证收盘=%s"
                % (len(ix), (ix.get("000001") or {}).get("close")),
                "持仓数量：%d"
                % len([v for v in pf.values() if v.get("close")]),
                "触发预警：%s / %s"
                % (d.get("triggered_count"), d.get("trigger_total"))]
        for line in info:
            print("### " + line, flush=True)

        print("=== 2/4 生成 HTML ===", flush=True)
        name = trade or today
        try:
            sh([sys.executable, "generate_report.py", mp,
                "site/%s.html" % name])
        except Exception as e:
            gen_ok = False
            raise RuntimeError("生成报告失败：%s: %s" % (type(e).__name__, e))

        print("=== 3/4 更新索引 ===", flush=True)
        shutil.copy("site/%s.html" % name, "site/latest.html")
        shutil.copy(mp, "site/market.json")
        if os.path.exists("fetch.log"):
            shutil.copy("fetch.log", "site/fetch.log")
        try:
            sh([sys.executable, "update_index.py", "site"])
        except Exception as e:
            print("!! 索引更新失败（不影响发布）：", e, flush=True)

    except Exception:
        gen_ok = False
        err = traceback.format_exc()
        print("!! 流水线异常：\n" + err, flush=True)
        try:
            write_error_page(err, info or ["流水线在抓取/生成阶段中断"])
        except Exception as e2:
            print("!! 错误页写入也失败了：", e2, flush=True)
        # 诊断数据也一并带上（错误页里链向它们）
        for src, dst in (("data/market.json", "site/market.json"),
                         ("fetch.log", "site/fetch.log")):
            try:
                if os.path.exists(src):
                    shutil.copy(src, dst)
            except Exception:
                pass
        try:
            sh([sys.executable, "update_index.py", "site"])
        except Exception as e:
            print("!! 索引更新失败（不影响发布）：", e, flush=True)

    print("=== 4/4 推送 gh-pages ===", flush=True)
    try:
        pushed = push_gh_pages(today)
    except Exception:
        # 推送本身失败是唯一必须让任务变红的情况：站点根本没更新。
        print("!! 推送失败：\n" + traceback.format_exc(), flush=True)
        return 1
    if not pushed:
        return 1
    if not gen_ok:
        print("!! 注意：本次报告生成失败，错误详情已推送到站点 /error.html"
              "（latest.html 保留上一次的好报告）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())