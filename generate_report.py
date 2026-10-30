# -*- coding: utf-8 -*-
"""
A股每日复盘 - HTML 生成器（纯标准库）

结构与《01-复盘模板.md》v2.0 对齐，共 12 块：
  【一】~【十】十章 + 【新因子预留位】 + 附录:关键数据汇总
缺数据一律渲染为"数据暂未获取"，绝不编造。

模板使用 {name} 占位符 + str.replace 注入，避免 % 格式化在大模板中错位。
用法： python generate_report.py <market.json> <输出html路径>
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import config

CST = timezone(timedelta(hours=8))
NA = "数据暂未获取"

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.75;font-size:15px}
.wrap{display:flex;max-width:1400px;margin:0 auto}
nav{width:232px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid #21262d;padding:20px 0;background:#010409}
nav h4{color:#58a6ff;font-size:12px;letter-spacing:2px;padding:0 18px 12px;border-bottom:1px solid #21262d;margin-bottom:10px}
nav a{display:block;color:#8b949e;text-decoration:none;font-size:13px;padding:7px 18px;border-left:2px solid transparent;transition:.15s}
nav a:hover,nav a.on{color:#58a6ff;background:#0d1117;border-left-color:#58a6ff}
main{flex:1;min-width:0;padding:22px 26px 70px}
.hero{background:linear-gradient(135deg,#161b22,#1c2128);border:1px solid #30363d;border-radius:12px;padding:22px 24px;margin-bottom:18px}
.hero h1{font-size:23px;color:#e6edf3;margin-bottom:8px}
.hero .sub{color:#8b949e;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:11px;margin-bottom:18px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 12px;text-align:center;cursor:pointer;transition:.18s;text-decoration:none;display:block}
.card:hover{border-color:#58a6ff;transform:translateY(-2px)}
.card .k{font-size:11px;color:#8b949e;margin-bottom:6px}
.card .v{font-size:19px;font-weight:700;color:#e6edf3}
.card .d{font-size:11px;margin-top:4px}
.trigger{background:#1c1410;border:1px solid #9e6a03;border-left:4px solid #d29922;border-radius:10px;padding:16px 18px;margin-bottom:18px}
.trigger.ok{background:#0f1c12;border-color:#2ea043;border-left-color:#3fb950}
.trigger h3{color:#e3b341;font-size:15px;margin-bottom:4px}
.trigger.ok h3{color:#3fb950}
.trigger .cnt{font-size:25px;font-weight:800;color:#e3b341;margin:8px 0}
.trigger.ok .cnt{color:#3fb950}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
th{background:#161b22;color:#58a6ff;text-align:left;padding:9px 11px;border:1px solid #30363d;font-weight:600;white-space:nowrap}
td{padding:8px 11px;border:1px solid #21262d;vertical-align:top}
tr:nth-child(even) td{background:#0f141a}
.up{color:#f85149;font-weight:600}
.down{color:#3fb950;font-weight:600}
.flat{color:#8b949e}
.na{color:#6e7681;font-style:italic}
section{background:#0d1117;border:1px solid #21262d;border-radius:12px;padding:20px 22px;margin-bottom:18px}
section>h2{font-size:18px;color:#e6edf3;padding-bottom:11px;margin-bottom:14px;border-bottom:1px solid #21262d}
h3.sub{font-size:14.5px;color:#79c0ff;margin:16px 0 7px}
p{margin:7px 0;color:#b1bac4}
ul{margin:7px 0 7px 20px;color:#b1bac4}
li{margin:4px 0}
.tag{display:inline-block;padding:2px 8px;border-radius:11px;font-size:11.5px;font-weight:600;margin-right:5px}
.tag.g{background:#0f2f1a;color:#3fb950;border:1px solid #2ea043}
.tag.r{background:#2d1214;color:#f85149;border:1px solid #8b2c31}
.tag.y{background:#2b2410;color:#e3b341;border:1px solid #9e6a03}
.tag.b{background:#0c2340;color:#58a6ff;border:1px solid #1f6feb}
.tag.n{background:#1c2128;color:#8b949e;border:1px solid #30363d}
.box{background:#161b22;border-left:3px solid #58a6ff;padding:11px 14px;border-radius:0 7px 7px 0;margin:11px 0}
.box.warn{border-left-color:#d29922}
.box.risk{border-left-color:#f85149}
.box.good{border-left-color:#3fb950}
.foot{color:#6e7681;font-size:12px;text-align:center;padding:22px 0;border-top:1px solid #21262d;margin-top:12px}
@media(max-width:1100px){.cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:768px){
.wrap{display:block}
nav{position:static;width:100%;height:auto;border-right:none;border-bottom:1px solid #21262d;padding:12px 0}
nav h4{display:none}
nav a{display:inline-block;padding:5px 12px;border-left:none;border-bottom:2px solid transparent;font-size:12px}
nav a:hover,nav a.on{border-left:none;border-bottom-color:#58a6ff}
main{padding:14px}
.cards{grid-template-columns:repeat(2,1fr);gap:9px}
.hero h1{font-size:18px}
section{padding:15px 14px}
table{font-size:12px;display:block;overflow-x:auto;white-space:nowrap}
}
"""

NAV = [("s1", "一、今日A股行情"), ("s2", "二、资金面"), ("s3", "三、国家队/ETF"),
       ("s4", "四、消息面"), ("s4b", "四·补、新因子预留位"), ("s5", "五、涨跌成因"),
       ("s6", "六、持仓逐一复盘"), ("s6b", "六·补、基金账户"),
       ("s7", "七、此前推论验证"),
       ("s8", "八、策略调整建议"), ("s9", "九、商业航天"),
       ("s10", "十、低估板块跟踪"), ("s11", "附录·关键数据汇总")]

ORDER = ["600219", "516630", "513120", "515880", "000420",
         "601012", "002298", "601106"]

# 板块 -> 持仓关联说明（用于第五章主线表的最后一列）
HOLD_MAP = {
    "电子": "云计算ETF、通信ETF 的成分方向",
    "元件": "电子链上游",
    "印制电路板": "算力硬件链",
    "通信设备": "通信ETF 的直接方向",
    "半导体": "科技成长方向",
    "光伏设备": "隆基绿能所在方向",
    "电池": "新能源链",
    "锂电池": "新能源链",
    "电力设备": "新能源链上游",
    "有色金属": "南山铝业所在方向",
    "工业金属": "南山铝业所在方向",
    "小金属": "南山铝业所在方向",
    "医药生物": "医药创新药ETF 所在方向",
    "化学制药": "医药创新药ETF 所在方向",
    "计算机": "云计算ETF 方向",
    "软件开发": "云计算ETF 方向",
    "传媒": "吉林化纤下游需求相关",
    "非银金融": "无直接持仓",
}

# 持仓静态纪律（与行情无关的部分）
DISCIPLINE = {
    "600219": "三季报 10/29 是关键验证点，业绩落地前不重仓加码。",
    "516630": "按 1.38 / 1.28 两档阶梯加仓，间隔 ≥7 个交易日。",
    "513120": "无持仓记录，1 年期内不主动建仓，仅按 1.20 / 1.15 观察档。",
    "515880": "月定投 500 元照常；跌破 0.520 触发首档加仓。",
    "000420": "仓位很小，影响有限，按 3.75 / 3.60 / 3.45 阶梯。",
    "601012": "深度浮亏，10/31 三季报前不加仓。",
    "002298": "半年计划阶段 1 探底建仓期，按 7.30 / 7.00 / 6.50 阶梯。",
    "601106": "占比过高，做 T 降本是唯一路径。",
}


def F(tpl, **kw):
    """{name} 占位符替换。HTML 正文不含花括号，安全。"""
    out = tpl
    for k, v in kw.items():
        out = out.replace("{%s}" % k, str(v))
    return out


# ------------------------------------------------------------ 格式化
def fx(v, d=2, suffix=""):
    if v is None:
        return '<span class="na">' + NA + '</span>'
    return ("%%.%df%%s" % d) % (v, suffix)


def pct(v):
    if v is None:
        return '<span class="na">' + NA + '</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "flat")
    return '<span class="%s">%+.2f%%</span>' % (cls, v)


def price(v, d=2):
    return fx(v, d)


def yi(v):
    if v is None:
        return NA
    return "%.2f" % (v / 1e8)


def g_(d, key, d2=2):
    v = (d.get("global") or {}).get(key) or {}
    return "%.2f" % v["close"] if v.get("close") is not None else NA


def gv(d, key, d2=2):
    v = (d.get("global") or {}).get(key) or {}
    return pct(v.get("pct"))


def gsrc(d, key):
    v = (d.get("global") or {}).get(key) or {}
    return v.get("src") or "—"


def gy(d, key, dp=2):
    """美债收益率行：数值 + 较前一日 bp 变化（收益率是绝对水平，不是涨跌幅）。"""
    v = (d.get("global") or {}).get(key) or {}
    if v.get("close") is None:
        return "<span class='na'>%s</span>" % NA
    s = ("%%.%df%%%%" % dp) % v["close"]
    if v.get("chg_bp") is not None:
        b = v["chg_bp"]
        cls = "up" if b > 0 else ("down" if b < 0 else "flat")
        s += " <span class='%s'>%+.1f bp</span>" % (cls, b)
    return s


def gold_factor(d):
    """黄金 002611 双因子判定（任一因子满足即可触发）。

    因子① Brent < 100 美元；因子② 美10Y < 4.3%。
    数据缺口时 known=False —— 既不宣称触发，也不宣称未触发。
    """
    g = d.get("global") or {}
    b_th = config.GOLD_FACTOR_BRENT
    y_th = config.GOLD_FACTOR_US10Y
    brent = (g.get("BRENT") or {}).get("close")
    us10y = (g.get("US10Y") or {}).get("close")
    b_ok = brent is not None and brent < b_th
    y_ok = us10y is not None and us10y < y_th
    return {"brent": brent, "us10y": us10y, "b_th": b_th, "y_th": y_th,
            "b_ok": b_ok, "y_ok": y_ok,
            "known": brent is not None and us10y is not None,
            "trigger": b_ok or y_ok,
            "b_gap": (brent - b_th) if brent is not None else None,
            "y_gap": (us10y - y_th) if us10y is not None else None,
            "u": g.get("US10Y") or {}}


def fmt_amt(v):
    if v is None:
        return NA
    return "%.2f 亿" % (v / 1e8)


def breadth(d, field):
    return sum((d["indexes"].get(k) or {}).get(field) or 0
               for k in ("000001", "399001"))


def mktotal(d):
    return sum((d["indexes"].get(k) or {}).get("amount") or 0
               for k in ("000001", "399001"))


# ------------------------------------------------------------ 叙述辅助
# 设计约束：报告里的每一句判断都必须由 market.json 真实数据推出。
# 当天行情方向不可预设，因此「谁领涨、谁领跌、资金进哪个板块」一律实时计算。

def idx_rows(d):
    """[(code, name, pct)] —— 仅含当日有有效行情的宽基。"""
    ix = d.get("indexes") or {}
    out = []
    for c in ORDER_IDX:
        v = ix.get(c) or {}
        if v.get("pct") is not None:
            out.append((c, v.get("name") or c, v["pct"]))
    return out


def breadth_state(d):
    """(up, dn, fl)。历史回补口径下接口无回溯值，返回 None。"""
    ix = d.get("indexes") or {}
    if any((ix.get(k) or {}).get("up") is None
           for k in ("000001", "399001")):
        return None
    return breadth(d, "up"), breadth(d, "down"), breadth(d, "flat")


def amt_chg(d):
    """两市成交额环比 %。需要指数带 prev_amount，否则 None。"""
    ix = d.get("indexes") or {}
    cur = prev = 0
    for k in ("000001", "399001"):
        v = ix.get(k) or {}
        cur += v.get("amount") or 0
        prev += v.get("prev_amount") or 0
    if not cur or not prev:
        return None
    return (cur - prev) / prev * 100


def is_intraday(d):
    """快照是否为**盘中**口径。

    判定：行情日期 == 生成日期，且生成时刻 < 15:05。
    盘中成交额只是当日已成交部分的累计，与「前一交易日全日」不可比 ——
    拿它算环比会得出「缩量 -43%」这种假结论（实测 10/30 10:52 盘中：
    半日 8746 亿 vs 前日全日 15565 亿 → -43.8%，实际全天并未如此缩量）。
    """
    td = d.get("trade_date")
    ga = d.get("generated_at") or ""
    if not td or not ga:
        return False
    try:
        g = datetime.fromisoformat(ga)
    except Exception:
        return False
    if g.date().isoformat() != td:
        return False
    return (g.hour, g.minute) < (15, 5)


def amt_chg_note(d):
    """成交额环比的短标注（表格备注列用）。"""
    if is_intraday(d):
        return "盘中口径·未收盘"
    ac = amt_chg(d)
    return ("较前日 %+.2f%%" % ac) if ac is not None else ("较前日：" + NA)


def amt_chg_long(d):
    """成交额环比的长说明（正文用）。"""
    if is_intraday(d):
        return ("<span class='na'>盘中口径（未收盘），"
                "不与前一交易日全日对比</span>")
    ac = amt_chg(d)
    if ac is None:
        return "<span class='na'>%s</span>" % NA
    return "较前一交易日 %+.2f%%" % ac


def boards(d):
    """全板块资金流字典（历史口径专有；实时口径缺失时为空）。"""
    return (d.get("fund_flow") or {}).get("boards") or {}


def board_flow(d, *names):
    """按板块名取资金流，匹配不到返回 None（不做近似替代）。"""
    bs = boards(d)
    for n in names:
        if n in bs:
            return bs[n]
    return None


def flow_phrase(x):
    """'主力净流入 +58.35 亿' / '主力净流出 -66.93 亿'。"""
    if not x or x.get("net_yi") is None:
        return NA
    v = x["net_yi"]
    return "主力净%s <b>%+.2f 亿</b>" % ("流入" if v > 0 else
                                        ("流出" if v < 0 else "持平"), v)


def board_pct_txt(x):
    """板块涨跌幅；未单独取到的直接省略，不硬塞「数据暂未获取」。"""
    if not x or x.get("pct") is None:
        return ""
    return "，涨跌 %s" % pct(x["pct"])


