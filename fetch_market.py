# -*- coding: utf-8 -*-
"""
A股每日复盘 - 行情抓取（纯标准库，无第三方依赖）

设计原则：
1. 数据诚实 —— 任何接口失败或字段缺失，一律写 null，由报告层渲染成"数据暂未获取"。
2. 不猜测 —— 绝不推算、插值或用相近品种替代（如 WTI 不代替 Brent）。
3. 交易日判定 —— 用上证指数最新行情时间戳(f86)判断今日是否交易日，避免节假日跑出重复报告。

用法： python fetch_market.py [输出目录]
输出： <输出目录>/market.json
"""
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

import config

CST = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _get(url, retries=10, timeout=20):
    """GET JSON，失败返回 None（绝不抛错到上层）。

    东财对本机是"间歇性掐连接"而非彻底封禁：同一个 URL 可能这次通、下次
    直接 Remote end closed。所以重试要拉长并带随机抖动，撞上放行窗口就拿到了。
    """
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "close",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if i == retries - 1:
                print("  [FAIL] %s -> %s" % (url[:90], e))
                return None
            time.sleep(min(1.5 ** i, 6) + random.uniform(0, 0.8))
    return None


def _diff(js):
    if not js or not isinstance(js.get("data"), dict):
        return []
    return js["data"].get("diff") or []


# ------------------------------------------------- 备用源：腾讯 qt.gtimg.cn
def tx_code(secid):
    """东财 secid -> 腾讯代码。

    必须以东财的 mkt 前缀为准，不能看代码首位数字：沪市指数 1.000001(上证)
    和 1.000688(科创50) 首位都是 0，按首位判会误拉成 sz000001(平安银行)、
    sz000688(国城矿业)。只有北交所 8 开头需要特殊处理。
    """
    if "." not in secid:
        return secid
    mkt, code = secid.split(".")
    if code[:1] == "8":
        return "bj" + code
    return ("sh" if mkt == "1" else "sz") + code


def _tx(secids, retries=4):
    """腾讯行情兜底。返回 {东财code: {...}}。

    东财对本机是间歇性掐连接，一旦抽风整个复盘就断。这个源独立于东财，
    且字段含义已与东财逐项比对确认（13/13 完全一致）：
      p[3]=最新 p[4]=昨收 p[31]=涨跌 p[32]=涨跌%
      p[30]=行情时间 yyyyMMddHHmmss
      p[35]=价格/成交量(手)/成交额(元)，取第三段
    涨跌家数腾讯不提供，恒为 None，由报告层标注"数据暂未获取"。
    """
    secids = list(secids)
    if not secids:
        return {}
    url = "https://qt.gtimg.cn/q=" + ",".join(tx_code(s) for s in secids)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://gu.qq.com/"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode("gbk", "replace")
            back = {s.split(".")[1]: s.split(".")[1] for s in secids}
            out = {}
            for line in raw.split("\n"):
                if "~" not in line:
                    continue
                p = line.split("~")
                if len(p) < 38:
                    continue
                code = back.get(p[2])
                if not code:
                    continue
                try:
                    amt = float(p[35].split("/")[2]) if "/" in p[35] else None
                    out[code] = {"name": p[1].strip(), "close": float(p[3]),
                                 "pct": float(p[32]), "chg": float(p[31]),
                                 "amount": amt, "time": p[30],
                                 "high": float(p[33]), "low": float(p[34]),
                                 "prev": float(p[4]), "open": float(p[5])}
                except (ValueError, IndexError):
                    continue
            if out:
                return out
        except Exception as e:
            if i == retries - 1:
                print("  [FAIL] 腾讯备用源 -> %s" % e)
        time.sleep(1.5 ** i + random.uniform(0, 0.5))
    return {}


