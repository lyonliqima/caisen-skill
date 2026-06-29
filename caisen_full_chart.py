#!/usr/bin/env python3
"""蔡森划线法 — 完整K线图 + 蔡森四色K线 + 对角趋势线"""

import requests, os, math
from PIL import Image, ImageDraw, ImageFont

# ═══════════════════════════════════════════
# 1. 获取K线数据 (东方财富API)
# ═══════════════════════════════════════════
url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
params = {
    'secid': '0.301458', 'fields1': 'f1,f2,f3,f4,f5,f6',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57',
    'klt': '101', 'fqt': '0', 'beg': '20260101', 'end': '20260618', 'lmt': '200'
}
r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
raw = r.json().get('data', {}).get('klines', [])

candles = []
for line in raw:
    parts = line.split(',')
    candles.append({
        'date': parts[0], 'open': float(parts[1]), 'close': float(parts[2]),
        'high': float(parts[3]), 'low': float(parts[4]),
        'volume': int(parts[5]), 'amount': float(parts[6])
    })

N = len(candles)
print(f'获取 {N} 根K线: {candles[0]["date"]} → {candles[-1]["date"]}')

# ═══════════════════════════════════════════
# 2. 计算均线
# ═══════════════════════════════════════════
def calc_ma(candles, period):
    ma = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        ma[i] = sum(c['close'] for c in candles[i - period + 1:i + 1]) / period
    return ma

ma5 = calc_ma(candles, 5)
ma10 = calc_ma(candles, 10)
ma20 = calc_ma(candles, 20)

# ═══════════════════════════════════════════
# 3. 蔡森 pattern-recognizer: 找局部极值
# ═══════════════════════════════════════════
def find_local_mins(candles, lookback=5):
    result = []
    for i in range(lookback, len(candles) - lookback):
        is_min = True
        for j in range(1, lookback + 1):
            if candles[i]['low'] > candles[i - j]['low'] or candles[i]['low'] > candles[i + j]['low']:
                is_min = False; break
        if is_min: result.append(i)
    return result

def find_local_maxs(candles, lookback=5):
    result = []
    for i in range(lookback, len(candles) - lookback):
        is_max = True
        for j in range(1, lookback + 1):
            if candles[i]['high'] < candles[i - j]['high'] or candles[i]['high'] < candles[i + j]['high']:
                is_max = False; break
        if is_max: result.append(i)
    return result

local_mins = find_local_mins(candles, 4)
local_maxs = find_local_maxs(candles, 4)

print(f'局部低点({len(local_mins)}): {[(i, candles[i]["date"], round(candles[i]["low"],2)) for i in local_mins]}')
print(f'局部高点({len(local_maxs)}): {[(i, candles[i]["date"], round(candles[i]["high"],2)) for i in local_maxs]}')

# ═══════════════════════════════════════════
# 4. 蔡森四色K线分类
# ═══════════════════════════════════════════
def four_color(c, prev_close):
    o, cl = c['open'], c['close']
    if cl >= o and cl >= prev_close: return 'red'      # 强势阳
    if cl < o and cl >= prev_close: return 'yellow'    # 假阴线
    if cl >= o and cl < prev_close: return 'green'     # 假阳线
    return 'blue'                                       # 弱势阴

kline_types = []
for i, c in enumerate(candles):
    prev = candles[i - 1]['close'] if i > 0 else c['open']
    kline_types.append(four_color(c, prev))

# ═══════════════════════════════════════════
# 5. 画布设置
# ═══════════════════════════════════════════
IMG_W, IMG_H = 1400, 800
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 80, 80, 60, 160
VOL_H = 100  # 成交量区高度
CHART_W = IMG_W - MARGIN_L - MARGIN_R
CHART_H = IMG_H - MARGIN_T - MARGIN_B - VOL_H - 20  # 主图高度
VOL_TOP = MARGIN_T + CHART_H + 20

img = Image.new('RGB', (IMG_W, IMG_H), '#FFFFFF')
d = ImageDraw.Draw(img)

# 字体
def gf(sz):
    for p in ['/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc',
              '/System/Library/Fonts/Supplemental/Arial Unicode.ttf']:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except: pass
    return ImageFont.load_default()

f10 = gf(10); f11 = gf(11); f12 = gf(12); f14 = gf(14); f16 = gf(16); f20 = gf(20)

# 价格范围
all_highs = [c['high'] for c in candles]
all_lows = [c['low'] for c in candles]
P_MAX = max(all_highs) * 1.02
P_MIN = min(all_lows) * 0.98
V_MAX = max(c['volume'] for c in candles) * 1.2

