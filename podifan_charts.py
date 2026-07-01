#!/usr/bin/env python3
"""蔡森破底翻可视化图表生成器 — 全市场扫描 + 量化信心度 + K线标注

用法:
  # 扫描指定股票
  python podifan_charts.py --stocks 300364,300501,300293

  # 全市场扫描（拉取全部A股，按信心度排序取前N）
  python podifan_charts.py --all --top 30

  # 从文件读取股票代码（每行一个 code 或 code,name）
  python podifan_charts.py --file stocks.txt --top 20

  # 按板块/概念过滤（可选，关键词匹配东方财富板块名）
  python podifan_charts.py --all --top 30 --sector 半导体

  # 仅输出扫描结果不画图
  python podifan_charts.py --all --top 50 --no-plot

  # 自定义回看窗口（默认60日）
  python podifan_charts.py --all --top 30 --window 90
"""

import requests, os, math, argparse, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime, timedelta

# 中文字体
for p in ['/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc']:
    if os.path.exists(p):
        fm.fontManager.addfont(p)
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'STHeiti', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

H = {'User-Agent': 'Mozilla/5.0'}


# ============ 数据获取 ============

def get_kline_eastmoney(code, days=250):
    """东方财富API获取K线（动态日期，默认拉最近 days 根）"""
    market = '1' if code.startswith(('6', '5')) else '0'
    secid = f'{market}.{code}'
    end = datetime.now().strftime('%Y%m%d')
    beg = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid, 'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57',
        'klt': '101', 'fqt': '0', 'beg': beg, 'end': end, 'lmt': str(days)
    }
    r = requests.get(url, params=params, headers=H, timeout=15)
    klines = r.json().get('data', {}).get('klines', [])
    candles = []
    for line in klines:
        parts = line.split(',')
        candles.append({
            'date': parts[0], 'open': float(parts[1]), 'close': float(parts[2]),
            'high': float(parts[3]), 'low': float(parts[4]),
            'volume': int(parts[5]), 'amount': float(parts[6])
        })
    return candles


def fetch_all_astocks(sector_keyword=None):
    """拉取全部A股列表（代码+名称），可选按板块关键词过滤"""
    url = 'http://80.push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': '1', 'pz': '10000', 'po': '1', 'np': '1',
        'fltt': '2', 'invt': '2', 'fid': 'f3',
        # 沪深A股 + 科创板 + 创业板
        'fs': 'm:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23',
        'fields': 'f12,f14'
    }
    r = requests.get(url, params=params, headers=H, timeout=20)
    data = r.json().get('data', {}).get('diff', [])
    stocks = []
    for item in data:
        code = item.get('f12', '')
        name = item.get('f14', '')
        # 过滤 ST / 退市 / 北交所(8/4开头)
        if not code or code.startswith(('8', '4')):
            continue
        if 'ST' in name or '退' in name:
            continue
        # 板块关键词过滤（简单名称匹配，更精确可用板块接口）
        if sector_keyword and sector_keyword not in name:
            continue
        stocks.append((code, name))
    return stocks


# ============ 破底翻检测 ============

def detect_podifan_levels(candles, window=60):
    """检测破底翻的关键价位，返回 best 结构（含信心度）"""
    n = len(candles)
    start = max(0, n - window)
    seg = candles[start:]
    sn = len(seg)

    close = np.array([c['close'] for c in seg])
    high = np.array([c['high'] for c in seg])
    low = np.array([c['low'] for c in seg])
    vol = np.array([c['volume'] for c in seg])
    tc = close[-1]

    # 局部低点
    lk = 5
    local_lows = []
    for i in range(lk, sn - lk):
        if all(low[i] <= low[i+j] for j in range(-lk, lk+1) if j != 0):
            local_lows.append(i)

    # 找最佳破底翻：遍历支撑位
    bt = 0.03
    best = None
    for sidx in local_lows:
        if sidx >= sn - 3:
            continue
        sprice = low[sidx]
        # 检查破底
        broke = False
        bl = tc
        bi = None
        for i in range(sidx + 1, sn):
            if low[i] < sprice * (1 - bt):
                broke = True
                if low[i] < bl:
                    bl = low[i]; bi = i
        if not broke:
            continue
        if tc < sprice:
            continue
        # 破底后不再创新低
        if bi is not None and bi < sn - 1:
            if min(low[bi+1:]) < bl * 0.98:
                continue
        bd = (sprice - bl) / sprice * 100
        rc = (tc - sprice) / sprice * 100
        if best is None or bd > best['bd']:
            best = {
                'sidx': sidx, 'sprice': sprice, 'bl': bl, 'bi': bi,
                'bd': bd, 'rc': rc,
                'sdate': seg[sidx]['date'],
                'bdate': seg[bi]['date'] if bi is not None else '',
            }
    # 计算信心度
    if best is not None:
        best['confidence'] = calc_confidence(best, seg, vol)
    return best, start, seg


