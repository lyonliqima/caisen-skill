#!/usr/bin/env python3
"""蔡森划线法 v4 — 纯倾斜线 + pattern-recognizer风格 + 简洁标注"""

from PIL import Image, ImageDraw, ImageFont
import os, math, sys

CAISEN_ROOT = os.environ.get('CAISEN_ROOT') or os.path.dirname(os.path.abspath(__file__))

# ─── 加载原图 ───
# 原写死的 Qoder 缓存截图（截屏2026-06-17 21.35.44）已不随仓库分发，改为命令行传入
if len(sys.argv) > 1:
    src = sys.argv[1]
else:
    sys.exit('用法: caisen_draw.py <源K线截图路径>')
img = Image.open(src).convert('RGBA')
ov = Image.new('RGBA', img.size, (0,0,0,0))
d = ImageDraw.Draw(ov)
W, H = img.size  # 910 x 371

# ─── 字体 ───
def gf(sz):
    for p in ['/System/Library/Fonts/PingFang.ttc','/System/Library/Fonts/STHeiti Medium.ttc']:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except: pass
    return ImageFont.load_default()
f12=gf(12); f10=gf(10); f14=gf(14); f16=gf(16)

# ═══════════════════════════════════════════
# 坐标校准
# 60.98→y136, 54.76→y192, slope=-9.03 px/$
# y = 684.13 - 9.03*price
# x: Feb1→75, +5.73px/day, +172px/month
# ═══════════════════════════════════════════
def p2y(p): return int(684.13 - 9.03*p)
def d2x(m,day=15): return int(75 + (m-2)*172 + (day-1)*5.73)
CHART_BOT = 338; CHART_RIGHT = 855

# 颜色
BLK=(0,0,0,220)
RED=(220,20,20,220)
GRN=(0,160,50,210)
PUR=(130,50,180,200)
ORG=(255,107,0,220)
W_=(255,255,255,255)
BB=(0,0,0,170); BR=(200,20,20,180); BG=(0,140,40,180); BO=(200,80,0,180); BP=(110,40,160,180)

def clamp_y(y): return max(20, min(CHART_BOT, y))

