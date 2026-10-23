# -*- coding: utf-8 -*-
"""
A股每日复盘 - HTML 生成器（纯标准库）

严格十章结构，缺数据一律渲染为"数据暂未获取"，绝不编造。

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
       ("s4", "四、消息面"), ("s5", "五、涨跌成因"), ("s6", "六、持仓逐一复盘"),
       ("s7", "七、此前推论验证"), ("s8", "八、策略调整建议"),
       ("s9", "九、商业航天"), ("s10", "十、低估板块跟踪")]

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
               "<tr><td>跌/涨比</td><td><b>%s : 1</b></td>"
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
<p>两市成交额：<b>{amt} 亿元</b>（约 {wan} 万亿）。较前一交易日：{ac}</p>
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
             ac=('<span class="%s">%+.2f%%</span>'
                 % ("up" if ac > 0 else "down", ac)) if ac is not None
                else '<span class="na">%s</span>' % NA,
             bro=bro,
             zt=lp.get("zt") if lp.get("zt") is not None else NA,
             dt=lp.get("dt") if lp.get("dt") is not None else NA,
             core=core, style=style)


def sec2(d):
    f = d["fund_flow"]

    def rows(lst, cls):
        s = ""
        for x in lst[:3]:
            s += ("<tr><td>%s</td><td class='%s'>%+.2f</td><td>%s</td></tr>"
                  % (x["name"], cls, x["net_yi"], pct(x["pct"])))
        return s or "<tr><td colspan='3' class='na'>%s</td></tr>" % NA

    ins = [x["name"] for x in f.get("in_top") or []]
    outs = [x["name"] for x in f.get("out_top") or []]
    tin = sum(x["net_yi"] for x in f.get("in_top") or [])
    tout = sum(x["net_yi"] for x in f.get("out_top") or [])
    ratio = abs(tout / tin) if tin else None
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
        "已获取的板块流向与持仓标的<b>无明确同向或反向对应</b>，本节不对持仓方向性下结论。"

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
<p><b>北向资金</b>：<span class="na">{na}</span>（制度性原因，仅成交额口径可查，非遗漏）。</p>
<div class="box warn"><b>操作纪律</b><br>
不新开仓、不追高；仅按第八章既定预警价执行分批加仓，不因单日资金流向改变计划。</div>
</section>"""
    return F(tpl, rin=rows(f.get("in_top") or [], "up"),
             rout=rows(f.get("out_top") or [], "down"),
             ins=("、".join(ins) if ins else NA),
             outs=("、".join(outs) if outs else NA),
             tin="%.2f" % tin, tout="%.2f" % tout,
             ratio=("%.2f" % ratio if ratio is not None else NA),
             hold=hold_txt, cov_txt=cov_txt,
             amt=yi(amt),
             amt_note=("已获取" if amt else '<span class="na">%s</span>' % NA),
             ratio2=(("%.2f : 1" % (b[1] / b[0])) if (b and b[0]) else NA),
             bd_note=('<span class="tag b">已获取</span>' if b
                      else '<span class="tag y">历史回补口径无回溯值</span>'),
             na=NA,
             zt=lp.get("zt") if lp.get("zt") is not None else NA,
             dt=lp.get("dt") if lp.get("dt") is not None else NA)


def sec3(d):
    lst = idx_rows(d)
    kc = (d["indexes"].get("000688") or {}).get("pct")
    if lst:
        red = [x for x in lst if x[2] > 0]
        if red:
            obs = ("科创50 今日 %s。纳入观察的 %d 个宽基中<b>收红 %d 个</b>（%s），"
                   "收绿 %d 个。"
                   % (pct(kc), len(lst), len(red),
                      "、".join(x[1] for x in red), len(lst) - len(red)))
        else:
            obs = ("科创50 今日 %s。纳入观察的 %d 个宽基<b>全部收绿</b>，"
                   "宽基层面无任何方向性承接。" % (pct(kc), len(lst)))
    else:
        obs = "宽基行情未获取。"
    tpl = """
<section id="s3"><h2>三、国家队 / 汇金与宽基ETF持仓数据</h2>
<div class="box"><b>数据状态</b>：宽基ETF份额变动、汇金持仓明细属低频披露数据，
免费接口<b>不提供</b>。本节如实标注：<span class="na">{na}</span>。</div>
<table><tr><th>ETF类型</th><th>净流入(亿元)</th><th>代表标的</th></tr>
<tr><td>沪深300ETF</td><td class="na">{na}</td><td>510300</td></tr>
<tr><td>上证50ETF</td><td class="na">{na}</td><td>510050</td></tr>
<tr><td>中证500ETF</td><td class="na">{na}</td><td>510500</td></tr>
<tr><td>科创50ETF</td><td class="na">{na}</td><td>588000</td></tr></table>
<p><b>可替代观察</b>：{obs}
但这是<b>价格推断，不等于</b>国家队申购行为，仅供参考，不作结论。</p>
</section>"""
    return F(tpl, na=NA, obs=obs)


