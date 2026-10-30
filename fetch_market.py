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
import csv
import io
import json
import os
import random
import re
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
    """最高/最低必须满足 high >= close >= low，且都是正数，否则视为无效（宁缺勿错）。

    0 尤其要当缺失处理：开盘集合竞价前行情源给的是 最高=最低=0，
    直接用会让"盘中最低 0.00"击穿所有下行档位，造成假盘中触发。
    """
    if close is None:
        return None, None
    h, l = _px(high), _px(low)
    if h is None or l is None:
        return None, None
    if h >= close >= l:
        return h, l
    return None, None


def _pct_of(close, pct, prev):
    """涨跌幅：盘前行情源给的 0 是"今日还没开盘"，不是真涨跌幅。

    盘前行情源给的是 上一交易日收盘(现价) + 上上交易日收盘(昨收)，
    所以 (现价-昨收)/昨收 正好还原出上一交易日的真实涨跌幅；
    收盘后平盘时这个式子同样得 0，不会误伤。
    """
    if pct not in (None, 0, 0.0):
        return pct
    if close and prev:
        return round((close - prev) / prev * 100, 2)
    return pct


def fetch_indexes():
    ids = [x[0] for x in config.INDEXES]
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f104,f105,f106"
           % ",".join(ids))
    out = {}
    for d in _diff(_get(url)):
        code, name = d.get("f12"), d.get("f14")
        close, prev = _px(d.get("f2")), _num(d.get("f18"))
        hi, lo = _ohlc(close, _num(d.get("f15")), _num(d.get("f16")))
        out[code] = {
            "name": name,
            "close": close,
            "pct": _pct_of(close, _num(d.get("f3")), prev),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),   # 成交额(元)
            "high": hi, "low": lo,
            "prev": prev,
            "up": d.get("f104"),
            "down": d.get("f105"),
            "flat": d.get("f106"),
        }
    # 东财缺位的用腾讯补（涨跌家数腾讯不提供，保留 None）
    # 注意：盘前东财可能返回 f2=0（还没有价格），这种情况也要算"缺位"，
    # 否则会拿 0 当收盘价，全局涨跌幅也会跟着失真。
    miss = [s for s in ids
            if not ((out.get(s.split(".")[1]) or {}).get("close"))]
    if miss:
        print("  [补源] 指数缺 %d 个，走腾讯" % len(miss))
        for code, row in _tx(miss).items():
            close, prev = _px(row["close"]), row["prev"]
            hi, lo = _ohlc(close, row["high"], row["low"])
            out[code] = {"name": row["name"], "close": close,
                         "pct": _pct_of(close, row["pct"], prev),
                         "chg": row["chg"],
                         "amount": row["amount"],
                         "high": hi, "low": lo,
                         "prev": prev,
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
        close, prev = _px(d.get("f2")), _num(d.get("f18"))
        hi, lo = _ohlc(close, _num(d.get("f15")), _num(d.get("f16")))
        raw[d.get("f12")] = {
            "close": close,
            "pct": _pct_of(close, _num(d.get("f3")), prev),
            "chg": _num(d.get("f4")),
            "amount": _num(d.get("f6")),
            "high": hi, "low": lo, "prev": prev,
        }
    # 东财缺位的用腾讯补齐，持仓价格是报告核心，绝不能留空。
    # 盘前东财返回 f2=0 也算缺位 —— 0 会造成假触发，必须让腾讯来补真价。
    miss = [s for s in ids
            if not ((raw.get(s.split(".")[1]) or {}).get("close"))]
    if miss:
        print("  [补源] 持仓缺 %d 个，走腾讯" % len(miss))
        for code, row in _tx(miss).items():
            close, prev = _px(row["close"]), row["prev"]
            hi, lo = _ohlc(close, row["high"], row["low"])
            raw[code] = {"close": close,
                         "pct": _pct_of(close, row["pct"], prev),
                         "chg": row["chg"], "amount": row["amount"],
                         "high": hi, "low": lo,
                         "prev": prev}
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
    """板块资金流。

    返回结构：
      in_top / out_top —— 主力净流入前5 / 净流出前5（板块级）
      boards          —— 全量板块字典 {板块名: {name,code,net_yi,pct}}，
                        供第七章（有色推论验证）、第八章（风险预警）、
                        第十章（低估板块信号检查）按名取用。

    ⚠️ 历史脚本 fetch_market_daily.py 会产出 boards，但实时抓取层原先**从不产出**，
       导致第七/八/十章的「板块资金流」永远判为缺失 —— 这是真 bug，不是数据源问题。
    """
    base = ("https://push2.eastmoney.com/api/qt/clist/get?fid=f62&np=1"
            "&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f62,f3")

    def rows(po, n):
        out = []
        for d in _diff(_get("%s&po=%d&pz=%d&pn=1" % (base, po, n))):
            # f62 可能拿到 "-" —— 东财对无数据板块的占位符，必须先转数字再算。
            # 2026-10-30 云端 runner 真实踩到：v 是 str，v / 1e8 直接 TypeError，
            # 整轮抓取崩掉 → market.json 没产出 → 站点被推成错误页。
            v = _num(d.get("f62"))
            if v is None:
                continue
            out.append({"name": d.get("f14"), "code": d.get("f12"),
                        "net_yi": round(v / 1e8, 2), "pct": _num(d.get("f3"))})
        return out

    in_top = rows(1, 5)
    out_top = rows(0, 5)

    # ---- 全量板块字典：一次拉全量（分页上限100，逐页取）----
    # 本机代理会掐 push2 clist，第一页就失败时直接放弃，不再翻页刷屏；
    # 云端 runner 不受该限制，能拿到完整板块字典。
    boards = {}
    for pn in range(1, 8):
        js = _get("%s&po=1&pz=100&pn=%d" % (base, pn))
        diff = _diff(js)
        if not diff:
            break
        for d in diff:
            nm = d.get("f14")
            v = _num(d.get("f62"))       # 同上："-" 占位符必须先转数字再算
            if not nm or v is None:
                continue
            boards[nm] = {"name": nm, "code": d.get("f12"),
                          "net_yi": round(v / 1e8, 2), "pct": _num(d.get("f3"))}
        total = (js.get("data") or {}).get("total") if isinstance(js.get("data"), dict) else None
        if total and len(boards) >= total:
            break

    return {"in_top": in_top, "out_top": out_top, "boards": boards,
            "universe": len(boards)}


def fetch_sina_sectors():
    """新浪行业/概念板块涨跌幅（第十章「有色板块涨跌 / 小金属概念涨跌」等行）。

    数据源（2026-10-28 本机实测可用，GBK）：
      https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php  行业板块 49 个
      https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php   概念/证监会行业 84 个
    文件格式： var X = {"code":"k1,k2,..."}，
      字段 1=名称 2=家数 3=平均价 4=涨跌额 5=涨跌幅% 6=成交量 7=成交额

    只取 config.SINA_SECTORS 里列出的板块；取不到不猜，缺项由报告层标注。
    """
    out = {}
    for url, kind in (
        ("https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php", "行业"),
        ("https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php", "概念"),
    ):
        txt = _get_text(url, SINA_HDR)
        if not txt:
            continue
        m = re.search(r"=\s*(\{.*\})", txt, re.S)
        if not m:
            continue
        for mm in re.finditer(r'"([a-zA-Z0-9_]+)"\s*:\s*"([^"]*)"', m.group(1)):
            p = mm.group(2).split(",")
            if len(p) < 6:
                continue
            name, pct = p[1], _num(p[5])
            if name is None or pct is None:
                continue
            out[name] = {"code": mm.group(1), "name": name, "pct": pct,
                         "chg": _num(p[4]), "n": _num(p[2]),
                         "avg": _num(p[3]), "kind": kind,
                         "src": "新浪财经板块行情"}
    # 按 config 清单裁剪，只保留报告需要的板块
    sel = {}
    for name, label, kind in config.SINA_SECTORS:
        hit = out.get(name)
        if hit:
            sel[label] = hit
    return sel


def _kline_amounts(secid):
    """日K线里的成交额（元）。东财日K的标准字段序必须整段请求才稳定：

        fields2=f51..f61 → 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
        成交额在 index 6（不是 index 2）

    只请求 f51,f53,f57 这种非标准子集会取不到值，所以这里用完整字段序，
    再用量级校验（两市单日成交额在百亿~万亿量级）防止把收盘价当成成交额。
    f51..f57 这个 7 字段变体的列序一致，成交额同样落在 index 6，作备用。
    """
    variants = [
        "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "f51,f52,f53,f54,f55,f56,f57",
    ]
    for fields2 in variants:
        js = _get("https://push2his.eastmoney.com/api/qt/stock/kline/get"
                  "?secid=%s&klt=101&fqt=0&end=20500101&lmt=3"
                  "&fields1=f1,f2,f3,f4,f5,f6&fields2=%s" % (secid, fields2))
        if not (js and isinstance(js.get("data"), dict)):
            continue
        out = []
        for k in (js["data"].get("klines") or []):
            p = k.split(",")
            if len(p) < 7:
                continue
            try:
                amt = float(p[6])
            except ValueError:
                continue
            if not (1e10 < amt < 1e13):      # 量级不对就不是成交额，丢弃
                continue
            out.append((p[0], amt))
        if out:
            return out
    return []


def fetch_prev_amount(trade_date):
    """上一交易日两市成交额（分指数，单位元）。

    「放量反弹」还是「缩量反弹」的分水岭就在这个数上 —— 报告里必须有它，
    不能留「较前日：数据暂未获取」。日K线末根=当日，前一根=上一交易日。
    """
    out = {}
    for secid, code in (("1.000001", "000001"), ("0.399001", "399001")):
        rows = _kline_amounts(secid)
        if len(rows) < 2:
            continue
        last_date, _ = rows[-1]
        if trade_date and last_date.replace("-", "") != trade_date.replace("-", ""):
            continue
        out[code] = rows[-2][1]
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
    """全球宏观：东财主源 + 新浪/腾讯/美财政部备用源，逐项补空。

    键名与旧版保持一致（DJIA/SPX/NDX/UDI/USDCNH/GC00Y/SI00Y/CL00Y），
    新增 BRENT / US10Y / US30Y / US5Y / US2Y / USDCNY / USDJPY / SPOT_XAU。
    补源顺序：东财 → 新浪 → 腾讯 → 美财政部；谁先拿到用谁，其余只补空位。
    """
    ids = ",".join(x[0] for x in config.GLOBAL)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f12,f14" % ids)
    out = {}
    for d in _diff(_get(url)):
        out[d.get("f12")] = {"name": d.get("f14"), "close": _num(d.get("f2")),
                             "pct": _num(d.get("f3")), "chg": _num(d.get("f4")),
                             "src": "东方财富"}

    def fill(new):
        for k, v in new.items():
            if not v:
                continue
            old = out.get(k)
            if not old or old.get("close") is None:
                out[k] = v

    fill(fetch_sina_hf())       # Brent / WTI / 黄金 / 白银 / 现货金
    fill(fetch_tx_hf())         # 外盘合约腾讯兜底
    fill(fetch_sina_fx())       # 美元指数 / 离岸在岸人民币 / USDJPY
    fill(fetch_tx_us_index())   # 美股三大指数腾讯兜底
    for k, v in fetch_us_treasury().items():   # 美债收益率（东财/新浪都不提供）
        if k in ("US10Y", "US30Y", "US5Y", "US2Y"):
            out[k] = v
    for k in ("BRENT", "US10Y", "US30Y", "US5Y", "US2Y",
              "USDCNY", "USDJPY", "SPOT_XAU"):
        out.setdefault(k, None)
    return out


# ------------------------------------------------ 文本类数据源（新浪 / 腾讯）
SINA_HDR = {"Referer": "https://finance.sina.com.cn/"}
TX_HDR = {"Referer": "https://gu.qq.com/"}


def _get_text(url, headers=None, enc="gbk", retries=3, timeout=15):
    """抓纯文本。新浪/腾讯返回的是 GB2312/GBK 的 var hq_str_xxx="..." 文本。

    超时/重试刻意压得比东财那套小：GitHub Actions 整个任务只有 15 分钟，
    新数据源有 5~6 个，每个都按 20s×4 来的话，光兜底就能吃掉整个时间窗。
    """
    hdr = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdr.update(headers)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(enc, "replace")
        except Exception as e:
            if i == retries - 1:
                print("  [FAIL] %s -> %s" % (url[:90], e))
            time.sleep(1.0 + i)
    return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_vars(txt, sep=","):
    """解析 var hq_str_xxx="..." / v_xxx="..." 文本。

    sep 要跟源对上：新浪 hf_* 与腾讯 hf_* 用逗号，腾讯美股用 ~。
    """
    out = {}
    for line in (txt or "").split("\n"):
        if "=" not in line:
            continue
        var, _, body = line.partition("=")
        key = var.strip()
        if key.startswith("var hq_str_"):
            key = key[len("var hq_str_"):]
        elif key.startswith("v_"):
            key = key[2:]
        else:
            continue
        body = body.strip().strip(";").strip('"')
        out[key] = body.split(sep)
    return out


def _parse_sina_vars(txt):
    return _parse_vars(txt, ",")


def fetch_sina_hf():
    """新浪 hf_* 外盘合约：Brent / WTI / COMEX黄金 / COMEX白银 / 伦敦现货金。

    字段序（2026-10-27 实测）：
      0=现价 1=空 2=买 3=卖 4=最高 5=最低 6=时间 7=昨收 8=开盘 12=日期 13=名称
    涨跌幅由 (现价-昨收)/昨收 自算 —— 与东财同名品种逐项比对，误差 <0.01pct。
    """
    codes = [c for c, _k, _n in config.SINA_HF]
    txt = _get_text("https://hq.sinajs.cn/list=" + ",".join(codes), SINA_HDR)
    raw = _parse_sina_vars(txt)
    out = {}
    for code, key, name in config.SINA_HF:
        p = raw.get(code)
        if not p or len(p) < 9:
            continue
        close, prev = _f(p[0]), _f(p[7])
        if close is None:
            continue
        out[key] = {
            "name": p[13] if len(p) > 13 and p[13] else name,
            "close": close, "prev": prev,
            "pct": round((close - prev) / prev * 100, 2) if prev else None,
            "high": _f(p[4]), "low": _f(p[5]),
            "time": p[6], "date": p[12] if len(p) > 12 else None,
            "src": "新浪财经 hf_*",
        }
    return out


def fetch_tx_hf():
    """腾讯 hf_* 外盘合约兜底。字段序与新浪不同：
      0=现价 1=涨跌幅 2=买 3=卖 4=最高 5=最低 6=时间 7=昨收 8=开盘 12=日期 13=名称
    （腾讯直接给涨跌幅，但仍用昨收校验一次，防止把卖价当现价。）
    """
    codes = [c for c, _k, _n in config.TX_HF]
    txt = _get_text("https://qt.gtimg.cn/q=" + ",".join(codes), TX_HDR)
    raw = _parse_sina_vars(txt)
    out = {}
    for code, key, name in config.TX_HF:
        p = raw.get(code)
        if not p or len(p) < 9:
            continue
        close, prev, pct = _f(p[0]), _f(p[7]), _f(p[1])
        if close is None or not prev:
            continue
        calc = round((close - prev) / prev * 100, 2)
        if pct is not None and abs(pct - calc) > 0.6:
            # 涨跌幅与昨收对不上 -> 字段序可能变了，宁缺勿错
            continue
        out[key] = {"name": p[13] if len(p) > 13 and p[13] else name,
                    "close": close, "prev": prev, "pct": calc,
                    "high": _f(p[4]), "low": _f(p[5]),
                    "time": p[6], "date": p[12] if len(p) > 12 else None,
                    "src": "腾讯财经 hf_*"}
    return out


def fetch_sina_fx():
    """新浪外汇 / 美元指数。

    字段序（2026-10-27 实测）：0=时间 1=现价 3=昨收 9=名称
    涨跌幅由 (现价-昨收)/昨收 自算：离岸人民币 -0.036%≈-0.04%、
    在岸人民币 -0.030%、美元指数 +0.2166%≈+0.22%，均与东财同刻读数一致。
    """
    codes = [c for c, _k, _n in config.SINA_FX]
    txt = _get_text("https://hq.sinajs.cn/list=" + ",".join(codes), SINA_HDR)
    raw = _parse_sina_vars(txt)
    out = {}
    for code, key, name in config.SINA_FX:
        p = raw.get(code)
        if not p or len(p) < 10:
            continue
        close, prev = _f(p[1]), _f(p[3])
        if close is None:
            continue
        out[key] = {"name": p[9] if p[9] else name, "close": close, "prev": prev,
                    "pct": round((close - prev) / prev * 100, 2) if prev else None,
                    "time": p[0], "src": "新浪财经"}
    return out


def fetch_tx_us_index():
    """腾讯美股三大指数。字段序（~ 分隔）：
      1=名称 3=最新 4=昨收 30=时间 31=涨跌额 32=涨跌幅 33=最高 34=最低
    """
    codes = [c for c, _k, _n in config.TX_US_INDEX]
    txt = _get_text("https://qt.gtimg.cn/q=" + ",".join(codes), TX_HDR)
    raw = _parse_vars(txt, "~")
    out = {}
    for code, key, name in config.TX_US_INDEX:
        p = raw.get(code)
        if not p or len(p) < 35:
            continue
        close, prev = _f(p[3]), _f(p[4])
        if close is None:
            continue
        pct = _f(p[32])
        calc = round((close - prev) / prev * 100, 2) if prev else None
        if pct is None:
            pct = calc
        elif calc is not None and abs(pct - calc) > 0.6:
            continue
        out[key] = {"name": p[1] if p[1] else name, "close": close, "prev": prev,
                    "pct": pct, "chg": _f(p[31]), "high": _f(p[33]),
                    "low": _f(p[34]), "time": p[30], "src": "腾讯财经"}
    return out


def _treasury_rows_csv(txt):
    """CSV -> [(iso, v10, v30, v5, v2), ...]，按日期倒序（第一行最新）。"""
    rows = list(csv.reader(io.StringIO(txt)))
    if len(rows) < 2:
        return []
    hdr = [h.strip() for h in rows[0]]

    def col(name):
        return hdr.index(name) if name in hdr else None

    idate, i10 = col("Date"), col("10 Yr")
    if idate is None or i10 is None:
        return []
    i30, i5, i2 = col("30 Yr"), col("5 Yr"), col("2 Yr")
    out = []
    for r in rows[1:]:
        if len(r) <= max(idate, i10):
            continue
        raw_date = (r[idate] or "").strip()
        if not raw_date:
            continue
        try:
            mm, dd, yyyy = raw_date.split("/")
            iso = "%s-%s-%s" % (yyyy, mm, dd)
            v10 = float(r[i10])
            v30 = float(r[i30]) if i30 is not None and r[i30] else None
            v5 = float(r[i5]) if i5 is not None and r[i5] else None
            v2 = float(r[i2]) if i2 is not None and r[i2] else None
        except (ValueError, IndexError):
            continue
        out.append((iso, v10, v30, v5, v2))
    return out


def _treasury_rows_xml(txt):
    """XML -> [(iso, v10, v30, v5, v2), ...]。CSV 通道抖动时的备用。"""
    pats = {
        "date": re.compile(r"<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>"),
        "10": re.compile(r"<d:BC_10YEAR[^>]*>([^<]+)</d:BC_10YEAR>"),
        "30": re.compile(r"<d:BC_30YEAR[^>]*>([^<]+)</d:BC_30YEAR>"),
        "5": re.compile(r"<d:BC_5YEAR[^>]*>([^<]+)</d:BC_5YEAR>"),
        "2": re.compile(r"<d:BC_2YEAR[^>]*>([^<]+)</d:BC_2YEAR>"),
    }
    out = []
    for blk in re.findall(r"<entry>(.*?)</entry>", txt, re.S):
        m = pats["date"].search(blk)
        m10 = pats["10"].search(blk)
        if not (m and m10):
            continue
        try:
            iso = m.group(1)[:10]
            v10 = float(m10.group(1))
            v30 = float(pats["30"].search(blk).group(1)) if pats["30"].search(blk) else None
            v5 = float(pats["5"].search(blk).group(1)) if pats["5"].search(blk) else None
            v2 = float(pats["2"].search(blk).group(1)) if pats["2"].search(blk) else None
        except (ValueError, AttributeError):
            continue
        out.append((iso, v10, v30, v5, v2))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def fetch_us_treasury():
    """美国财政部官方每日收益率曲线 —— 美10Y/美30Y 的唯一可靠源。

    东财不提供美债收益率；新浪 gb_$tnx 实测返回空串，不可用。
    CSV 与 XML 两个官方通道都试，谁先通用谁；两个都抖就留空，由报告层标注。
    """
    year = datetime.now(CST).year
    csv_url = ("https://home.treasury.gov/resource-center/data-chart-center/"
               "interest-rates/daily-treasury-rates.csv/%d/all"
               "?type=daily_treasury_yield_curve&field_tdr_date_value=%d"
               "&page&_format=csv" % (year, year))
    xml_url = ("https://home.treasury.gov/resource-center/data-chart-center/"
               "interest-rates/pages/xml?data=daily_treasury_yield_curve"
               "&field_tdr_date_value=%d" % year)
    hdr = {"Referer": "https://home.treasury.gov/"}

    series = []
    t = _get_text(csv_url, hdr, enc="utf-8", retries=3, timeout=25)
    if t and "10 Yr" in t:
        series = _treasury_rows_csv(t)
    if not series:
        print("      [补源] 美财政部 CSV 不可用，改走官方 XML 通道")
        t = _get_text(xml_url, hdr, enc="utf-8", retries=2, timeout=30)
        if t:
            series = _treasury_rows_xml(t)
    if not series:
        return {}
    series.sort(key=lambda x: x[0], reverse=True)

    out = {}
    iso, v10, v30, v5, v2 = series[0]
    src = "美国财政部官方收益率曲线"
    out["US10Y"] = {"name": "美10Y国债收益率", "close": v10, "prev": None,
                    "pct": None, "date": iso, "src": src}
    out["US30Y"] = {"name": "美30Y国债收益率", "close": v30, "prev": None,
                    "pct": None, "date": iso, "src": src}
    out["US5Y"] = {"name": "美5Y国债收益率", "close": v5, "prev": None,
                   "pct": None, "date": iso, "src": src}
    out["US2Y"] = {"name": "美2Y国债收益率", "close": v2, "prev": None,
                   "pct": None, "date": iso, "src": src}
    if len(series) > 1:
        _, p10, p30, p5, p2 = series[1]
        for k, pv in (("US10Y", p10), ("US30Y", p30), ("US5Y", p5), ("US2Y", p2)):
            v = out[k]
            v["prev"] = pv
            v["prev_date"] = series[1][0]
            if pv is not None and v.get("close") is not None:
                v["chg_bp"] = round((v["close"] - pv) * 100, 1)
    vals = [x[1] for x in series]
    below = [x for x in series if x[1] < config.GOLD_FACTOR_US10Y]
    out["US10Y"]["ytd_min"] = min(vals)
    out["US10Y"]["ytd_max"] = max(vals)
    out["US10Y"]["ytd_days"] = len(series)
    out["US10Y"]["days_below_thr"] = len(below)
    out["US10Y"]["last_below_date"] = below[0][0] if below else None
    out["US10Y"]["min_date"] = min(series, key=lambda x: x[1])[0]
    out["US10Y"]["max_date"] = max(series, key=lambda x: x[1])[0]
    return out


def fetch_proxy_etf():
    """第九章代理 ETF（军工ETF国泰 512660）当日表现。

    015790 是场外基金，没有盘中行情，只能用代理 ETF 观察该方向当日强弱。
    代理关系写在 config.AEROSPACE_FUND 里，这里只负责取价。
    """
    code = config.AEROSPACE_FUND.get("proxy_code")
    if not code:
        return None
    secid = config.secid(code)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f18" % secid)
    for d in _diff(_get(url)):
        if d.get("f12") == code:
            close, prev = _px(d.get("f2")), _num(d.get("f18"))
            if close:
                return {"name": d.get("f14"), "close": close,
                        "pct": _pct_of(close, _num(d.get("f3")), prev),
                        "chg": _num(d.get("f4")),
                        "amount": _num(d.get("f6")), "prev": prev,
                        "src": "东方财富"}
            break        # 盘前 f2=0（还没有价格）→ 转腾讯补真价
    row = _tx([secid]).get(code)
    if row:
        close, prev = _px(row["close"]), row["prev"]
        return {"name": row["name"], "close": close,
                "pct": _pct_of(close, row["pct"], prev),
                "chg": row["chg"], "amount": row["amount"], "prev": prev,
                "src": "腾讯财经"}
    return None


def fetch_broad_etfs():
    """第三章：国家队/汇金观察用宽基ETF真实行情。

    说明：汇金持仓明细与ETF份额变动属低频披露数据，免费接口确实不提供；
    但这 4 只宽基 ETF 是普通 ETF，收盘价/涨跌幅/成交额完全可以实时拿到，
    旧版脚本把整张表写死成"数据暂未获取"，属于可修缺口。
    """
    ids = [config.secid(c) for c, _ in config.BROAD_ETFS]
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=%s"
           "&fields=f2,f3,f4,f5,f6,f12,f14,f18" % ",".join(ids))
    raw = {}
    for d in _diff(_get(url)):
        close, prev = _px(d.get("f2")), _num(d.get("f18"))
        raw[d.get("f12")] = {"name": d.get("f14"), "close": close,
                             "pct": _pct_of(close, _num(d.get("f3")), prev),
                             "amount": _num(d.get("f6")),
                             "prev": prev}
    miss = [s for s in ids
            if not ((raw.get(s.split(".")[1]) or {}).get("close"))]
    if miss:
        print("  [补源] 宽基ETF缺 %d 个，走腾讯" % len(miss))
        for code, row in _tx(miss).items():
            raw[code] = {"name": row["name"], "close": _px(row["close"]),
                         "pct": _pct_of(_px(row["close"]), row["pct"],
                                        row["prev"]),
                         "amount": row["amount"],
                         "prev": row["prev"]}
    out = {}
    for code, name in config.BROAD_ETFS:
        v = raw.get(code) or {}
        out[code] = {"name": v.get("name") or name, "close": v.get("close"),
                     "pct": v.get("pct"), "amount": v.get("amount"),
                     "prev": v.get("prev")}
    return out


