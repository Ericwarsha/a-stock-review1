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
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

import config

CST = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _get(url, retries=3, timeout=20):
    """GET JSON，失败返回 None（绝不抛错到上层）。"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if i == retries - 1:
                print("  [FAIL] %s -> %s" % (url[:90], e))
                return None
            time.sleep(1.2 * (i + 1))
    return None


def _diff(js):
    if not js or not isinstance(js.get("data"), dict):
        return []
    return js["data"].get("diff") or []


# ---------------------------------------------------------------- 交易日
def trading_day():
    """用上证指数最新行情时间戳判断今日是否交易日。"""
    js = _get("https://push2.eastmoney.com/api/qt/stock/get"
              "?secid=1.000001&fields=f43,f86")
    ts = None
    if js and isinstance(js.get("data"), dict):
        ts = js["data"].get("f86")
    if not ts:
        return None, None
    quote_dt = datetime.fromtimestamp(ts, CST)
    today = datetime.now(CST).date()
    return quote_dt.date().isoformat(), quote_dt.isoformat()


# ---------------------------------------------------------------- 指数
def fetch_indexes():
    ids = ",".join(x[0] for x in config.INDEXES)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f104,f105,f106" % ids)
    out = {}
    for d in _diff(_get(url)):
        code, name = d.get("f12"), d.get("f14")
        out[code] = {
            "name": name,
            "close": _num(d.get("f2")),
            "pct": _num(d.get("f3")),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),   # 成交额(元)
            "up": d.get("f104"),
            "down": d.get("f105"),
            "flat": d.get("f106"),
        }
    return out


# ---------------------------------------------------------------- 持仓
def fetch_portfolio():
    ids = ",".join(config.secid(c) for c, *_ in config.PORTFOLIO)
    ids += "," + ",".join(config.secid(c) for c, _ in config.WATCH_ETFS)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14" % ids)
    raw = {}
    for d in _diff(_get(url)):
        raw[d.get("f12")] = {
            "close": _num(d.get("f2")),
            "pct": _num(d.get("f3")),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),
        }
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
                     "pnl_pct": pnl,
                     "mv": round(px * shares, 2) if (px and shares) else None}
    watch = {}
    for code, name in config.WATCH_ETFS:
        q = raw.get(code, {})
        watch[code] = {"name": name, "close": q.get("close"),
                       "pct": q.get("pct")}
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
def _nearest(ladder, px, fmt="%.3f"):
    """未触发时，返回现价上方最近的一档及其距离。"""
    above = [lv for lv in ladder if px > lv]
    if not above:
        return None, None
    lv = min(above)
    return lv, lv - px


def evaluate_triggers(portfolio):
    """下行触发判定：价格 <= 档位 且 当日跌幅 <= 0。"""
    rows = []
    for code, ladder in config.ADD_LADDER.items():
        px = (portfolio.get(code) or {}).get("close")
        name = (portfolio.get(code) or {}).get("name", code)
        if px is None:
            rows.append({"code": code, "name": name, "trigger": None,
                         "note": "行情未获取，无法判定"})
            continue
        hit = next((lv for lv in sorted(ladder, reverse=True) if px <= lv), None)
        if hit:
            note = "已触发 %.3f" % hit
        else:
            lv, gap = _nearest(ladder, px)
            note = "未触发，距最近档位 %.3f 还差 %.3f" % (lv, gap)
        rows.append({"code": code, "name": name, "ladder": ladder,
                     "close": px, "trigger": hit, "note": note})
    # 中国一重做T买点：需同时满足 价格<=2.81 且 跌幅>=3%
    yz = portfolio.get("601106") or {}
    px, pct = yz.get("close"), yz.get("pct")
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
    rows.append({"code": "601106", "name": "中国一重（做T买点）",
                 "ladder": [config.T_BUY], "close": px,
                 "trigger": config.T_BUY if t_ok else None, "note": t_note})
    for code, ladder in config.WATCH_LADDER.items():
        px = (portfolio.get(code) or {}).get("close")
        name = (portfolio.get(code) or {}).get("name", code)
        hit = next((lv for lv in sorted(ladder, reverse=True)
                    if px is not None and px <= lv), None)
        if px is None:
            note = "行情未获取"
        elif hit:
            note = "已触发 %.3f" % hit
        else:
            lv, gap = _nearest(ladder, px)
            note = "未触发，距最近档位 %.3f 还差 %.3f" % (lv, gap)
        rows.append({"code": code, "name": name, "ladder": ladder,
                     "close": px, "trigger": hit, "note": note})
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
    data = {
        "trade_date": trade_date,
        "quote_time": quote_time,
        "generated_at": datetime.now(CST).isoformat(),
        "is_trading_day": (trade_date == today),
        "indexes": idx, "portfolio": pf, "watch_etfs": watch,
        "fund_flow": flow, "limit_pool": limits, "global": glb,
        "triggers": trig, "triggered_count": up, "trigger_total": len(trig),
    }
    path = os.path.join(outdir, "market.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n完成 -> %s  (触发 %d/%d)" % (path, up, len(trig)))


if __name__ == "__main__":
    main()