def calc_confidence(best, seg, vol):
    """破底翻信心度计算（参考 pattern-algorithms.md：基础60，3日站稳75，最高85）

    加分项：
      - 破底深度 3-7%（合理洗盘）+5；>10%（可能真跌破）-5
      - 收回幅度 ≥3% +5；≥5% 再+5
      - 站稳天数 ≥3 +5；≥5 再+3
      - 翻回时放量（>前5日均量×1.3）+5
      - 水底型（破底前20日波动率<5%）+5
    """
    base = 60
    bd = best['bd']
    rc = best['rc']
    sn = len(seg)
    bi = best['bi']

    # 破底深度
    if 3 <= bd <= 7:
        base += 5
    elif bd > 10:
        base -= 5
    elif bd > 15:
        base -= 10

    # 收回幅度
    if rc >= 3:
        base += 5
    if rc >= 5:
        base += 5

    # 站稳天数（从破底到现在的K线数）
    stand_days = (sn - 1 - bi) if bi is not None else 0
    if stand_days >= 3:
        base += 5
    if stand_days >= 5:
        base += 3

    # 翻回时放量：检查最近3日是否有放量
    if sn >= 6:
        vol_ma5 = np.mean(vol[-8:-3]) if sn >= 8 else np.mean(vol[:-3])
        recent_vol = np.mean(vol[-3:])
        if recent_vol > vol_ma5 * 1.3:
            base += 5

    # 水底型：破底前20日波动率低
    sidx = best['sidx']
    if sidx >= 20:
        pre_seg = seg[max(0, sidx-20):sidx]
        if len(pre_seg) >= 10:
            pre_closes = np.array([c['close'] for c in pre_seg])
            volatility = np.std(pre_closes) / np.mean(pre_closes) * 100
            if volatility < 5:
                base += 5

    return min(max(base, 0), 85)


# ============ 绘图 ============

