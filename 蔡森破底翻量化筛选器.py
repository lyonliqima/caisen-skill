#!/usr/bin/env python3
"""
蔡森破底翻量化筛选器 v7 — 东方财富首选 + 新浪/腾讯 fallback
- 新浪列表API获取上涨股
- K线数据源（按优先级自动降级）：
    1) 东方财富 push2his（前复权日K，免key，首选）
    2) 新浪 K线API
    3) 腾讯财经 fqkline（并发抗造，最终兜底）
- 修复版算法：遍历所有局部低点，全程检查破底翻
"""
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
# 运行参数（可用命令行覆盖，便于「节流全量版」一键复跑）
# ============================================================
MAX_WORKERS = 8                  # 并发线程数（默认8；全量扫描建议 3）
REQUEST_DELAY = (0.05, 0.10)     # 每只股票随机延时区间(秒)，避免被代理限流
USE_EASTMONEY = True             # 是否启用东方财富(首选)；沙箱不可达时用 --no-eastmoney 跳过

H = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Referer': 'https://finance.sina.com.cn/'}

# ============================================================
# 1. 新浪列表API：分页获取上涨股
# ============================================================
def get_risers():
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
            # 加交易所前缀
            if code.startswith('6'):
                full_code = 'sh' + code
            else:
                full_code = 'sz' + code
            risers.append({'code': full_code, 'name': name, 'change': chg})
        if stop: break
        time.sleep(0.3)
        if page % 10 == 0: print(f'  已拉取{page}页，{len(risers)}只...')
    return risers

# ============================================================
# 2. K线API（东方财富首选 + 新浪 + 腾讯 三级 fallback）
#    数据源优先级：东方财富(push2his) > 新浪 > 腾讯财经
#    每个源失败自动降级，避免单一接口限流导致整轮失败。
#    三者均返回统一结构：list[dict(date,open,close,high,low,volume)]
# ============================================================
def _secid_of(code):
    # sh600519 -> 1.600519 ; sz300454 -> 0.300454
    return ('1.' + code[2:]) if code.startswith('sh') else ('0.' + code[2:])

def get_kline_eastmoney(code):
    # 东方财富前复权日K（免key）。字段：f51=日期 f52=开 f53=收 f54=高 f55=低 f56=量
    # 首选数据源；被限流/不可达时由调用方自动降级到新浪/腾讯。
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
    params = {'symbol': code, 'scale': '240', 'ma': 'no', 'datalen': '250'}  # 250日≈1年
    r = requests.get(url, params=params, headers=H, timeout=8)
    data = json.loads(r.text)
    if not data or len(data) < 40: return None
    return data  # list of dicts: close/high/low/volume

def get_kline_tencent(code):
    # 腾讯财经前复权日K，免key、并发抗造；返回 [日期,开,收,高,低,量]
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
    # 数据源优先级：东方财富(可关) -> 新浪 -> 腾讯；每个源失败重试1次
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
# 3. 蔡森破底翻量化检测（修复版）
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
    
    # === 长期历史低位过滤（核心新增）===
    # 用全部数据（最多250日≈1年）计算历史位置
    long_high = np.max(high)
    long_low = np.min(low)
    # 距1年高跌幅
    drop_from_year_high = (1 - tc / long_high) * 100 if long_high > 0 else 0
    # 历史分位：过去1年有多少天收盘价低于当前价
    close_sorted = np.sort(close)
    rank = np.searchsorted(close_sorted, tc)
    percentile = rank / n * 100  # 越低=越接近历史最低
    # 只保留历史分位<30%的（即当前价格在过去1年的底部30%区域）
    if percentile > 30: return None
    # 距1年高点必须跌超40%
    if drop_from_year_high < 40: return None
    
    # 局部极值 lookback=5
    lk = 5; local_lows = []
    for i in range(start + lk, n - lk):
        if all(low[i] <= low[i+j] for j in range(-lk, lk+1) if j != 0):
            local_lows.append((i, low[i]))
    if not local_lows: return None
    
    cands = [(idx, val) for idx, val in local_lows if idx < n - 5]
    if not cands: return None
    
    # 遍历所有支撑位
    bt = 0.03; best = None; best_conf = 0
    
    for sidx, sprice in cands:
        # 全程检查破底（从支撑形成后到今天）
        broke = False; bl = tc; bi = None
        for i in range(sidx + 1, n):
            if low[i] < sprice * (1 - bt):
                broke = True
                if low[i] < bl: bl = low[i]; bi = i
        if not broke: continue
        if tc < sprice: continue  # 未收回
        
        # 破底后不再创新低
        if bi and bi < n - 1:
            if min(low[bi+1:]) < bl * 0.98: continue
        
        bd = (sprice - bl) / sprice * 100
        rc = (tc - sprice) / sprice * 100
        dh = (1 - pr60) * 100  # 距60日高跌幅
        vt = volume[-1]
        va5 = np.mean(volume[-6:-1]) if n >= 6 else np.mean(volume)
        vr = vt / va5 if va5 > 0 else 0
        ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:])
        ma20 = np.mean(close[-20:]) if n >= 20 else np.mean(close)
        
        conf = 60
        if vr > 1.5: conf += 4
        if vr > 2.0: conf += 2
        if bd > 5: conf += 3
        if rc > 3: conf += 3
        if pr60 < 0.60: conf += 3
        if percentile < 10: conf += 3  # 极端低位加分
        elif percentile < 20: conf += 1  # 很低位加分
        if tc > ma5 > ma10: conf += 2
        conf = min(conf, 75)
        
        if conf > best_conf:
            best_conf = conf
            best = {
                '代码': code, '名称': name,
                '最新价': round(tc, 2), '今日涨幅%': round(change_pct, 2),
                '支撑价': round(sprice, 2), '破底最低': round(bl, 2),
                '破底深度%': round(bd, 1), '收回幅度%': round(rc, 1),
                '距60日高跌幅%': round(dh, 1), '距年高跌幅%': round(drop_from_year_high, 1),
                '历史分位%': round(percentile, 1),
                '量比vs5日均': round(vr, 2),
                'MA5': round(ma5, 2), 'MA20': round(ma20, 2), 'confidence': conf,
            }
    return best