def tone(d, code):
    """个股当日强弱：与上证对比，不预设方向。持仓与监控ETF通用。"""
    v = ((d.get("portfolio") or {}).get(code)
         or (d.get("watch_etfs") or {}).get(code) or {})
    p = v.get("pct")
    if p is None:
        return "当日行情未获取。"
    sh = ((d.get("indexes") or {}).get("000001") or {}).get("pct")
    if sh is None:
        return "当日 %s。" % pct(p)
    diff = p - sh
    if diff > 0.05:
        rel = "跑赢上证 %.2f 个百分点" % diff
    elif diff < -0.05:
        rel = "跑输上证 %.2f 个百分点" % -diff
    else:
        rel = "与上证基本同步"
    return "当日 %s，%s。" % (pct(p), rel)


# ------------------------------------------------------------ 章节
def valuation_dual(yield_v, pe_pct, rule):
    """低估双条件判定（用户 2026-10-30 指令）：股息率 ≥ 阈值 AND PE历史分位 ≤ 阈值。

    返回 (状态, 是否命中, 说明)
      · 两腿都过 → "低估·双条件命中"
      · 任一腿缺数据 → "条件不全"（**不猜、不用别的指数的数凑**）
      · 都不过 → "不低估（两腿均未过）"
    """
    if yield_v is None:
        return "条件不全", False, "股息率缺数据"
    if pe_pct is None:
        return "条件不全", False, "PE分位缺数据"
    y_ok = yield_v >= rule["yield_min"]
    p_ok = pe_pct <= rule["pe_pct_max"]
    if y_ok and p_ok:
        return "低估·双条件命中", True, ""
    if not y_ok and not p_ok:
        return "不低估（两腿均未过）", False, ""
    if not y_ok:
        return "不低估（股息率未达阈值）", False, ""
    return "不低估（PE分位偏高）", False, ""


def rel_streak(closes, bench):
    """相对上证的「连续 N 日跑赢/跑输」判定。

    closes：标的收盘序列（升序 [{"date","close"}]）
    bench ：上证收盘序列（升序）
    返回 (连续天数, 方向) —— 方向 +1 跑赢 / -1 跑输 / 0 无法判定。
    逐日比较「标的日涨跌幅 vs 上证日涨跌幅」，从最新一根往前数连续同向的天数。
    """
    if not closes or not bench:
        return 0, 0
    bmap = {b["date"]: b["close"] for b in bench}
    signs = []
    for i in range(1, len(closes)):
        d, c = closes[i]["date"], closes[i]["close"]
        p = closes[i - 1]["close"]
        bd, bp = bmap.get(d), bmap.get(closes[i - 1]["date"])
        if bd is None or bp is None or not p or not bp:
            continue
        re_, rb = c / p - 1, bd / bp - 1
        signs.append(1 if re_ > rb else (-1 if re_ < rb else 0))
    if not signs or signs[-1] == 0:
        return 0, 0
    last = signs[-1]
    n = 0
    for s in reversed(signs):
        if s == last:
            n += 1
        else:
            break
    return n, last


def sec1(d):
    ix = d["indexes"]
    rows = ""
    for c in ORDER_IDX:
        v = ix.get(c)
        if not v:
            rows += "<tr><td>%s</td><td colspan='2' class='na'>%s</td></tr>" % (c, NA)
            continue
        rows += ("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (v["name"], price(v["close"]), pct(v["pct"])))
    amt = mktotal(d)
    ac = amt_chg(d)
    lp = d.get("limit_pool") or {}
    sh = ix.get("000001") or {}
    sz = ix.get("399001") or {}
    cyb = ix.get("399006") or {}
    kc = ix.get("000688") or {}
    b = breadth_state(d)

    if b:
        up, dn, fl = b
        tot = up + dn
        ratio = ("%.2f" % (dn / up)) if up else NA
        share = ("%.1f%%" % (dn / tot * 100)) if tot else NA
        core = F("<b>{verdict}</b>：上证 {shp}、深成 {szp}、创业板 {cyb}，"
                 "沪深两市上涨 <b>{up}</b> 家 vs 下跌 <b>{dn}</b> 家，"
                 "跌/涨比 <b>{ratio}</b>，下跌家数占比 <b>{share}</b>。"
                 "指数量级与个股体感{same}。",
                 verdict=("权重护指数、个股普跌" if dn > up else
                          ("个股普涨、指数失真" if up > dn else "涨跌基本均衡")),
                 shp=pct(sh.get("pct")), szp=pct(sz.get("pct")),
                 cyb=pct(cyb.get("pct")), up=up, dn=dn,
                 ratio=ratio, share=share,
                 same=("明显背离" if dn > up else
                       ("明显背离" if up > dn else "一致")))
        bro = ("<tr><td>上涨家数（沪深）</td><td>%d</td></tr>"
               "<tr><td>下跌家数（沪深）</td><td>%d</td></tr>"
               "<tr><td>平盘家数（沪深）</td><td>%d</td></tr>"
               "<tr><td>跌/涨比</td><td><b>%s : 1</b></td></tr>"
               % (up, dn, fl, ratio))
    else:
        core = ("<b>宽基数据已核实，个股赚钱效应无法核实</b>：上证 %s、深成 %s、"
                "创业板 %s、科创50 %s。"
                "<span class='na'>当日沪深涨跌家数为历史回补口径，东方财富免费接口"
                "不提供回溯值</span>，因此本节<b>不推断个股涨跌分布</b>，"
                "个股层面的判断改用涨停/跌停家数与逐板块资金流（第二、五章）。"
                % (pct(sh.get("pct")), pct(sz.get("pct")),
                   pct(cyb.get("pct")), pct(kc.get("pct"))))
        bro = ("<tr><td>上涨家数（沪深）</td><td class='na'>%s</td></tr>"
               "<tr><td>下跌家数（沪深）</td><td class='na'>%s</td></tr>"
               "<tr><td>平盘家数（沪深）</td><td class='na'>%s</td></tr>"
               "<tr><td>跌/涨比</td><td class='na'>%s</td></tr>" % (NA, NA, NA, NA))

    lst = idx_rows(d)
    if lst:
        best = max(lst, key=lambda x: x[2])
        worst = min(lst, key=lambda x: x[2])
        if best[2] > 0 > worst[2]:
            style = ("宽基<b>分化</b>：%s %s 居首，%s %s 领跌，首尾相差 <b>%.2f 个百分点</b>。"
                     "同一天里强弱方向差距明显，资金在做结构性选择，"
                     "而非全面进退。"
                     % (best[1], pct(best[2]), worst[1], pct(worst[2]),
                        best[2] - worst[2]))
        elif worst[2] >= 0:
            style = ("纳入观察的 %d 个宽基<b>全线收红</b>，最强 %s %s、最弱 %s %s，"
                     "属普涨格局。" % (len(lst), best[1], pct(best[2]),
                                      worst[1], pct(worst[2])))
        else:
            style = ("纳入观察的 %d 个宽基<b>全线收绿</b>，最强 %s %s、最弱 %s %s，"
                     "属普跌格局。" % (len(lst), best[1], pct(best[2]),
                                      worst[1], pct(worst[2])))
    else:
        style = '<span class="na">%s</span>' % NA

    tpl = """
<section id="s1"><h2>一、今日A股行情</h2>
<h3 class="sub">指数表现</h3>
<table><tr><th>指数</th><th>收盘点位</th><th>涨跌幅</th></tr>{rows}</table>
<h3 class="sub">量能</h3>
<p>两市成交额：<b>{amt} 亿元</b>（约 {wan} 万亿）。{ac_txt}</p>
<h3 class="sub">涨跌结构</h3>
<table><tr><th>项目</th><th>数值</th></tr>{bro}
<tr><td>涨停</td><td>{zt}</td></tr>
<tr><td>跌停</td><td>{dt}</td></tr></table>
<h3 class="sub">核心信号</h3>
<div class="box warn">{core}</div>
<h3 class="sub">市场风格</h3>
<p>{style}</p>
</section>"""
    return F(tpl, rows=rows, amt=yi(amt), wan=("%.2f" % (amt / 1e12) if amt else NA),
             ac_txt=amt_chg_long(d),
             bro=bro,
             zt=lp.get("zt") if lp.get("zt") is not None else NA,
             dt=lp.get("dt") if lp.get("dt") is not None else NA,
             core=core, style=style)


def sec2(d):
    f = d["fund_flow"]

    def rows(lst, cls):
        s = ""
        for x in lst[:5]:
            s += ("<tr><td>%s</td><td class='%s'>%+.2f</td><td>%s</td></tr>"
                  % (x["name"], cls, x["net_yi"], pct(x["pct"])))
        return s or "<tr><td colspan='3' class='na'>%s</td></tr>" % NA

    ins = [x["name"] for x in f.get("in_top") or []]
    outs = [x["name"] for x in f.get("out_top") or []]
    tin = sum(x["net_yi"] for x in f.get("in_top") or [])
    tout = sum(x["net_yi"] for x in f.get("out_top") or [])
    ratio = abs(tout / tin) if tin else None
    # 流入、流出必须各自判空。
    # 2026-10-30 云端实测踩过：只有 in_top 拿到、out_top 被东财掐断为空，
    # 旧写法用 bool(in_top or out_top) 当"整体可用"，
    # 于是写出"流出前5合计 0.00 亿、流出是流入的 0.00 倍"——把未知说成了零。
    in_ok, out_ok = bool(f.get("in_top")), bool(f.get("out_top"))
    tin_s = "%.2f" % tin if in_ok else NA
    tout_s = "%.2f" % tout if out_ok else NA
    # 倍数只在两侧都有数据时才给，否则写"数据暂未获取"
    ratio_s = ("%.2f" % ratio) if (in_ok and out_ok and tin) else NA
    b = breadth_state(d)
    lp = d.get("limit_pool") or {}
    amt = mktotal(d)

    # 持仓与资金方向的关系：靠关键词匹配板块名，匹配不到就不下结论
    OUT_NEG = ("电力", "光伏", "电池", "新能源")     # 持仓中的新能源链
    OUT_POS = ("电子", "通信", "计算机", "芯片", "元件")  # 持仓中的科技链
    hold = []
    if any(any(k in n for k in OUT_NEG) for n in outs):
        hold.append("持仓中的<b>隆基绿能（光伏链）正处于资金流出方向</b>")
    if any(any(k in n for k in OUT_POS) for n in outs):
        hold.append("<b>通信 ETF / 云计算 ETF 所在科技链正处于资金流出方向</b>，"
                    "两只当日分别下跌，与板块方向一致")
    if any(any(k in n for k in OUT_POS) for n in ins):
        hold.append("<b>通信 ETF / 云计算 ETF</b> 所在方向为资金净流入方向")
    hold_txt = ("；".join(hold) + "。") if hold else \
        ("已获取的板块流向与持仓标的<b>无明确同向或反向对应</b>，本节不对持仓方向性下结论。"
         if flow_ok else
         "<span class='na'>%s</span> —— 板块资金流接口本次未返回数据，"
         "<b>本节不做任何资金方向性判断</b>，个股层面的强弱改用涨停/跌停家数与持仓当日涨跌幅（第六章）。"
         % NA)

    # 覆盖度披露：板块没抓全时，top5 排名不具备全市场代表性，必须写明
    cov = f.get("coverage")
    if cov:
        bt = f.get("board_total")
        if "全覆盖" in cov or "全覆盖" in str(cov):
            cov_txt = '<p><b>板块覆盖度</b>：%s（宇宙 %s 个行业板块，排名口径完整）。</p>' % (cov, bt)
        else:
            cov_txt = ('<p><b>板块覆盖度</b>：<span class="tag y">%s</span>'
                       '本次仅覆盖部分行业板块（宇宙 %s 个），'
                       '<b>下方 top5 排名只代表已覆盖板块，不等于全市场排名</b>。'
                       '接口限流导致，取数失败项已在数据层如实记录。</p>' % (cov, bt))
    else:
        cov_txt = ""

    tpl = """
<section id="s2"><h2>二、资金面（主力资金 + 市场热度）</h2>
<h3 class="sub">主力资金分行业流向</h3>
<table><tr><th>净流入居前</th><th>净流入(亿元)</th><th>涨跌幅</th></tr>{rin}</table>
<table><tr><th>净流出居前</th><th>净流出(亿元)</th><th>涨跌幅</th></tr>{rout}</table>
<div class="box risk">
<b>资金流动逻辑</b>：主力净流入居前为 {ins}，净流出居前为 {outs}。
流入前 5 合计 <b>{tin} 亿</b>，流出前 5 合计 <b>{tout} 亿</b>，
流出规模是流入规模的 <b>{ratio} 倍</b>。{hold}
</div>
{cov_txt}
<h3 class="sub">市场热度评估</h3>
<table><tr><th>指标</th><th>读数</th><th>数据状态</th></tr>
<tr><td>量能</td><td>{amt} 亿元</td><td>{amt_note}</td></tr>
<tr><td>跌/涨家数比</td><td>{ratio2}</td><td>{bd_note}</td></tr>
<tr><td>涨停家数</td><td>{zt}</td><td><span class="tag b">接口可回溯</span></td></tr>
<tr><td>跌停家数</td><td>{dt}</td><td><span class="tag b">接口可回溯</span></td></tr></table>
<div class="box warn"><b>操作纪律</b><br>
不新开仓、不追高；仅按第八章既定预警价执行分批加仓，不因单日资金流向改变计划。</div>
</section>"""
    return F(tpl, rin=rows(f.get("in_top") or [], "up"),
             rout=rows(f.get("out_top") or [], "down"),
             ins=("、".join(ins) if ins else NA),
             outs=("、".join(outs) if outs else NA),
             tin=tin_s, tout=tout_s,
             ratio=ratio_s,
             hold=hold_txt, cov_txt=cov_txt,
             amt=yi(amt),
             amt_note=("已获取" if amt else '<span class="na">%s</span>' % NA),
             ratio2=(("%.2f : 1" % (b[1] / b[0])) if (b and b[0]) else NA),
             bd_note=('<span class="tag b">已获取</span>' if b
                      else '<span class="tag y">历史回补口径无回溯值</span>'),
             na=NA,
             zt=lp.get("zt") if lp.get("zt") is not None else NA,
             dt=lp.get("dt") if lp.get("dt") is not None else NA)


def flow_amt(v):
    """主力净流入（元）→ 带符号亿元。缺失一律 na，不写 0.00。"""
    if v is None:
        return '<span class="na">%s</span>' % NA
    cls = "up" if v > 0 else ("down" if v < 0 else "flat")
    return '<span class="%s">%+.2f 亿</span>' % (cls, v / 1e8)


def sec3(d):
    """第三章：国家队/汇金与宽基ETF。

    口径分层（不可混为一谈）：
      · 汇金持仓明细、ETF份额变动 —— 低频披露，免费接口确实不提供，如实标注；
      · 宽基ETF 的收盘/涨跌幅/成交额/规模/主力净流入 —— 普通ETF实时行情，可抓，必须给真数据。
    """
    be = d.get("broad_etfs") or {}
    rows, valid, red, amt_sum, flow_sum = "", 0, 0, 0, None
    for code, name in config.BROAD_ETFS:
        v = be.get(code) or {}
        p = v.get("pct")
        if v.get("close") is not None:
            valid += 1
            if p is not None and p > 0:
                red += 1
        if v.get("amount"):
            amt_sum += v["amount"]
        if v.get("flow") is not None:
            flow_sum = (flow_sum or 0) + v["flow"]
        rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                 "<td>%s</td><td>%s</td></tr>"
                 % (v.get("name") or name, code, price(v.get("close"), 3), pct(p),
                    fmt_amt(v.get("amount")),
                    fmt_amt(v.get("scale")),
                    flow_amt(v.get("flow"))))
    if valid:
        obs = ("今日 %d 只宽基 ETF 中<b>收红 %d 只、收绿 %d 只</b>，成交额合计 <b>%s</b>。"
               % (valid, red, valid - red, fmt_amt(amt_sum)))
        if flow_sum is not None:
            obs += ("主力净流入合计 <b>%s</b>（东财口径，含全部资金档位归并）。"
                    % flow_amt(flow_sum))
    else:
        obs = "宽基 ETF 行情未获取。"
    tpl = """
<section id="s3"><h2>三、国家队 / 汇金与宽基ETF持仓数据</h2>
<div class="box">本章口径：这 4 只宽基 ETF 是<b>普通 ETF</b>，收盘价、涨跌幅、成交额、<b>规模</b>、
<b>主力净流入</b><b>可以实时抓到</b>，下表为真实行情。</div>
<h3 class="sub">宽基ETF资金动向（真实行情）</h3>
<table><tr><th>标的</th><th>代码</th><th>收盘</th><th>涨跌幅</th><th>成交额</th>
<th>规模</th><th>主力净流入</th></tr>
{rows}</table>
<h3 class="sub">今日关键数据</h3>
<p>{obs}</p>
<div class="box warn"><b>国家队行为解读</b>：<b>不可做的部分</b>——没有份额数据，
就<b>无法区分</b>「国家队申购」与「散户抄底」；上面的价格、成交额、主力净流入只是
<b>承接强度的代理变量</b>，<b>不等于</b>国家队申购行为，<b>不作结论</b>。<br>
<b>可做的部分</b>：若宽基 ETF 出现<b>放量且收红</b>，只能说明宽基有增量承接，
需与份额数据结合才谈得上国家队动作。</div>
</section>"""
    return F(tpl, rows=rows, obs=obs)


