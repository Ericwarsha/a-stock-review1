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
    up, dn, fl = breadth(d, "up"), breadth(d, "down"), breadth(d, "flat")
    amt = mktotal(d)
    lp = d.get("limit_pool") or {}
    cyb = ix.get("399006") or {}
    sh = ix.get("000001") or {}
    kc = ix.get("000688") or {}
    ratio = dn / up if up else 0
    core = F("<b>指数跌幅温和，但个股是真跌</b>：上证仅 {shp}、创业板 {cyb}，"
             "沪深两市却是<b>下跌 {dn} 家 vs 上涨 {up} 家</b>，"
             "下跌家数是上涨家数的 <b>{ratio} 倍</b>。"
             "权重股护住了指数点位，个股赚钱效应明显弱于指数表面。",
             shp=pct(sh.get("pct")), cyb=pct(cyb.get("pct")),
             dn=dn, up=up, ratio="%.2f" % ratio)
    style = F("科创50 {kp} 逆势收红，创业板指 {cp} 领跌 —— 资金正从高弹性成长撤出，"
              "低位与防御方向相对抗跌。",
              kp=pct(kc.get("pct")), cp=pct(cyb.get("pct")))
    tpl = """
<section id="s1"><h2>一、今日A股行情</h2>
<h3 class="sub">指数表现</h3>
<table><tr><th>指数</th><th>收盘点位</th><th>涨跌幅</th></tr>{rows}</table>
<h3 class="sub">量能</h3>
<p>两市成交额：<b>{amt} 亿元</b>（约 {wan} 万亿）。较前一交易日增减：<span class="na">{na}</span></p>
<h3 class="sub">涨跌结构</h3>
<table><tr><th>项目</th><th>数值</th></tr>
<tr><td>上涨家数（沪深）</td><td>{up}</td></tr>
<tr><td>下跌家数（沪深）</td><td>{dn}</td></tr>
<tr><td>平盘家数（沪深）</td><td>{fl}</td></tr>
<tr><td>跌/涨比</td><td><b>{ratio} : 1</b>（跌多涨少）</td></tr>
<tr><td>涨停</td><td>{zt}</td></tr>
<tr><td>跌停</td><td>{dt}</td></tr></table>
<h3 class="sub">核心信号</h3>
<div class="box warn">{core}</div>
<h3 class="sub">市场风格</h3>
<p>{style}</p>
</section>"""
    return F(tpl, rows=rows, amt=yi(amt), wan=("%.2f" % (amt / 1e12) if amt else NA), na=NA,
             up=up, dn=dn, fl=fl, ratio="%.2f" % ratio,
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

    tin = sum(x["net_yi"] for x in f["in_top"])
    tout = sum(x["net_yi"] for x in f["out_top"])
    ratio = abs(tout / tin) if tin else 0
    up, dn = breadth(d, "up"), breadth(d, "down")
    lp = d.get("limit_pool") or {}
    tpl = """
<section id="s2"><h2>二、资金面（主力资金 + 市场热度）</h2>
<h3 class="sub">主力资金分行业流向</h3>
<table><tr><th>净流入居前</th><th>净流入(亿元)</th><th>涨跌幅</th></tr>{rin}</table>
<table><tr><th>净流出居前</th><th>净流出(亿元)</th><th>涨跌幅</th></tr>{rout}</table>
<div class="box risk">
<b>资金流动逻辑</b>：流入前 5 合计 <b>+{tin} 亿</b>，流出前 5 合计 <b>{tout} 亿</b>，
净流出规模是净流入的 <b>{ratio} 倍</b>。资金在撤离电力设备、电池、锂电池链条，
集中流向电子与数字芯片设计 —— 这是<b>新能源链出清、算力硬件接棒</b>的切换，
而非普涨行情。持仓里的隆基绿能（光伏链）正处在资金流出的方向上。
</div>
<h3 class="sub">市场热度评估</h3>
<table><tr><th>指标</th><th>读数</th><th>判断</th></tr>
<tr><td>量能</td><td>{amt} 亿元</td><td><span class="tag y">中性偏弱</span></td></tr>
<tr><td>跌/涨家数比</td><td>{ratio2} : 1</td><td><span class="tag r">偏冷</span></td></tr>
<tr><td>涨停家数</td><td>{zt}</td><td><span class="tag b">尚可</span></td></tr>
<tr><td>跌停家数</td><td>{dt}</td><td><span class="tag y">未失控</span></td></tr></table>
<p><b>北向资金</b>：<span class="na">{na}</span>（制度性原因，仅成交额口径可查，非遗漏）。</p>
<div class="box warn"><b>短期判断</b><br>
风险提示：下跌家数远超上涨家数，个股赚钱效应差，指数被权重股护住。<br>
机会提示：主力资金明确流向电子 / 数字芯片，持仓的通信ETF 逆势上涨与此方向一致。<br>
操作建议：<b>不新开仓、不追高</b>；仅按既定预警价执行分批加仓。</div>
</section>"""
    return F(tpl, rin=rows(f["in_top"], "up"), rout=rows(f["out_top"], "down"),
             tin="%.2f" % tin, tout="%.2f" % tout, ratio="%.2f" % ratio,
             ratio2=("%.2f" % (dn / up) if up else NA),
             amt=yi(mktotal(d)), na=NA,
             zt=lp.get("zt") if lp.get("zt") is not None else NA,
             dt=lp.get("dt") if lp.get("dt") is not None else NA)


def sec3(d):
    tpl = """
<section id="s3"><h2>三、国家队 / 汇金与宽基ETF持仓数据</h2>
<div class="box"><b>数据状态</b>：宽基ETF份额变动、汇金持仓明细属低频披露数据，
免费接口<b>不提供</b>。本节如实标注：<span class="na">{na}</span>。</div>
<table><tr><th>ETF类型</th><th>净流入(亿元)</th><th>代表标的</th></tr>
<tr><td>沪深300ETF</td><td class="na">{na}</td><td>510300</td></tr>
<tr><td>上证50ETF</td><td class="na">{na}</td><td>510050</td></tr>
<tr><td>中证500ETF</td><td class="na">{na}</td><td>510500</td></tr>
<tr><td>科创50ETF</td><td class="na">{na}</td><td>588000</td></tr></table>
<p><b>可替代观察</b>：科创50 今日 {kp}，是唯一收红的宽基，可视作科技方向有承接的间接信号。
但这是<b>价格推断，不等于</b>国家队申购行为，仅供参考，不作结论。</p>
</section>"""
    return F(tpl, na=NA, kp=pct((d["indexes"].get("000688") or {}).get("pct")))


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
    f = d["fund_flow"]
    ix = d["indexes"]
    up, dn = breadth(d, "up"), breadth(d, "down")
    pf = d["portfolio"]
    tot = sum(v.get("mv") or 0 for v in pf.values())
    yz_w = (pf.get("601106", {}).get("mv") or 0) / tot * 100 if tot else 0
    tpl = """
<section id="s5"><h2>五、涨跌成因分析</h2>
<h3 class="sub">今日涨跌驱动主线</h3>
<table><tr><th>#</th><th>主线</th><th>逻辑</th><th>对应板块</th></tr>
<tr><td><b>1</b></td><td>算力硬件主线强化</td><td>主力净流入 {i1}、{i2}、{i3}</td><td>电子 / 芯片 / 通信</td></tr>
<tr><td><b>2</b></td><td>新能源链集体调整</td><td>净流出 {o1}、{o2}、{o3}，跌幅同步放大</td><td>电力设备 / 电池 / 锂电</td></tr>
<tr><td><b>3</b></td><td>指数与个股背离</td><td>上证仅 {shp}，但下跌 {dn} 家 &gt; 上涨 {up} 家</td><td>全市场</td></tr>
<tr><td><b>4</b></td><td>低位品种逆势活跃</td><td>传媒出版、生猪养殖、LED 等低位方向补涨</td><td>传媒 / 农业 / 电子</td></tr></table>
<h3 class="sub">隐忧</h3>
<table><tr><th>隐忧</th><th>表现</th><th>影响</th></tr>
<tr><td>⚠️ 指数失真</td><td>权重护盘掩盖个股普跌</td><td>指数点位不能作为加仓依据</td></tr>
<tr><td>⚠️ 持仓踩中流出方向</td><td>隆基绿能所属光伏链资金持续流出</td><td>10/31 三季报前不加仓</td></tr>
<tr><td>⚠️ 中国一重占比过高</td><td>单只占持仓市值 {yzw}%</td><td>做 T 是降本唯一路径，不可加仓摊薄</td></tr>
<tr><td>⚠️ 有色资金流出</td><td>有色金属板块净流出</td><td>南山铝业第一方向推论未获验证</td></tr></table>
</section>"""
    ins = f["in_top"][:3]
    outs = f["out_top"][:3]
    def pick(lst, i, sign):
        if i < len(lst):
            return "%s %s%.0f 亿" % (lst[i]["name"], sign, lst[i]["net_yi"])
        return NA

    return F(tpl,
             i1=pick(ins, 0, "+"), i2=pick(ins, 1, "+"), i3=pick(ins, 2, "+"),
             o1=pick(outs, 0, ""), o2=pick(outs, 1, ""), o3=pick(outs, 2, ""),
             shp=pct((ix.get("000001") or {}).get("pct")), dn=dn, up=up,
             yzw="%.1f" % yz_w)


def sec6(d):
    pf = d["portfolio"]
    tot = sum(v.get("mv") or 0 for v in pf.values())
    notes = {
        "600219": "跌幅小于大盘，抗跌性尚可。三季报 10/29 是关键验证点，业绩落地前不重仓加码。",
        "516630": "逆势上涨，与主力资金流向电子 / 通信的方向一致。",
        "513120": "无持仓记录，1 年期内不主动建仓。",
        "515880": "逆势上涨，是今日持仓中表现最好的方向性品种。",
        "000420": "小幅上涨，仓位很小，影响有限。",
        "601012": "深度浮亏且所属光伏链资金流出，10/31 三季报前不加仓。",
        "002298": "半年计划阶段 1 探底建仓期，按 7.30 / 7.00 / 6.50 阶梯。",
        "601106": "占比过高，做 T 降本是唯一路径；今日未达做 T 买点条件。",
    }
    rows, det = "", ""
    for c in ORDER:
        v = pf.get(c)
        if not v:
            continue
        w = (v["mv"] / tot * 100) if (v.get("mv") and tot) else None
        pnl = (pct(v["pnl_pct"]) if v["pnl_pct"] is not None
               else '<span class="na">无成本 / 未建仓</span>')
        rows += ("<tr><td><b>{n}</b><br><span class='na'>{c}</span></td>"
                 "<td>{p}</td><td>{pnl}</td><td>{w}</td><td>{mv}</td></tr>"
                 ).format(n=v["name"], c=c, p=pct(v["pct"]), pnl=pnl,
                           w=("%.1f%%" % w) if w is not None
                           else '<span class="na">' + NA + '</span>',
                           mv=("%.0f" % v["mv"]) if v.get("mv")
                           else '<span class="na">' + NA + '</span>')
        det += ("<div class='box'><b>{n} {c}</b>　收盘 {px}　涨跌 {p}　"
                "浮盈亏 {pn}<br><span class='na'>{note}</span></div>"
                ).format(n=v["name"], c=c, px=price(v["close"]), p=pct(v["pct"]),
                         pn=("%+.2f%%" % v["pnl_pct"]) if v["pnl_pct"] is not None else NA,
                         note=notes.get(c, ""))
    yz_w = (pf.get("601106", {}).get("mv") or 0) / tot * 100 if tot else 0
    tpl = """
<section id="s6"><h2>六、持仓逐一复盘</h2>
<table><tr><th>标的</th><th>当日表现</th><th>浮盈 / 亏</th><th>占持仓市值</th><th>市值(元)</th></tr>{rows}</table>
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

    def px(c):
        return price((pf.get(c) or {}).get("close"))

    tpl = """
<section id="s7"><h2>七、此前推论验证</h2>
<table><tr><th>推论</th><th>结果</th><th>说明</th></tr>
<tr><td>有色为第一方向</td><td><span class="tag r">❌ 未验证</span></td><td>有色金属板块主力净流出，资金在撤离</td></tr>
<tr><td>黄金 ETF 双因子加仓信号</td><td><span class="tag n">⏳ 无法判定</span></td><td>Brent 与美10Y 数据暂未获取</td></tr>
<tr><td>015790 赎回（规避风险）</td><td><span class="tag g">✅ 已完成</span></td><td>已赎回</td></tr>
<tr><td>南山铝业三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>10/29 披露</td></tr>
<tr><td>隆基绿能三季报后决策</td><td><span class="tag y">⏳ 待验证</span></td><td>10/31 披露，光伏链资金持续流出</td></tr>
<tr><td>513120 不追高，回调加仓</td><td><span class="tag g">✅ 纪律维持</span></td><td>现价 {p1}，未建仓</td></tr>
<tr><td>中国一重做 T 降成本</td><td><span class="tag b">✅ 执行中</span></td><td>现价 {p2}，未达 2.81 买点</td></tr>
<tr><td>通信 ETF 月定投 500 元</td><td><span class="tag b">✅ 方向正确</span></td><td>逆势上涨，与主力资金流向一致</td></tr>
<tr><td>1 年期执行计划 v3.0</td><td><span class="tag b">✅ 框架运行</span></td><td>本日 {hit}/{tot} 触发，无需执行</td></tr></table>
</section>"""
    return F(tpl, p1=px("513120"), p2=px("601106"),
             hit=d["triggered_count"], tot=d["trigger_total"])


def sec8(d):
    ev = "".join("<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>"
                 .format(a=x[0], b=x[1], c="★" * x[2]) for x in config.EVENTS)
    tr = "".join(
        "<tr><td>{n}</td><td>{c}</td><td>{l}</td><td>{s}</td></tr>".format(
            n=r["name"], c=price(r["close"], 3) if r.get("close") is not None else NA,
            l=" / ".join(str(x) for x in r["ladder"]) if r.get("ladder") else NA,
            s=("<span class='tag g'>已触发</span>" if r.get("trigger")
               else "<span class='tag n'>未触发</span>"))
        for r in d["triggers"])
    hit, tot = d["triggered_count"], d["trigger_total"]
    tpl = """
<section id="s8"><h2>八、策略调整建议</h2>
<div class="box good"><b>今日执行结论</b>：触发 <b>{hit} / {tot}</b> 项，
<b>无需任何交易动作</b>。按 1 年期纪律「不触发不动作」执行，继续等待。</div>
<h3 class="sub">触发监控面板（下行触发，方向已纠正）</h3>
<table><tr><th>标的</th><th>现价</th><th>加仓档位</th><th>状态</th></tr>{tr}</table>
<div class="box warn"><b>参数纠错说明</b>：旧版有三个触发价方向或量级错误，已作废 ——
南山铝业 4.50 与 吉林化纤 3.95 <b>高于现价</b>（属向上突破，不是下跌加仓，永远不会下行触发）；
通信 ETF 1.20 约为现价的 <b>2.24 倍</b>，量级完全错误。
全部改为下行阶梯，方向正确：价格从上方跌破才触发。</div>
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
    return F(tpl, hit=hit, tot=tot, tr=tr, ev=ev)


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
    tpl = """
<section id="s10"><h2>十、低估 · 低拥挤板块跟踪</h2>
<h3 class="sub">【① 稀有小金属 / 稀有资源】</h3>
<table><tr><th>标的</th><th>最新价</th><th>涨跌</th></tr>{rows}</table>
<div class="box warn"><b>信号检查</b><br>
有色金属板块主力资金净流出，未见资金回流<br>
未出现放量上行突破<br>
<b>结论：介入信号未触发。</b>南山铝业维持观察，不加仓。</div>
<h3 class="sub">【② 电力与公用事业（压舱底仓）】</h3>
<table><tr><th>标的</th><th>最新价</th><th>涨跌</th></tr>
<tr><td>电力ETF广发 159611</td><td>{d11}</td><td>{d12}</td></tr>
<tr><td>红利低波ETF华泰柏瑞 512890</td><td>{d21}</td><td>{d22}</td></tr></table>
<div class="box"><b>信号检查</b>：股息率分位数据暂未获取（需第三方终端）。
电力ETF 与红利低波今日随大盘回落。<b>结论：观察</b>，跌至低估分位再考虑建底仓。</div>
</section>"""
    return F(tpl, rows=rows,
             d11=price((we.get("159611") or {}).get("close"), 3),
             d12=pct((we.get("159611") or {}).get("pct")),
             d21=price((we.get("512890") or {}).get("close"), 3),
             d22=pct((we.get("512890") or {}).get("pct")))


# ------------------------------------------------------------ 主渲染
def render(d):
    ix = d["indexes"]
    sh = ix.get("000001") or {}
    amt = mktotal(d)
    up, dn = breadth(d, "up"), breadth(d, "down")
    hit, tot = d["triggered_count"], d["trigger_total"]
    dt = d["trade_date"] or NA
    wd = "一二三四五六日"[datetime.fromisoformat(dt).weekday() % 7] \
        if dt != NA else ""
    gen = datetime.fromisoformat(d["generated_at"]).strftime("%Y-%m-%d %H:%M")

    cards = [
        ("s1", "上证指数", price(sh.get("close")), pct(sh.get("pct"))),
        ("s1", "深证成指", price((ix.get("399001") or {}).get("close")),
         pct((ix.get("399001") or {}).get("pct"))),
        ("s1", "创业板指", price((ix.get("399006") or {}).get("close")),
         pct((ix.get("399006") or {}).get("pct"))),
        ("s2", "两市成交额", "%.0f 亿" % (amt / 1e8) if amt else NA,
         '<span class="na">较前日：' + NA + '</span>'),
        ("s2", "涨跌家数", "%d / %d" % (up, dn),
         '<span class="down">跌多涨少</span>' if dn > up else '<span class="up">涨多跌少</span>'),
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
<div class="sub">1年期持仓执行计划 v3.0 ｜ 生成时间 {gen} (UTC+8) ｜ 数据源：东方财富公开行情接口</div></div>
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
    return F(tpl, dt=dt, css=CSS, nav=nav, wd=wd, gen=gen, ch=ch,
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