# ---------------------------------------------------------------- 交易日
def trading_day():
    """判定最近交易日 + 是否今日。

    主源：日K线（push2his 主机）。最后一根日K的日期 = 最近一个交易日，
          比实时行情接口(push2)稳定得多 —— 后者会间歇性被限流。
    备源：实时行情时间戳，仅在K线不可用时启用。

    不可退化为 None：一旦为 None，调用方会误判成非交易日而静默跳过发布。
    """
    trade_date = quote_time = None

    js = _get("https://push2his.eastmoney.com/api/qt/stock/kline/get"
              "?secid=1.000001&klt=101&fqt=0&end=20500101&lmt=2"
              "&fields1=f1,f2,f3&fields2=f51,f53")
    if js and isinstance(js.get("data"), dict):
        ks = js["data"].get("klines") or []
        if ks:
            trade_date = ks[-1].split(",")[0]
            quote_time = trade_date + " 15:00"

    if not trade_date:
        js = _get("https://push2.eastmoney.com/api/qt/stock/get"
                  "?secid=1.000001&fields=f43,f86")
        if js and isinstance(js.get("data"), dict) and js["data"].get("f86"):
            dt = datetime.fromtimestamp(js["data"]["f86"], CST)
            trade_date, quote_time = dt.date().isoformat(), dt.isoformat()

    if not trade_date:
        # 第三道备用源：ulist.np/get 实测可用性最好（stock/get、clist/get
        # 会被服务端间歇性掐断，而它同时也是指数/持仓的主力接口）。
        # f124 = 最新行情时间戳；休市日该值会停留在上一个交易日的收盘时刻，
        # 因此它天然给出"最近一个交易日"，与日K线主源语义一致。
        js = _get("https://push2.eastmoney.com/api/qt/ulist.np/get"
                  "?fltt=2&secids=1.000001&fields=f124")
        for row in _diff(js):
            if row.get("f124"):
                dt = datetime.fromtimestamp(row["f124"], CST)
                trade_date, quote_time = dt.date().isoformat(), dt.isoformat()
                break

    if not trade_date:
        # 第四道备用源：腾讯行情。独立于东财，几乎不受东财掐连接影响，
        # p[30] 行情时间前 8 位即行情日期，休市日会停在上一个交易日。
        for row in _tx(["1.000001"]).values():
            if row.get("time"):
                ts = str(row["time"])
                if len(ts) >= 8:
                    d = ts[:8]
                    trade_date = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
                    quote_time = "%s %s:%s:%s" % (
                        trade_date, ts[8:10], ts[10:12], ts[12:14])
                break

    if not trade_date:
        print("  [WARN] 四个交易日数据源均失败，无法判定交易日")
    return trade_date, quote_time


# ---------------------------------------------------------------- 指数
def _ohlc(close, high, low):
    """最高/最低必须满足 high >= close >= low，否则视为无效（宁缺勿错）。"""
    if close is None:
        return None, None
    if high is not None and low is not None:
        if high >= close >= low:
            return high, low
        return None, None
    return None, None


def fetch_indexes():
    ids = [x[0] for x in config.INDEXES]
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f104,f105,f106"
           % ",".join(ids))
    out = {}
    for d in _diff(_get(url)):
        code, name = d.get("f12"), d.get("f14")
        hi, lo = _ohlc(_num(d.get("f2")), _num(d.get("f15")), _num(d.get("f16")))
        out[code] = {
            "name": name,
            "close": _num(d.get("f2")),
            "pct": _num(d.get("f3")),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),   # 成交额(元)
            "high": hi, "low": lo,
            "prev": _num(d.get("f18")),
            "up": d.get("f104"),
            "down": d.get("f105"),
            "flat": d.get("f106"),
        }
    # 东财缺位的用腾讯补（涨跌家数腾讯不提供，保留 None）
    miss = [s for s in ids if s.split(".")[1] not in out]
    if miss:
        print("  [补源] 指数缺 %d 个，走腾讯" % len(miss))
        for code, row in _tx(miss).items():
            out[code] = {"name": row["name"], "close": row["close"],
                         "pct": row["pct"], "chg": row["chg"],
                         "amount": row["amount"],
                         "high": row["high"], "low": row["low"],
                         "prev": row["prev"],
                         "up": None, "down": None, "flat": None}
    return out