# 坐标映射
def price_to_y(p):
    return MARGIN_T + CHART_H - int((p - P_MIN) / (P_MAX - P_MIN) * CHART_H)

def idx_to_x(i):
    candle_w = CHART_W / N
    return MARGIN_L + int((i + 0.5) * candle_w)

CANDLE_W = max(3, CHART_W // N - 2)

# 四色K线颜色
COLOR_MAP = {
    'red':    '#E74C3C',   # 强势阳
    'yellow': '#F1C40F',   # 假阴线
    'green':  '#27AE60',   # 假阳线
    'blue':   '#1F5EFF',   # 弱势阴
}

# ═══════════════════════════════════════════
# 6. 画背景网格
# ═══════════════════════════════════════════
# 标题
d.text((MARGIN_L, 8), '钧崴电子 301458 · 蔡森划线法', fill='#333', font=f20)
d.text((MARGIN_L, 34), f'{candles[0]["date"]} → {candles[-1]["date"]}  共{N}根日K', fill='#888', font=f11)

# 水平网格 + 价格标签
grid_count = 6
for i in range(grid_count + 1):
    p = P_MIN + (P_MAX - P_MIN) * i / grid_count
    y = price_to_y(p)
    d.line([(MARGIN_L, y), (IMG_W - MARGIN_R, y)], fill='#F0F0F0', width=1)
    d.text((5, y - 7), f'{p:.2f}', fill='#999', font=f10)

# 竖直网格 + 日期标签
date_interval = max(1, N // 8)
for i in range(0, N, date_interval):
    x = idx_to_x(i)
    d.line([(x, MARGIN_T), (x, MARGIN_T + CHART_H)], fill='#F5F5F5', width=1)
    d.text((x - 25, MARGIN_T + CHART_H + 3), candles[i]['date'][5:], fill='#999', font=f10)

# 图表边框
d.rectangle([(MARGIN_L, MARGIN_T), (IMG_W - MARGIN_R, MARGIN_T + CHART_H)], outline='#DDD', width=1)

# ═══════════════════════════════════════════
# 7. 画K线蜡烛
# ═══════════════════════════════════════════
for i, c in enumerate(candles):
    x = idx_to_x(i)
    y_open = price_to_y(c['open'])
    y_close = price_to_y(c['close'])
    y_high = price_to_y(c['high'])
    y_low = price_to_y(c['low'])
    color = COLOR_MAP[kline_types[i]]

    # 上下影线
    d.line([(x, y_high), (x, y_low)], fill=color, width=1)

    # 实体
    body_top = min(y_open, y_close)
    body_bot = max(y_open, y_close)
    body_h = max(1, body_bot - body_top)
    hw = CANDLE_W // 2

    if c['close'] >= c['open']:
        # 阳线: 填充
        d.rectangle([(x - hw, body_top), (x + hw, body_bot)], fill=color)
    else:
        # 阴线: 空心 (白色填充+边框)
        d.rectangle([(x - hw, body_top), (x + hw, body_bot)], fill='#FFFFFF', outline=color, width=1)

# ═══════════════════════════════════════════
# 8. 画均线
# ═══════════════════════════════════════════
def draw_ma_line(ma_data, color, label, y_offset=0):
    points = []
    for i, v in enumerate(ma_data):
        if v is not None:
            points.append((idx_to_x(i), price_to_y(v)))
    if len(points) < 2: return
    d.line(points, fill=color, width=1)
    d.text((points[-1][0] + 5, points[-1][1] - 6 + y_offset), label, fill=color, font=f10)

draw_ma_line(ma5, '#3498DB', 'MA5')
draw_ma_line(ma10, '#E67E22', 'MA10')
draw_ma_line(ma20, '#9B59B6', 'MA20')

# ═══════════════════════════════════════════
# 9. 画成交量
# ═══════════════════════════════════════════
d.line([(MARGIN_L, VOL_TOP), (IMG_W - MARGIN_R, VOL_TOP)], fill='#EEE', width=1)
for i, c in enumerate(candles):
    x = idx_to_x(i)
    vh = int(c['volume'] / V_MAX * VOL_H)
    color = COLOR_MAP[kline_types[i]]
    hw = CANDLE_W // 2
    d.rectangle([(x - hw, VOL_TOP + VOL_H - vh), (x + hw, VOL_TOP + VOL_H)], fill=color + '80')

d.text((MARGIN_L + 5, VOL_TOP + 2), '成交量', fill='#999', font=f10)

# ═══════════════════════════════════════════
# 10. 蔡森划线 (纯倾斜对角线)
# ═══════════════════════════════════════════

def pin_mark(x, y, label, color, pos="bottom"):
    """蔡森标记点: 圆圈+标签"""
    r = 5
    d.ellipse([(x-r, y-r), (x+r, y+r)], fill=None, outline=color, width=2)
    if label:
        bb = f10.getbbox(label)
        tw = bb[2] - bb[0]
        if pos == "bottom":
            d.text((x - tw//2, y + r + 3), label, fill=color, font=f10)
        else:
            d.text((x - tw//2, y - r - 13), label, fill=color, font=f10)

def label_box(x, y, txt, fg='#FFF', bg='#333'):
    bb = f12.getbbox(txt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad = 4
    d.rounded_rectangle([(x-pad, y-pad), (x+tw+pad, y+th+pad)], radius=3, fill=bg)
    d.text((x, y), txt, fill=fg, font=f12)

def dashed_line(p1, p2, color, w=2, dash=12, gap=6):
    x1, y1 = p1; x2, y2 = p2
    dx = x2 - x1; dy = y2 - y1
    L = math.sqrt(dx*dx + dy*dy)
    if L == 0: return
    dx /= L; dy /= L; pos = 0
    while pos < L:
        e = min(pos + dash, L)
        d.line([(x1+dx*pos, y1+dy*pos), (x1+dx*e, y1+dy*e)], fill=color, width=w)
        pos += dash + gap

def extend_line(p1, p2, x_end):
    """从p1经过p2延伸到x_end"""
    if p2[0] == p1[0]: return (x_end, p2[1])
    slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
    return (x_end, int(p1[1] + slope * (x_end - p1[0])))

# ─── 选择触点最多的趋势线 ───
# 低点序列: 取最后几个形成上升趋势的
# 高点序列: 取最后几个形成上升阻力的

# 对低点: 尝试找上升序列 (low递增)
ascending_lows = []
for idx in local_mins:
    if not ascending_lows or candles[idx]['low'] > candles[ascending_lows[-1]]['low'] * 0.95:
        ascending_lows.append(idx)
    elif candles[idx]['low'] < candles[ascending_lows[-1]]['low'] * 0.9:
        ascending_lows = [idx]  # reset

# 对高点: 找上升序列
ascending_highs = []
for idx in local_maxs:
    if not ascending_highs or candles[idx]['high'] > candles[ascending_highs[-1]]['high'] * 0.95:
        ascending_highs.append(idx)
    elif candles[idx]['high'] < candles[ascending_highs[-1]]['high'] * 0.9:
        ascending_highs = [idx]

print(f'\n上升低点序列: {[(i, candles[i]["date"], round(candles[i]["low"],2)) for i in ascending_lows]}')
print(f'上升高点序列: {[(i, candles[i]["date"], round(candles[i]["high"],2)) for i in ascending_highs]}')

# ─── ① 黑色粗线: 主上升趋势支撑线 (下轨) ───
# "点多的为主": 取触点最多的上升趋势线
# 用前两个和最后两个低点来确定
if len(ascending_lows) >= 2:
    # 取序列中最早和最晚的两个点
    i1 = ascending_lows[0]
    i2 = ascending_lows[-1]
    p1 = (idx_to_x(i1), price_to_y(candles[i1]['low']))
    p2 = (idx_to_x(i2), price_to_y(candles[i2]['low']))

    # 延伸线
    ext_end = extend_line(p1, p2, IMG_W - MARGIN_R + 30)
    ext_start = extend_line(p2, p1, MARGIN_L - 10)

    # 画粗线
    d.line([ext_start, ext_end], fill='#000000', width=3)

    # 标注所有触点
    for idx in ascending_lows:
        px = idx_to_x(idx)
        py = price_to_y(candles[idx]['low'])
        pin_mark(px, py, f'{candles[idx]["low"]:.1f}', '#000000', 'bottom')

    # 标签
    label_box(ext_end[0] - 120, ext_end[1] - 22, '上升趋势线(下轨)', '#FFF', '#000000CC')

# ─── ② 红色倾斜线: 通道阻力线 (上轨) ───
if len(ascending_highs) >= 2:
    i1 = ascending_highs[0]
    i2 = ascending_highs[-1]
    p1 = (idx_to_x(i1), price_to_y(candles[i1]['high']))
    p2 = (idx_to_x(i2), price_to_y(candles[i2]['high']))

    ext_end = extend_line(p1, p2, IMG_W - MARGIN_R + 30)
    ext_start = extend_line(p2, p1, MARGIN_L - 10)

    d.line([ext_start, ext_end], fill='#E74C3C', width=2)

    for idx in ascending_highs:
        px = idx_to_x(idx)
        py = price_to_y(candles[idx]['high'])
        pin_mark(px, py, f'{candles[idx]["high"]:.1f}', '#E74C3C', 'top')

    label_box(ext_end[0] - 110, ext_end[1] - 22, '阻力线(上轨)', '#FFF', '#E74C3CCC')

# ─── ③ 橙色虚线: 颈线 neckline ───
# W底: 找两个相近的低点, 颈线 = 两底之间的峰值向右延伸
if len(local_mins) >= 2:
    # 找最近的两个低点
    lm1, lm2 = local_mins[-2], local_mins[-1]
    # 两底之间的高点
    peak_idx = lm1
    peak_val = candles[lm1]['close']
    for k in range(lm1, lm2 + 1):
        if candles[k]['high'] > peak_val:
            peak_val = candles[k]['high']
            peak_idx = k

    # 颈线 = 从峰值向右延伸的倾斜线
    neck_p = (idx_to_x(peak_idx), price_to_y(peak_val))
    # 用峰值和右底后第一个高点定斜率
    after_lm2 = [i for i in local_maxs if i > lm2]
    if after_lm2:
        neck_p2 = (idx_to_x(after_lm2[0]), price_to_y(candles[after_lm2[0]]['high']))
        neck_end = extend_line(neck_p, neck_p2, IMG_W - MARGIN_R + 30)
    else:
        # 水平延伸 (如果找不到第二个点)
        neck_end = (IMG_W - MARGIN_R + 30, neck_p[1])

    dashed_line(neck_p, neck_end, '#FF6B00', w=2, dash=10, gap=6)
    pin_mark(neck_p[0], neck_p[1], f'颈峰{peak_val:.1f}', '#FF6B00', 'top')
    label_box(neck_end[0] - 130, neck_end[1] + 5, '颈线(突破确认)', '#FFF', '#FF6B00CC')

# ─── ④ 绿色虚线: 测幅满足目标 ───
# 通道高度 = 上轨y - 下轨y (在最后一个低点x位置)
if len(ascending_lows) >= 2 and len(ascending_highs) >= 2:
    test_x = idx_to_x(ascending_lows[-1])
    # 下轨在test_x的y值
    low_i1, low_i2 = ascending_lows[0], ascending_lows[-1]
    low_slope = (price_to_y(candles[low_i2]['low']) - price_to_y(candles[low_i1]['low'])) / (idx_to_x(low_i2) - idx_to_x(low_i1)) if idx_to_x(low_i2) != idx_to_x(low_i1) else 0
    lower_y = price_to_y(candles[low_i1]['low']) + low_slope * (test_x - idx_to_x(low_i1))

    # 上轨在test_x的y值
    high_i1, high_i2 = ascending_highs[0], ascending_highs[-1]
    high_slope = (price_to_y(candles[high_i2]['high']) - price_to_y(candles[high_i1]['high'])) / (idx_to_x(high_i2) - idx_to_x(high_i1)) if idx_to_x(high_i2) != idx_to_x(high_i1) else 0
    upper_y = price_to_y(candles[high_i1]['high']) + high_slope * (test_x - idx_to_x(high_i1))

    ch_width_px = abs(upper_y - lower_y)
    # 满足目标: 上轨再向上一个通道宽度
    target_y = upper_y - ch_width_px
    # 在上轨终点位置画
    t_start = (ext_end[0] - 150, int(upper_y - ch_width_px * 0.3))  # 大致位置
    t_end = (ext_end[0], int(target_y))
    # 平行于上轨的绿色虚线
    if len(ascending_highs) >= 2:
        hi1, hi2 = ascending_highs[0], ascending_highs[-1]
        hp1 = (idx_to_x(hi1), price_to_y(candles[hi1]['high']) - ch_width_px)
        hp2 = (idx_to_x(hi2), price_to_y(candles[hi2]['high']) - ch_width_px)
        hp_end = extend_line(hp1, hp2, IMG_W - MARGIN_R + 30)
        dashed_line(hp1, hp_end, '#27AE60', w=2, dash=14, gap=7)

        # 计算目标价格
        # 目标y对应的价格
        target_price = P_MIN + (P_MAX - P_MIN) * (1 - (hp_end[1] - MARGIN_T) / CHART_H)
        label_box(hp_end[0] - 130, hp_end[1] - 22, f'满足目标 ~{target_price:.1f}', '#FFF', '#27AE60CC')

# ─── ⑤ 紫色: 近期加速趋势线 ───
# 最近5根K线如果有明显上升, 画加速线
recent = candles[-10:]
if recent[-1]['close'] > recent[0]['close'] * 1.05:
    ri1 = N - 10
    ri2 = N - 1
    rp1 = (idx_to_x(ri1), price_to_y(candles[ri1]['low']))
    rp2 = (idx_to_x(ri2), price_to_y(candles[ri2]['low']))
    d.line([rp1, rp2], fill='#8E44AD', width=2)
    label_box(rp2[0] + 8, rp2[1] - 6, '加速', '#FFF', '#8E44ADCC')

# ─── ⑥ ATH标注 + 箭头 ───
ath_idx = max(range(N), key=lambda i: candles[i]['high'])
ath_x = idx_to_x(ath_idx)
ath_y = price_to_y(candles[ath_idx]['high'])
# 红色向上箭头
sz = 12
d.polygon([(ath_x, ath_y - sz - 8), (ath_x - sz//2, ath_y - 4), (ath_x + sz//2, ath_y - 4)], fill='#E74C3C')
label_box(ath_x + 10, ath_y - 20, f'ATH {candles[ath_idx]["high"]:.2f}', '#FFF', '#E74C3CCC')

# ─── ⑦ 进场"+"止损"X" ───
# 回踩下轨的位置 (最近的一个局部低点之后)
if ascending_lows:
    last_low_idx = ascending_lows[-1]
    # 找最近一个回踩下轨的位置
    for i in range(last_low_idx + 1, N):
        trend_y = price_to_y(candles[low_i1]['low']) + low_slope * (idx_to_x(i) - idx_to_x(low_i1))
        actual_y = price_to_y(candles[i]['low'])
        if abs(actual_y - trend_y) < 10:  # 接近趋势线
            ex = idx_to_x(i)
            ey = int(trend_y)
            # 画+
            s = 8
            d.line([(ex-s, ey), (ex+s, ey)], fill='#333', width=3)
            d.line([(ex, ey-s), (ex, ey+s)], fill='#333', width=3)
            label_box(ex + 12, ey - 16, '回踩+', '#FFF', '#333333CC')

            # 止损X (下方)
            sx = ex + 15
            sy = ey + 30
            cs = 7
            d.line([(sx-cs, sy-cs), (sx+cs, sy+cs)], fill='#E74C3C', width=3)
            d.line([(sx-cs, sy+cs), (sx+cs, sy-cs)], fill='#E74C3C', width=3)
            label_box(sx + 12, sy - 10, '止损X', '#FFF', '#E74C3CCC')
            break

# ─── ⑧ 四色K线图例 ───
legend_y = IMG_H - 30
legend_x = MARGIN_L
for typ, name, desc in [
    ('red', '强势阳', '收≥开 且 收≥昨收'),
    ('yellow', '假阴线', '收<开 且 收≥昨收'),
    ('green', '假阳线', '收≥开 且 收<昨收'),
    ('blue', '弱势阴', '收<开 且 收<昨收'),
]:
    c = COLOR_MAP[typ]
    d.rectangle([(legend_x, legend_y - 8), (legend_x + 14, legend_y + 6)], fill=c)
    d.text((legend_x + 18, legend_y - 8), f'{name}({desc})', fill='#666', font=f10)
    legend_x += 220

# 统计
type_counts = {t: kline_types.count(t) for t in ['red', 'yellow', 'green', 'blue']}
d.text((MARGIN_L, legend_y - 30), f'四色K线统计: 红{type_counts["red"]} 黄{type_counts["yellow"]} 绿{type_counts["green"]} 蓝{type_counts["blue"]}', fill='#888', font=f11)

# ─── 底部免责 ───
d.text((IMG_W - MARGIN_R - 250, IMG_H - 15), '蔡森划线法 · 点多的为主 · 教学演示', fill='#CCC', font=f10)

# ═══════════════════════════════════════════
# 保存
# ═══════════════════════════════════════════
out = '/Users/weihaoli/Desktop/蔡森 skill/junwei-301458-caisen-full.png'
img.save(out, quality=95)
print(f'\n✅ 已保存: {out}')
print(f'图片尺寸: {IMG_W}x{IMG_H}')
print(f'价格范围: {P_MIN:.2f} ~ {P_MAX:.2f}')
print(f'ATH: {candles[ath_idx]["date"]} = {candles[ath_idx]["high"]:.2f}')
print(f'上升低点: {len(ascending_lows)}个, 上升高点: {len(ascending_highs)}个')