def fetch_news(trade_date):
    """消息面：东财 7x24 快讯 + 持仓个股公告。

    快讯只取 trade_date 当天的（休市日则回退到最近一天）；公告取最近 3 天，
    按时间倒序，均为真实接口返回，不做改写。
    """
    out = {"kuaixun": [], "ann": [], "kx_date": None}

    txt = _get_text("https://newsapi.eastmoney.com/kuaixun/v1/"
                    "getlist_102_ajaxResult_50_1_.html",
                    {"Referer": "https://kuaixun.eastmoney.com/"},
                    enc="utf-8", retries=3)
    if txt:
        m = re.search(r"var ajaxResult=(\{.*\})\s*;?\s*$", txt, re.S)
        if m:
            try:
                js = json.loads(m.group(1))
            except ValueError:
                js = {}
            items = []
            for it in (js.get("LivesList") or []):
                ts = it.get("showtime") or ""
                items.append({"time": ts, "date": ts[:10], "title": it.get("title"),
                              "url": it.get("url_w"), "column": it.get("column")})
            if items:
                out["kx_date"] = items[0]["date"]
                if trade_date:
                    same = [x for x in items if x["date"] == trade_date]
                    out["kuaixun"] = same or items[:10]
                else:
                    out["kuaixun"] = items[:12]

    codes = ",".join(c for c, *_ in config.PORTFOLIO)
    txt = _get_text("https://np-anotice-stock.eastmoney.com/api/security/ann"
                    "?page_size=50&page_index=1&ann_type=A&client_source=web"
                    "&stock_list=%s" % codes,
                    {"Referer": "https://data.eastmoney.com/"}, enc="utf-8", retries=3)
    if txt:
        try:
            js = json.loads(txt)
        except ValueError:
            js = {}
        rows = []
        for it in ((js.get("data") or {}).get("list") or []):
            names = [c.get("short_name") for c in (it.get("codes") or [])]
            cols = [c.get("column_name") for c in (it.get("columns") or [])]
            ts = it.get("display_time") or ""
            rows.append({"time": ts, "date": ts[:10],
                         "name": "、".join(n for n in names if n),
                         "title": it.get("title"),
                         "type": "、".join(c for c in cols if c),
                         "art": it.get("art_code")})
        if trade_date:
            base = datetime.fromisoformat(trade_date).date()
            keep = []
            for r in rows:
                try:
                    dt = datetime.fromisoformat(r["date"]).date()
                except ValueError:
                    continue
                if (base - dt).days <= 3:
                    keep.append(r)
            out["ann"] = keep
        else:
            out["ann"] = rows[:12]
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _px(v):
    """价格必须是正数，否则按缺失处理。

    盘前（开盘集合竞价前）东财对个股/ETF 返回 f2=0 —— 含义是"还没有价格"，
    不是"价格是 0"。直接当 0 用会同时毁掉两件事：
      · 触发判定：0 <= 任何下行档位 → 全部假触发（实测南山铝业 4.15 档假触发）
      · 浮盈亏：按 0 算成 -100%
    所以 0 必须当缺失，交给腾讯补源；补源也没有就如实报"行情未获取"。
    """
    n = _num(v)
    if n is None or n <= 0:
        return None
    return n


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
        drop_ok = pct is not None and pct <= config.T_BUY_MAX_DROP
        t_ok = price_ok and drop_ok
        pct_s = "%.2f%%" % pct if pct is not None else config.NA
        t_note = ("已触发（价格 %.2f ≤ %.2f，跌幅 %s）"
                  % (px, config.T_BUY, pct_s) if t_ok else
                  "未触发，价格 %.2f（需 ≤ %.2f，尚差 %.2f），跌幅 %s（需 ≤ %.0f%%）"
                  % (px, config.T_BUY, px - config.T_BUY, pct_s, config.T_BUY_MAX_DROP))
    # 盘中口径：最低价与最低价对应的跌幅同时满足才算盘中触发
    t_intra = bool(lo is not None and lo <= config.T_BUY
                    and lo_pct is not None and lo_pct <= config.T_BUY_MAX_DROP)
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
def _safe(label, fn, default, *args, **kw):
    """辅助数据块的降级护栏。

    辅助块（资金流/涨跌停/全球/宽基/代理/消息/板块）抓取失败时，
    只让这一块变成「数据暂未获取」，不能拖垮整轮 —— 核心块（指数/持仓）
    失败要抛错，因为没有它们报告本身就没意义；但辅助块缺失只是少一段结论。

    2026-10-30 云端 runner 实测教训：一次 f62 的类型问题就让整轮抓取崩掉，
    market.json 没产出，publish.py 只能把错误页推上 gh-pages，
    站点反而比跑崩之前更糟。
    """
    try:
        return fn(*args, **kw)
    except Exception as e:
        print("  [降级] %s 抓取失败 -> 该块置空：%s: %s"
              % (label, type(e).__name__, e))
        return default