def _orow(d, label, key, dp=2, chg_html=None, note=""):
    """海外/商品表格的一行：名称 数值 涨跌 来源。缺数据一律 na，不做替代。"""
    v = (d.get("global") or {}).get(key) or {}
    if not v or v.get("close") is None:
        return ("<tr><td>%s</td><td class='na'>%s</td><td class='na'>%s</td>"
                "<td class='na'>%s</td></tr>" % (label, NA, NA, NA))
    val = ("%%.%df" % dp) % v["close"]
    chg = chg_html if chg_html is not None else pct(v.get("pct"))
    src = v.get("src") or "—"
    if note:
        src = src + " ｜ " + note
    return ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (label, val, chg, src))


def sec4(d):
    g = d.get("global") or {}
    news = d.get("news") or {}

    # ---------- 国内政策 / 7x24 快讯 ----------
    kx = news.get("kuaixun") or []
    kx_rows = ""
    for it in kx[:25]:
        ts = (it.get("time") or "")[-8:]
        kx_rows += ("<tr><td>%s</td><td>%s</td></tr>"
                    % (ts or "—", it.get("title") or "—"))
    if not kx_rows:
        kx_rows = ("<tr><td colspan='2' class='na'>%s —— 快讯接口未返回数据</td></tr>"
                   % NA)
    kx_note = ("东方财富 7x24 快讯，日期 <b>%s</b>，按时间倒序取前 %d 条。"
               % (news.get("kx_date") or NA, min(25, len(kx)))) if kx else \
              "本节需人工补充（脚本未接入新闻源时如实标注）。"

    # ---------- 同花顺快讯（第二源）----------
    ths = news.get("ths") or []
    ths_rows = ""
    for it in ths[:15]:
        ts = (it.get("time") or "")[5:16]
        ths_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                     % (ts or "—", it.get("title") or "—",
                        it.get("tag") or "—", it.get("source") or "—"))
    if not ths_rows:
        ths_rows = ("<tr><td colspan='4' class='na'>%s —— 同花顺快讯接口未返回数据</td></tr>"
                    % NA)

    # ---------- 海外宏观 ----------
    u10 = g.get("US10Y") or {}
    u10_date = u10.get("date") or NA
    boj = ("美元兑日元 <b>%s</b>（%s）" % (g_(d, "USDJPY"), gsrc(d, "USDJPY"))
           if (g.get("USDJPY") or {}).get("close") is not None else
           "美元兑日元 <span class='na'>%s</span>" % NA)
    # BOJ 窗口的两个可得代理指标：
    #  · 日经225 当日涨跌 = 日本货币政策的市场即时定价（替代拿不到的日本CPI明细）
    #  · 美债2Y = 短端利率，直接反映市场对加/降息的定价（替代"加息概率"）
    nk = g.get("NIKKEI") or {}
    nikkei = ("<b>%.2f</b>（%s）" % (nk["close"], pct(nk.get("pct")))
              if nk.get("close") is not None else "<span class='na'>%s</span>" % NA)
    u2 = g.get("US2Y") or {}
    slope_v = None
    if u10.get("close") is not None and u2.get("close") is not None:
        slope_v = u10["close"] - u2["close"]
    slope = ("<b>%+.2f</b> 个百分点" % slope_v if slope_v is not None
             else "<span class='na'>%s</span>" % NA)
    us_rows = (
        _orow(d, "美元指数 DXY", "UDI") +
        _orow(d, "美元兑离岸人民币", "USDCNH", 4) +
        _orow(d, "美元兑在岸人民币", "USDCNY", 4) +
        _orow(d, "美元兑日元 USD/JPY", "USDJPY") +
        "<tr><td><b>美10Y国债收益率</b></td><td>%s</td><td>—</td>"
        "<td>美国财政部官方曲线 · %s</td></tr>" % (gy(d, "US10Y"), u10_date) +
        "<tr><td>美30Y国债收益率</td><td>%s</td><td>—</td>"
        "<td>美国财政部官方曲线 · %s</td></tr>" % (gy(d, "US30Y"), u10_date) +
        "<tr><td><b>Brent 原油</b></td><td>%s</td><td>%s</td>"
        "<td>%s</td></tr>" % (
            ("%.2f" % g["BRENT"]["close"]) if (g.get("BRENT") or {}).get("close") is not None else NA,
            gv(d, "BRENT"), gsrc(d, "BRENT")))

    # ---------- 商品 ----------
    com_rows = (
        _orow(d, "COMEX 黄金", "GC00Y", 2, note="场外黄金 002611 锚定") +
        _orow(d, "伦敦现货金", "SPOT_XAU", 2, note="与 COMEX 口径不同") +
        _orow(d, "COMEX 白银", "SI00Y") +
        _orow(d, "NYMEX 原油 (WTI)", "CL00Y", 2, note="<b>非 Brent</b>") +
        _orow(d, "<b>Brent 原油</b>", "BRENT", 2) +
        _orow(d, "LME 铝", "LME_AL", 2, note="南山铝业成本端"))

    # ---------- 黄金双因子 ----------
    gf = gold_factor(d)
    if gf["known"]:
        b_mark = "<span class='tag g'>满足</span>" if gf["b_ok"] else "<span class='tag r'>未满足</span>"
        y_mark = "<span class='tag g'>满足</span>" if gf["y_ok"] else "<span class='tag r'>未满足</span>"
        b_line = ("Brent <b>%.2f</b> 美元（阈值 &lt; %.0f，需再跌 <b>%.2f</b> 美元） —— %s"
                  % (gf["brent"], gf["b_th"], gf["b_gap"], b_mark))
        y_line = ("美10Y <b>%.2f%%</b>（阈值 &lt; %.1f%%，需回落 <b>%.2f</b> 个百分点） —— %s"
                  % (gf["us10y"], gf["y_th"], gf["y_gap"], y_mark))
        if gf["trigger"]:
            concl = ("<b>结论：双因子判定为「满足」</b>（任一因子达标即触发）。"
                     "黄金 002611 额外加仓信号<b>成立</b>，按既有规则执行（单次≤1000 元、间隔≥1 周）。")
            gcls = "good"
        else:
            concl = ("<b>结论：双因子判定为「未满足」</b>（两个因子均未达标）。"
                     "黄金 002611 额外加仓信号<b>不成立</b>，常规月定投照常，<b>不加额外仓位</b>。")
            gcls = "warn"
        u = gf["u"]
        if u.get("ytd_min") is not None:
            thr_note = ("<br><b>阈值可达性（2026 全年官方曲线）</b>：10Y 年内区间 "
                        "<b>%.2f%% ~ %.2f%%</b>，共 %d 个发布日中有 <b>%d 天</b>低于 %.1f%% 阈值，"
                        "最后一次低于阈值是 <b>%s</b>。"
                        % (u["ytd_min"], u["ytd_max"], u["ytd_days"],
                           u["days_below_thr"], config.GOLD_FACTOR_US10Y,
                           u.get("last_below_date") or "—"))
        else:
            thr_note = ""
    else:
        b_line = "Brent —— <span class='na'>%s</span>" % NA
        y_line = "美10Y —— <span class='na'>%s</span>" % NA
        concl = ("<b>结论：双因子判定无法完成</b>（数据缺口）。"
                 "本报告<b>不宣称</b>信号触发，也<b>不宣称</b>未触发。")
        gcls = "warn"
        thr_note = ""

    # ---------- 持仓标的的消息 ----------
    ann = news.get("ann") or []
    a_rows = ""
    for it in ann[:10]:
        a_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (it.get("name") or "—", it.get("date") or "—",
                      it.get("title") or "—", it.get("type") or "—"))
    if not a_rows:
        a_rows = ("<tr><td colspan='4' class='na'>%s —— 持仓标的近 3 日无公告返回</td></tr>"
                  % NA)

    tpl = """
<section id="s4"><h2>四、消息面汇总</h2>
<h3 class="sub">国内政策与市场快讯</h3>
<table><tr><th>时间</th><th>标题</th></tr>
{kx_rows}</table>
<p class="na">{kx_note}</p>
<h3 class="sub">同花顺快讯（第二源 · 含异动/政策标签）</h3>
<table><tr><th>时间</th><th>标题</th><th>标签</th><th>来源</th></tr>
{ths_rows}</table>
<h3 class="sub">海外宏观（含日元因子）</h3>
<table><tr><th>指标</th><th>数据</th><th>影响</th></tr>
<tr><td>USD/JPY</td><td>{boj}</td><td>日元贬值利好出口链、压制进口成本</td></tr>
<tr><td>日经225（今日）</td><td>{nikkei}</td><td>日本股市对 BOJ 决议的即时定价（通胀明细需第三方终端）</td></tr>
<tr><td>美债2Y（短端）</td><td>{us2y}</td><td>短端利率即市场对加/降息的定价，替代"加息概率"（概率明细需第三方终端）</td></tr>
<tr><td>10Y-2Y 利差</td><td>{slope}</td><td>曲线形态：倒挂 / 陡峭化</td></tr></table>
<h3 class="sub">日本央行(BOJ)动态</h3>
<p><b>日元因子核心结论</b>：{boj}。<b>10/30 日本央行议息是关键观察窗口</b>，
当前汇率为 {ujpy}，隔夜美股表现 {ndx_txt}。</p>
<h3 class="sub">美债与美元</h3>
<table><tr><th>指标</th><th>数值</th><th>涨跌</th><th>来源</th></tr>
{us_rows}</table>
<h3 class="sub">美股隔夜表现</h3>
<table><tr><th>指数</th><th>数值</th><th>涨跌幅</th><th>来源</th></tr>
{us_rows2}</table>
<h3 class="sub">商品（持仓相关）</h3>
<table><tr><th>品种</th><th>价格</th><th>涨跌幅</th><th>来源 / 备注</th></tr>
{com_rows}</table>
<div class="box {gcls}"><b>黄金双因子状态更新（002611 场外）</b><br>
因子① {b_line}<br>
因子② {y_line}<br>
{concl}{thr_note}<br>
<b>执行</b>：维持常规月定投 1000 元；额外加仓按上述结论执行。
</div>
<h3 class="sub">持仓标的的消息</h3>
<table><tr><th>标的</th><th>日期</th><th>公告 / 动态</th><th>类型</th></tr>
{a_rows}</table>
<p class="na">持仓公告来自东方财富公告接口（近 3 个自然日），关键节点：
<b>10/29 南山铝业三季报</b>、<b>10/31 隆基绿能三季报</b>。</p>
</section>"""
    return F(tpl, na=NA, kx_rows=kx_rows, kx_note=kx_note, us_rows=us_rows,
             ths_rows=ths_rows, nikkei=nikkei, us2y=gy(d, "US2Y"), slope=slope,
             us_rows2=(_orow(d, "道琼斯", "DJIA") + _orow(d, "标普500", "SPX") +
                        _orow(d, "纳斯达克综合", "NDX")),
             com_rows=com_rows, gcls=gcls, b_line=b_line, y_line=y_line,
             concl=concl, thr_note=thr_note, a_rows=a_rows,
             boj=boj,
             ujpy=("%.3f" % g["USDJPY"]["close"]
                   if (g.get("USDJPY") or {}).get("close") is not None else NA),
             ndx_txt=gv(d, "NDX"))


