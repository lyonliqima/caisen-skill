#!/usr/bin/env python3
"""
# ⚠️ pattern_score 是形态强度分（52-80），**不是**研判置信度。
# 禁止把本字段直接填入 predictions-ledger 的 confidence，也禁止用它映射仓位。
蔡森破底翻量化筛选器 v8 — 收盘价口径 · 全市场宽口径

============================================================
蔡森「破底翻」定义（收盘价口径，来源：蔡森形态学 pattern-algorithms.md 形态5）
============================================================
- 破底：某根 K 线【收盘价】跌破前低支撑（×0.97，幅度通常 2~3%）。
- 翻回：之后某根 K 线【收盘价】重新站上前低之上。
- 铁律：盘中最低价跌破但收盘站回前低 = 不算破（主力洗盘），支撑仍有效。
        → 故本脚本全程以【收盘价】为判定基准，盘中影线不单独构成破底。
- 3日站稳：连续 3 日收盘价 ≥ 前低 → 翻回确认，可靠性大幅提升。
- 止损锚定「前低」（第一条颈线），绝不锚定破底最低点。

网上通说（pchome 理财周刊 / ThinkMarkets / 和讯）：
「破了底，如果再翻回来，就代表有人在照顾，所以叫破底翻」——
破底翻是一个【买点】：股价先跌破支撑引发恐慌，随后快速收回到支撑之上，
代表空方力竭、多方接手，是底部反转信号（胜率随大盘多空而变，约 50%~80%）。

============================================================
本脚本两种入选类型（满足其一即入选）
============================================================
A. 破底翻（经典）：60日窗口内存在前低支撑 → 之后【收盘价】曾跌破（破底）
        → 当前【收盘价】已站回前低之上（翻回）→ 破底后未再创更低收盘。
B. 守住前低（用户口径）：存在前低支撑且盘中曾测试（最低价触及前低）→
        全程【收盘价】从未有效跌破前低（收盘价没破前低）→
        且已连续 ≥ --hold-days 天收盘站在前低之上（几天稳定在前低上面）。
    ※ 两类都不要求「今日大涨」，故默认全市场宽口径扫描。

数据源（按优先级自动降级）：东方财富 push2his > 新浪 > 腾讯财经。
"""
import os
import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime
import concurrent.futures
import time
import random
import argparse

# ============================================================
# 运行参数（可用命令行覆盖）
# ============================================================
MAX_WORKERS = 8                  # 并发线程数（默认8；全量扫描建议 3）
REQUEST_DELAY = (0.05, 0.10)    # 每只股票随机延时区间(秒)，避免被代理限流
USE_EASTMONEY = True             # 是否启用东方财富(首选)；沙箱不可达时用 --no-eastmoney 跳过

# ---- 破底翻判定参数（可在 main() 用命令行覆盖）----
BOTTOM_PCT = 30      # 历史分位上限%：只保留过去1年收盘价处于底部 BOTTOM_PCT% 的股票
BOTTOM_DROP = 40     # 距年高跌幅下限%：必须距1年高点深跌超此值才算「底部区域」
HOLD_DAYS = 3       # 「守住前低」最少连续站稳天数（几天稳定在前低上面）
BT = 0.03           # 破底/守住容忍度（小数，=3%）；收盘价跌破前低×(1-BT) 才算破

H = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Referer': 'https://finance.sina.com.cn/'}

# ============================================================
# 1. 新浪列表API：分页获取股票池
# ============================================================
def get_risers():
    """旧快模式：只取今日上涨股（涨幅降序，遇到 ≤0 即停）。"""
    url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    risers = []
    for page in range(1, 70):
        params = {'page': str(page), 'num': '100', 'sort': 'changepercent',
                  'asc': '0', 'node': 'hs_a', 'symbol': '', '_s_r_a': 'sort'}
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=H, timeout=15)
                data = json.loads(r.text)
                break
            except:
                time.sleep(1.5 * (attempt + 1)); data = None
        if not data: continue

        stop = False
        for item in data:
            chg = float(item.get('changepercent', 0))
            if chg <= 0: stop = True; break
            name = item['name']; code = item['code']  # 纯数字代码如'300522'
            if any(x in name for x in ['ST', '退', 'N ']): continue
            # 只保留沪深主板/创业板/科创板，过滤北交所
            if not (code.startswith(('60', '00', '30', '68'))): continue
            full_code = 'sh' + code if code.startswith('6') else 'sz' + code
            risers.append({'code': full_code, 'name': name, 'change': chg})
        if stop: break
        time.sleep(0.3)
        if page % 10 == 0: print(f'  已拉取{page}页，{len(risers)}只...')
    return risers