def draw_podifan(code, name, candles, best, start, seg, outdir):
    """绘制破底翻K线图（信心度从 best['confidence'] 读取）"""
    conf = best.get('confidence', 60)
    sn = len(seg)
    plot_n = min(60, sn)
    plot = seg[-plot_n:]
    pn = len(plot)

    fig, (ax, axv) = plt.subplots(2, 1, figsize=(13, 7.5), gridspec_kw={'height_ratios': [3, 1]},
                                   sharex=True)
    fig.subplots_adjust(hspace=0.05, left=0.07, right=0.95, top=0.90, bottom=0.08)

    x = np.arange(pn)

    # 蔡森四色K线
    for i in range(pn):
        c = plot[i]
        o, cl, hi, lo = c['open'], c['close'], c['high'], c['low']
        prev_cl = plot[i-1]['close'] if i > 0 else o
        if cl >= o and cl >= prev_cl:
            color = '#e74c3c'  # 强势阳 红
        elif cl < o and cl >= prev_cl:
            color = '#f39c12'  # 假阴线 黄
        elif cl >= o and cl < prev_cl:
            color = '#27ae60'  # 假阳线 绿
        else:
            color = '#16a085'  # 强势阴 青绿

        ax.vlines(i, lo, hi, color=color, linewidth=0.8, zorder=2)
        body_bottom = min(o, cl)
        body_height = abs(cl - o) or 0.01
        rect = Rectangle((i - 0.35, body_bottom), 0.7, body_height,
                         facecolor=color, edgecolor=color, linewidth=0.5, zorder=3)
        ax.add_patch(rect)

    offset = sn - pn
    sidx_plot = best['sidx'] - offset
    bi_plot = best['bi'] - offset if best['bi'] is not None else None

    tc = plot[-1]['close']
    sprice = best['sprice']
    bl = best['bl']

    # === 蔡森破底翻标注 ===
    ax.axhline(y=sprice, color='#2ecc71', linewidth=1.8, linestyle='--', alpha=0.85, zorder=5)
    ax.text(pn - 0.5, sprice, f' 支撑位 {sprice:.2f}', color='#2ecc71', fontsize=9,
            va='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#2ecc71', alpha=0.9))

    if bi_plot is not None and 0 <= bi_plot < pn:
        ax.annotate(f'破底 {bl:.2f}\n({best["bdate"]})',
                    xy=(bi_plot, bl), xytext=(bi_plot + 3, bl - (sprice - bl) * 1.5),
                    fontsize=8.5, color='#e74c3c', fontweight='bold', ha='center',
                    arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5),
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e', edgecolor='#e74c3c', alpha=0.95))
        ax.plot(bi_plot, bl, 'v', color='#e74c3c', markersize=10, zorder=10)

    if 0 <= sidx_plot < pn:
        ax.plot(sidx_plot, sprice, 'o', color='#2ecc71', markersize=8, zorder=10)
        ax.annotate(f'支撑形成\n{sprice:.2f}\n({best["sdate"]})',
                    xy=(sidx_plot, sprice), xytext=(sidx_plot - 2, sprice + (sprice - bl) * 1.2),
                    fontsize=8, color='#2ecc71', ha='center',
                    arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=1.2),
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#2ecc71', alpha=0.9))

    ax.plot(pn - 1, tc, '*', color='#f1c40f', markersize=14, zorder=10)
    ax.annotate(f'当前 {tc:.2f}\n收回+{best["rc"]:.1f}%',
                xy=(pn - 1, tc), xytext=(pn - 6, tc + (sprice - bl) * 0.8),
                fontsize=9, color='#f1c40f', fontweight='bold', ha='center',
                arrowprops=dict(arrowstyle='->', color='#f1c40f', lw=1.5),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e', edgecolor='#f1c40f', alpha=0.95))

    target = sprice + (sprice - bl)
    ax.axhline(y=target, color='#FF6B00', linewidth=1.5, linestyle=':', alpha=0.8, zorder=5)
    ax.text(pn - 0.5, target, f' 测幅目标 {target:.2f}', color='#FF6B00', fontsize=9,
            va='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#FF6B00', alpha=0.9))

    stop_loss = sprice * 0.97
    ax.axhline(y=stop_loss, color='#c0392b', linewidth=1.2, linestyle=':', alpha=0.6, zorder=5)
    ax.text(pn - 0.5, stop_loss, f' 止损 {stop_loss:.2f}', color='#c0392b', fontsize=8,
            va='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#c0392b', alpha=0.85))

    def ma(data, p):
        res = [np.nan] * len(data)
        for i in range(p - 1, len(data)):
            res[i] = np.mean(data[i-p+1:i+1])
        return res
    closes = np.array([c['close'] for c in plot])
    ax.plot(x, ma(closes, 5), color='#3498db', linewidth=1, alpha=0.7, label='MA5')
    ax.plot(x, ma(closes, 20), color='#9b59b6', linewidth=1, alpha=0.7, label='MA20')

    vol_colors = ['#e74c3c' if plot[i]['close'] >= plot[i]['open'] else '#16a085' for i in range(pn)]
    axv.bar(x, [c['volume'] for c in plot], color=vol_colors, width=0.7, alpha=0.8)
    vol_ma5 = ma(np.array([c['volume'] for c in plot]), 5)
    axv.plot(x, vol_ma5, color='#f39c12', linewidth=1.2, alpha=0.8, label='均量5')

    step = max(1, pn // 10)
    axv.set_xticks(x[::step])
    axv.set_xticklabels([plot[i]['date'][5:] for i in range(0, pn, step)], rotation=30, fontsize=8)

    title = f'{name}({code})  蔡森破底翻形态  |  信心度 {conf}'
    ax.set_title(title, fontsize=13, fontweight='bold', color='#e0e0e0', pad=12)
    ax.set_facecolor('#0d1117')
    axv.set_facecolor('#0d1117')
    fig.patch.set_facecolor('#0d1117')
    ax.tick_params(colors='#888')
    axv.tick_params(colors='#888')
    for spine in ax.spines.values():
        spine.set_color('#333')
    for spine in axv.spines.values():
        spine.set_color('#333')
    ax.legend(loc='upper left', fontsize=8, facecolor='#1a1a2e', edgecolor='#333', labelcolor='#ccc')
    axv.legend(loc='upper left', fontsize=8, facecolor='#1a1a2e', edgecolor='#333', labelcolor='#ccc')
    ax.grid(True, alpha=0.08, color='#666')
    axv.set_ylabel('成交量', fontsize=9, color='#888')

    info = (f'破底深度:{best["bd"]:.1f}%  收回:+{best["rc"]:.1f}%  '
            f'支撑:{sprice:.2f}→破底:{bl:.2f}→当前:{tc:.2f}  目标:{target:.2f}')
    fig.text(0.5, 0.02, info, ha='center', fontsize=9, color='#aaa')

    outpath = os.path.join(outdir, f'podifan_{code}_{name}.png')
    fig.savefig(outpath, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return outpath


# ============ 扫描引擎 ============

def scan_one(code, name, window, outdir, no_plot):
    """扫描单只股票，返回结果 dict 或 None"""
    try:
        candles = get_kline_eastmoney(code)
        if len(candles) < 40:
            return None
        best, start, seg = detect_podifan_levels(candles, window=window)
        if best is None:
            return None
        result = {
            'code': code, 'name': name,
            'confidence': best['confidence'],
            'sprice': best['sprice'], 'bl': best['bl'],
            'bd': best['bd'], 'rc': best['rc'],
            'sdate': best['sdate'], 'bdate': best['bdate'],
            'close': seg[-1]['close'],
            'target': best['sprice'] + (best['sprice'] - best['bl']),
            'stop_loss': best['sprice'] * 0.97,
        }
        if not no_plot:
            result['chart'] = draw_podifan(code, name, candles, best, start, seg, outdir)
        return result
    except Exception as e:
        return {'code': code, 'name': name, 'error': str(e)}


def scan_stocks(stocks, window, outdir, top_n, no_plot, max_workers=8):
    """并发扫描股票列表，按信心度排序返回前 top_n"""
    results = []
    total = len(stocks)
    print(f'开始扫描 {total} 只股票（并发 {max_workers}）...')
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(scan_one, c, n, window, outdir, no_plot): (c, n) for c, n in stocks}
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if r and 'error' not in r:
                results.append(r)
                print(f'  [{done}/{total}] ✅ {r["name"]}({r["code"]}) 信心度{r["confidence"]} '
                      f'破底{r["bd"]:.1f}% 收回+{r["rc"]:.1f}%')
            elif r and 'error' in r:
                print(f'  [{done}/{total}] ❌ {r["name"]}({r["code"]}) {r["error"]}')
            if done % 100 == 0:
                print(f'  进度 {done}/{total}，已发现 {len(results)} 个破底翻')

    results.sort(key=lambda x: x['confidence'], reverse=True)
    if top_n:
        results = results[:top_n]
    return results


def save_summary(results, outdir):
    """保存扫描汇总（txt + csv）"""
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    txt_path = os.path.join(outdir, f'podifan_scan_{ts}.txt')
    csv_path = os.path.join(outdir, f'podifan_scan_{ts}.csv')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f'蔡森破底翻扫描结果  {ts}\n')
        f.write(f'共发现 {len(results)} 个破底翻形态\n')
        f.write('=' * 80 + '\n')
        f.write(f'{"排名":<4}{"代码":<8}{"名称":<10}{"信心度":<6}{"支撑":<8}{"破底":<8}'
                f'{"深度%":<7}{"收回%":<7}{"现价":<8}{"目标":<8}{"止损":<8}\n')
        f.write('-' * 80 + '\n')
        for i, r in enumerate(results, 1):
            f.write(f'{i:<4}{r["code"]:<8}{r["name"]:<10}{r["confidence"]:<6}'
                    f'{r["sprice"]:<8.2f}{r["bl"]:<8.2f}{r["bd"]:<7.1f}{r["rc"]:<7.1f}'
                    f'{r["close"]:<8.2f}{r["target"]:<8.2f}{r["stop_loss"]:<8.2f}\n')
    with open(csv_path, 'w', encoding='utf-8-sig') as f:
        f.write('排名,代码,名称,信心度,支撑位,破底价,破底深度%,收回幅度%,现价,目标价,止损价,支撑日期,破底日期\n')
        for i, r in enumerate(results, 1):
            f.write(f'{i},{r["code"]},{r["name"]},{r["confidence"]},'
                    f'{r["sprice"]:.2f},{r["bl"]:.2f},{r["bd"]:.1f},{r["rc"]:.1f},'
                    f'{r["close"]:.2f},{r["target"]:.2f},{r["stop_loss"]:.2f},'
                    f'{r["sdate"]},{r["bdate"]}\n')
    return txt_path, csv_path