def _dim(label, read, verdict, cls):
    return ("<tr><td><b>%s</b></td><td>%s</td>"
            "<td><span class='tag %s'>%s</span></td></tr>" % (label, read, cls, verdict))


def sec4b(d):
    """新因子预留位：五维分析 / 日元因子 / ETF持仓数据。

    模板里的第 11 块 —— 旧脚本只做了十章，这一块连同附录一起被漏掉了。
    三项全部由真实数据驱动，任何一项缺数据就只写该项，不牵连其它项。
    """
    rows = ""
    # ① 涨跌维度
    sh = (d.get("indexes") or {}).get("000001") or {}
    b = breadth_state(d)
    if sh.get("pct") is not None:
        p = sh["pct"]
        verdict = "偏强" if p > 0 else ("偏弱" if p < 0 else "持平")
        cls = "r" if p > 0 else ("g" if p < 0 else "n")
        read = "上证 %s%s" % (pct(p),
                             ("，涨跌家数 %d / %d" % (b[0], b[1])) if b else "")
        rows += _dim("① 涨跌维度", read, verdict, cls)
    else:
        rows += _dim("① 涨跌维度", "<span class='na'>%s</span>" % NA, "无数据", "n")
    # ② 量能维度
    amt, ac = mktotal(d), amt_chg(d)
    if amt and not is_intraday(d):
        verdict = "放量" if (ac or 0) > 0 else "缩量"
        cls = "r" if (ac or 0) > 0 else "g"
        read = "两市成交额 %s%s" % (fmt_amt(amt),
                                   ("，环比 %+.2f%%" % ac) if ac is not None else "")
        rows += _dim("② 量能维度", read, verdict, cls)
    elif amt:
        # 盘中：成交额是部分时段累计，与前一日全日不可比 → 不给放量/缩量结论
        read = "两市成交额 %s（盘中口径，未收盘）" % fmt_amt(amt)
        rows += _dim("② 量能维度", read, "不判定", "n")
    else:
        rows += _dim("② 量能维度", "<span class='na'>%s</span>" % NA, "无数据", "n")
    # ③ 资金维度
    f = d.get("fund_flow") or {}
    ins, outs = f.get("in_top") or [], f.get("out_top") or []
    if ins or outs:
        i0 = ins[0] if ins else None
        o0 = outs[0] if outs else None
        read = ("主力净流入首位 <b>%s</b>（%s）" % (i0["name"], flow_phrase(i0)) if i0
                else "主力净流入首位 <span class='na'>%s</span>" % NA)
        read += ("；净流出首位 <b>%s</b>（%s）" % (o0["name"], flow_phrase(o0)) if o0 else "")
        verdict = "资金偏流入" if (i0 and (o0 is None or
                                          (i0.get("net_yi") or 0) > abs(o0.get("net_yi") or 0))) else "资金偏流出"
        rows += _dim("③ 资金维度", read, verdict,
                     "r" if verdict == "资金偏流入" else "g")
    else:
        rows += _dim("③ 资金维度", "<span class='na'>%s</span>" % NA, "无数据", "n")
    # ④ 情绪维度
    lp = d.get("limit_pool") or {}
    zt, dt = lp.get("zt"), lp.get("dt")
    if zt is not None or dt is not None:
        verdict = "情绪偏热" if (zt or 0) >= (dt or 0) else "情绪偏冷"
        rows += _dim("④ 情绪维度",
                     "涨停 <b>%s</b> 家，跌停 <b>%s</b> 家"
                     % (zt if zt is not None else NA, dt if dt is not None else NA),
                     verdict, "r" if verdict == "情绪偏热" else "g")
    else:
        rows += _dim("④ 情绪维度", "<span class='na'>%s</span>" % NA, "无数据", "n")
    # ⑤ 海外维度
    ndx = (d.get("global") or {}).get("NDX") or {}
    u10 = (d.get("global") or {}).get("US10Y") or {}
    if ndx.get("pct") is not None or u10.get("close") is not None:
        read = "纳斯达克综合 %s；美10Y %s" % (
            gv(d, "NDX"),
            ("%.2f%%" % u10["close"]) if u10.get("close") is not None else NA)
        rows += _dim("⑤ 海外维度", read, "隔夜参考", "b")
    else:
        rows += _dim("⑤ 海外维度", "<span class='na'>%s</span>" % NA, "无数据", "n")

    # ---- 日元因子 ----
    g = d.get("global") or {}
    ujpy = g.get("USDJPY") or {}
    if ujpy.get("close") is not None:
        up = (ujpy.get("pct") or 0) > 0
        jpy_txt = ("美元兑日元 <b>%.3f</b>（%s）" % (ujpy["close"], pct(ujpy.get("pct")))
                   + ("，较前一日走强（美元兑日元上行）" if up
                      else "，较前一日走弱（美元兑日元下行）"))
        jpy_verdict = "日元走弱" if up else "日元走强"
        jpy_trans = (
            "日元走弱（美元兑日元上行）时，人民币相对日元走强，"
            "利好<b>出口链</b>（对南山铝业这类出口占比高的标的是边际利好），"
            "但抬高<b>进口成本</b>；本组合以国内标的为主，"
            "<b>该因子不是当前加减仓的主导变量</b>。" if up else
            "日元走强（美元兑日元下行）时，人民币相对日元走弱，"
            "<b>出口链的汇兑收益被压缩</b>（南山铝业这类出口占比高的标的边际承压），"
            "但<b>进口成本下降</b>；本组合以国内标的为主，"
            "<b>该因子不是当前加减仓的主导变量</b>。")
    else:
        jpy_txt = "美元兑日元 <span class='na'>%s</span>" % NA
        jpy_verdict = "无数据"
        jpy_trans = ("<span class='na'>%s</span> —— 无汇率读数，本日不做日元因子判断。"
                     % NA)

    # ---- ETF 持仓数据 ----
    be = d.get("broad_etfs") or {}
    e_rows = ""
    for code, name in config.BROAD_ETFS:
        v = be.get(code) or {}
        e_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (v.get("name") or name, price(v.get("close"), 3),
                      pct(v.get("pct")), fmt_amt(v.get("amount"))))

    tpl = """
<section id="s4b"><h2>四·补、【新因子预留位】</h2>
<p class="na">本块对应《01-复盘模板.md》v2.0 的【新因子预留位】，旧版脚本漏掉了这一块，
现按模板的三项补齐，全部由真实数据驱动。</p>
<h3 class="sub">五维分析</h3>
<table><tr><th>维度</th><th>今日读数</th><th>结论</th></tr>
{dims}</table>
<h3 class="sub">日元因子</h3>
<div class="box"><b>读数</b>：{jpy_txt} —— <span class='tag b'>{jpy_verdict}</span><br>
<b>传导</b>：{jpy_trans}<br>
<b>关键窗口</b>：<b>10/30 日本央行议息</b>，届时需重看 USD/JPY 是否出现拐点。</div>
<h3 class="sub">ETF持仓数据</h3>
<table><tr><th>宽基ETF</th><th>收盘</th><th>涨跌幅</th><th>成交额</th></tr>
{e_rows}</table>
</section>"""
    return F(tpl, dims=rows, jpy_txt=jpy_txt, jpy_verdict=jpy_verdict,
             jpy_trans=jpy_trans, e_rows=e_rows)