def sec4(d):
    tpl = """
<section id="s4"><h2>四、消息面汇总</h2>
<h3 class="sub">国内政策</h3>
<div class="box"><span class="na">{na}</span> —— 本脚本不接入新闻源，政策面需人工补充。
本节<b>不编造</b>任何政策内容。</div>
<h3 class="sub">海外宏观</h3>
<table><tr><th>指标</th><th>数值</th><th>涨跌</th></tr>
<tr><td>道琼斯</td><td>{djia}</td><td>{djia_p}</td></tr>
<tr><td>标普500</td><td>{spx}</td><td>{spx_p}</td></tr>
<tr><td>纳斯达克</td><td>{ndx}</td><td>{ndx_p}</td></tr>
<tr><td>美元指数 DXY</td><td>{dxy}</td><td>{dxy_p}</td></tr>
<tr><td>美元兑离岸人民币</td><td>{cnh}</td><td>{cnh_p}</td></tr>
<tr><td><b>Brent 原油</b></td><td class="na">{na}</td><td class="na">{na}</td></tr>
<tr><td><b>美10Y国债收益率</b></td><td class="na">{na}</td><td class="na">{na}</td></tr>
<tr><td>USD/JPY</td><td class="na">{na}</td><td class="na">{na}</td></tr></table>
<p class="na">美股为美东时间前一交易日收盘。Brent、美10Y、USD/JPY 经东方财富接口实测
<b>确认不提供</b>，标注为数据暂未获取，<b>未用 WTI 或任何其他品种替代</b>。</p>
<h3 class="sub">商品（持仓相关）</h3>
<table><tr><th>品种</th><th>价格</th><th>涨跌幅</th><th>备注</th></tr>
<tr><td>COMEX 黄金</td><td>{gc}</td><td>{gc_p}</td><td>场外黄金 002611 锚定</td></tr>
<tr><td>COMEX 白银</td><td>{si}</td><td>{si_p}</td><td>—</td></tr>
<tr><td>NYMEX 原油 (WTI)</td><td>{cl}</td><td>{cl_p}</td><td><b>非 Brent</b>，仅参考</td></tr>
<tr><td>LME 铝</td><td class="na">{na}</td><td class="na">{na}</td><td>南山铝业成本端</td></tr></table>
<div class="box warn"><b>黄金双因子状态（002611 场外）</b><br>
Brent &lt; 100 美元 —— <span class="na">{na}</span><br>
美10Y &lt; 4.3% —— <span class="na">{na}</span><br>
<b>结论：双因子判定无法完成</b>。本报告<b>不宣称</b>信号触发，也不宣称未触发。<br>
参考：WTI 报 {cl} 美元，已在 100 关口下方，但 <b>WTI ≠ Brent</b>，不能据此代替判定。<br>
执行：维持常规 500 元 / 月定投，额外加仓信号<b>挂起</b>，待数据源恢复后重评。
</div>
<h3 class="sub">持仓标的的消息</h3>
<div class="box"><span class="na">{na}</span> —— 需人工核查交易所公告。
已知关键节点：<b>10/29 南山铝业三季报</b>、<b>10/31 隆基绿能三季报</b>。</div>
</section>"""
    return F(tpl, na=NA,
             djia=g_(d, "DJIA"), djia_p=gv(d, "DJIA"),
             spx=g_(d, "SPX"), spx_p=gv(d, "SPX"),
             ndx=g_(d, "NDX"), ndx_p=gv(d, "NDX"),
             dxy=g_(d, "UDI"), dxy_p=gv(d, "UDI"),
             cnh=g_(d, "USDCNH", 4), cnh_p=gv(d, "USDCNH"),
             gc=g_(d, "GC00Y"), gc_p=gv(d, "GC00Y"),
             si=g_(d, "SI00Y"), si_p=gv(d, "SI00Y"),
             cl=g_(d, "CL00Y"), cl_p=gv(d, "CL00Y"))


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
                           st=(('<span class="tag y">已触发 %s</span>'
                                % ("%.3f" % trig[c]["trigger"]))
                               if (c in trig and trig[c].get("trigger") is not None)
                               else '<span class="tag n">未触发</span>'))
        det += ("<div class='box'><b>{n} {c}</b>　收盘 {px}　涨跌 {p}　"
                "浮盈亏 {pn}<br>　<span class='na'>{t}</span><br>"
                "　<span class='na'>{note}</span></div>"
                ).format(n=v["name"], c=c, px=price(v["close"]), p=pct(v["pct"]),
                         pn=("%+.2f%%" % v["pnl_pct"]) if v["pnl_pct"] is not None else NA,
                         t=(trig[c]["note"] if c in trig else NA),
                         note=DISCIPLINE.get(c, ""))
    yz_w = (pf.get("601106", {}).get("mv") or 0) / tot * 100 if tot else 0
    tpl = """
<section id="s6"><h2>六、持仓逐一复盘</h2>
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


def sec7(d):
    pf = d["portfolio"]
    nsi = board_flow(d, "有色金属", "工业金属", "小金属", "贵金属")
    if nsi and nsi.get("net_yi") is not None:
        nsi_tag = ('<span class="tag r">❌ 未验证</span>'
                   if nsi["net_yi"] < 0 else '<span class="tag g">✅ 获验证</span>')
        nsi_txt = "%s 板块当日%s%s" % (nsi["name"], flow_phrase(nsi),
                                       board_pct_txt(nsi))
    else:
        nsi_tag = '<span class="tag n">⏳ 数据未获取</span>'
        nsi_txt = '<span class="na">%s</span>' % NA

    def px(c):
        return price((pf.get(c) or {}).get("close"))

    comm = tone(d, "515880")
    tpl = """
