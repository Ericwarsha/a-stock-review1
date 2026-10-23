# -*- coding: utf-8 -*-
"""
A股每日复盘 —— 历史日K补数（用于补跑漏掉的交易日）。

与 fetch_market.py 的区别：
  fetch_market.py       抓「实时」快照，只能在收盘后当天跑（15:30）。
  fetch_market_daily.py 抓「日K」，可回补任意历史交易日。

产出 market.json 的 schema 与 fetch_market.py 完全一致，可直接喂给 generate_report.py。

数据诚实原则沿用：接口给不出的一律写 null，由报告层渲染成「数据暂未获取」。

用法：
  python fetch_market_daily.py 2026-10-22 [输出目录]
  python fetch_market_daily.py --auto [输出目录]   # 自动取「今天之前的最近交易日」
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import config
from fetch_market import _get, _num, _diff, evaluate_triggers, fetch_limit_pool

CST = timezone(timedelta(hours=8))

# 东方财富对单主机限流很紧，逐日回补要打上千个请求。
# 1./2./3./4. 前缀是独立主机，轮转使用可把压力摊开，显著降低被拒率。
BHOSTS = ["1.push2his.eastmoney.com", "2.push2his.eastmoney.com",
          "3.push2his.eastmoney.com", "4.push2his.eastmoney.com",
          "push2his.eastmoney.com"]
_bctr = 0
_blk = threading.Lock()
_PREFIX = re.compile(r"^https://push2his\.eastmoney\.com/")


def _rotate(url):
    """把 push2his 主域名换成轮转主机，其余原样返回。"""
    global _bctr
    if not _PREFIX.match(url):
        return url
    with _blk:
        h = BHOSTS[_bctr % len(BHOSTS)]
        _bctr += 1
    return "https://" + h + "/" + url.split("/", 3)[3]


def _get2(url, retries=5, timeout=25):
    """带主机轮转的 GET JSON。底层调用 fetch_market._get（不可自调用）。"""
    return _get(_rotate(url), retries=retries, timeout=timeout)

# 日K字段：日期,开,收,高,低,量,额,振幅,涨跌幅,涨跌额,换手率
K_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
# 资金流日K：取全字段以便校验「小+中+大+超 = 0」
FF_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59"


def kline(secid, end, lmt=8):
    """返回 {日期: {开,收,高,低,量,额,振幅,涨跌幅,涨跌额,换手率}}。"""
    js = _get2("https://push2his.eastmoney.com/api/qt/stock/kline/get"
              "?secid=%s&klt=101&fqt=0&end=%s&lmt=%d"
              "&fields1=f1,f2,f3&fields2=%s" % (secid, end.replace("-", ""), lmt, K_FIELDS))
    out = {}
    if not js or not isinstance(js.get("data"), dict):
        return out
    for row in js["data"].get("klines") or []:
        c = row.split(",")
        if len(c) < 11:
            continue
        out[c[0]] = {
            "open": _num(c[1]), "close": _num(c[2]), "high": _num(c[3]),
            "low": _num(c[4]), "volume": _num(c[5]), "amount": _num(c[6]),
            "amplitude": _num(c[7]), "pct": _num(c[8]), "chg": _num(c[9]),
            "turnover": _num(c[10]),
        }
    return out


def last_session_before(end_date, n=6):
    """取 end_date 之前（含）最后一个已有K线的交易日。"""
    ks = kline("1.000001", end_date, lmt=n)
    return max(ks) if ks else None


# ---------------------------------------------------------------- 指数
def fetch_indexes(date):
    out = {}
    for secid, name in config.INDEXES:
        ks = kline(secid, date)
        k = ks.get(date)
        code = secid.split(".")[1]
        if not k:
            out[code] = {"name": name, "close": None, "pct": None,
                         "chg": None, "amount": None, "prev_amount": None,
                         # 历史涨跌家数：东方财富免费接口不提供回溯值，如实置 null
                         "up": None, "down": None, "flat": None}
            continue
        prev_key = max((x for x in ks if x < date), default=None)
        out[code] = {
            "name": name, "close": k["close"], "pct": k["pct"],
            "chg": k["chg"], "amount": k["amount"],
            "prev_amount": (ks.get(prev_key) or {}).get("amount"),
            # 历史涨跌家数：东方财富免费接口不提供回溯值，如实置 null
            "up": None, "down": None, "flat": None,
        }
    return out


# ---------------------------------------------------------------- 持仓
def fetch_portfolio(date):
    ids = [config.secid(c) for c, *_ in config.PORTFOLIO]
    ids += [config.secid(c) for c, _ in config.WATCH_ETFS]
    raw = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for code, secid in zip([c for c, *_ in config.PORTFOLIO]
                               + [c for c, _ in config.WATCH_ETFS], ids):
            raw[code] = kline(secid, date).get(date)
    out = {}
    for code, name, cost, shares, kind in config.PORTFOLIO:
        k = raw.get(code) or {}
        px = k.get("close")
        pnl = round((px - cost) / cost * 100, 2) if (px is not None and cost) else None
        out[code] = {"name": name, "cost": cost, "shares": shares, "kind": kind,
                     "close": px, "pct": k.get("pct"), "chg": k.get("chg"),
                     "amount": k.get("amount"), "pnl_pct": pnl,
                     "mv": round(px * shares, 2) if (px and shares) else None}
    watch = {}
    for code, name in config.WATCH_ETFS:
        k = raw.get(code) or {}
        watch[code] = {"name": name, "close": k.get("close"), "pct": k.get("pct")}
    return out, watch


# ---------------------------------------------------------------- 资金流
def board_list(page=100, max_pages=12):
    """分页拉全部行业板块。

    接口单页上限 100 条，直接 pz=600 会被截断，
    导致排名只在部分板块里做，漏掉电子/电力设备这类一级行业。
    """
    out, pn, total = [], 1, None
    while pn <= max_pages:
        js = _get2("https://push2his.eastmoney.com/api/qt/clist/get?fid=f62&np=1"
                   "&po=1&pz=%d&pn=%d&fltt=2&invt=2&fs=m:90+t:2"
                   "&fields=f12,f14" % (page, pn))
        diff = _diff(js)
        if not diff:
            break
        out.extend([(d.get("f12"), d.get("f14")) for d in diff if d.get("f12")])
        if total is None and isinstance(js.get("data"), dict):
            total = js["data"].get("total")
        if total is not None and len(out) >= total:
            break
        if len(diff) < page:
            break
        pn += 1
        time.sleep(0.2)
    seen, uniq = set(), []                       # 去重
    for c, n in out:
        if c not in seen:
            seen.add(c)
            uniq.append((c, n))
    return uniq


def board_flow_net(item, date):
    """单板块主力净流入（亿元）。只发 1 个请求，失败返回 None 待补。"""
    code, name = item
    ff = _get2("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
              "?lmt=6&klt=101&secid=90.%s&fields1=f1,f2,f3,f7&fields2=%s"
              % (code, FF_FIELDS))
    if not ff or not isinstance(ff.get("data"), dict):
        return None
    for row in ff["data"].get("klines") or []:
        c = row.split(",")
        if c[0] == date and len(c) >= 2:
            v = _num(c[1])
            if v is not None:
                return {"name": name, "code": code,
                        "net_yi": round(v / 1e8, 2), "pct": None}
    return None


def board_pct(item, date):
    """单板块当日涨跌幅。只对最终入选的 top/bottom 板块调用。"""
    code, name = item
    k = kline("90." + code, date, lmt=3).get(date)
    if not k:
        return None
    return {"pct": k.get("pct")}


def _run(items, fn, workers):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def fetch_fund_flow(date, rounds=3, workers=5, cache_dir="data"):
    """两阶段抓取：
       1) 先只取全部板块的主力净流入（1 请求/板块，低并发多轮重试补漏）
       2) 排名后只对入选的 10 个板块补涨跌幅（10 请求）
    这样把总请求数控制在 ~510，且避免为拿涨跌幅把所有板块再打一遍。

    接口限流很硬，单次跑很难拿满 496 个板块，因此每轮成功的结果都落盘缓存，
    多次运行可累积收敛，不必每次从零开始。
    """
    boards_l = board_list()
    if not boards_l:
        return {"in_top": [], "out_top": [], "boards": {}, "universe": 0,
                "coverage": "板块列表获取失败"}

    os.makedirs(cache_dir, exist_ok=True)
    cpath = os.path.join(cache_dir, "_ff_cache_%s.json" % date)
    got = {}
    if os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as f:
                got = {k: v for k, v in json.load(f).items() if v}
            print("      命中本地缓存 %d 个板块" % len(got))
        except Exception:
            got = {}

    def save():
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False)

    missing = [b for b in boards_l if b[0] not in got]
    for rd in range(rounds):
        if not missing:
            break
        print("      第 %d 轮：待补 %d 个板块" % (rd + 1, len(missing)))
        res = _run(missing, lambda b: board_flow_net(b, date), workers)
        nxt = []
        for item, r in zip(missing, res):
            if r:
                got[item[0]] = r
            else:
                nxt.append(item)
        missing = nxt
        save()
        if missing:
            time.sleep(2.0 * (rd + 1))

    have = sorted(got.values(), key=lambda r: r["net_yi"], reverse=True)
    picked = [(x["code"], x["name"]) for x in (have[:5] + list(reversed(have[-5:])))]
    pcts = _run(picked, lambda b: board_pct(b, date), 4)
    pmap = {b[0]: r["pct"] for b, r in zip(picked, pcts) if r}
    for x in have:
        x["pct"] = pmap.get(x["code"])

    total = len(boards_l)
    if missing:
        cov = "部分覆盖 %d/%d，%d 个板块多次重试仍失败" % (len(have), total, len(missing))
    else:
        cov = "全覆盖 %d/%d" % (len(have), total)
    print("      覆盖：%s" % cov)
    return {"in_top": have[:5],
            "out_top": list(reversed(have[-5:])),
            "boards": {r["name"]: r for r in have},
            "universe": len(have),
            "board_total": total,
            "coverage": cov}


# ---------------------------------------------------------------- 全球
# key 必须与 generate_report.g_() 的取法一致（DJIA/SPX/...），
# 否则报告层按代码取不到，会整片显示「数据暂未获取」。
GLOBAL_KEY = {
    "100.DJIA": "DJIA", "100.SPX": "SPX", "100.NDX": "NDX",
    "100.UDI": "UDI", "133.USDCNH": "USDCNH",
    "101.GC00Y": "GC00Y", "101.SI00Y": "SI00Y", "102.CL00Y": "CL00Y",
}


def fetch_global(date):
    """美股取前一美东交易日收盘（A股15:30出报告时能看到的最新美股收盘）。"""
    prev = datetime.fromisoformat(date).date() - timedelta(days=1)
    while prev.weekday() >= 5:                      # 跳过周末
        prev -= timedelta(days=1)
    us_date = prev.isoformat()
    pairs = list(zip([x[0] for x in config.GLOBAL],
                     [x[1] for x in config.GLOBAL]))
    out = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda p: kline(p[0], us_date, lmt=6).get(us_date), pairs))
    for (secid, name), k in zip(pairs, res):
        key = GLOBAL_KEY.get(secid, name)
        out[key] = {"name": name,
                    "close": (k or {}).get("close"),
                    "pct": (k or {}).get("pct")}
    out["BRENT"] = None
    out["US10Y"] = None
    out["_us_session"] = us_date
    return out


# ---------------------------------------------------------------- 主流程
def patch_flow_only(date, outdir):
    """复用已有 market_<date>.json，只重跑资金流与触发判定。

    指数/持仓/海外这些都已经抓对了，没必要为补资金流再被打一轮限流。
    """
    path = os.path.join(outdir, "market_%s.json" % date)
    if not os.path.exists(path):
        raise SystemExit("找不到 %s，无法做增量补丁" % path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    print("[A] 修补缺失指数（限流打空的条目重抓）...")
    fixed = 0
    for secid, name in config.INDEXES:
        code = secid.split(".")[1]
        cur = (data.get("indexes") or {}).get(code) or {}
        if cur.get("close") is not None:
            continue
        ks = kline(secid, date, lmt=8)
        k = ks.get(date)
        if not k:
            print("      [WARN] %s 仍取不到，保留为空" % name)
            continue
        prev_key = max((x for x in ks if x < date), default=None)
        data["indexes"][code] = {
            "name": name, "close": k["close"], "pct": k["pct"], "chg": k["chg"],
            "amount": k["amount"],
            "prev_amount": (ks.get(prev_key) or {}).get("amount"),
            "up": None, "down": None, "flat": None,
        }
        fixed += 1
        print("      补齐 %s close=%.2f pct=%+.2f%%"
              % (name, k["close"], k["pct"]))
        time.sleep(1.5)

    print("[B] 重抓行业资金流 ...")
    data["fund_flow"] = fetch_fund_flow(date)

    print("[C] 修补海外宏观（限流打空或 key 错位的条目重抓）...")
    g = data.get("global") or {}
    need_g = not any((g.get(k) or {}).get("close") is not None
                     for k in GLOBAL_KEY.values())
    if need_g:
        data["global"] = fetch_global(date)
        gg = data["global"]
        for k in ("DJIA", "SPX", "NDX", "UDI", "USDCNH", "GC00Y", "SI00Y", "CL00Y"):
            v = gg.get(k) or {}
            if v.get("close") is not None:
                print("      %-8s %12.2f  %s"
                      % (k, v["close"],
                         ("%+.2f%%" % v["pct"]) if v.get("pct") is not None else "—"))
            else:
                print("      [WARN] %s 仍取不到，保留为空" % k)
    else:
        print("      已有数据，跳过")

    print("[D] 重算触发判定（本地计算，不发请求）...")
    trig = evaluate_triggers(data["portfolio"])
    data["triggers"] = trig
    data["triggered_count"] = sum(1 for r in trig if r.get("trigger"))
    data["trigger_total"] = len(trig)
    data["generated_at"] = datetime.now(CST).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n已更新 -> %s  (触发 %d/%d)"
          % (path, data["triggered_count"], data["trigger_total"]))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    outdir = args[1] if len(args) > 1 else "data"
    if "--auto" in sys.argv:
        today = datetime.now(CST).date()
        date = last_session_before(today.isoformat())
        if date == today.isoformat():               # 今天已收盘则也算
            pass
        print("[auto] 目标交易日 = %s" % date)
    else:
        date = args[0]

    if "--flow-only" in sys.argv:
        time.sleep(3)
        patch_flow_only(date, outdir)
        return

    os.makedirs(outdir, exist_ok=True)

    print("[0/6] 接口预热（避开刚跑完大批量请求后的限流窗口）...")
    time.sleep(6)

    print("[1/6] 校验交易日 %s ..." % date)
    sh = kline("1.000001", date).get(date)
    if not sh:
        raise SystemExit("%s 不是交易日或数据不可用，终止（不生成任何报告）" % date)
    print("      上证收盘 %.2f  涨跌 %+.2f%%" % (sh["close"], sh["pct"]))

    print("[2/6] 指数 ...")
    idx = fetch_indexes(date)
    print("[3/6] 持仓与监控ETF ...")
    pf, watch = fetch_portfolio(date)
    print("[4/6] 行业资金流（逐板块日K，低并发多轮重试）...")
    flow = fetch_fund_flow(date)
    limits = fetch_limit_pool(date)
    print("[5/6] 全球宏观（美股取前一美东交易日）...")
    glb = fetch_global(date)
    print("      美股口径日 = %s" % glb.get("_us_session"))
    print("[6/6] 触发判定 ...")
    trig = evaluate_triggers(pf)

    hit = sum(1 for r in trig if r.get("trigger"))
    data = {
        "trade_date": date,
        "quote_time": date + " 15:00",
        "generated_at": datetime.now(CST).isoformat(),
        "is_trading_day": True,
        "source": "historical-daily-kline",
        "indexes": idx, "portfolio": pf, "watch_etfs": watch,
        "fund_flow": flow, "limit_pool": limits, "global": glb,
        "triggers": trig, "triggered_count": hit, "trigger_total": len(trig),
    }
    path = os.path.join(outdir, "market_%s.json" % date)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n完成 -> %s  (触发 %d/%d)" % (path, hit, len(trig)))


if __name__ == "__main__":
    main()