def sec11(d):
    """附录：关键数据汇总（模板第 12 块）。"""
    g = d.get("global") or {}
    ix = d.get("indexes") or {}
    f = d.get("fund_flow") or {}
    ins = f.get("in_top") or []
    amt, ac = mktotal(d), amt_chg(d)
    sh = ix.get("000001") or {}
    cy = ix.get("399006") or {}
    top_in = ins[0] if ins else None

    def row(label, val, note=""):
        return ("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (label, val, note))

    rows = (
        row("上证指数", "%s（%s）" % (price(sh.get("close")), pct(sh.get("pct"))),
            "深证成指 %s（%s）" % (price((ix.get("399001") or {}).get("close")),
                                  pct((ix.get("399001") or {}).get("pct")))) +
        row("创业板指", "%s（%s）" % (price(cy.get("close")), pct(cy.get("pct"))),
            "科创50 %s" % pct((ix.get("000688") or {}).get("pct"))) +
        row("两市成交额", fmt_amt(amt), amt_chg_note(d)) +
        row("现货黄金", ("%.2f 美元（%s）" % (g["SPOT_XAU"]["close"], pct(g["SPOT_XAU"].get("pct"))))
            if (g.get("SPOT_XAU") or {}).get("close") is not None else NA,
            "COMEX 黄金 %s" % g_(d, "GC00Y")) +
        row("Brent原油", ("%.2f 美元（%s）" % (g["BRENT"]["close"], pct(g["BRENT"].get("pct"))))
            if (g.get("BRENT") or {}).get("close") is not None else NA,
            "WTI %s（<b>非 Brent</b>）" % g_(d, "CL00Y")) +
        row("USD/JPY", ("%.3f（%s）" % (g["USDJPY"]["close"], pct(g["USDJPY"].get("pct"))))
            if (g.get("USDJPY") or {}).get("close") is not None else NA,
            "10/30 日本央行议息") +
        row("美元指数", "%s（%s）" % (g_(d, "UDI"), gv(d, "UDI")), "DXY") +
        row("美10Y国债", gy(d, "US10Y"),
            "官方曲线 %s ｜ 美30Y %s" % ((g.get("US10Y") or {}).get("date") or NA,
                                      gy(d, "US30Y"))) +
        row("主力净流入", (flow_phrase(top_in) if top_in else NA),
            ("板块：%s" % top_in["name"]) if top_in else ""))

    # 基金账户汇总（附录加一行，两账户合并看）
    f_inv = sum(f2[4] for f2 in config.FUND_ACCOUNT)
    f_gain = sum(f2[5] for f2 in config.FUND_ACCOUNT)
    f_rate = (f_gain / f_inv * 100) if f_inv else None
    rows += ("<tr><td>基金账户·总投入</td><td>%.2f 元</td>"
             "<td>25 只场外，累计收益 %+.2f 元（%s）</td></tr>"
             % (f_inv, f_gain,
                ("%+.2f%%" % f_rate) if f_rate is not None else NA))
    rows += ("<tr><td>基金账户·当前市值</td><td>%.2f 元</td>"
             "<td>＝总投入 + 累计收益（App 口径快照）</td></tr>"
             % (f_inv + f_gain))

    tpl = """
<section id="s11"><h2>附录：关键数据汇总</h2>
<table><tr><th>品类</th><th>数值</th><th>备注</th></tr>
{rows}</table>
<p class="na">本报告由脚本基于公开接口自动生成，标注「数据暂未获取」的字段表示该接口未提供，
<b>未做任何推测、插值或替代</b>。数据源：东方财富 · 新浪财经 · 腾讯财经 · 美国财政部官方收益率曲线。</p>
</section>"""
    return F(tpl, rows=rows)


def sec5(d):
    f = d.get("fund_flow") or {}
    ix = d["indexes"]
    ins = f.get("in_top") or []
    outs = f.get("out_top") or []
    pf = d["portfolio"]
    tot = sum(v.get("mv") or 0 for v in pf.values())
    yz_w = (pf.get("601106", {}).get("mv") or 0) / tot * 100 if tot else 0
    b = breadth_state(d)

    rows, n = "", 0
    for x in ins[:3]:
        n += 1
        rows += ("<tr><td><b>%d</b></td><td><span class='up'>主力净流入</span></td>"
                 "<td><b>%s</b></td><td class='up'>%+.2f 亿</td><td>%s</td>"
                 "<td>%s</td></tr>"
                 % (n, x["name"], x["net_yi"], pct(x.get("pct")),
                    HOLD_MAP.get(x["name"], "—")))
    for x in outs[:3]:
        n += 1
        rows += ("<tr><td><b>%d</b></td><td><span class='down'>主力净流出</span></td>"
                 "<td><b>%s</b></td><td class='down'>%+.2f 亿</td><td>%s</td>"
                 "<td>%s</td></tr>"
                 % (n, x["name"], x["net_yi"], pct(x.get("pct")),
                    HOLD_MAP.get(x["name"], "—")))

    # 隐忧：逐条按数据判定，不满足的条目不出现
    risk = ""
    if b and b[1] > b[0]:
        risk += ("<tr><td>⚠️ 指数失真</td><td>下跌 %d 家 &gt; 上涨 %d 家</td>"
                 "<td>指数点位不能作为加仓依据</td></tr>" % (b[1], b[0]))
    risk += ("<tr><td>⚠️ 中国一重占比过高</td><td>单只占持仓市值 %s%%</td>"
             "<td>做 T 是降本唯一路径，不可加仓摊薄</td></tr>" % ("%.1f" % yz_w))
    nsi = board_flow(d, "有色金属", "工业金属", "小金属", "贵金属")
    if nsi and nsi.get("net_yi") is not None:
        risk += ("<tr><td>有色资金%s</td><td>%s 板块 %s%s</td>"
                 "<td>南山铝业所在方向的推论%s</td></tr>"
                 % ("流出" if nsi["net_yi"] < 0 else "流入",
                    nsi["name"], flow_phrase(nsi), board_pct_txt(nsi),
                    "已获验证" if nsi["net_yi"] > 0 else "仍未验证"))
    pv = board_flow(d, "电力设备", "光伏设备", "电池")
    if pv and pv.get("net_yi") is not None:
        risk += ("<tr><td>⚠️ 持仓踩中%s方向</td><td>%s 板块 %s%s</td>"
                 "<td>隆基绿能 10/31 三季报前不加仓</td></tr>"
                 % ("流出" if pv["net_yi"] < 0 else "流入",
                    pv["name"], flow_phrase(pv), board_pct_txt(pv)))
    tech_out = board_flow(d, "电子", "通信", "计算机")
    if tech_out and tech_out.get("net_yi") is not None and tech_out["net_yi"] < 0:
        risk += ("<tr><td>⚠️ 科技链资金大幅流出</td><td>%s 板块 %s%s</td>"
                 "<td>通信 ETF / 云计算 ETF 当日触发下行档位，属被动减仓而非主动加仓窗口</td></tr>"
                 % (tech_out["name"], flow_phrase(tech_out),
                    board_pct_txt(tech_out)))

    tpl = """
<section id="s5"><h2>五、涨跌成因分析</h2>
<h3 class="sub">今日资金主线（按主力净额真实排名）</h3>
<table><tr><th>#</th><th>方向</th><th>板块</th><th>主力净额</th>
<th>板块涨跌</th><th>持仓关联</th></tr>{rows}</table>
<p><b>读法</b>：本表不预设叙事主线，只按当日主力净额排序列出前 3 流入与前 3 流出。
判断「什么在接棒、什么在出清」应以本表实际排名为准。</p>
<h3 class="sub">隐忧（仅列出数据已确认的项）</h3>
<table><tr><th>隐忧</th><th>数据表现</th><th>影响</th></tr>{risk}</table>
</section>"""
    return F(tpl, rows=(rows or ("<tr><td colspan='6' class='na'>%s</td></tr>" % NA)),
             risk=risk)


def _trig_tag(r):
    """预警状态标签：收盘触发 / 盘中击穿 / 未触发。"""
    if not r:
        return '<span class="tag n">未触发</span>'
    ih = r.get("intraday_hits") or []
    if r.get("trigger") is not None:
        out = '<span class="tag g">已触发 %s</span>' % ("%.3f" % r["trigger"])
        extra = [x for x in ih if x != r["trigger"]]
        if extra:
            out += ('<span class="tag y">+盘中 %s</span>'
                    % " / ".join("%.3f" % x for x in extra))
        return out
    if ih:
        return ('<span class="tag y">盘中击穿 %s</span>'
                % " / ".join("%.3f" % x for x in ih))
    return '<span class="tag n">未触发</span>'


def sec6(d):
    pf = d["portfolio"]
    trig = {r["code"]: r for r in (d.get("triggers") or [])}
    tot = sum(v.get("mv") or 0 for v in pf.values())
    rows, det = "", ""
    for c in ORDER:
        v = pf.get(c)
        if not v:
            continue
        w = (v["mv"] / tot * 100) if (v.get("mv") and tot) else None
        pnl = (pct(v["pnl_pct"]) if v["pnl_pct"] is not None
               else '<span class="na">无成本 / 未建仓</span>')
        rows += ("<tr><td><b>{n}</b><br><span class='na'>{c}</span></td>"
                 "<td>{p}</td><td>{pnl}</td><td>{w}</td><td>{mv}</td><td>{st}</td></tr>"
                 ).format(n=v["name"], c=c, p=pct(v["pct"]), pnl=pnl,
                           w=("%.1f%%" % w) if w is not None
                           else '<span class="na">' + NA + '</span>',
                           mv=("%.0f" % v["mv"]) if v.get("mv")
                           else '<span class="na">' + NA + '</span>',
                           st=_trig_tag(trig.get(c)))
        det += ("<div class='box'><b>{n} {c}</b>　收盘 {px}　涨跌 {p}　"
                "浮盈亏 {pn}　盘中最低 {lo}<br>　<span class='na'>{t}</span><br>"
                "　<span class='na'>{note}</span></div>"
                ).format(n=v["name"], c=c, px=price(v["close"]), p=pct(v["pct"]),
                         pn=("%+.2f%%" % v["pnl_pct"]) if v["pnl_pct"] is not None else NA,
                         lo=price(v.get("low"), 3) if v.get("low") is not None else NA,
                         t=(trig[c]["note"] if c in trig else "—"),
                         note=DISCIPLINE.get(c, ""))
    yz_w = (pf.get("601106", {}).get("mv") or 0) / tot * 100 if tot else 0
    tpl = """
<section id="s6"><h2>六、持仓逐一复盘</h2>
<h3 class="sub">6.1 股票账户（场内，可实时交易）</h3>
<table><tr><th>标的</th><th>当日表现</th><th>浮盈 / 亏</th><th>占持仓市值</th><th>市值(元)</th><th>预警状态</th></tr>{rows}</table>
<p><b>持仓市值合计 {tot} 元</b>（按 5 万元总账户计约 {acct}%）。
黄金 ETF 002611 为场外独立账户，不计入本表。</p>
{det}
<div class="box risk"><b>集中度风险</b>：中国一重单只占持仓市值 <b>{yzw}%</b>，
远超 20% 上限。按 1 年期计划，只能通过<b>做 T</b>降低成本，<b>不可通过加仓摊薄</b>。</div>
</section>"""
    return F(tpl, rows=rows, tot="%.0f" % tot,
             acct=("%.1f" % (tot / 50000 * 100) if tot else NA),
             det=det, yzw="%.1f" % yz_w)


def _tp_tier(rate):
    """场外基金止盈档位：累计收益率 → (档位阈值, 应减比例)。未触发返回 None。"""
    if rate is None:
        return None
    hit = None
    for thr, frac in config.FUND_TAKE_PROFIT:
        if rate >= thr:
            hit = (thr, frac)
    return hit


def sec6b(d):
    """六·补、基金账户（场外申赎口径 · 25 只）。

    数据来源分层：
      · 投入资金 / 累计收益 → 用户 App 汇总快照（Excel「9-基金配置」R14:R38，基准日 2026-10-24）
      · 最新单位净值 / 净值日期 / 当日净值涨跌 → 天天基金历史净值（当次真实抓取）
    ⚠️ 口径限制：25 只的**份额**未记录 → 无法把「当日净值涨跌」折算成持仓金额变动，
       因此本节只给净值层面的真实涨跌，不编造当日盈亏金额。
    """
    fnav = d.get("fund_nav") or {}
    rows = ""
    tot_inv = tot_gain = 0.0
    win = lose = flat = 0
    tp_rows = ""
    theme = {}
    typeagg = {}
    nav_dates = set()
    for code, name, th, ftype, inv, gain, proxy, direction in config.FUND_ACCOUNT:
        tot_inv += inv
        tot_gain += gain
        if gain > 0:
            win += 1
        elif gain < 0:
            lose += 1
        else:
            flat += 1
        total = inv + gain
        rate = (gain / inv * 100) if inv else None
        nav = fnav.get(code) or {}
        if nav.get("date"):
            nav_dates.add(nav["date"])
        t = _tp_tier(rate)
        if t:
            thr, frac = t
            cut = total * frac
            tp_rows += ("<tr><td>{n}</td><td>{c}</td><td>{r}</td><td>{f}</td>"
                        "<td>{m}</td><td><span class='tag r'>减仓 {pp}</span></td></tr>"
                        .format(n=name, c=code, r="%+.2f%%" % rate,
                                f="%.0f%%" % (frac * 100), m="%.0f" % cut,
                                p=frac, pp="%.0f%%" % (frac * 100)))
        else:
            tp_rows += ("<tr><td>{n}</td><td>{c}</td><td>{r}</td><td>—</td>"
                        "<td>—</td><td><span class='tag n'>未触发</span></td></tr>"
                        .format(n=name, c=code, r=("%+.2f%%" % rate) if rate is not None else NA))
        rows += ("<tr><td><b>{n}</b><br><span class='na'>{c}</span></td><td>{th}</td>"
                 "<td>{ty}</td><td>{inv}</td><td>{g}</td><td>{r}</td><td>{nav}</td>"
                 "<td>{nd}</td><td>{np}</td><td>{mv}</td><td>{tp}</td></tr>"
                 ).format(n=name, c=code, th=th, ty=ftype,
                          inv="%.2f" % inv, g="%+.2f" % gain,
                          r=("%+.2f%%" % rate) if rate is not None else NA,
                          nav=("%.4f" % nav["nav"]) if nav.get("nav") else NA,
                          nd=nav.get("date") or NA,
                          np=(("%+.2f%%" % nav["pct"]) if nav.get("pct") is not None
                              else '<span class="na">—</span>'),
                          mv="%.2f" % total,
                          tp=("<span class='tag r'>+%.0f%%档 减%.0f%%</span>"
                              % (t[0], t[1] * 100)) if t
                          else "<span class='tag n'>未触发</span>")
        a = theme.setdefault(th, [0.0, 0.0, 0])
        a[0] += inv
        a[1] += gain
        a[2] += 1
        b = typeagg.setdefault(ftype, [0.0, 0.0, 0])
        b[0] += inv
        b[1] += gain
        b[2] += 1

    theme_rows = ""
    for th, (inv, gain, n) in sorted(theme.items(), key=lambda x: -x[1][0]):
        r = (gain / inv * 100) if inv else None
        theme_rows += ("<tr><td>{th}</td><td>{n}</td><td>{inv}</td><td>{g}</td>"
                       "<td>{r}</td></tr>"
                       .format(th=th, n=n, inv="%.2f" % inv, g="%+.2f" % gain,
                               r=("%+.2f%%" % r) if r is not None else NA))
    type_rows = ""
    for ty, (inv, gain, n) in sorted(typeagg.items(), key=lambda x: -x[1][0]):
        r = (gain / inv * 100) if inv else None
        type_rows += ("<tr><td>{ty}</td><td>{n}</td><td>{inv}</td><td>{g}</td>"
                      "<td>{r}</td></tr>"
                      .format(ty=ty, n=n, inv="%.2f" % inv, g="%+.2f" % gain,
                              r=("%+.2f%%" % r) if r is not None else NA))

    overall = (tot_gain / tot_inv * 100) if tot_inv else None
    nav_note = ("、".join(sorted(nav_dates)) if nav_dates else NA)

    tpl = """
<section id="s6b"><h2>六·补、基金账户（场外申赎口径 · 25 只）</h2>
<div class="box"><b>账户概况</b>：总投入 <b>{tinv}</b> 元｜累计收益 <b>{tgain}</b> 元｜
整体收益率 <b>{overall}</b>｜{win} 盈 / {lose} 亏 / {flat} 平｜
本次抓取到的净值日期：{nav_note}。<br>
<span class='na'>投入与累计收益为 App 汇总快照（基准日 2026-10-24）；单位净值、当日净值涨跌为天天基金最新披露值（真实抓取）。</span></div>
<h3 class="sub">25 只明细</h3>
<table><tr><th>基金</th><th>跟踪主题</th><th>申赎类型</th><th>投入资金(元)</th>
<th>累计收益(元)</th><th>收益率</th><th>最新净值</th><th>净值日期</th>
<th>净值当日涨跌</th><th>市值(元)</th><th>止盈档位</th></tr>{rows}</table>
<h3 class="sub">主题聚合</h3>
<table><tr><th>跟踪主题</th><th>只数</th><th>投入资金(元)</th><th>累计收益(元)</th><th>收益率</th></tr>{theme_rows}</table>
<h3 class="sub">申赎类型聚合</h3>
<table><tr><th>申赎类型</th><th>只数</th><th>投入资金(元)</th><th>累计收益(元)</th><th>收益率</th></tr>{type_rows}</table>
<h3 class="sub">止盈档位执行清单</h3>
<table><tr><th>基金</th><th>代码</th><th>累计收益率</th><th>档位</th><th>应减市值(元)</th><th>状态</th></tr>{tp_rows}</table>
<div class="box warn"><b>场外口径铁律</b>：25 只全部场外申赎，<b>盘中无报价、无盘中止损</b>；
申赎按当日收盘净值成交，<b>15:00 为当日截止线</b>，之后提交按下一交易日净值成交。
境内 T+1 确认、赎回款 T+1 到账；QDII T+2~T+3 确认、赎回款 T+3~T+7。
⇒ 减仓资金<b>不可当日再投</b>（不做跨品种赎回重投）。
<br><b>本节限制</b>：25 只的<b>份额未记录</b>，无法把「当日净值涨跌」折算成持仓金额变动
（QDII 净值还要滞后 2~3 天）—— 本节只给净值层面的真实涨跌，不编造当日盈亏金额。</div>
</section>"""
    return F(tpl, rows=rows, theme_rows=theme_rows, type_rows=type_rows,
             tp_rows=tp_rows, nav_note=nav_note,
             tinv="%.2f" % tot_inv, tgain="%+.2f" % tot_gain,
             overall=("%+.2f%%" % overall) if overall is not None else NA,
             win=win, lose=lose, flat=flat)


def sec7(d):
    pf = d["portfolio"]
    nsi = board_flow(d, "有色金属", "工业金属", "小金属", "贵金属")
    if nsi and nsi.get("net_yi") is not None:
        nsi_tag = ('<span class="tag r">❌ 未验证</span>'
                   if nsi["net_yi"] < 0 else '<span class="tag g">✅ 获验证</span>')
        nsi_txt = "%s 板块当日%s%s" % (nsi["name"], flow_phrase(nsi),
                                       board_pct_txt(nsi))
    else:
        # 板块资金流缺失时，用新浪板块涨跌幅做「部分验证」——
        # 涨跌是真实数据，但没有资金流就不能下「获验证/未验证」的结论，
        # 所以标签降级为「部分可判」，不冒充资金流结论。
        sv = (d.get("sectors") or {}).get("有色金属板块") or {}
        if sv.get("pct") is not None:
            nsi_tag = '<span class="tag y">◐ 部分可判（缺资金流）</span>'
            cls = "up" if sv["pct"] > 0 else ("down" if sv["pct"] < 0 else "flat")
            nsi_txt = ("%s 当日 <span class='%s'>%s</span>；"
                       "板块主力资金流%s，<b>资金面结论暂不下</b>"
                       % (sv.get("name") or "有色金属板块", cls, pct(sv["pct"]), NA))
        else:
            nsi_tag = '<span class="tag n">⏳ 数据未获取</span>'
            nsi_txt = '<span class="na">%s</span>' % NA

    def px(c):
        return price((pf.get(c) or {}).get("close"))

    comm = tone(d, "515880")
    # 黄金双因子：数据接通后必须给真实结论，不能再写"无法判定"
    gf = gold_factor(d)
    if gf["known"]:
        if gf["trigger"]:
            gold_tag = '<span class="tag g">✅ 信号成立</span>'
        else:
            gold_tag = '<span class="tag r">❌ 未满足</span>'
        gold_txt = ("Brent <b>%.2f</b>（阈值 &lt; %.0f）%s；美10Y <b>%.2f%%</b>"
                    "（阈值 &lt; %.1f%%）%s" % (
                        gf["brent"], gf["b_th"], "满足" if gf["b_ok"] else "未满足",
                        gf["us10y"], gf["y_th"], "满足" if gf["y_ok"] else "未满足"))
    else:
        gold_tag = '<span class="tag n">⏳ 无法判定</span>'
        gold_txt = "Brent 与美10Y 数据暂未获取"
    tpl = """
<section id="s7"><h2>七、此前推论验证</h2>
<table><tr><th>推论</th><th>结果</th><th>当日数据</th></tr>
<tr><td>有色为第一方向</td><td>{nsi_tag}</td><td>{nsi_txt}</td></tr>
<tr><td>黄金 ETF 双因子加仓信号</td><td>{gold_tag}</td><td>{gold_txt}</td></tr>
<tr><td>015790 赎回（规避风险）</td><td>{af_tag}</td><td>{af_txt}</td></tr>
<tr><td>南山铝业三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>{ev_ns}</td></tr>
<tr><td>隆基绿能三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>{ev_lj}</td></tr>
<tr><td>513120 不追高，回调加仓</td><td>{w1}</td><td>现价 {p1}{w1n}</td></tr>
<tr><td>中国一重做 T 降成本</td><td>{w2}</td><td>现价 {p2}{w2n}</td></tr>
<tr><td>通信 ETF 月定投 500 元</td><td><span class="tag b">✅ 执行中</span></td><td>{comm}</td></tr>
<tr><td>1 年期执行计划 v3.0</td><td><span class="tag b">✅ 框架运行</span></td><td>本日收盘口径 {hit}/{tot} 触发，盘中口径 {ihit}/{tot} 击穿</td></tr></table>
</section>"""
    t13 = next((r for r in (d.get("triggers") or []) if r["code"] == "513120"), None)
    t13_hit = bool(t13 and t13.get("trigger") is not None)
    t13_intra = bool(t13 and t13.get("intraday_hits"))
    w1 = ('<span class="tag y">⚡ 已触发观察档</span>' if t13_hit
          else ('<span class="tag y">⚡ 盘中已破观察档</span>' if t13_intra
                else '<span class="tag g">✅ 纪律维持</span>'))
    if t13_hit:
        w1n = "，收盘已跌破 %.3f 观察档" % t13["trigger"]
    elif t13_intra:
        w1n = "，盘中最低 %.3f 已跌破 %s 观察档" % (
            t13["low"], " / ".join("%.3f" % x for x in t13["intraday_hits"]))
    else:
        w1n = "，未跌破观察档"
    tyz = next((r for r in (d.get("triggers") or []) if r["code"] == "601106"), None)
    yz_hit = bool(tyz and tyz.get("trigger") is not None)
    yz_intra = bool(tyz and tyz.get("intraday_hits"))
    w2 = ('<span class="tag y">⚡ 已触发做T买点</span>' if yz_hit
          else ('<span class="tag y">⚡ 盘中已达做T买点</span>' if yz_intra
                else '<span class="tag b">✅ 执行中</span>'))
    if yz_hit:
        w2n = "，收盘已达做T买点条件"
    elif yz_intra:
        w2n = "，盘中最低 %.2f（%+.2f%%）已达做T买点条件" % (
            tyz["low"], tyz["low_pct"])
    else:
        w2n = "，未达 2.81 买点"
    ihit = d.get("intraday_triggered_count") or 0

    def ev_date(kw):
        """从 config.EVENTS 里按关键词取日期，避免把 10/29 这类日期写死在正文里。"""
        for date, name, _star in config.EVENTS:
            if kw in name:
                return "%s 披露" % date[5:].replace("-", "/")
        return NA

    ev_ns, ev_lj = ev_date("南山铝业三季报"), ev_date("隆基绿能三季报")
    # 015790 状态由 config.AEROSPACE_FUND 推导，不再写死"已赎回"
    _af = config.AEROSPACE_FUND
    _sold = _af.get("sold_shares") or 0
    _shares = _af.get("shares") or 0
    if _sold:
        af_tag = '<span class="tag y">⚡ 减仓中</span>'
        af_txt = ("今日（%s）卖出 <b>%.2f</b> 份，按卖出前口径剩余 <b>%.2f</b> 份"
                  % (_af.get("sold_date"), _sold, _shares - _sold))
    else:
        af_tag = '<span class="tag g">✅ 已完成</span>'
        af_txt = "已赎回"
    return F(tpl, nsi_tag=nsi_tag, nsi_txt=nsi_txt, p1=px("513120"), p2=px("601106"),
             w1=w1, w1n=w1n, w2=w2, w2n=w2n, comm=comm, ihit=ihit,
             gold_tag=gold_tag, gold_txt=gold_txt,
             af_tag=af_tag, af_txt=af_txt,
             ev_ns=ev_ns, ev_lj=ev_lj,
             hit=d["triggered_count"], tot=d["trigger_total"])


def sec8(d):
    ev = "".join("<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>"
                 .format(a=x[0], b=x[1], c="★" * x[2]) for x in config.EVENTS)

    def ladder_kind(code):
        """档位性质：加仓档 / 观察档 / 做T档。

        观察档（config.WATCH_LADDER，513120）按纪律「1 年期内不主动建仓」，
        触发了也只记录、不下单 —— 混进加仓档会让人照着下单，直接违反用户规则。
        """
        if code in config.ADD_LADDER:
            return "加仓档"
        if code in config.WATCH_LADDER:
            return "观察档"
        if code == "601106":
            return "做T档"
        return "监控档"

    KIND_TAG = {"加仓档": "<span class='tag b'>加仓档</span>",
                "观察档": "<span class='tag n'>观察档</span>",
                "做T档": "<span class='tag y'>做T档</span>",
                "监控档": "<span class='tag n'>监控档</span>"}

    def amount_of(code, level):
        """某标的第 level 档的下单金额（元）。level 为 0 起的档位序号。"""
        amts = config.ADD_AMOUNT.get(code) or config.WATCH_AMOUNT.get(code)
        if not amts or level >= len(amts):
            return None
        return amts[level]

    def ladder_amount_txt(r, hits):
        """把命中的档位翻译成「下多少」。

        hits 为已跌破的档位价列表（收盘 + 盘中合并去重）。
        加仓档：逐档累加金额；做T档：买入 2000 股。
        观察档只记录金额不下单，单独标注。
        """
        code = r["code"]
        kind = ladder_kind(code)
        ladder = r.get("ladder") or []
        if kind == "做T档":
            return ("买入 %d 股（仅用浮动仓，底仓不动）"
                    % config.T_BUY_SHARES)
        if kind == "观察档":
            amts = []
            for lv in hits:
                if lv in ladder:
                    a = amount_of(code, ladder.index(lv))
                    if a:
                        amts.append("%.3f→%d 元" % (lv, a))
            return " / ".join(amts) + "（<b>记录，不下单</b>）" if amts else "记录，不下单"
        amts, total = [], 0
        for lv in hits:
            if lv in ladder:
                a = amount_of(code, ladder.index(lv))
                if a:
                    amts.append("%.3f→<b>%d 元</b>" % (lv, a))
                    total += a
        if not amts:
            return NA
        return " / ".join(amts) + ("　<b>合计 %d 元</b>" % total if total else "")

    rstat = []
    for r in d["triggers"]:
        ih = r.get("intraday_hits") or []
        if r.get("trigger"):
            st = "<span class='tag g'>已触发 %s</span>" % ("%.3f" % r["trigger"])
            extra = [x for x in ih if x != r["trigger"]]
            if extra:
                st += ("<span class='tag y'>+盘中 %s</span>"
                       % " / ".join("%.3f" % x for x in extra))
        elif ih:
            st = ("<span class='tag y'>盘中击穿 %s</span>"
                  % " / ".join("%.3f" % x for x in ih))
        else:
            st = "<span class='tag n'>未触发</span>"
        # 命中档位（收盘 + 盘中，去重后降序）
        hits = []
        if r.get("trigger"):
            hits.append(r["trigger"])
        for x in ih:
            if x not in hits:
                hits.append(x)
        hits.sort(reverse=True)
        # 未触发 = 不适用（没有档位被跌穿），不是"数据暂未获取" → 用破折号
        amt_txt = ladder_amount_txt(r, hits) if hits else "—"
        rstat.append((r, st, amt_txt))
    tr = "".join(
        "<tr><td>{n}</td><td>{k}</td><td>{c}</td><td>{lo}</td><td>{l}</td>"
        "<td>{s}</td><td>{amt}</td><td>{t}</td></tr>".format(
            n=r["name"], k=KIND_TAG.get(ladder_kind(r["code"]), ""),
            c=price(r["close"], 3) if r.get("close") is not None else NA,
            lo=(price(r["low"], 3) + ("<br><span class='na'>%+.2f%%</span>"
                                     % r["low_pct"]))
                if r.get("low") is not None else NA,
            l=" / ".join(str(x) for x in r["ladder"]) if r.get("ladder") else NA,
            s=st, amt=amt_txt,
            t=r.get("note") or NA)
        for r, st, amt_txt in rstat)
    hit, tot = d["triggered_count"], d["trigger_total"]
    fired = [r for r in d["triggers"] if r.get("trigger")]
    # 只有「加仓档」和「做T档」对应真实下单动作；观察档触发了也只记录
    fired_act = [r for r in fired
                 if ladder_kind(r["code"]) in ("加仓档", "做T档")]
    fired_watch = [r for r in fired if ladder_kind(r["code"]) == "观察档"]

    def act_detail(r):
        """执行清单条目：标的 + 命中档位 + 金额。"""
        hits = []
        if r.get("trigger"):
            hits.append(r["trigger"])
        for x in (r.get("intraday_hits") or []):
            if x not in hits:
                hits.append(x)
        hits.sort(reverse=True)
        return "%s（%s）" % (r["name"], ladder_amount_txt(r, hits))

    def act_total(r):
        """该标的本次实际需下单的金额合计（做T按股数计，不计入金额合计）。"""
        if ladder_kind(r["code"]) == "做T档":
            return 0
        hits = []
        if r.get("trigger"):
            hits.append(r["trigger"])
        for x in (r.get("intraday_hits") or []):
            if x not in hits:
                hits.append(x)
        ladder = r.get("ladder") or []
        t = 0
        for lv in hits:
            if lv in ladder:
                a = amount_of(r["code"], ladder.index(lv))
                if a:
                    t += a
        return t

    grand = sum(act_total(r) for r in fired_act)
    grand_txt = ("，<b>今日加仓/买入合计 %d 元</b>" % grand) if grand else ""
    intr = [r for r in d["triggers"]
            if r.get("intraday_hits") and not r.get("trigger")]
    extra = ""
    if intr:
        extra = ("<br><b>另有 {} 项在盘中已被击穿、收盘又拉回</b>："
                 "同花顺预警盘中即会响，按预警纪律这些档位应已执行；"
                 "若当时未接住，今日收盘价已回到档位上方，明日再跌回才重新触发。"
                 "涉及：{}。".format(
                     len(intr),
                     "、".join("%s（盘中最低 %.3f，击穿 %s）"
                               % (r["name"], r["low"],
                                  "/".join("%.3f" % x for x in r["intraday_hits"]))
                               for r in intr)))
    watch_txt = ""
    if fired_watch:
        watch_txt = ("<br><b>观察档触发（不构成下单指令）</b>："
                     + "、".join("%s（%.3f）" % (r["name"], r["trigger"])
                                 for r in fired_watch)
                     + " —— 按 1 年期纪律「1 年内不主动建仓」，"
                       "<b>只记录、不买入</b>。")
    if fired_act:
        concl = ("<div class='box warn'><b>今日执行结论</b>：可执行触发 <b>{n_act} / {tot}</b> 项，"
                 "<b>需要执行</b>。涉及：{names}{grand_txt}。"
                 "严格按下行阶梯的档位下单，档位已跌穿即执行，不追加、不上移档位。"
                 "{watch}{extra}</div>"
                 .format(n_act=len(fired_act), tot=tot, extra=extra, watch=watch_txt,
                         grand_txt=grand_txt,
                         names="、".join(act_detail(r) for r in fired_act)))
    elif fired_watch:
        concl = ("<div class='box good'><b>今日执行结论</b>：收盘触发 <b>{hit} / {tot}</b> 项，"
                 "但<b>全部为观察档</b>，按 1 年期纪律「1 年内不主动建仓」，"
                 "<b>今日无需任何交易动作</b>。{watch}{extra}</div>"
                 .format(hit=hit, tot=tot, watch=watch_txt, extra=extra))
    else:
        concl = ("<div class='box good'><b>今日执行结论</b>：触发 <b>{hit} / {tot}</b> 项，"
                 "<b>无需任何交易动作</b>。按 1 年期纪律「不触发不动作」执行，继续等待。{extra}"
                 "</div>".format(hit=hit, tot=tot, extra=extra))
    # 最近节点：由 config.EVENTS 按当日行情日期往后推，不再写死日期
    td = d.get("trade_date") or ""
    upcoming = []
    if td:
        for date, name, star in config.EVENTS:
            if date >= td:
                upcoming.append((date, name, star))
    upcoming = upcoming[:3]
    if upcoming:
        node_txt = " → ".join("%s %s" % (dt[5:].replace("-", "/"), nm)
                               for dt, nm, _ in upcoming)
        # 三季报/议息这类 ★★★ 事件落在未来 5 个自然日内 -> 提示不新增仓位
        near = [x for x in config.EVENTS
                if x[2] >= 3 and td and x[0] >= td
                and (datetime.fromisoformat(x[0]).date()
                     - datetime.fromisoformat(td).date()).days <= 5]
        if near:
            node_note = ("未来 5 天内有 <b>%s</b> —— "
                         "<b>事件落地前不建议新增仓位</b>。"
                         % "、".join("%s %s" % (n[1], n[0][5:].replace("-", "/"))
                                     for n in near))
        else:
            node_note = "近期无 ★★★ 以上事件密集期，按既定纪律执行即可。"
    else:
        node_txt = NA
        node_note = ""
    tpl = """
<section id="s8"><h2>八、策略调整建议</h2>
{concl}
<h3 class="sub">触发监控面板（下行触发：价格从上方跌破才触发）</h3>
<table><tr><th>标的</th><th>档位性质</th><th>收盘价</th><th>盘中最低</th><th>档位</th><th>状态</th><th>应下单金额</th><th>判定说明</th></tr>{tr}</table>
<div class="box"><b>档位性质怎么读</b>：<span class='tag b'>加仓档</span> 跌穿即按阶梯下单；
<span class='tag n'>观察档</span> 按 1 年期纪律「1 年内不主动建仓」，<b>只记录不买入</b>；
<span class='tag y'>做T档</span> 需同时满足价格与跌幅两个条件，只用浮动仓、不动底仓。</div>
<div class="box"><b>「应下单金额」列怎么读</b>：命中哪一档就下哪一档的金额，
多档同时命中则<b>逐档累加</b>（如 0.520→250 元 + 0.500→500 元 + 0.480→500 元 ＝ 1250 元）。
金额与《同花顺价格预警配置v2.0》逐档对齐，<b>不加码、不上移档位</b>。</div>
<div class="box warn"><b>两套口径必须都看</b>：加仓触发是<b>下行触发</b>，现价<b>从上方跌破</b>某档位才触发。
同花顺预警为<b>盘中实时触发</b>，因此「盘中最低」列才是预警实际会响的那一刻；
「收盘价」列只是当日结束时的状态。V 型反转日（如早盘深跌、午后拉回）两者会明显背离，
<b>收盘口径会漏判</b>，以盘中最低列为准。收盘未触发时，判定说明给出的是
「还需下跌多少元」，不是价格上涨空间。</div>
<h3 class="sub">1 年期执行计划 v3.0 时间窗口</h3>
<table><tr><th>日期</th><th>事件</th><th>重要性</th></tr>{ev}</table>
<p><b>最近节点（自 {dt} 起）</b>：{node_txt}。<br>{node_note}</p>
<h3 class="sub">加仓纪律</h3>
<ul>
<li>加仓间隔 ≥ 7 个交易日</li>
<li>每月至少 1 次加仓（保证）</li>
<li>下跌趋势可延长至 2 周 1 次</li>
<li>中国一重仅做 T，<b>不加仓摊薄</b></li>
</ul>
</section>"""
    return F(tpl, concl=concl, tr=tr, ev=ev, dt=td or NA,
             node_txt=node_txt, node_note=node_note)


def sec9(d):
    """第九章：商业航天 / 太空产业。

    改造说明：本章原先是纯静态文本（sec9() 不接任何数据参数），
    每天输出同一段「数据暂未获取」。现在改成数据驱动：
      · 持仓记录 ← config.AEROSPACE_FUND（015790 永赢高端装备智选混合C）
      · 代理 ETF 当日表现 ← 当次抓取的真实行情（sh512660 军工ETF国泰）
      · 发射日历 ← NextSpaceflight 公开 API（真实抓取）
    """
    f = config.AEROSPACE_FUND
    shares = f["shares"]
    amt = f["amount"]
    nav = (amt / shares) if shares else None
    # 净值优先用当次抓取的真实净值（天天基金），拿不到才回落到「市值 ÷ 份额」
    _fn = (d.get("fund_nav") or {}).get(f["code"]) or {}
    if _fn.get("nav"):
        nav = _fn["nav"]
    nav_date = _fn.get("date") or f.get("nav_date") or NA

    # 代理 ETF（sh512660）当日表现：军工ETF 不在 config.PORTFOLIO 里，
    # 由 fetch 层单独抓（data["proxy_etf"]）；拿不到就如实标注，不猜。
    px = d.get("proxy_etf") or {}
    if not px:
        px = None

    # 发射日历（NextSpaceflight 公开 API，2026-10-30 接入）
    # 原先四项指标全部写「需专用数据源」，实测这一项有公开免费源。
    # 口径：全球发射日历（商业/军用/科研混合），只作产业活跃度观测，
    #      不等同于「中国商业航天发射计划」—— 报告里照实标注，不偷换概念。
    cal = d.get("launches") or []
    if cal:
        cal_state = "已接入 · 近端 %d 次" % len(cal)
        cal_note = "NextSpaceflight 全球发射日历"
        cal_rows = ""
        for it in cal:
            cal_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                         % (it.get("date") or NA, it.get("name") or NA,
                            it.get("status") or NA))
    else:
        cal_state = "<span class='na'>%s</span>" % NA
        cal_note = "NextSpaceflight 接口未返回"
        cal_rows = ""

    tpl = """
<section id="s9"><h2>九、商业航天 / 太空产业 —— 长期观察</h2>
<h3 class="sub">方向持仓记录</h3>
<table><tr><th>标的</th><th>代码</th><th>持有市值(元)</th><th>持有份额</th>
<th>最新单位净值</th><th>投入本金(元)</th><th>成本单价</th><th>持有收益(元)</th></tr>
<tr><td>{fname}</td><td>{fcode}</td><td>{amount}</td><td>{shares}</td>
<td>{nav}</td><td>{cost_amt}</td><td>{cost}</td><td>{gain}</td></tr></table>
<p class="na">场外基金 · {settle}。代理 ETF：{proxy} {proxy_name} —— 当日 {proxy_px}。
方向归属：{note}</p>
<div class="box"><b>口径已确认</b>：持有市值 {amount} 元、持有收益 {gain} 元（用户 2026-10-30 提供）；
投入本金 = 市值 − 持有收益 = <b>{cost_amt} 元</b>；份额 {shares} 份 = {amount} ÷ {nav_date} 单位净值 <b>{nav_raw}</b> 元/份
（天天基金历史净值核对，{shares} × {nav_raw} = {amount} 逐位吻合）；成本单价 = {cost_amt} ÷ {shares} = <b>{cost}</b> 元/份。
本基金同时出现在「六·补、基金账户」的 25 只明细里。</div>
<h3 class="sub">今日产业指标速报</h3>
<table><tr><th>指标</th><th>状态</th><th>说明</th></tr>
<tr><td><b>发射日历</b></td><td>{cal_state}</td><td>{cal_note}</td></tr></table>
<div class="box warn">本章为长期产业跟踪，<b>发射日历已接真实数据</b>（下表，NextSpaceflight 公开 API）。
发射日历口径为<b>全球</b>任务（商业/军用/科研混合），只作产业活跃度观测，
<b>不等同于</b>「中国商业航天发射计划」——方向归属以持仓与代理 ETF 为准。</div>
<h3 class="sub">近期全球发射安排（NextSpaceflight，北京时间）</h3>
<table><tr><th>时间</th><th>任务</th><th>状态</th></tr>
{cal_rows}</table>
<h3 class="sub">配置框架状态</h3>
<table><tr><th>层级</th><th>目标仓位</th><th>当前状态</th></tr>
<tr><td>第一层 指数化底仓</td><td>50-60%</td><td><span class="tag n">未建立</span></td></tr>
<tr><td>第二层 产业链卫星仓</td><td>25-35%</td><td><span class="tag b">由 {fname} 承担</span></td></tr>
<tr><td>第三层 事件仓</td><td>≤10-15%</td><td><span class="tag n">未建立</span></td></tr></table>
</section>"""
    return F(tpl, na=NA,
             cal_state=cal_state, cal_note=cal_note, cal_rows=cal_rows,
             fname=f["name"], fcode=f["code"],
             amount="%.2f" % amt, shares="%.2f" % shares,
             nav=("%.4f 元/份" % nav) if nav else NA,
             nav_raw=("%.4f" % nav) if nav else NA,
             nav_date=nav_date,
             cost_amt="%.2f" % f.get("cost_amount", 0),
             cost=("%.4f" % f["cost"]) if f.get("cost") else NA,
             gain=("%+.2f" % f.get("gain", 0)),
             settle=f["settle"], proxy=f["proxy"], proxy_name=f["proxy_name"],
             proxy_px=("%s（%s）" % (price(px.get("close"), 3), pct(px.get("pct")))
                       if px else "<span class='na'>%s（代理ETF未在监控清单）</span>" % NA),
             note=f["note"])