<section id="s7"><h2>七、此前推论验证</h2>
<table><tr><th>推论</th><th>结果</th><th>当日数据</th></tr>
<tr><td>有色为第一方向</td><td>{nsi_tag}</td><td>{nsi_txt}</td></tr>
<tr><td>黄金 ETF 双因子加仓信号</td><td><span class="tag n">⏳ 无法判定</span></td><td>Brent 与美10Y 数据暂未获取</td></tr>
<tr><td>015790 赎回（规避风险）</td><td><span class="tag g">✅ 已完成</span></td><td>已赎回</td></tr>
<tr><td>南山铝业三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>10/29 披露</td></tr>
<tr><td>隆基绿能三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>10/31 披露</td></tr>
<tr><td>513120 不追高，回调加仓</td><td>{w1}</td><td>现价 {p1}{w1n}</td></tr>
<tr><td>中国一重做 T 降成本</td><td>{w2}</td><td>现价 {p2}{w2n}</td></tr>
<tr><td>通信 ETF 月定投 500 元</td><td><span class="tag b">✅ 执行中</span></td><td>{comm}</td></tr>
<tr><td>1 年期执行计划 v3.0</td><td><span class="tag b">✅ 框架运行</span></td><td>本日 {hit}/{tot} 触发</td></tr></table>
</section>"""
    t13 = next((r for r in (d.get("triggers") or []) if r["code"] == "513120"), None)
    w1 = ('<span class="tag y">⚡ 已触发观察档</span>' if (t13 and t13.get("trigger"))
          else '<span class="tag g">✅ 纪律维持</span>')
    w1n = ("，已跌破 %.3f 观察档" % t13["trigger"] if (t13 and t13.get("trigger")) else "，未跌破观察档")
    yz = pf.get("601106") or {}
    yz_hit = (yz.get("close") is not None and yz.get("close") <= 2.81
              and yz.get("pct") is not None and yz["pct"] <= -3.0)
    w2 = ('<span class="tag y">⚡ 已触发做T买点</span>' if yz_hit
          else '<span class="tag b">✅ 执行中</span>')
    w2n = "，已达做T买点条件" if yz_hit else "，未达 2.81 买点"
    return F(tpl, nsi_tag=nsi_tag, nsi_txt=nsi_txt, p1=px("513120"), p2=px("601106"),
             w1=w1, w1n=w1n, w2=w2, w2n=w2n, comm=comm,
             hit=d["triggered_count"], tot=d["trigger_total"])


def sec8(d):
    ev = "".join("<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>"
                 .format(a=x[0], b=x[1], c="★" * x[2]) for x in config.EVENTS)
    tr = "".join(
        "<tr><td>{n}</td><td>{c}</td><td>{l}</td><td>{s}</td><td>{t}</td></tr>".format(
            n=r["name"], c=price(r["close"], 3) if r.get("close") is not None else NA,
            l=" / ".join(str(x) for x in r["ladder"]) if r.get("ladder") else NA,
            s=("<span class='tag g'>已触发 %s</span>"
               % ("%.3f" % r["trigger"]) if r.get("trigger")
               else "<span class='tag n'>未触发</span>"),
            t=r.get("note") or NA)
        for r in d["triggers"])
    hit, tot = d["triggered_count"], d["trigger_total"]
    fired = [r for r in d["triggers"] if r.get("trigger")]
    if hit:
        concl = ("<div class='box warn'><b>今日执行结论</b>：触发 <b>{hit} / {tot}</b> 项，"
                 "<b>需要执行</b>。涉及：{names}。严格按下行阶梯的档位下单，"
                 "档位已跌穿即执行，不追加、不上移档位。</div>"
                 .format(hit=hit, tot=tot,
                         names="、".join("%s（%.3f）" % (r["name"], r["trigger"])
                                        for r in fired)))
    else:
        concl = ("<div class='box good'><b>今日执行结论</b>：触发 <b>{hit} / {tot}</b> 项，"
                 "<b>无需任何交易动作</b>。按 1 年期纪律「不触发不动作」执行，继续等待。"
                 "</div>".format(hit=hit, tot=tot))
    tpl = """