# ---------------------------------------------------------------- 持仓
def fetch_portfolio():
    ids = [config.secid(c) for c, *_ in config.PORTFOLIO]
    ids += [config.secid(c) for c, _ in config.WATCH_ETFS]
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18" % ",".join(ids))
    raw = {}
    for d in _diff(_get(url)):
        hi, lo = _ohlc(_num(d.get("f2")), _num(d.get("f15")), _num(d.get("f16")))
        raw[d.get("f12")] = {
            "close": _num(d.get("f2")),
            "pct": _num(d.get("f3")),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),
            "high": hi, "low": lo, "prev": _num(d.get("f18")),
        }
    # 东财缺位的用腾讯补齐，持仓价格是报告核心，绝不能留空
    miss = [s for s in ids if s.split(".")[1] not in raw]
    if miss:
        print("  [补源] 持仓缺 %d 个，走腾讯" % len(miss))
        for code, row in _tx(miss).items():
            raw[code] = {"close": row["close"], "pct": row["pct"],
                         "chg": row["chg"], "amount": row["amount"],
                         "high": row["high"], "low": row["low"],
                         "prev": row["prev"]}
    out = {}
    for code, name, cost, shares, kind in config.PORTFOLIO:
        q = raw.get(code, {})
        px = q.get("close")
        pnl = None
        if px is not None and cost:
            pnl = round((px - cost) / cost * 100, 2)
        out[code] = {"name": name, "cost": cost, "shares": shares,
                     "kind": kind, "close": px, "pct": q.get("pct"),
                     "chg": q.get("chg"), "amount": q.get("amount"),
                     "high": q.get("high"), "low": q.get("low"),
                     "prev": q.get("prev"),
                     "pnl_pct": pnl,
                     "mv": round(px * shares, 2) if (px and shares) else None}
    watch = {}
    for code, name in config.WATCH_ETFS:
        q = raw.get(code, {})
        watch[code] = {"name": name, "close": q.get("close"),
                       "pct": q.get("pct"),
                       "high": q.get("high"), "low": q.get("low")}
    return out, watch


# ---------------------------------------------------------------- 资金面
def fetch_fund_flow():
    base = ("https://push2.eastmoney.com/api/qt/clist/get?fid=f62&np=1"
            "&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f62,f3")
    def top(po, n):
        rows = []
        for d in _diff(_get("%s&po=%d&pz=%d&pn=1" % (base, po, n))):
            v = d.get("f62")
            if v is None:
                continue
            rows.append({"name": d.get("f14"), "code": d.get("f12"),
                         "net_yi": round(v / 1e8, 2), "pct": _num(d.get("f3"))})
        return rows
    return {"in_top": top(1, 5), "out_top": top(0, 5)}


def fetch_prev_amount(trade_date):
    """上一交易日两市成交额（分指数，单位元）。

    「放量反弹」还是「缩量反弹」的分水岭就在这个数上 —— 报告里必须有它，
    不能留「较前日：数据暂未获取」。日K线末根=当日，前一根=上一交易日。
    """
    out = {}
    for secid, code in (("1.000001", "000001"), ("0.399001", "399001")):
        js = _get("https://push2his.eastmoney.com/api/qt/stock/kline/get"
                  "?secid=%s&klt=101&fqt=0&end=20500101&lmt=3"
                  "&fields1=f1,f2,f3&fields2=f51,f53,f57" % secid)
        if not (js and isinstance(js.get("data"), dict)):
            continue
        ks = js["data"].get("klines") or []
        if len(ks) < 2:
            continue
        last = ks[-1].split(",")
        prev = ks[-2].split(",")
        # 只有当末根K线确实就是当日时，前一根才是「上一交易日」
        if trade_date and last[0].replace("-", "") != trade_date.replace("-", ""):
            continue
        try:
            out[code] = float(prev[2])
        except (ValueError, IndexError):
            continue
    return out


def fetch_limit_pool(trade_date):
    """涨停/跌停家数。date 需为 yyyyMMdd。"""
    d = (trade_date or "").replace("-", "")
    if len(d) != 8:
        return {"zt": None, "dt": None}
    res = {}
    for key, path, sort in (("zt", "getTopicZTPool", "fbt:asc"),
                            ("dt", "getTopicDTPool", "fund:asc")):
        js = _get("https://push2ex.eastmoney.com/%s"
                  "?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
                  "&Pageindex=0&pagesize=1&sort=%s&date=%s" % (path, sort, d))
        res[key] = js["data"]["tc"] if js and js.get("data") else None
    return res


# ---------------------------------------------------------------- 全球
def fetch_global():
    ids = ",".join(x[0] for x in config.GLOBAL)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f12,f14" % ids)
    out = {}
    for d in _diff(_get(url)):
        out[d.get("f12")] = {"name": d.get("f14"),
                             "close": _num(d.get("f2")),
                             "pct": _num(d.get("f3"))}
    # 东方财富不提供，显式置 None
    out["BRENT"] = None
    out["US10Y"] = None
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 触发判定
def _nearest(ladder, px):
    """未触发时，返回现价<b>下方最近的一档</b>及还需下跌多少。

    注意：下行触发阶梯里，最先跌破的是价格最高的档位，
    因此这里必须取「低于现价的档位中最大的一个」(max)，
    取 min 会跳到最低档，导致提示的距离虚高、方向显示为负数。
    """
    below = [lv for lv in ladder if px > lv]
    if not below:
        return None, None
    lv = max(below)
    return lv, px - lv