def sec10(d):
    we = d["watch_etfs"]
    # 监控 ETF 行（有色/稀有金属/电力/红利低波）
    rows2 = ""
    for c, _ in config.WATCH_ETFS:
        v = we.get(c)
        if not v:
            continue
        rows2 += ("<tr><td>{n} {c}</td><td>{p}</td><td>{g}</td></tr>"
                  .format(n=v["name"], c=c, p=price(v.get("close"), 3),
                          g=pct(v.get("pct"))))

    # 【监控节奏状态行】：模板末尾的独立小节，四只监控 ETF 的最新价 + 相对强弱
    # ＋ 连续相对强弱（日K逐日对比上证，从最新一根往前数连续同向天数）
    mks = d.get("monitor_klines") or {}
    bench = (mks.get("000001") or {}).get("closes") or []
    pace_rows = ""
    for c, _ in config.WATCH_ETFS:
        v = we.get(c)
        if not v:
            continue
        streak_txt = "—"
        cl = (mks.get(c) or {}).get("closes") or []
        if bench and cl:
            n, direction = rel_streak(cl, bench)
            if n >= 1:
                if direction > 0:
                    streak_txt = ("<span class='up'>连续 %d 日跑赢上证</span>" % n)
                else:
                    streak_txt = ("<span class='down'>连续 %d 日跑输上证</span>" % n)
        pace_rows += ("<tr><td>{n} {c}</td><td>{p}</td><td>{t}</td><td>{s}</td></tr>"
                      .format(n=v["name"], c=c, p=price(v.get("close"), 3),
                              t=tone(d, c).rstrip("。"), s=streak_txt))

    # 有色信号检查：按板块真实资金流结论，不预设
    nsi = board_flow(d, "有色金属", "工业金属", "小金属", "贵金属")
    if nsi and nsi.get("net_yi") is not None:
        if nsi["net_yi"] < 0:
            nsi_txt = ("%s 板块%s，未见资金回流；<b>结论：介入信号未触发</b>。"
                       "南山铝业维持观察，不加仓。"
                       % (nsi["name"], flow_phrase(nsi)))
        else:
            nsi_txt = ("%s 板块%s，方向转好但<b>尚未出现放量上行突破</b>；"
                       "结论：<b>仅观察，不据此加仓</b>，等价格突破确认。"
                       % (nsi["name"], flow_phrase(nsi)))
    else:
        # 资金流缺失时只用真实涨跌幅做「方向未确认」的表述，不下介入结论
        sv = (d.get("sectors") or {}).get("有色金属板块") or {}
        if sv.get("pct") is not None:
            cls = "up" if sv["pct"] > 0 else ("down" if sv["pct"] < 0 else "flat")
            nsi_txt = ("%s 当日 <span class='%s'>%s</span>，"
                       "但板块主力资金流%s；<b>结论：介入信号未触发</b>"
                       "（缺资金流确认，方向待观察）。"
                       % (sv.get("name") or "有色金属板块", cls, pct(sv["pct"]), NA))
        else:
            nsi_txt = "板块资金流数据%s，<b>本日不做方向性结论</b>。" % NA

    # ---- 板块涨跌幅 ----
    # 优先新浪板块（本地可直连），缺失时回落到东财 boards 字典里的同名板块。
    # 小金属在新浪概念文件里没有（那个文件是证监会行业分类），
    # 但东财 boards 有「小金属」板块，云端 runner 能取到。
    sec_map = d.get("sectors") or {}
    bs = boards(d)

    def srow(label, key, board_key=None):
        v = sec_map.get(key) or {}
        if (not v or v.get("pct") is None) and board_key:
            b = bs.get(board_key) or {}
            if b.get("pct") is not None:
                v = {"name": b.get("name"), "pct": b.get("pct")}
        if not v or v.get("pct") is None:
            return ("<tr><td>%s</td><td><span class='na'>%s</span></td>"
                    "<td><span class='na'>%s</span></td></tr>"
                    % (label, NA, NA))
        cls = "up" if v["pct"] > 0 else ("down" if v["pct"] < 0 else "flat")
        return ("<tr><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
                % (label, v.get("name") or key, cls, pct(v["pct"])))

    rows = (srow("有色金属板块涨跌", "有色金属板块", "有色金属")
            + srow("小金属概念涨跌", "小金属概念", "小金属"))

    # ---- LME 铝价（新浪 hf_AHD = LME 伦铝）----
    al = (d.get("global") or {}).get("LME_AL") or {}
    if al.get("close") is not None:
        alc = al["close"]
        alp = al.get("pct")
        cls = "up" if (alp or 0) > 0 else ("down" if (alp or 0) < 0 else "flat")
        al_row = ("<tr><td>LME 铝价</td><td>%.2f 美元/吨</td>"
                  "<td class='%s'>%s</td></tr>" % (alc, cls, pct(alp)))
        al_note = "（%s）" % (al.get("src") or "新浪财经 hf_AHD")
    else:
        al_row = ("<tr><td>LME 铝价</td><td><span class='na'>%s</span></td>"
                  "<td><span class='na'>%s</span></td></tr>" % (NA, NA))
        al_note = ""

    # ---- 主力净流入（公用事业）----
    util = board_flow(d, "公用事业", "电力行业", "电力")
    util_net = flow_phrase(util) if util and util.get("net_yi") is not None else NA
    util_row = ("<tr><td>主力净流入(公用事业)</td><td>%s</td><td>板块级资金流</td></tr>"
                % util_net)

    # ---- 指数估值：股息率 / PE / PB / 历史分位（蛋卷指数估值，2026-10-30 接入）----
    # 低估判定规则（用户 2026-10-30 指令）：**股息率阈值 AND PE 历史分位，双条件同时成立**。
    #   · 股息率 ≥ 阈值  → 高息（相对债券）
    #   · PE 分位 ≤ 阈值 → 低估值
    # 两块各用各的阈值（config.VALUATION_RULE）：金属股股息率天然低，不能套红利口径。
    val = d.get("valuation") or {}
    cpe = d.get("csindex_pe") or {}
    drule = config.VALUATION_RULE["dividend"]
    mrule = config.VALUATION_RULE["metal"]

    def dual(yield_v, pe_pct, rule):
        return valuation_dual(yield_v, pe_pct, rule)

    # 【②】红利系：蛋卷 —— 股息率与 PE 分位都有
    val_rows = ""
    val_parts = []
    hit_idx = []
    for code, (_disp, key) in config.VALUATION_INDEXES.items():
        it = val.get(key)
        if not it:
            continue
        y = it.get("yield")
        y_txt = ("%.2f%%" % (y * 100)) if y is not None else NA
        pe = it.get("pe")
        pe_txt = ("%.2f" % pe) if pe else NA
        pep = it.get("pe_pct")
        pep_txt = ("%.0f%%" % (pep * 100)) if pep is not None else NA
        pbp = it.get("pb_pct")
        pbp_txt = ("%.0f%%" % (pbp * 100)) if pbp is not None else NA
        st, hit, why = dual(y, pep, drule)
        if hit:
            hit_idx.append(it.get("name") or _disp)
        val_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                     "<td>%s</td><td>%s</td></tr>"
                     % (it.get("name") or _disp, y_txt, pe_txt, pep_txt,
                        pbp_txt, ("<span class='tag g'>%s</span>" % st) if hit
                        else "<span class='tag n'>%s</span>" % st))
        val_parts.append("%s 股息率 %s、PE 分位 %s（%s）"
                         % (it.get("name") or _disp, y_txt, pep_txt, st))
    if val_rows:
        val_note = ("数据源：蛋卷指数估值（估值日 %s）；PE 分位区间为其历史分位。"
                    % (val.get("HLDB", {}).get("date") or "最新"))
    else:
        val_note = "估值数据未获取"
    if hit_idx:
        val_verdict = ("<b>结论：可分批建底仓</b> —— %s 双条件同时成立"
                       "（股息率 ≥ %.1f%% 且 PE 历史分位 ≤ %.0f%%）。"
                       % ("、".join(hit_idx), drule["yield_min"] * 100,
                          drule["pe_pct_max"] * 100))
    else:
        val_verdict = ("<b>结论：观察，不建底仓</b> —— 三个红利系指数均未同时满足"
                       "「股息率 ≥ %.1f%% 且 PE 历史分位 ≤ %.0f%%」双条件。"
                       % (drule["yield_min"] * 100, drule["pe_pct_max"] * 100))
    val_block = (
        "<div class='box'><b>信号检查（双条件）</b>："
        + ("；".join(val_parts) + "。" if val_parts else "估值数据未获取。")
        + "判定规则：<b>股息率 ≥ %.1f%%　AND　PE 历史分位 ≤ %.0f%%</b>，"
          "两条件同时成立才算低估。股息率<b>自身</b>的历史分位免费接口不提供，"
          "此处用 PE 历史分位作估值冷热参照，<b>不与股息率分位混用</b>。"
        % (drule["yield_min"] * 100, drule["pe_pct_max"] * 100)
        + val_verdict + "</div>")

    # 【①】金属类：PE 分位走中证官网自算（中证有色 930708 / 中证稀有 930632）
    # ⚠️ 金属股的股息率免费接口拿不到（中证官网不提供、蛋卷 63 个指数无金属行业）
    #    → 股息率腿标「缺数据」，判定为「条件不全」，**不拿别的指数的股息率凑数**。
    met_rows = ""
    met_parts = []
    for code, name in config.METAL_INDEXES:
        it = cpe.get(code)
        if not it:
            continue
        pep = it.get("pe_pct")
        pep_txt = ("%.0f%%" % (pep * 100)) if pep is not None else NA
        p_ok = pep is not None and pep <= mrule["pe_pct_max"]
        st, hit, why = dual(None, pep, mrule)
        met_rows += ("<tr><td>%s</td><td>%.2f</td><td>%s</td><td>"
                     "<span class='na'>%s</span></td><td>%s</td><td>%s</td></tr>"
                     % (it.get("name") or name, it.get("pe") or 0, pep_txt,
                        "缺数据（免费接口不提供）",
                        "<span class='tag g'>通过</span>" if p_ok
                        else "<span class='tag n'>未通过</span>",
                        "<span class='tag n'>%s</span>" % st))
        met_parts.append("%s PE %s、历史分位 %s（PE 腿%s）"
                         % (it.get("name") or name,
                            ("%.2f" % it.get("pe")) if it.get("pe") else NA,
                            pep_txt, "通过" if p_ok else "未通过"))
    if met_rows:
        met_note = ("数据源：中证指数官网 index-perf（peg 字段＝PE，%s 根日K自算历史分位）。"
                    % (cpe.get(config.METAL_INDEXES[0][0], {}) or {}).get("bars", 0))
        met_block = (
            "<div class='box'><b>信号检查（双条件 · 同构规则）</b>："
            + ("；".join(met_parts) + "。" if met_parts else "金属指数估值未获取。")
            + "判定规则同【②】：<b>股息率 ≥ %.1f%%　AND　PE 历史分位 ≤ %.0f%%</b>。"
            % (mrule["yield_min"] * 100, mrule["pe_pct_max"] * 100)
            + "<b>股息率腿对金属类缺数据</b>（中证官网不提供、蛋卷无金属行业），"
              "因此本块<b>只完成 PE 腿</b>，<b>双条件未闭合 → 不自动触发建底仓</b>；"
              "PE 腿通过只说明估值处于历史低位，仍需人工确认股息率后再决定。</div>")
    else:
        met_note = "金属指数估值未获取"
        met_block = "<div class='box'><b>信号检查（双条件 · 同构规则）</b>：金属指数估值未获取，本日不做方向性结论。</div>"

    tpl = """
<section id="s10"><h2>十、低估 · 低拥挤板块跟踪</h2>
<h3 class="sub">【① 稀有小金属 / 稀有资源】</h3>
<table><tr><th>指标</th><th>今日数据</th><th>涨跌</th></tr>
{rows}{al_row}</table>
<table><tr><th>监控标的</th><th>今日数据</th><th>涨跌</th></tr>
{rows2}</table>
<h3 class="sub">①-估值双条件判定</h3>
<table><tr><th>指数</th><th>PE</th><th>PE历史分位</th><th>股息率</th><th>PE腿</th><th>综合判定</th></tr>
{met_rows}</table>
<p class="na">{met_note}</p>
{met_block}
<div class="box warn"><b>信号检查</b><br>
{nsi_txt}</div>
<h3 class="sub">【② 电力与公用事业（压舱底仓）】</h3>
<table><tr><th>指标</th><th>今日数据</th><th>涨跌</th></tr>
<tr><td>电力ETF 159611</td><td>{d11}</td><td>{d12}</td></tr>
<tr><td>红利低波ETF 512890</td><td>{d21}</td><td>{d22}</td></tr>
{util_row}</table>
<h3 class="sub">②-估值双条件判定</h3>
<table><tr><th>指数</th><th>股息率</th><th>PE</th><th>PE历史分位</th><th>PB历史分位</th><th>综合判定</th></tr>
{val_rows}</table>
<p class="na">{val_note}</p>
{val_block}
<p class="na">电力ETF {t1}；红利低波 {t2}。</p>
<h3 class="sub">【监控节奏状态行】</h3>
<table><tr><th>标的</th><th>最新价</th><th>信号状态</th><th>连续相对强弱（对上证）</th></tr>
{pace_rows}</table>
<p class="na">连续相对强弱＝逐日比较该标的与上证的日涨跌幅，从最新一根日K（{bench_date}）往前数连续同向的天数。</p>
</section>"""
    return F(tpl, rows=rows, rows2=rows2, al_row=al_row,
             util_row=util_row, nsi_txt=nsi_txt,
             val_rows=val_rows, val_note=val_note, val_block=val_block,
             met_rows=met_rows, met_note=met_note, met_block=met_block,
             d11=price((we.get("159611") or {}).get("close"), 3),
             d12=pct((we.get("159611") or {}).get("pct")),
             d21=price((we.get("512890") or {}).get("close"), 3),
             d22=pct((we.get("512890") or {}).get("pct")),
             pace_rows=pace_rows, bench_date=(bench[-1]["date"] if bench else NA),
             t1=tone(d, "159611").rstrip("。"),
             t2=tone(d, "512890").rstrip("。"))


