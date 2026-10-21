# -*- coding: utf-8 -*-
"""
站点索引维护：扫描 site/ 下 YYYY-MM-DD.html，按日期倒序重建 index.html。
保留最近 30 篇。纯标准库。

用法： python update_index.py [site目录]
"""
import os
import re
import sys

PAT = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")

CARDS = """
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:28px 18px 60px}}
.wrap{{max-width:1000px;margin:0 auto}}
h1{{font-size:24px;color:#e6edf3;margin-bottom:6px}}
.sub{{color:#8b949e;font-size:13px;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:13px}}
a.card{{display:block;background:#161b22;border:1px solid #30363d;border-radius:11px;padding:16px 16px 14px;text-decoration:none;color:inherit;transition:.18s;position:relative}}
a.card:hover{{border-color:#58a6ff;transform:translateY(-2px)}}
a.card .d{{font-size:16px;font-weight:700;color:#58a6ff}}
a.card .w{{font-size:12px;color:#8b949e;margin-top:5px}}
.new{{position:absolute;top:11px;right:11px;background:#da3633;color:#fff;font-size:10px;padding:2px 7px;border-radius:9px;font-weight:700}}
.foot{{color:#6e7681;font-size:12px;text-align:center;margin-top:28px;border-top:1px solid #21262d;padding-top:18px}}
@media(max-width:600px){{h1{{font-size:19px}}.grid{{grid-template-columns:1fr}}}}
</style>""".strip()

WD = "一二三四五六日"

TITLES = {
    "2026-10-19": "1年期首批加仓执行日",
    "2026-10-20": "LPR不变 + 央行政策框架转型",
    "2026-10-21": "沪指连阳后首回落，创业板领跌 1.62%",
}

BLURB = {
    "2026-10-19": "1年期执行计划首批 3200 元加仓落地，首批 7 只触发位全部就位。",
    "2026-10-20": "LPR 报价不变，央行政策框架转型表述，市场窄幅整理。",
    "2026-10-21": "指数跌幅温和但个股普跌：下跌 3092 家 vs 上涨 1967 家，主力资金从新能源链切向电子算力。加仓触发 0/7。",
}


def title_for(d):
    return TITLES.get(d, "A股持仓每日复盘")


def build(site):
    files = []
    for f in os.listdir(site):
        m = PAT.match(f)
        if m:
            files.append(m.group(1))
    files.sort(reverse=True)
    total = len(files)
    files = files[:30]

    cards = []
    for i, d in enumerate(files):
        try:
            import datetime
            wd = WD[datetime.date.fromisoformat(d).weekday()]
        except Exception:
            wd = ""
        badge = '<span class="new">NEW</span>' if i == 0 else ""
        blurb = BLURB.get(d, "自动生成的每日持仓复盘。")
        cards.append(
            '<a class="card" href="{d}.html">{badge}'
            '<div class="d">{d} 周{wd}</div>'
            '<div class="w">{t}</div>'
            '<div class="w" style="margin-top:8px">{b}</div></a>'
            .format(d=d, wd=wd, t=title_for(d), b=blurb, badge=badge))

    if not cards:
        cards = ['<p style="color:#8b949e">暂无报告。请等待首次定时任务运行。</p>']

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A股持仓复盘中心</title>{css}</head><body>
<div class="wrap">
<h1>A股持仓复盘中心</h1>
<div class="sub">1年期持仓执行计划 v3.0 ｜ 共 {total} 篇 ｜ 由 GitHub Actions 每日 15:30 自动生成</div>
<div class="grid">{cards}</div>
<div class="foot">数据来源：东方财富公开行情接口。标注「数据暂未获取」的字段表示该接口未提供，
未做任何推测或替代。本站不构成投资建议，入市有风险，投资需谨慎。</div>
</div></body></html>""".format(css=CARDS, total=total, cards="".join(cards))


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "site"
    os.makedirs(site, exist_ok=True)
    html = build(site)
    p = os.path.join(site, "index.html")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    nojekyll = os.path.join(site, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
    print("索引已更新 -> %s" % p)


if __name__ == "__main__":
    main()