def _low_pct(v):
    """盘中最低价相对昨收的涨跌幅（%）。"""
    lo, prev = v.get("low"), v.get("prev")
    if lo is None or not prev:
        return None
    return round((lo - prev) / prev * 100, 2)


def _intraday_hits(ladder, low):
    """盘中最低价击穿的档位（从高到低）。同花顺预警是盘中实时触发的，
    只用收盘价判定会漏掉 V 型反转日里盘中已跌穿、收盘又拉回来的档位。"""
    if low is None:
        return []
    return [lv for lv in sorted(ladder, reverse=True) if low <= lv]


def evaluate_triggers(portfolio):
    """下行触发判定，两套口径同时输出：

    - 收盘口径(trigger)：收盘价是否已跌破档位
    - 盘中口径(intraday_hits)：盘中最低价是否击穿过档位（= 同花顺预警口径）
    """
    rows = []
    for code, ladder in config.ADD_LADDER.items():
        v = portfolio.get(code) or {}
        px, name = v.get("close"), v.get("name", code)
        if px is None:
            rows.append({"code": code, "name": name, "trigger": None,
                         "intraday_hits": [],
                         "note": "行情未获取，无法判定"})
            continue
        hit = next((lv for lv in sorted(ladder, reverse=True) if px <= lv), None)
        ih = _intraday_hits(ladder, v.get("low"))
        if hit:
            note = "已触发 %.3f" % hit
        else:
            lv, gap = _nearest(ladder, px)
            note = ("未触发，现价高于最近档位 %.3f，需再跌 %.3f 才触发" % (lv, gap)
                    if lv is not None else "未触发，现价已高于全部档位")
        if ih and not hit:
            note += "；但盘中最低 %.3f 已击穿 %s" % (
                v["low"], " / ".join("%.3f" % x for x in ih))
        elif ih and hit:
            extra = [x for x in ih if x != hit]
            if extra:
                note += "；盘中最低 %.3f 还击穿了 %s" % (
                    v["low"], " / ".join("%.3f" % x for x in extra))
            else:
                note += "（盘中最低 %.3f）" % v["low"]
        rows.append({"code": code, "name": name, "ladder": ladder,
                     "close": px, "low": v.get("low"),
                     "low_pct": _low_pct(v),
                     "trigger": hit, "intraday_hits": ih, "note": note})
    # 中国一重做T买点：需同时满足 价格<=2.81 且 跌幅>=3%
    yz = portfolio.get("601106") or {}
    px, pct = yz.get("close"), yz.get("pct")
    lo, lo_pct = yz.get("low"), _low_pct(yz)
    if px is None:
        t_ok, t_note = None, "行情未获取"
    else:
        price_ok = px <= config.T_BUY
        drop_ok = pct is not None and pct <= -3.0
        t_ok = price_ok and drop_ok
        pct_s = "%.2f%%" % pct if pct is not None else config.NA
        t_note = ("已触发（价格 %.2f ≤ %.2f，跌幅 %s）"
                  % (px, config.T_BUY, pct_s) if t_ok else
                  "未触发，价格 %.2f（需 ≤ %.2f，尚差 %.2f），跌幅 %s（需 ≤ -3%%）"
                  % (px, config.T_BUY, px - config.T_BUY, pct_s))
    # 盘中口径：最低价与最低价对应的跌幅同时满足才算盘中触发
    t_intra = bool(lo is not None and lo <= config.T_BUY
                    and lo_pct is not None and lo_pct <= -3.0)
    if t_intra and not t_ok:
        t_note += "；但盘中最低 %.2f（%.2f%%）已同时满足做T条件" % (lo, lo_pct)
    elif t_intra:
        t_note += "（盘中最低 %.2f，%.2f%%）" % (lo, lo_pct)
    rows.append({"code": "601106", "name": "中国一重（做T买点）",
                 "ladder": [config.T_BUY], "close": px, "low": lo,
                 "low_pct": lo_pct,
                 "trigger": config.T_BUY if t_ok else None,
                 "intraday_hits": [config.T_BUY] if t_intra else [],
                 "note": t_note})
    for code, ladder in config.WATCH_LADDER.items():
        v = portfolio.get(code) or {}
        px, name = v.get("close"), v.get("name", code)
        hit = next((lv for lv in sorted(ladder, reverse=True)
                    if px is not None and px <= lv), None)
        ih = _intraday_hits(ladder, v.get("low"))
        if px is None:
            note = "行情未获取"
        elif hit:
            note = "已触发 %.3f" % hit
        else:
            lv, gap = _nearest(ladder, px)
            note = ("未触发，现价高于最近档位 %.3f，需再跌 %.3f 才触发" % (lv, gap)
                    if lv is not None else "未触发，现价已高于全部档位")
        if ih and not hit:
            note += "；但盘中最低 %.3f 已击穿 %s" % (
                v["low"], " / ".join("%.3f" % x for x in ih))
        elif ih and hit:
            extra = [x for x in ih if x != hit]
            if extra:
                note += "；盘中最低 %.3f 还击穿了 %s" % (
                    v["low"], " / ".join("%.3f" % x for x in extra))
            else:
                note += "（盘中最低 %.3f）" % v["low"]
        rows.append({"code": code, "name": name, "ladder": ladder,
                     "close": px, "low": v.get("low"),
                     "low_pct": _low_pct(v),
                     "trigger": hit, "intraday_hits": ih, "note": note})
    return rows