def _trade_state(trade_date, today):
    """交易日状态措辞。

    trade_date < today 有两种完全不同的含义，不能都叫「非交易日」：
      · 盘前/未收盘 —— 今天明明是交易日，只是数据还没产生（手动在早上触发就是这种）
      · 真休市 —— 节假日/周末
    """
    if trade_date == today:
        return "交易日"
    now = datetime.now(CST)
    if trade_date and now.weekday() < 5 and now.hour < 15:
        # 工作日但 15:00 收盘前，行情源给的还是上一个交易日的收盘数据
        # （盘前东财个股甚至给 f2=0）。这是"今天还没出数据"，不是休市。
        return ("今日数据未出（取最近交易日 %s 的收盘数据）" % trade_date)
    return "非交易日(休市)"


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "data"
    os.makedirs(outdir, exist_ok=True)

    print("[1/8] 判定交易日 ...")
    trade_date, quote_time = trading_day()
    today = datetime.now(CST).date().isoformat()
    print("      行情日期=%s  当前=%s  %s"
          % (trade_date, today, _trade_state(trade_date, today)))
    print("[2/8] 指数 ...")
    idx = _safe("指数", fetch_indexes, {})
    pa = fetch_prev_amount(trade_date)
    for code, amt in pa.items():
        if code in idx:
            idx[code]["prev_amount"] = amt
    if pa:
        print("      上一交易日成交额已回填：%s"
              % ", ".join("%s=%.0f亿" % (k, v / 1e8) for k, v in pa.items()))
    print("[3/8] 持仓与监控ETF ...")
    pf, watch = _safe("持仓与监控ETF", fetch_portfolio, ({}, {}))
    print("[4/8] 资金面与涨跌停 ...")
    flow = _safe("板块资金流", fetch_fund_flow, {})
    limits = _safe("涨跌停家数", fetch_limit_pool,
                   {"zt": None, "dt": None}, trade_date)
    print("      板块资金流字典：%d 个板块" % len(flow.get("boards") or {}))
    sectors = _safe("新浪板块涨跌幅", fetch_sina_sectors, {})
    print("[5/8] 全球宏观（东财+新浪+腾讯+美财政部）...")
    glb = _safe("全球宏观", fetch_global, {})
    print("      已获取：%s"
          % ", ".join(sorted(k for k, v in glb.items() if v and v.get("close"))))
    print("[6/8] 宽基ETF（第三章 国家队/汇金观察）+ 第九章代理ETF ...")
    broad = _safe("宽基ETF", fetch_broad_etfs, {})
    print("      宽基ETF到位：%d / %d"
          % (len([v for v in broad.values() if v.get("close")]), len(broad)))
    proxy = _safe("第九章代理ETF", fetch_proxy_etf, None)
    print("      第九章代理ETF %s：%s"
          % (config.AEROSPACE_FUND.get("proxy_code"),
             ("%s %s" % (proxy.get("close"), proxy.get("pct"))) if proxy else "未获取"))
    print("[7/8] 消息面（7x24快讯 + 持仓公告）...")
    news = _safe("消息面", fetch_news,
                 {"kuaixun": [], "ann": [], "kx_date": None}, trade_date)
    print("      快讯 %d 条（日期 %s）｜ 持仓公告 %d 条"
          % (len(news["kuaixun"]), news.get("kx_date"), len(news["ann"])))
    print("      新浪板块涨跌幅：%d 个" % len(sectors))
    print("[8/8] 触发判定 ...")
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
        "broad_etfs": broad, "news": news, "proxy_etf": proxy,
        "sectors": sectors,
        "triggers": trig, "triggered_count": up, "trigger_total": len(trig),
        "intraday_triggered_count": iup,
    }
    path = os.path.join(outdir, "market.json")
    # 东财对本机是间歇性掐连接，一次失败的全量运行会把上一轮已经抓到的
    # 好数据整个覆盖掉（指数清空、持仓全 null）。这里做一次完整度仲裁：
    # 新数据比磁盘上已有的更差就不落盘，保住最后一次可用快照。
    #
    # 但「更新交易日」优先于「完整度」：只要新快照的行情日期比旧的更新，
    # 就必须用新的 —— 否则一次残缺的新一轮会把报告退回成昨天的日期，
    # 而日报错日期比缺几个字段严重得多。只有同一天内的重复运行才比完整度。
    score = len(idx) + len([v for v in pf.values() if v.get("close")]) \
        + (2 if trade_date else 0)
    # 全部数据源都失败时，宁可让 publish.py 推一个说清原因的错误页，
    # 也不要生成一份"看起来正常、实际全空"的报告 —— 后者更危险。
    if not trade_date or score <= 0:
        raise RuntimeError(
            "交易日无法判定或全部行情源失败（指数 %d 个 / 持仓有效 %d 只），"
            "拒绝生成空报告" % (len(idx),
                                len([v for v in pf.values() if v.get("close")])))
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
    old_date = (old or {}).get("trade_date")
    newer = bool(trade_date and old_date and trade_date > old_date)
    if newer:
        print("\n>> 新快照行情日期 %s 晚于磁盘已有 %s —— 按新日期落盘"
              "（完整度 %d vs %d）" % (trade_date, old_date, score, best))
    elif score < best:
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