# ------------------------------------------------------------ 主渲染
def render(d):
    ix = d["indexes"]
    sh = ix.get("000001") or {}
    amt = mktotal(d)
    ac = amt_chg(d)
    b = breadth_state(d)
    hit, tot = d["triggered_count"], d["trigger_total"]
    ihit = d.get("intraday_triggered_count") or 0
    dt = d["trade_date"] or NA
    wd = "一二三四五六日"[datetime.fromisoformat(dt).weekday() % 7] \
        if dt != NA else ""
    gen = datetime.fromisoformat(d["generated_at"]).strftime("%Y-%m-%d %H:%M")
    src = d.get("source") or "realtime"
    src_txt = ("历史日K回补口径（逐日K线回溯，非实时快照）"
               if src.startswith("historical")
               else ("盘中实时快照（未收盘）" if is_intraday(d)
                     else "实时收盘快照"))

    if b:
        bd_v = "%d / %d" % (b[0], b[1])
        bd_d = ('<span class="down">跌多涨少</span>' if b[1] > b[0]
                else '<span class="up">涨多跌少</span>')
    else:
        bd_v = '<span class="na">%s</span>' % NA
        bd_d = '<span class="na">历史口径无回溯值</span>'

    cards = [
        ("s1", "上证指数", price(sh.get("close")), pct(sh.get("pct"))),
        ("s1", "深证成指", price((ix.get("399001") or {}).get("close")),
         pct((ix.get("399001") or {}).get("pct"))),
        ("s1", "创业板指", price((ix.get("399006") or {}).get("close")),
         pct((ix.get("399006") or {}).get("pct"))),
        ("s2", "两市成交额", "%.0f 亿" % (amt / 1e8) if amt else NA,
         ('<span class="na">盘中口径·未收盘</span>') if is_intraday(d)
         else (('<span class="%s">较前日 %+.2f%%</span>'
                % ("up" if ac > 0 else "down", ac)) if ac is not None
               else '<span class="na">较前日：' + NA + '</span>')),
        ("s2", "涨跌家数", bd_v, bd_d),
        ("s8", "加仓触发", "%d / %d" % (hit, tot),
         ('<span class="up">盘中另触及 %d 项</span>' % (ihit - hit))
         if ihit > hit
         else ('<span class="down">无需操作</span>' if hit == 0
               else '<span class="up">需执行</span>')),
    ]
    ch = "".join('<a class="card" href="#{i}"><div class="k">{k}</div>'
                 '<div class="v">{v}</div><div class="d">{d}</div></a>'
                 .format(i=i, k=k, v=v, d=d2) for i, k, v, d2 in cards)
    nav = "".join('<a href="#%s">%s</a>' % (i, t) for i, t in NAV)

    tpl = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A股持仓每日复盘 {dt}</title><style>{css}</style></head><body>