# ---------------------------------------------------------------- 主流程
def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "data"
    os.makedirs(outdir, exist_ok=True)

    print("[1/6] 判定交易日 ...")
    trade_date, quote_time = trading_day()
    today = datetime.now(CST).date().isoformat()
    print("      行情日期=%s  当前=%s  %s"
          % (trade_date, today,
             "交易日" if trade_date == today else "非交易日(将生成休市说明)"))

    print("[2/6] 指数 ...")
    idx = fetch_indexes()
    pa = fetch_prev_amount(trade_date)
    for code, amt in pa.items():
        if code in idx:
            idx[code]["prev_amount"] = amt
    if pa:
        print("      上一交易日成交额已回填：%s"
              % ", ".join("%s=%.0f亿" % (k, v / 1e8) for k, v in pa.items()))
    print("[3/6] 持仓与监控ETF ...")
    pf, watch = fetch_portfolio()
    print("[4/6] 资金面与涨跌停 ...")
    flow = fetch_fund_flow()
    limits = fetch_limit_pool(trade_date)
    print("[5/6] 全球宏观 ...")
    glb = fetch_global()
    print("[6/6] 触发判定 ...")
    trig = evaluate_triggers(pf)

    up = sum(1 for r in trig if r.get("trigger"))
    iup = sum(1 for r in trig if r.get("intraday_hits"))
    data = {
        "trade_date": trade_date,
        "quote_time": quote_time,
        "generated_at": datetime.now(CST).isoformat(),
        "is_trading_day": (trade_date == today),
        "indexes": idx, "portfolio": pf, "watch_etfs": watch,
        "fund_flow": flow, "limit_pool": limits, "global": glb,
        "triggers": trig, "triggered_count": up, "trigger_total": len(trig),
        "intraday_triggered_count": iup,
    }
    path = os.path.join(outdir, "market.json")
    # 东财对本机是间歇性掐连接，一次失败的全量运行会把上一轮已经抓到的
    # 好数据整个覆盖掉（指数清空、持仓全 null）。这里做一次完整度仲裁：
    # 新数据比磁盘上已有的更差就不落盘，保住最后一次可用快照。
    score = len(idx) + len([v for v in pf.values() if v.get("close")]) \
        + (2 if trade_date else 0)
    best, old = -1, None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
            opf = old.get("portfolio") or {}
            best = len(old.get("indexes") or {}) \
                + len([v for v in opf.values() if v.get("close")]) \
                + (2 if old.get("trade_date") else 0)
        except Exception:
            old, best = None, -1
    if score < best:
        print("\n!! 新抓取完整度 %d < 磁盘已有 %d，保留旧快照不覆盖"
              % (score, best))
        print("!! 旧快照行情日期=%s 指数=%d 持仓=%d"
              % (old.get("trade_date"), len(old.get("indexes") or {}),
                 len([v for v in (old.get("portfolio") or {}).values()
                      if v.get("close")])))
        print("完成(沿用旧快照) -> %s" % path)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n完成 -> %s  (触发 %d/%d, 完整度 %d)"
          % (path, up, len(trig), score))


if __name__ == "__main__":
    main()