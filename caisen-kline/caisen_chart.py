# -*- coding: utf-8 -*-
"""
蔡森方法论 · 通用出图模板（全市场适用：A股/港股/美股/期货/汇率/指数/商品）
版式（作者 2026-08-03 定稿）：
  主图  = K线 + 全部标注（标签一律放空白区，远则箭头指向，不覆盖K线）
  副图1 = 成交量
  副图2 = 中文文字分析（结构判定 / 关键价位 / 风险报酬 / 量价论据 / C1-C4）
配色 = A股习惯：涨红跌绿

S7 工程健壮性（P2-1~P2-8）修复均已落地：
  P2-1  render() 不再就地修改入参 levels（深拷贝）
  P2-2  水平线标签防重叠 + 不出界（双向夹边界 + 梯形兜底）
  P2-3  idx_of() 非交易日返回最近交易日，不崩溃
  P2-4  pad 自适应（真实右侧留白占比≥20%），标签不压 K 线
  P2-5  字体探测可用 CJK 字体，换机器不豆腐块
  P2-6  文字副图溢出保护（测量 + 动态缩字号）
  P2-7  footer 标注「非实时快照」（Meta.footer 经 render_signal 落图）
  P2-8  数字写死问题已在动态生成阶段解决，仅残留于 _archive/ 旧单文件 demo
"""
import bisect
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib import font_manager


def _resolve_cn_fonts():
    """探测系统真实可用的中文字体，避免硬编码 macOS 字体导致换机器豆腐块（P2-5）。"""
    candidates = ['Hiragino Sans GB', 'STHeiti', 'PingFang SC', 'Arial Unicode MS',
                  'Songti SC', 'Heiti SC', 'Microsoft YaHei', 'SimHei',
                  'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC',
                  'Source Han Sans SC', 'Heiti TC']
    avail = []
    for name in candidates:
        try:
            font_manager.findfont(name, fallback_to_default=False)
        except Exception:
            continue
        avail.append(name)
    if avail:
        return avail
    # 兜底：扫描系统里任意含 CJK 覆盖的字体
    for f in font_manager.fontManager.ttflist:
        if any(k in f.name for k in ('CJK', 'Hei', 'Song', 'YaHei', 'PingFang',
                                     'Hiragino', 'WenQuanYi', 'Han', 'Gothic', 'Mincho')):
            return [f.name]
    return ['DejaVu Sans']   # 实在没有就退回，至少英文可读


CN_FONTS = _resolve_cn_fonts()
plt.rcParams['font.sans-serif'] = CN_FONTS
plt.rcParams['axes.unicode_minus'] = False

# 字体缺字警告：这些字符在部分中文字体里缺失，写文案时禁用
# U+2212 MINUS SIGN「−」→ 用 ASCII「-」或中文「减」
# 中文等宽字体不存在 → 文字副图禁用 family='monospace'


def _place_levels(ls_, lo, hi, min_gap, pad_y):
    """计算每条水平线标签的 y（数据坐标）。贴近真实价位、互不重叠且在 ylim 内；
    若放不下则退化为均匀梯形（引线指向真实价位）。就地写回 ls_[i]['ly']。

    修复 P2-2：旧实现自下而上扩散循环漏掉末项，最底标签会跑出 ylim 下界。
    """
    n = len(ls_)
    if n == 0:
        return
    avail = hi - lo
    # 贪心：贴近价位 + 双向夹边界、保间距
    ys = [min(max(lv['y'], lo + pad_y), hi - pad_y) for lv in ls_]
    for i in range(1, n):
        if ys[i - 1] - ys[i] < min_gap:
            ys[i] = ys[i - 1] - min_gap
    for i in range(n - 2, -1, -1):
        if ys[i] - ys[i + 1] < min_gap:
            ys[i] = ys[i + 1] + min_gap
        if ys[i] < lo + pad_y:
            ys[i] = lo + pad_y
    # 校验：越界或重叠 → 退化为均匀梯形（保证不出界、不重叠）
    bad = (ys[0] > hi - pad_y) or (ys[-1] < lo + pad_y) or \
          any(ys[i] - ys[i + 1] < min_gap * 0.999 for i in range(n - 1))
    if bad:
        ys = [hi - pad_y - (i + 0.5) / n * (avail - 2 * pad_y) for i in range(n)]
    for lv, y in zip(ls_, ys):
        lv['ly'] = y


def _protect_text_overflow(fig, ax, artists, max_iter=3):
    """文字副图溢出保护（P2-6）：测量左右两栏文本包围盒，若超出面板（底/右界）
    则缩小字号并重绘，最多 max_iter 次；极端长文本兜底截断到 6pt 仍放不下时省略号。"""
    for _ in range(max_iter):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        overflow = False
        for t in artists:
            bb = t.get_window_extent(renderer).transformed(ax.transAxes.inverted())
            if bb.y0 < -0.03 or bb.x1 > 1.03:
                overflow = True
                break
        if not overflow:
            return
        for t in artists:
            t.set_fontsize(max(6.0, t.get_fontsize() * 0.92))
    # 仍溢出：极端长文本兜底，避免静默裁掉整段（截断右栏最后一行）
    for t in artists:
        s = t.get_text()
        if len(s) > 900:
            t.set_text(s[:897] + "\n…（详见文字报告）")