def arrow(d,x,y,dir,c,sz=14):
    if dir=='up': d.polygon([(x,y-sz),(x-sz//2,y),(x+sz//2,y)],fill=c)
    elif dir=='down': d.polygon([(x,y+sz),(x-sz//2,y),(x+sz//2,y)],fill=c)

def lbl(d,pos,txt,font,f=W_,b=BB,pad=3):
    bb=font.getbbox(txt); tw,th=bb[2]-bb[0],bb[3]-bb[1]
    x,y=pos
    if b: d.rounded_rectangle([x-pad,y-pad,x+tw+pad,y+th+pad],radius=3,fill=b)
    d.text((x,y),txt,fill=f,font=font)

def pin(d, x, y, label, color, pos="bottom"):
    """标记点: 小圆圈+标签"""
    r = 4
    d.ellipse([(x-r,y-r),(x+r,y+r)], fill=color, outline=W_, width=1)
    if label:
        bb = f10.getbbox(label)
        tw = bb[2] - bb[0]
        if pos == "bottom":
            d.text((x - tw//2, y + r + 3), label, fill=color, font=f10)
        else:
            d.text((x - tw//2, y - r - 13), label, fill=color, font=f10)

def dashed(d,p1,p2,c,w=2,dash=10,gap=6):
    x1,y1=p1;x2,y2=p2;dx=x2-x1;dy=y2-y1;L=math.sqrt(dx*dx+dy*dy)
    if L==0:return
    dx/=L;dy/=L;pos=0
    while pos<L:
        e=min(pos+dash,L)
        d.line([(x1+dx*pos,y1+dy*pos),(x1+dx*e,y1+dy*e)],fill=c,width=w)
        pos+=dash+gap

def extend_line(p1, p2, x_end):
    """从p1经过p2延伸到x_end"""
    if p2[0] == p1[0]: return (x_end, p2[1])
    slope = (p2[1]-p1[1])/(p2[0]-p1[0])
    return (x_end, int(p1[1] + slope*(x_end - p1[0])))

# ═══════════════════════════════════════════════════════════
# 蔡森划线 (参考炒股app pattern-recognizer.ts)
#
# 方法: findLocalMins → 连接低点画上升倾斜趋势线
#       findLocalMaxs → 连接高点画阻力倾斜线
#       颈线 = 连接峰值的倾斜虚线
#       所有线都是对角线, 由2个数据点定义
# ═══════════════════════════════════════════════════════════

# ── 局部低点 (Local Mins) ──
LM1 = (d2x(2,5),  clamp_y(p2y(33.5)))   # Feb低点
LM2 = (d2x(3,28), clamp_y(p2y(31.25)))  # 绝对低点
LM3 = (d2x(4,15), clamp_y(p2y(38.0)))   # 4月回调
LM4 = (d2x(5,12), clamp_y(p2y(42.0)))   # 5月回调

# ── 局部高点 (Local Maxs) ──
LH1 = (d2x(2,20), clamp_y(p2y(37.0)))   # Feb反弹高
LH2 = (d2x(4,25), clamp_y(p2y(44.0)))   # 4月底高
LH3 = (d2x(5,28), clamp_y(p2y(49.0)))   # 5月底高

# ═══════════════════════════════════════
# ① 黑色粗线: 上升趋势支撑线 (下轨)
# 连接 LM2(31.25) → LM4(42): 3个触点的线
# ═══════════════════════════════════════
slope_low = (LM4[1]-LM2[1])/(LM4[0]-LM2[0])

# 往左延伸到LM1验证
ext_left = (LM1[0], int(LM2[1] + slope_low*(LM1[0]-LM2[0])))
ext_left = (ext_left[0], clamp_y(ext_left[1]))

# 往右延伸到图表末端
ext_right = extend_line(LM2, LM4, CHART_RIGHT)
ext_right = (ext_right[0], clamp_y(ext_right[1]))

# 画线: 左延伸 → LM2 → LM4 → 右延伸
d.line([ext_left, LM2], fill=BLK, width=3)
d.line([LM2, LM4], fill=BLK, width=3)
d.line([LM4, ext_right], fill=BLK, width=2)

# pin标注低点
pin(d, LM2[0], LM2[1], "31.25", BLK, "bottom")
pin(d, LM3[0], LM3[1], "38", BLK, "bottom")
pin(d, LM4[0], LM4[1], "42", BLK, "bottom")

# 标签
lbl(d, (ext_right[0]-100, clamp_y(ext_right[1])-20), '上升趋势线', f12, W_, BB)

# ═══════════════════════════════════════
# ② 红色倾斜线: 通道阻力线 (上轨)
# 连接 LH1(37) → LH3(49): 3个触点
# ═══════════════════════════════════════
slope_high = (LH3[1]-LH1[1])/(LH3[0]-LH1[0])

# 延伸到图表右端
ext_high_right = extend_line(LH1, LH3, CHART_RIGHT)
ext_high_right = (ext_high_right[0], clamp_y(ext_high_right[1]))

d.line([LH1, LH3], fill=RED, width=2)
d.line([LH3, ext_high_right], fill=RED, width=2)

# pin标注高点
pin(d, LH1[0], LH1[1], "37", RED, "top")
pin(d, LH2[0], LH2[1], "44", RED, "top")
pin(d, LH3[0], LH3[1], "49", RED, "top")

lbl(d, (ext_high_right[0]-80, clamp_y(ext_high_right[1])-20), '阻力线', f12, W_, BR)

# ═══════════════════════════════════════
# ③ 橙色虚线: W底颈线
# 左底LM1(33.5) + 右底LM2(31.25)
# 峰值在两底之间: ~2/25, 价格37
# ═══════════════════════════════════════
neck_peak = (d2x(2,25), clamp_y(p2y(37.0)))
neck_right = extend_line(LM2, neck_peak, CHART_RIGHT)
neck_right = (neck_right[0], clamp_y(neck_right[1]))
dashed(d, neck_peak, neck_right, ORG, w=2, dash=8, gap=5)
pin(d, neck_peak[0], neck_peak[1], "颈峰", ORG, "top")
lbl(d, (neck_right[0]-110, clamp_y(neck_right[1])-20), '颈线(突破确认)', f10, W_, BO)

# ═══════════════════════════════════════
# ④ 绿色虚线: 测幅满足目标
# 通道宽度 = 上轨y - 下轨y (在同x位置)
# 满足 = 上轨再往上移一个通道宽度
# ═══════════════════════════════════════
mid_x = LH3[0]
lower_y_at_mid = int(LM2[1] + slope_low*(mid_x-LM2[0]))
upper_y_at_mid = LH3[1]
ch_w = abs(upper_y_at_mid - lower_y_at_mid)
# 目标线起点和终点
target_start = (LH3[0], clamp_y(LH3[1] - ch_w))
target_end = (CHART_RIGHT, clamp_y(LH3[1] - ch_w + slope_high*(CHART_RIGHT-LH3[0])))
dashed(d, target_start, target_end, GRN, w=2, dash=12, gap=6)
# 目标价格
target_p = 49 + (49 - 42)  # 约56
lbl(d, (target_end[0]-100, clamp_y(target_end[1])-18), '带量目标~56', f12, W_, BG)

# ═══════════════════════════════════════
# ⑤ 紫色: 近期加速通道
# LH3(49) → 6/4 ATH 58.99
# ═══════════════════════════════════════
ATH_jun4 = (d2x(6,4), clamp_y(p2y(58.99)))
d.line([LH3, ATH_jun4], fill=PUR, width=2)
# 平行支撑: 从LM4(42)画平行线
para_end = (ATH_jun4[0], int(LM4[1] + (ATH_jun4[1]-LH3[1])/(ATH_jun4[0]-LH3[0])*(ATH_jun4[0]-LM4[0])))
para_end = (para_end[0], clamp_y(para_end[1]))
d.line([LM4, para_end], fill=PUR, width=1)
lbl(d, (ATH_jun4[0]+5, ATH_jun4[1]+5), '加速', f10, W_, BP)

# ═══════════════════════════════════════
# ⑥ ATH标注 + 红色箭头
# ═══════════════════════════════════════
ath_x = d2x(6,17)
ath_y = clamp_y(p2y(65.82))
arrow(d, ath_x-3, ath_y-3, 'up', RED, 14)
lbl(d, (ath_x+12, ath_y-8), '65.82', f12, W_, BR)

# ═══════════════════════════════════════
# ⑦ 进场"+"止损"X"
# ═══════════════════════════════════════
# 回踩下轨的位置 (约6/8)
entry_x = d2x(6,8)
entry_y = int(LM2[1] + slope_low*(entry_x-LM2[0]))
entry_y = clamp_y(entry_y)
sz=7
d.line([(entry_x-sz,entry_y),(entry_x+sz,entry_y)], fill=W_, width=3)
d.line([(entry_x,entry_y-sz),(entry_x,entry_y+sz)], fill=W_, width=3)
lbl(d,(entry_x+10,entry_y-14), '回踩+', f10, W_, BB)

# 止损: 下轨下方约3%
stop_x = entry_x + 12
stop_y = clamp_y(entry_y + 25)
csz=6
d.line([(stop_x-csz,stop_y-csz),(stop_x+csz,stop_y+csz)], fill=RED, width=3)
d.line([(stop_x-csz,stop_y+csz),(stop_x+csz,stop_y-csz)], fill=RED, width=3)
lbl(d,(stop_x+10,stop_y-8), '止损X', f10, W_, BR)

# ═══════════════════════════════════════
# ⑧ 涨幅标注
# ═══════════════════════════════════════
lbl(d,(d2x(4,10), clamp_y(p2y(46))), '+110.6%', f14, (0,220,60,255), BB)

# ═══ 底部免责 ═══
lbl(d,(d2x(5,20), H-24), '蔡森划线法 · 点多的为主 · 教学演示', f10, (180,180,180,200), BB)

# ─── 合并 & 保存 ───
result = Image.alpha_composite(img, ov)
out = os.path.join(CAISEN_ROOT, 'junwei-301458-caisen-lines.png')
result.save(out, quality=95)
print(f'✅ {out}')
print(f'下轨: LM2(31.25)→LM4(42), slope={slope_low:.3f}')
print(f'上轨: LH1(37)→LH3(49), slope={slope_high:.3f}')
print(f'通道宽度(px): {ch_w}')
print(f'颈线: peak({neck_peak})→右延伸')
print(f'加速通道: LH3(49)→ATH58.99')