# ============ 主入口 ============

def parse_stocks_arg(s):
    """解析 --stocks 参数：300364,300501 或 300364:中文在线,300501:海顺新材"""
    stocks = []
    for item in s.split(','):
        item = item.strip()
        if not item:
            continue
        if ':' in item:
            code, name = item.split(':', 1)
        else:
            code, name = item, ''
        stocks.append((code.strip(), name.strip()))
    return stocks


def load_stock_file(path):
    """从文件读取股票（每行 code 或 code,name）"""
    stocks = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ',' in line:
                code, name = line.split(',', 1)
            else:
                code, name = line, ''
            stocks.append((code.strip(), name.strip()))
    return stocks


def main():
    parser = argparse.ArgumentParser(description='蔡森破底翻扫描器')
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--stocks', help='指定股票代码（逗号分隔，可带名称 300364:中文在线）')
    g.add_argument('--all', action='store_true', help='扫描全市场A股')
    g.add_argument('--file', help='从文件读取股票代码（每行一个）')
    parser.add_argument('--top', type=int, default=30, help='取信心度前N名（默认30）')
    parser.add_argument('--window', type=int, default=60, help='回看窗口K线数（默认60）')
    parser.add_argument('--sector', help='板块/名称关键词过滤（如 半导体、军工）')
    parser.add_argument('--no-plot', action='store_true', help='不画图，仅输出扫描结果')
    parser.add_argument('--workers', type=int, default=8, help='并发数（默认8）')
    parser.add_argument('--outdir', default='/Users/weihaoli/Desktop/蔡森 skill/output',
                        help='输出目录')
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # 获取股票列表
    if args.stocks:
        stocks = parse_stocks_arg(args.stocks)
    elif args.file:
        stocks = load_stock_file(args.file)
    else:  # --all
        print('拉取全A股列表...')
        stocks = fetch_all_astocks(sector_keyword=args.sector)
        print(f'共 {len(stocks)} 只股票待扫描')

    # 扫描
    results = scan_stocks(stocks, args.window, args.outdir, args.top, args.no_plot,
                          max_workers=args.workers)

    # 汇总输出
    print(f'\n{"=" * 80}')
    print(f'扫描完成：共发现 {len(results)} 个破底翻形态（按信心度排序）')
    print(f'{"排名":<4}{"代码":<8}{"名称":<10}{"信心度":<6}{"支撑":<8}{"破底":<8}'
          f'{"深度%":<7}{"收回%":<7}{"现价":<8}{"目标":<8}{"止损":<8}')
    print('-' * 80)
    for i, r in enumerate(results, 1):
        print(f'{i:<4}{r["code"]:<8}{r["name"]:<10}{r["confidence"]:<6}'
              f'{r["sprice"]:<8.2f}{r["bl"]:<8.2f}{r["bd"]:<7.1f}{r["rc"]:<7.1f}'
              f'{r["close"]:<8.2f}{r["target"]:<8.2f}{r["stop_loss"]:<8.2f}')

    txt_path, csv_path = save_summary(results, args.outdir)
    print(f'\n汇总已保存：\n  {txt_path}\n  {csv_path}')


if __name__ == '__main__':
    main()