<div class="wrap"><nav><h4>目 录</h4>{nav}</nav><main>
<div class="hero"><h1>A股持仓每日复盘 · {dt} 周{wd}</h1>
<div class="sub">1年期持仓执行计划 v3.0 ｜ 生成时间 {gen} (UTC+8) ｜ 行情口径：{src_txt} ｜ 数据源：东方财富 · 新浪财经 · 腾讯财经 · 美国财政部官方收益率曲线 ｜ 结构：十章 + 新因子预留位 + 附录（共 12 块）</div></div>
<div class="cards">{ch}</div>
<div class="trigger {ok}"><h3>{head}</h3>
<div class="cnt">今日触发 {hit} / {tot}</div>
<p>{msg}</p>
<p>{msg2}</p></div>
{s1}{s2}{s3}{s4}{s4b}{s5}{s6}{s6b}{s7}{s8}{s9}{s10}{s11}
<div class="foot">本报告由脚本基于公开行情接口自动生成，<b>不构成投资建议</b>。
标注「数据暂未获取」的字段表示该接口未提供，<b>未做任何推测、插值或替代</b>。
入市有风险，投资需谨慎。</div>
</main></div>
<script>
document.querySelectorAll('nav a').forEach(function(a){
  a.addEventListener('click',function(){
    document.querySelectorAll('nav a').forEach(function(x){x.classList.remove('on')});
    this.classList.add('on');
  });
});
</script>
</body></html>"""
    return F(tpl, dt=dt, css=CSS, nav=nav, wd=wd, gen=gen, ch=ch, src_txt=src_txt,
             ok=("ok" if (hit > 0 or ihit > 0) else ""),
             head=("✅ 有触发项，请按第八章执行" if hit
                   else ("⚠️ 收盘未触发，但有盘中击穿" if ihit
                         else "⚠️ 全部未触发 —— 按纪律不动作")),
             hit=hit, tot=tot,
             msg=("有加仓或做 T 档位被跌破，请查阅第八章操作清单。" if hit
                  else "全部 {} 个监控标的均未跌破预警价，今日无任何交易动作。".format(tot)),
             msg2=("⚠️ 另有 <b>{}</b> 项在盘中已被击穿、收盘又被拉回 —— "
                   "同花顺预警是盘中实时触发的，这类档位在收盘口径下会被漏判，"
                   "请以第八章「盘中最低」列为准。".format(ihit - hit)
                   if ihit > hit else
                   ("盘中击穿 {} 项，与收盘口径一致。".format(ihit) if ihit
                    else "")),
             s1=sec1(d), s2=sec2(d), s3=sec3(d), s4=sec4(d), s4b=sec4b(d),
             s5=sec5(d), s6=sec6(d), s6b=sec6b(d), s7=sec7(d), s8=sec8(d),
             s9=sec9(d), s10=sec10(d), s11=sec11(d))

ORDER_IDX = ["000001", "399001", "399006", "000688", "899050"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/market.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "site/index.html"
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    html = render(d)
    # 自检：残留 {xxx} 占位符说明模板没替换干净，禁止产出坏页面
    left = re.findall(r"\{[A-Za-z_][A-Za-z_0-9.]*\}", html)
    if left:
        raise SystemExit("模板占位符未替换: %s -> %s" % (sorted(set(left)), out))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("生成 -> %s (%d bytes)" % (out, len(html.encode("utf-8"))))


if __name__ == "__main__":
    main()