def get_all_stocks():
    """宽口径模式（默认）：拉取全市场 A 股列表（按代码排序分页，不做涨幅过滤）。"""
    url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    stocks = []
    for page in range(1, 80):
        params = {'page': str(page), 'num': '100', 'sort': 'symbol', 'asc': '1',
                  'node': 'hs_a', 'symbol': '', '_s_r_a': 'sort'}
        ok = False; data = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=H, timeout=15)
                data = json.loads(r.text); ok = True; break
            except:
                time.sleep(1.0 * (attempt + 1)); data = None
        if not ok or not data: break
        for item in data:
            name = item.get('name', ''); code = item.get('code', '')
            if any(x in name for x in ['ST', '退', 'N ']): continue
            if not (code.startswith(('60', '00', '30', '68'))): continue
            full_code = 'sh' + code if code.startswith('6') else 'sz' + code
            try: chg = float(item.get('changepercent', 0))
            except: chg = 0.0
            stocks.append({'code': full_code, 'name': name, 'change': chg})
        if len(data) < 100: break
        time.sleep(0.3)
        if page % 10 == 0: print(f'  已拉取{page}页，{len(stocks)}只...')
    return stocks

# ============================================================
# 2. K线API（东方财富首选 + 新浪 + 腾讯 三级 fallback）
# ============================================================
def _secid_of(code):
    return ('1.' + code[2:]) if code.startswith('sh') else ('0.' + code[2:])

def get_kline_eastmoney(code):
    secid = _secid_of(code)
    hosts = [
        'https://push2his.eastmoney.com/api/qt/stock/kline/get',
        'https://push2.eastmoney.com/api/qt/stock/kline/get',
    ]
    params = {'secid': secid, 'fields1': 'f1,f2,f3',
              'fields2': 'f51,f52,f53,f54,f55,f56',
              'klt': '101', 'fqt': '1', 'lmt': '250', 'end': '20500101'}
    h_em = {**H, 'Referer': 'https://quote.eastmoney.com/'}
    for host in hosts:
        try:
            r = requests.get(host, params=params, headers=h_em, timeout=8)
            j = r.json()
            kls = (j.get('data') or {}).get('klines')
            if not kls:
                continue
            out = []
            for s in kls:
                p = s.split(',')
                if len(p) < 6:
                    continue
                try:
                    out.append({'date': p[0], 'open': float(p[1]), 'close': float(p[2]),
                                'high': float(p[3]), 'low': float(p[4]), 'volume': float(p[5])})
                except (ValueError, TypeError):
                    continue
            if len(out) >= 40:
                return out
        except Exception:
            continue
    return None

def get_kline_sina(code):
    url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
    params = {'symbol': code, 'scale': '240', 'ma': 'no', 'datalen': '250'}
    r = requests.get(url, params=params, headers=H, timeout=8)
    data = json.loads(r.text)
    if not data or len(data) < 40: return None
    return data

def get_kline_tencent(code):
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    r = requests.get(url, params={'param': f'{code},day,,,250,qfq'}, headers=H, timeout=8)
    j = r.json()
    node = (j.get('data') or {}).get(code)
    if not node: return None
    arr = node.get('qfqday') or node.get('day')
    if not arr: return None
    out = []
    for row in arr:
        if len(row) < 6: continue
        try:
            out.append({'date': row[0], 'open': float(row[1]), 'close': float(row[2]),
                        'high': float(row[3]), 'low': float(row[4]), 'volume': float(row[5])})
        except (ValueError, TypeError):
            continue
    return out if len(out) >= 40 else None

def get_kline(code):
    sources = (get_kline_eastmoney, get_kline_sina, get_kline_tencent) if USE_EASTMONEY \
              else (get_kline_sina, get_kline_tencent)
    for fn in sources:
        for attempt in range(2):
            try:
                d = fn(code)
                if d: return d
            except Exception:
                time.sleep(0.4 * (attempt + 1))
    return None