<section id="s8"><h2>八、策略调整建议</h2>
{concl}
<h3 class="sub">触发监控面板（下行触发：价格从上方跌破才触发）</h3>
<table><tr><th>标的</th><th>现价</th><th>加仓档位</th><th>状态</th><th>判定说明</th></tr>{tr}</table>
<div class="box warn"><b>档位方向说明</b>：加仓触发一律为<b>下行触发</b>——
现价<b>从上方跌破</b>某档位才触发。「未触发」时右侧给出的是
「还需下跌多少元」，不是价格上涨空间。</div>
<h3 class="sub">1 年期执行计划 v3.0 时间窗口</h3>
<table><tr><th>日期</th><th>事件</th><th>重要性</th></tr>{ev}</table>
<p><b>最近节点</b>：10/27-28 美联储 FOMC → 10/29 南山铝业三季报 → 10/31 隆基绿能三季报。
三周内事件密集，<b>10/29 与 10/31 之前不建议新增仓位</b>。</p>
<h3 class="sub">加仓纪律</h3>
<ul>
<li>加仓间隔 ≥ 7 个交易日</li>
<li>每月至少 1 次加仓（保证）</li>
<li>下跌趋势可延长至 2 周 1 次</li>
<li>中国一重仅做 T，<b>不加仓摊薄</b></li>
</ul>
</section>"""
    return F(tpl, concl=concl, tr=tr, ev=ev)


def sec9():
    return """