def render(df, meta, levels, events, text_left, text_right, out,
           pad=40, ylim=None, figsize=(17, 15.5), panel_ratios=(6.4, 1.5, 6.0),
           vol_events=None, footer=None, dpi=250, measures=None, plain_arrows=None,
           return_fig=False):
    """
    df          : DataFrame，index=DatetimeIndex，列 open/high/low/close/volume
    meta        : dict(title=..., ylabel='价格', vlabel='成交量（手）')
    levels      : [dict(y=价位, c=颜色, ls=线型, lw=线宽, txt='名称 价位 ← 作用说明', x0=起点x索引)]
                  → 水平线默认画到数据右端（x0 省略=-2 全宽）；设 x0 可让线只从某根 K 线起画
                    （如颈线只从首触点画起，避免延伸到无关左段，P1-2）。标签放右侧空白区，
                    自动防重叠 + 不出界 + 箭头指回（P2-2）。
    events      : [dict(xy=(x索引, y价), xytext=(x索引, y价), txt='①...', fc=底色, ec=边框色)]
                  → K线上的关键点，文字放空白区，箭头指向
    text_left/right : 文字副图左右两栏内容（str，自己控制换行）
    vol_events  : [dict(xy=(x,y), xytext=(x,y), txt=..., c=...)] 成交量副图标注（可选）
    measures    : [dict(x=索引, y0=, y1=, label='H=114', c=颜色)] 垂直双箭头量距标尺（可选）
    plain_arrows: [dict(xy=(x,y), xytext=(x,y), c=, rad=)] 无文字辅助箭头（可选）
    footer      : 图底部一行来源/免责（str）
    """
    n = len(df)
    pad = max(pad, max(40, int(0.25 * (n + 1)) + 1))   # P2-4：真实右侧留白占比≥20%（pad/(n+1+pad)），标签不压 K 线
    fig = plt.figure(figsize=figsize, facecolor='white')
    gs = fig.add_gridspec(3, 1, height_ratios=list(panel_ratios), hspace=0.10,
                          left=0.055, right=0.985, top=0.955, bottom=0.02)
    ax1, ax2, ax3 = fig.add_subplot(gs[0]), None, fig.add_subplot(gs[2])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    mc = mpf.make_marketcolors(up='#e2231a', down='#12a13f', edge='inherit', wick='inherit',
                               volume={'up': '#e2231a', 'down': '#12a13f'})
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', gridcolor='#e0e0e0',
                               facecolor='white', figcolor='white',
                               rc={'font.sans-serif': CN_FONTS})
    mpf.plot(df, type='candle', ax=ax1, volume=ax2, style=style,
             datetime_format='%m/%d', xrotation=0, warn_too_much_data=10 ** 6)

    ax1.set_xlim(-2, n - 1 + pad)
    ax2.set_xlim(-2, n - 1 + pad)
    if ylim:
        ax1.set_ylim(*ylim)
    else:
        # 主图上/下留白带：标注只许落在空白横带，绝不插进 K 线中部（项目硬约束 2026-08-04）
        _kh = float(df["high"].max()); _kl = float(df["low"].min()); _kr = _kh - _kl
        ax1.set_ylim(_kl - _kr * 0.20, _kh + _kr * 0.20)
    ax1.set_ylabel(meta.get('ylabel', '价格'), fontsize=11)
    ax2.set_ylabel(meta.get('vlabel', '成交量'), fontsize=11)
    ax1.set_title(meta['title'], fontsize=15, fontweight='bold', pad=12)
    ax1.tick_params(labelbottom=False)

    line_end, lbl_x = n - 0.5, n + 1.5

    # ---- 水平价位线 + 右侧标签（自动防重叠 + 不出界，P2-1/P2-2） ----
    lo, hi = ax1.get_ylim()
    avail = hi - lo
    min_gap = avail * 0.13
    pad_y = avail * 0.02
    lvls = [dict(d) for d in levels]          # P2-1：深拷贝，绝不污染调用方入参
    ls_ = sorted(lvls, key=lambda d: -d['y'])
    _place_levels(ls_, lo, hi, min_gap, pad_y)   # P2-2：防重叠 + 不出界（含梯形兜底）
    for lv in ls_:
        # S10 颈线带 / S11 套牢区：中线条目带 band 键时，先画浅色带区(axhspan)，中线叠在其上
        if lv.get('band'):
            lo_b, hi_b = lv['band']
            ax1.axhspan(lo_b, hi_b, color=lv.get('band_c', lv.get('c', '#1565c0')),
                        alpha=0.10, zorder=0, lw=0)
        x0 = lv.get('x0', -2)   # S4(P1-2)：颈线只从首触点画起，不延伸到无关左段
        ax1.plot([x0, line_end], [lv['y']] * 2, color=lv['c'],
                 ls=lv.get('ls', '--'), lw=lv.get('lw', 1.4), zorder=1)
        # 标签与线同高时用直线连接，避免 angle 连接样式退化告警
        cs = 'arc3,rad=0' if abs(lv['ly'] - lv['y']) < 1e-6 else 'angle,angleA=0,angleB=90,rad=4'
        ax1.annotate(lv['txt'], xy=(line_end, lv['y']), xytext=(lbl_x, lv['ly']),
                     fontsize=9.6, color=lv['c'], va='center', ha='left',
                     bbox=dict(boxstyle='round,pad=0.35', fc='white', ec=lv['c'], lw=1.0, alpha=0.95),
                     arrowprops=dict(arrowstyle='-|>', color=lv['c'], lw=1.1, shrinkA=0, shrinkB=2,
                                     connectionstyle=cs))

    # ---- K线关键点：文字放空白区 + 箭头指向 ----
    for ev in events:
        ann = ax1.annotate(ev['txt'], xy=ev['xy'], xytext=ev['xytext'],
                     fontsize=ev.get('fs', 9.8), ha='left', va='center', color='#222222',
                     bbox=dict(boxstyle='round,pad=0.4', fc=ev.get('fc', '#f5f5f5'),
                               ec=ev.get('ec', '#666666'), lw=1.2),
                     arrowprops=dict(arrowstyle='-|>', color=ev.get('ec', '#666666'), lw=1.4,
                                     connectionstyle=f"arc3,rad={ev.get('rad', 0.15)}"))
        ann._ev = True   # 标记：要点标注框（自检只验这些）

    # ---- 无文字辅助箭头（如颈线第二取样点） ----
    for pa in (plain_arrows or []):
        ax1.annotate('', xy=pa['xy'], xytext=pa['xytext'],
                     arrowprops=dict(arrowstyle='-|>', color=pa.get('c', '#1565c0'),
                                     lw=pa.get('lw', 1.4),
                                     connectionstyle=f"arc3,rad={pa.get('rad', 0)}"))

    # ---- 垂直双箭头量距标尺（形态高度 H / 等幅段） ----
    for m in (measures or []):
        ax1.annotate('', xy=(m['x'], m['y1']), xytext=(m['x'], m['y0']),
                     arrowprops=dict(arrowstyle='<|-|>', color=m.get('c', '#2e7d32'), lw=1.3))
        ax1.text(m['x'] - 1.2, (m['y0'] + m['y1']) / 2, m['label'], color=m.get('c', '#2e7d32'),
                 fontsize=10, rotation=90, va='center', ha='right', fontweight='bold')

    # ---- 成交量副图标注 ----
    for ve in (vol_events or []):
        ax2.annotate(ve['txt'], xy=ve['xy'], xytext=ve['xytext'], fontsize=9.5,
                     color=ve.get('c', '#e2231a'), va='center',
                     arrowprops=dict(arrowstyle='-|>', color=ve.get('c', '#e2231a'), lw=1.3))
    vm = df['volume'].mean()
    ax2.axhline(vm, color='#888888', ls=':', lw=1.0)
    ax2.text(n + 0.5, vm, f'区间均量 {vm:.0f}', fontsize=9, color='#666666', va='center')

    # ---- 副图2：中文文字分析 ----
    ax3.axis('off')
    ax3.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax3.transAxes,
                                fc='#fafafa', ec='#cccccc', lw=1.0, zorder=0))
    t_left = ax3.text(0.012, 0.965, text_left, transform=ax3.transAxes, fontsize=10.2,
                      va='top', ha='left', linespacing=1.62, color='#1a1a1a')
    t_right = ax3.text(0.505, 0.965, text_right, transform=ax3.transAxes, fontsize=10.2,
                       va='top', ha='left', linespacing=1.62, color='#1a1a1a')
    ax3.plot([0.497, 0.497], [0.04, 0.97], transform=ax3.transAxes, color='#cccccc', lw=1.0)
    _protect_text_overflow(fig, ax3, [t_left, t_right])   # P2-6

    if footer:
        fig.text(0.5, 0.005, footer, ha='center', fontsize=9.5, color='#777777')

    if return_fig:
        return fig
    fig.savefig(out, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def idx_of(df, date_str):
    """把日期转成 K 线 x 索引；非交易日（周末/节假日）返回最近交易日索引，不崩溃（P2-3）。"""
    idx = list(df.index)
    ts = pd.Timestamp(date_str)
    try:
        return idx.index(ts)
    except ValueError:
        pos = bisect.bisect_left(idx, ts)
        if pos <= 0:
            return 0
        if pos >= len(idx):
            return len(idx) - 1
        before, after = idx[pos - 1], idx[pos]
        return (pos - 1) if (ts - before) <= (after - ts) else pos