# ============================================================
# 3. 蔡森破底翻量化检测（v8 · 收盘价口径 · 两类入选）
# ============================================================
def detect_podifan(kdata, code, name, change_pct):
    if not kdata or len(kdata) < 40: return None

    n = len(kdata)
    close = np.array([float(d['close']) for d in kdata])
    high = np.array([float(d['high']) for d in kdata])
    low = np.array([float(d['low']) for d in kdata])
    volume = np.array([float(d['volume']) for d in kdata])
    tc = close[-1]

    # === 60日窗口用于破底翻检测 ===
    window = min(60, n); start = n - window
    ph60 = np.max(high[start:])
    pr60 = tc / ph60 if ph60 > 0 else 1
    if pr60 > 0.85: return None  # 60日高位过滤

    # === 长期历史低位过滤（底部区域，破底翻才有意义）===
    long_high = np.max(high); long_low = np.min(low)
    drop_from_year_high = (1 - tc / long_high) * 100 if long_high > 0 else 0
    close_sorted = np.sort(close)
    rank = np.searchsorted(close_sorted, tc)
    percentile = rank / n * 100
    if percentile > BOTTOM_PCT: return None
    if drop_from_year_high < BOTTOM_DROP: return None

    # === 局部极值（寻找前低支撑）===
    # 蔡森要点：前低 = 破底发生「前」的局部最低价，不能把破底新低误当支撑。
    # 故用「左侧 lk 根都更高 + 紧邻右侧1根更高」判定（破底可能在之后数根才发生，
    # 右侧不必全更高），避免破底K线把前低挤出局部极小值。
    lk = 5; local_lows = []
    for i in range(start + lk, n):
        if not all(low[i] <= low[i - j] for j in range(1, lk + 1)):
            continue
        if i + 1 < n and low[i] > low[i + 1]:
            continue
        local_lows.append((i, low[i]))
    if not local_lows: return None

    cands = [(idx, val) for idx, val in local_lows if idx < n - 2]  # 给「站稳」判断留空间
    if not cands: return None

    thr = 1 - BT  # 收盘价守住/破底阈值
    best = None; best_conf = 0

    for sidx, sprice in cands:
        if (n - 1) <= sidx:
            continue
        seg_close = close[sidx + 1:]
        seg_low = low[sidx + 1:]
        min_close_after = np.min(seg_close)
        min_low_after = np.min(seg_low)

        # 测试过支撑？盘中最低价曾触及/接近前低（否则「没破」是 trivial 的）
        if min_low_after > sprice * (1 + BT):
            continue

        # —— 收盘价口径判定（蔡森铁律：盘中破但收盘站回 = 不算破）——
        broke = min_close_after < sprice * thr          # 收盘价曾跌破前低 = 破底
        close_held = min_close_after >= sprice * thr   # 收盘价从未有效跌破
        recovered = tc >= sprice * thr                 # 当前收盘已站回前低
        if not recovered:
            continue

        # 几天稳定在前低上面：自前低之后（含今日）连续收盘 ≥ 前低 的天数
        hold_days = 0
        for i in range(n - 1, sidx, -1):
            if close[i] >= sprice * thr:
                hold_days += 1
            else:
                break

        if broke:
            # —— 类型A：经典破底翻（收盘破底 → 收盘翻回）——
            bl = min_close_after                         # 破底最低收盘
            bd = (sprice - bl) / sprice * 100
            bi = sidx + 1 + int(np.argmin(seg_close))  # 破底最低收盘所在索引
            # 破底后未再创更低收盘（止损锚定前低，不锚定破底最低）
            if bi < n - 1:
                if np.min(close[bi + 1:]) < bl * 0.98:
                    continue
            is_podi = True
        else:
            # —— 类型B：守住前低（收盘全程未破 + 稳定 ≥ HOLD_DAYS 天）——
            if not (close_held and hold_days >= HOLD_DAYS):
                continue
            bl = sprice; bd = 0.0
            is_podi = False

        # —— 指标与评分 ——
        rc = (tc - sprice) / sprice * 100            # 收回/站上幅度
        dh = (1 - pr60) * 100                         # 距60日高跌幅
        vt = volume[-1]
        va5 = np.mean(volume[-6:-1]) if n >= 6 else np.mean(volume)
        vr = vt / va5 if va5 > 0 else 0
        ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:])
        ma20 = np.mean(close[-20:]) if n >= 20 else np.mean(close)

        if is_podi:
            conf = 60
            if vr > 1.5: conf += 4
            if vr > 2.0: conf += 2
            if bd > 5: conf += 3
            if rc > 3: conf += 3
            if pr60 < 0.60: conf += 3
            if percentile < 10: conf += 3
            elif percentile < 20: conf += 1
            if tc > ma5 > ma10: conf += 2
            if hold_days >= 3: conf += 3          # 3日站稳加分
            if hold_days >= 5: conf += 2
            typ = '破底翻'
        else:
            # 守住前低型：以站稳天数定基础分（1天≈52，3天≈56，5天≈60…）
            conf = 50 + min(hold_days, 8) * 2
            if vr > 1.5: conf += 3
            if percentile < 10: conf += 3
            elif percentile < 20: conf += 1
            if tc > ma5 > ma10: conf += 2
            if pr60 < 0.60: conf += 2
            typ = '守住前低'

        conf = min(conf, 80)

        if conf > best_conf:
            best_conf = conf
            best = {
                '代码': code, '名称': name, '类型': typ,
                '最新价': round(tc, 2), '今日涨幅%': round(change_pct, 2),
                '前低支撑': round(sprice, 2),
                '破底最低': round(bl, 2) if is_podi else None,
                '破底深度%': round(bd, 1) if is_podi else None,
                '收回幅度%': round(rc, 1),
                '站稳天数': hold_days,
                '距60日高跌幅%': round(dh, 1), '距年高跌幅%': round(drop_from_year_high, 1),
                '历史分位%': round(percentile, 1),
                '量比vs5日均': round(vr, 2),
                'MA5': round(ma5, 2), 'MA20': round(ma20, 2), 'pattern_score': conf,
            }
    return best