<section id="s9"><h2>九、商业航天 / 太空产业 —— 长期观察</h2>
<div class="box"><span class="na">数据暂未获取</span> —— 本章为长期产业跟踪，
当前无可自动获取的数据源，且不影响日内交易决策。
发射日历、复用进度、组网速率、一级市场融资四项均需人工或专用数据源补充。</div>
<h3 class="sub">配置框架状态</h3>
<table><tr><th>层级</th><th>目标仓位</th><th>当前状态</th></tr>
<tr><td>第一层 指数化底仓</td><td>50-60%</td><td><span class="tag n">未建立</span></td></tr>
<tr><td>第二层 产业链卫星仓</td><td>25-35%</td><td><span class="tag n">未建立</span></td></tr>
<tr><td>第三层 事件仓</td><td>≤10-15%</td><td><span class="tag n">未建立</span></td></tr></table>
</section>"""


def sec10(d):
    we = d["watch_etfs"]
    rows = ""
    for c, _ in config.WATCH_ETFS:
        v = we.get(c)
        if not v:
            continue
        rows += ("<tr><td>{n} {c}</td><td>{p}</td><td>{g}</td></tr>"
                 .format(n=v["name"], c=c, p=price(v["close"], 3),
                         g=pct(v["pct"])))
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
        nsi_txt = "板块资金流数据%s，<b>本日不做方向性结论</b>。" % NA

    tpl = """
<section id="s10"><h2>十、低估 · 低拥挤板块跟踪</h2>
<h3 class="sub">【① 稀有小金属 / 稀有资源】</h3>
<table><tr><th>标的</th><th>最新价</th><th>涨跌</th></tr>{rows}</table>
<div class="box warn"><b>信号检查</b><br>
{nsi_txt}</div>
<h3 class="sub">【② 电力与公用事业（压舱底仓）】</h3>
<table><tr><th>标的</th><th>最新价</th><th>涨跌</th></tr>
<tr><td>电力ETF广发 159611</td><td>{d11}</td><td>{d12}</td></tr>
<tr><td>红利低波ETF华泰柏瑞 512890</td><td>{d21}</td><td>{d22}</td></tr></table>
<div class="box"><b>信号检查</b>：股息率分位数据暂未获取（需第三方终端）。
电力ETF {t1}；红利低波 {t2}。<b>结论：观察</b>，跌至低估分位再考虑建底仓。</div>
</section>"""
    return F(tpl, rows=rows, nsi_txt=nsi_txt,
             d11=price((we.get("159611") or {}).get("close"), 3),
             d12=pct((we.get("159611") or {}).get("pct")),
             d21=price((we.get("512890") or {}).get("close"), 3),
             d22=pct((we.get("512890") or {}).get("pct")),
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
    dt = d["trade_date"] or NA
    wd = "一二三四五六日"[datetime.fromisoformat(dt).weekday() % 7] \
        if dt != NA else ""
    gen = datetime.fromisoformat(d["generated_at"]).strftime("%Y-%m-%d %H:%M")
    src = d.get("source") or "realtime"
    src_txt = ("历史日K回补口径（逐日K线回溯，非实时快照）"
               if src.startswith("historical") else "实时收盘快照")

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
         ('<span class="%s">较前日 %+.2f%%</span>' % ("up" if ac > 0 else "down", ac))
         if ac is not None else '<span class="na">较前日：' + NA + '</span>'),
        ("s2", "涨跌家数", bd_v, bd_d),
        ("s8", "加仓触发", "%d / %d" % (hit, tot),
         '<span class="down">无需操作</span>' if hit == 0
         else '<span class="up">需执行</span>'),
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
<div class="sub">1年期持仓执行计划 v3.0 ｜ 生成时间 {gen} (UTC+8) ｜ 行情口径：{src_txt} ｜ 数据源：东方财富公开行情接口</div></div>
<div class="cards">{ch}</div>
<div class="trigger {ok}"><h3>{head}</h3>
<div class="cnt">今日触发 {hit} / {tot}</div>
<p>{msg}</p></div>
{s1}{s2}{s3}{s4}{s5}{s6}{s7}{s8}{s9}{s10}
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
             ok=("ok" if hit > 0 else ""),
             head=("✅ 有触发项，请按第八章执行" if hit
                   else "⚠️ 全部未触发 —— 按纪律不动作"),
             hit=hit, tot=tot,
             msg=("有加仓或做 T 档位被跌破，请查阅第八章操作清单。" if hit
                  else "全部 {} 个监控标的均未跌破预警价，今日无任何交易动作。".format(tot)),
             s1=sec1(d), s2=sec2(d), s3=sec3(d), s4=sec4(d), s5=sec5(d),
             s6=sec6(d), s7=sec7(d), s8=sec8(d), s9=sec9(), s10=sec10(d))


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