def scan_one(args):
    code, name, chg = args
    try:
        time.sleep(random.uniform(*REQUEST_DELAY))
        kdata = get_kline(code)
        return detect_podifan(kdata, code, name, chg)
    except: return None

# ============================================================
def main():
    global MAX_WORKERS, REQUEST_DELAY, USE_EASTMONEY
    ap = argparse.ArgumentParser(description='蔡森破底翻量化筛选器')
    ap.add_argument('--workers', type=int, default=MAX_WORKERS, help='并发线程数（全量扫描建议3）')
    ap.add_argument('--delay', type=float, default=REQUEST_DELAY[1], help='每只股票最大随机延时(秒)')
    ap.add_argument('--no-eastmoney', action='store_true', help='跳过东方财富(沙箱不可达时加速)')
    args = ap.parse_args()
    MAX_WORKERS = args.workers
    REQUEST_DELAY = (0.0, args.delay)
    USE_EASTMONEY = not args.no_eastmoney

    print("=" * 70)
    print("  蔡森破底翻量化筛选器 v7 — 东方财富首选 + 破底翻 + 长期历史低位")
    print("  过滤：历史分位<30% + 距年高跌幅>40%")
    print(f"  运行模式: 线程={MAX_WORKERS}  延时≤{args.delay}s  东方财富={'开' if USE_EASTMONEY else '关(跳过)'}")
    print("=" * 70)
    
    print("\n[1/3] 拉取上涨股...")
    t0 = time.time()
    risers = get_risers()
    risers = [r for r in risers if r['change'] >= 0.5]
    print(f"  涨幅≥0.5%: {len(risers)}只 ({time.time()-t0:.1f}s)")
    
    stocks = [(r['code'], r['name'], r['change']) for r in risers]  # code已带sh/sz前缀
    
    print(f"\n[2/3] 扫描{len(stocks)}只 ({MAX_WORKERS}线程)...")
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
                eta = (len(stocks) - done) / (done / el)
                print(f"  {done}/{len(stocks)}  候选:{len(results)}  "
                      f"失败:{fails}  {done/el:.1f}/s  ETA:{eta:.0f}s")
    
    total = time.time() - t1
    print(f"\n  完成! {total:.0f}s  候选:{len(results)}  失败:{fails}")
    
    if not results:
        print("  ❌ 无候选"); return
    
    df = pd.DataFrame(results).sort_values('confidence', ascending=False)
    today_str = datetime.now().strftime('%Y%m%d')
    df.to_csv(f'/Users/weihaoli/Desktop/蔡森 skill/破底翻候选_{today_str}.csv',
              index=False, encoding='utf-8-sig')
    
    def pt(sub, title):
        print(f"\n  {title}: {len(sub)}只")
        if len(sub) == 0: return
        print(f"  {'代码':12} {'名称':10} {'价格':>8} {'今涨':>6} {'年高跌':>7} {'分位':>5} {'破底':>5} {'收回':>6} {'量比':>5} {'conf':>4}")
        print(f"  {'-'*95}")
        for _, r in sub.iterrows():
            print(f"  {r['代码']:12} {r['名称']:10} {r['最新价']:8.2f} {r['今日涨幅%']:+5.1f}% "
                  f"{r['距年高跌幅%']:6.1f}% {r['历史分位%']:4.1f}% {r['破底深度%']:4.1f}% "
                  f"{r['收回幅度%']:+5.1f}% {r['量比vs5日均']:4.1f}x {r['confidence']:3d}")
    
    print(f"\n{'='*100}")
    print(f"  📊 破底翻候选 ({len(results)}只 / {len(stocks)}只, 成功率{len(results)/(len(stocks)-fails)*100:.1f}%)")
    print(f"{'='*100}")
    pt(df[df['confidence']>=70], "⭐⭐⭐ 极高(≥70)")
    pt(df[(df['confidence']>=67)&(df['confidence']<70)], "⭐⭐ 高(67-69)")
    pt(df[(df['confidence']>=63)&(df['confidence']<67)], "⭐ 中(63-66)")
    pt(df[df['confidence']<63], "○ 低(60-62)")
    
    print(f"\n{'='*100}")
    print(f"  📈 统计: 扫描{len(stocks)} | K线失败{fails} | 候选{len(results)} | 耗时{total:.0f}s")
    print(f"  平均距年高跌:{df['距年高跌幅%'].mean():.1f}% 平均历史分位:{df['历史分位%'].mean():.1f}% 平均涨幅:{df['今日涨幅%'].mean():.1f}%")

if __name__ == '__main__':
    main()
