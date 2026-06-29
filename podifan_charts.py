#!/usr/bin/env python3
"""蔡森破底翻可视化图表生成器 — 为高分候选股生成60日K线+破底翻标注"""

import requests, os, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime

# 中文字体
for p in ['/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc']:
    if os.path.exists(p):
        fm.fontManager.addfont(p)
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'STHeiti', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

H = {'User-Agent': 'Mozilla/5.0'}

def get_kline_eastmoney(code):
    """东方财富API获取K线"""
    market = '1' if code.startswith(('6', '5')) else '0'
    secid = f'{market}.{code}'
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid, 'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57',
        'klt': '101', 'fqt': '0', 'beg': '20260101', 'end': '20261231', 'lmt': '250'
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

def detect_podifan_levels(candles, window=60):
    """检测破底翻的关键价位"""
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
    return best, start, seg

def draw_podifan(code, name, candles, best, start, seg, conf, outdir):
    """绘制破底翻K线图"""
    sn = len(seg)
    # 只画最近60日
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

        # 影线
        ax.vlines(i, lo, hi, color=color, linewidth=0.8, zorder=2)
        # 实体
        body_bottom = min(o, cl)
        body_height = abs(cl - o) or 0.01
        rect = Rectangle((i - 0.35, body_bottom), 0.7, body_height,
                         facecolor=color, edgecolor=color, linewidth=0.5, zorder=3)
        ax.add_patch(rect)

    # 调整best的index到plot范围
    offset = sn - pn  # plot开始的偏移
    sidx_plot = best['sidx'] - offset
    bi_plot = best['bi'] - offset if best['bi'] is not None else None

    tc = plot[-1]['close']
    sprice = best['sprice']
    bl = best['bl']

    # === 蔡森破底翻标注 ===
    # 1. 支撑位水平线（绿色虚线）
    ax.axhline(y=sprice, color='#2ecc71', linewidth=1.8, linestyle='--', alpha=0.85, zorder=5)
    ax.text(pn - 0.5, sprice, f' 支撑位 {sprice:.2f}', color='#2ecc71', fontsize=9,
            va='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#2ecc71', alpha=0.9))

    # 2. 破底最低点标记（红色）
    if bi_plot is not None and 0 <= bi_plot < pn:
        ax.annotate(f'破底 {bl:.2f}\n({best["bdate"]})',
                    xy=(bi_plot, bl), xytext=(bi_plot + 3, bl - (sprice - bl) * 1.5),
                    fontsize=8.5, color='#e74c3c', fontweight='bold', ha='center',
                    arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5),
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e', edgecolor='#e74c3c', alpha=0.95))
        ax.plot(bi_plot, bl, 'v', color='#e74c3c', markersize=10, zorder=10)

    # 3. 支撑形成点标记
    if 0 <= sidx_plot < pn:
        ax.plot(sidx_plot, sprice, 'o', color='#2ecc71', markersize=8, zorder=10)
        ax.annotate(f'支撑形成\n{sprice:.2f}\n({best["sdate"]})',
                    xy=(sidx_plot, sprice), xytext=(sidx_plot - 2, sprice + (sprice - bl) * 1.2),
                    fontsize=8, color='#2ecc71', ha='center',
                    arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=1.2),
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#2ecc71', alpha=0.9))

    # 4. 翻回确认点（当前价）
    ax.plot(pn - 1, tc, '*', color='#f1c40f', markersize=14, zorder=10)
    ax.annotate(f'当前 {tc:.2f}\n收回+{best["rc"]:.1f}%',
                xy=(pn - 1, tc), xytext=(pn - 6, tc + (sprice - bl) * 0.8),
                fontsize=9, color='#f1c40f', fontweight='bold', ha='center',
                arrowprops=dict(arrowstyle='->', color='#f1c40f', lw=1.5),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e', edgecolor='#f1c40f', alpha=0.95))

    # 5. 目标价线（橙色虚线）目标价 = sprice + (sprice - bl)
    target = sprice + (sprice - bl)
    ax.axhline(y=target, color='#FF6B00', linewidth=1.5, linestyle=':', alpha=0.8, zorder=5)
    ax.text(pn - 0.5, target, f' 测幅目标 {target:.2f}', color='#FF6B00', fontsize=9,
            va='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#FF6B00', alpha=0.9))

    # 6. 止损线（红色点线）
    stop_loss = sprice * 0.97
    ax.axhline(y=stop_loss, color='#c0392b', linewidth=1.2, linestyle=':', alpha=0.6, zorder=5)
    ax.text(pn - 0.5, stop_loss, f' 止损 {stop_loss:.2f}', color='#c0392b', fontsize=8,
            va='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#c0392b', alpha=0.85))

    # 均线
    def ma(data, p):
        res = [np.nan] * len(data)
        for i in range(p - 1, len(data)):
            res[i] = np.mean(data[i-p+1:i+1])
        return res
    closes = np.array([c['close'] for c in plot])
    ax.plot(x, ma(closes, 5), color='#3498db', linewidth=1, alpha=0.7, label='MA5')
    ax.plot(x, ma(closes, 20), color='#9b59b6', linewidth=1, alpha=0.7, label='MA20')

    # 成交量
    vol_colors = ['#e74c3c' if plot[i]['close'] >= plot[i]['open'] else '#16a085' for i in range(pn)]
    axv.bar(x, [c['volume'] for c in plot], color=vol_colors, width=0.7, alpha=0.8)
    vol_ma5 = ma(np.array([c['volume'] for c in plot]), 5)
    axv.plot(x, vol_ma5, color='#f39c12', linewidth=1.2, alpha=0.8, label='均量5')

    # X轴日期
    step = max(1, pn // 10)
    axv.set_xticks(x[::step])
    axv.set_xticklabels([plot[i]['date'][5:] for i in range(0, pn, step)], rotation=30, fontsize=8)

    # 标题
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

    # 副信息
    info = (f'破底深度:{best["bd"]:.1f}%  收回:+{best["rc"]:.1f}%  '
            f'支撑:{sprice:.2f}→破底:{bl:.2f}→当前:{tc:.2f}')
    fig.text(0.5, 0.02, info, ha='center', fontsize=9, color='#aaa')

    outpath = os.path.join(outdir, f'podifan_{code}_{name}.png')
    fig.savefig(outpath, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return outpath

def main():
    outdir = '/Users/weihaoli/Desktop/蔡森 skill/output'
    os.makedirs(outdir, exist_ok=True)

    # 高分候选股
    candidates = [
        ('300364', '中文在线', 72),
        ('300501', '海顺新材', 71),
        ('300293', '蓝英装备', 69),
        ('688591', '泰凌微', 69),
        ('300609', '汇纳科技', 68),
    ]

    results = []
    for code, name, conf in candidates:
        print(f'\n处理 {name}({code})...')
        try:
            candles = get_kline_eastmoney(code)
            print(f'  获取 {len(candles)} 根K线')
            if len(candles) < 40:
                print(f'  ❌ K线不足'); continue
            best, start, seg = detect_podifan_levels(candles)
            if best is None:
                print(f'  ❌ 未检测到破底翻'); continue
            print(f'  ✅ 支撑{best["sprice"]:.2f} 破底{best["bl"]:.2f} '
                  f'深度{best["bd"]:.1f}% 收回+{best["rc"]:.1f}%')
            path = draw_podifan(code, name, candles, best, start, seg, conf, outdir)
            results.append((name, code, path))
            print(f'  📊 图表: {path}')
        except Exception as e:
            print(f'  ❌ 错误: {e}')

    print(f'\n{"="*60}')
    print(f'生成 {len(results)} 张破底翻图表')
    for name, code, path in results:
        print(f'  {name}({code}): {path}')

if __name__ == '__main__':
    main()