def scan_one(args):
    code, name, chg = args
    try:
        time.sleep(random.uniform(*REQUEST_DELAY))
        kdata = get_kline(code)
        return detect_podifan(kdata, code, name, chg)
    except:
        return None

# ============================================================
def _fmt(cell, kind='f'):
    if cell is None: return '-'
    if kind == 'f': return f'{cell:.2f}'
    if kind == 'p': return f'{cell:+.1f}%'
    if kind == 'd': return f'{cell:.0f}'
    if kind == 'x': return f'{cell:.1f}x'
    return str(cell)

def main():
    global MAX_WORKERS, REQUEST_DELAY, USE_EASTMONEY
    global BOTTOM_PCT, BOTTOM_DROP, HOLD_DAYS, BT
    ap = argparse.ArgumentParser(description='蔡森破底翻量化筛选器 v8')
    ap.add_argument('--workers', type=int, default=MAX_WORKERS, help='并发线程数（全量扫描建议3）')
    ap.add_argument('--delay', type=float, default=REQUEST_DELAY[1], help='每只股票最大随机延时(秒)')
    ap.add_argument('--no-eastmoney', action='store_true', help='跳过东方财富(沙箱不可达时加速)')
    ap.add_argument('--all', action='store_true', help='全市场宽口径扫描（默认；不要求今日大涨）')
    ap.add_argument('--risers', action='store_true', help='仅扫描今日上涨股（旧快模式）')
    ap.add_argument('--bottom-pct', type=float, default=BOTTOM_PCT, help='历史分位上限%%(默认30)')
    ap.add_argument('--bottom-drop', type=float, default=BOTTOM_DROP, help='距年高跌幅下限%%(默认40)')
    ap.add_argument('--hold-days', type=int, default=HOLD_DAYS, help='守住前低最少站稳天数(默认3)')
    ap.add_argument('--bt', type=float, default=BT * 100, help='破底/守住容忍度%%(默认3)')
    args = ap.parse_args()

    MAX_WORKERS = args.workers
    REQUEST_DELAY = (0.0, args.delay)
    USE_EASTMONEY = not args.no_eastmoney
    BOTTOM_PCT = args.bottom_pct
    BOTTOM_DROP = args.bottom_drop
    HOLD_DAYS = args.hold_days
    BT = args.bt / 100.0

    mode_all = args.all or (not args.risers)   # 默认宽口径
    print('=' * 70)
    print('  蔡森破底翻量化筛选器 v8 — 收盘价口径 · 全市场宽口径')
    print(f'  过滤：历史分位<{BOTTOM_PCT:.0f}% + 距年高跌>{BOTTOM_DROP:.0f}%')
    print(f'  入选：破底翻(收盘破→翻回) 或 守住前低(收盘未破+站稳≥{HOLD_DAYS}天)')
    print(f'  运行模式: 线程={MAX_WORKERS}  延时≤{args.delay}s  东方财富={"开" if USE_EASTMONEY else "关"}'
          f'  口径={"全市场" if mode_all else "仅上涨股"}')
    print('=' * 70)

    print('\n[1/3] 拉取股票池...')
    t0 = time.time()
    if mode_all:
        stocks_raw = get_all_stocks()
        print(f'  全市场: {len(stocks_raw)}只 ({time.time()-t0:.1f}s)')
    else:
        stocks_raw = get_risers()
        stocks_raw = [r for r in stocks_raw if r['change'] >= 0.5]
        print(f'  涨幅≥0.5%: {len(stocks_raw)}只 ({time.time()-t0:.1f}s)')

    stocks = [(r['code'], r['name'], r['change']) for r in stocks_raw]

    print(f'\n[2/3] 扫描{len(stocks)}只 ({MAX_WORKERS}线程)...')
    results = []; done = 0; fails = 0; t1 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(scan_one, s): s for s in stocks}
        for f in concurrent.futures.as_completed(futs):
            done += 1
            r = f.result()
            if r: results.append(r)
            else: fails += 1
            if done % 200 == 0:
                el = time.time() - t1
                eta = (len(stocks) - done) / (done / el) if done else 0
                print(f'  {done}/{len(stocks)}  候选:{len(results)}  '
                      f'失败:{fails}  {done/el:.1f}/s  ETA:{eta:.0f}s')

    total = time.time() - t1
    print(f'\n  完成! {total:.0f}s  候选:{len(results)}  失败:{fails}')

    if not results:
        print('  ❌ 无候选'); return

    df = pd.DataFrame(results).sort_values('pattern_score', ascending=False)
    today_str = datetime.now().strftime('%Y%m%d')
    _root = os.environ.get('CAISEN_ROOT') or os.path.dirname(os.path.abspath(__file__))
    out_csv = os.path.join(_root, f'破底翻候选_{today_str}.csv')
    df.to_csv(out_csv, index=False, encoding='utf-8-sig')

    def pt(sub, title):
        print(f'\n  {title}: {len(sub)}只')
        if len(sub) == 0: return
        print("  代码          名称      类型     价格     今涨   年高跌  分位  前低     站稳 破底   收回    量比  conf")
        print("  " + "-" * 100)
        for _, r in sub.iterrows():
            print("  {code:12} {name:10} {typ:8} {price:8} {chg:6} {yhd:6}% {pct:4}% "
                  "{sup:7} {hold:4} {bd:5} {rc:6} {vr:5} {cf:3d}".format(
                      code=r['代码'], name=r['名称'], typ=r['类型'],
                      price=_fmt(r['最新价']), chg=_fmt(r['今日涨幅%'], 'p'),
                      yhd=_fmt(r['距年高跌幅%'], 'f'), pct=_fmt(r['历史分位%'], 'f'),
                      sup=_fmt(r['前低支撑']), hold=_fmt(r['站稳天数'], 'd'),
                      bd=_fmt(r['破底深度%'], 'f'), rc=_fmt(r['收回幅度%'], 'p'),
                      vr=_fmt(r['量比vs5日均'], 'x'), cf=int(r['pattern_score'])))

    print(f"\n{'='*108}")
    print(f"  📊 破底翻候选 ({len(results)}只 / {len(stocks)}只, 成功率{len(results)/(len(stocks)-fails)*100:.1f}%)")
    print(f"{'='*108}")
    pt(df[df['pattern_score'] >= 70], '⭐⭐⭐ 极高(≥70)')
    pt(df[(df['pattern_score'] >= 67) & (df['pattern_score'] < 70)], '⭐⭐ 高(67-69)')
    pt(df[(df['pattern_score'] >= 63) & (df['pattern_score'] < 67)], '⭐ 中(63-66)')
    pt(df[df['pattern_score'] < 63], '○ 低(<63)')

    # 按类型拆分统计
    n_podi = (df['类型'] == '破底翻').sum()
    n_hold = (df['类型'] == '守住前低').sum()
    print(f"\n{'='*108}")
    print(f"  📈 统计: 扫描{len(stocks)} | K线失败{fails} | 候选{len(results)} "
          f"(破底翻{n_podi} / 守住前低{n_hold}) | 耗时{total:.0f}s")
    print(f"  平均距年高跌:{df['距年高跌幅%'].mean():.1f}%  "
          f"平均历史分位:{df['历史分位%'].mean():.1f}%  "
          f"平均站稳:{df['站稳天数'].mean():.1f}天")
    print(f"  CSV: {out_csv}")

if __name__ == '__main__':
    main()
