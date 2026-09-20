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
from matplotlib.patches import Rectangle


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


def _protect_text_overflow(fig, ax, artists, max_iter=4):
    """文字副图溢出保护（P2-6）：测量左右两栏文本包围盒，若超出面板（底/右界）
    则缩小字号并重绘，最多 max_iter 次；极端长文本兜底**按整行**截断（不再从
    897 字符中间硬切，避免把一整句结论切掉半句 —— 2026-09-20 修正）。"""
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
    # 仍溢出：按整行兜底截断（保留完整句子 + 明确指向 .md 报告）
    for t in artists:
        s = t.get_text()
        if len(s) > 900:
            keep, acc = [], 0
            for ln in s.split("\n"):
                if keep and acc + len(ln) + 1 > 880:
                    break
                keep.append(ln)
                acc += len(ln) + 1
            t.set_text("\n".join(keep) + "\n…（本栏过长，完整文字见同名 .md 报告）")


# ===================================================================
# 四色K线渲染层（作者 2026-09-20 定稿：蔡森出图固定配色）
#   颜色 = EMA12/EMA50 四色状态（红=多头强势/黄=多头回调/蓝=空头反弹/绿=空头弱势）
#   实心 = 收阴，空心 = 收阳（保留「涨跌」维度，颜色专管「阵营」维度）
#   mplfinance 不支持逐根任意配色 → 自绘 K 线与量柱
# ===================================================================

def _four_color_plan(df, trend):
    """把趋势状态转成逐根 (颜色, 透明度) 列表；暖机区降透明度如实标注。

    两档淡化：暖机区（前 116 根）轻淡化 0.72 —— 标出低置信但颜色仍清楚；
    数据根数 < 暖机根数时（全图无一根可信）重淡化 0.45 + 图例红字警讯。
    不淡化到 0.42 那种程度：作者要的是「每次画图都用这个配色」，图不能整体发白。
    """
    import caisen_trend as T
    n = len(df)
    st = list(trend['state'].values)
    wu = int(trend['warmup'])
    short = bool(trend.get('data_short'))
    cols, alphas = [], []
    for i in range(n):
        cols.append(T.STATE_COLOR.get(st[i], '#9e9e9e'))
        if short:
            alphas.append(T.DATA_SHORT_ALPHA)
        else:
            alphas.append(T.WARMUP_ALPHA if i < wu else 1.0)
    return cols, alphas


def _draw_candles_manual(ax, df, cols, alphas, hollow_up=True):
    n = len(df)
    o = df['open'].astype(float).values
    h = df['high'].astype(float).values
    l = df['low'].astype(float).values
    c = df['close'].astype(float).values
    for i in range(n):
        col, a = cols[i], alphas[i]
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.9, alpha=a, zorder=3,
                solid_capstyle='round')
        oi, ci = o[i], c[i]
        bot, top = (oi, ci) if ci >= oi else (ci, oi)   # bot ≤ top（2026-09-20 修正取反 bug）
        if top - bot <= 1e-12:                      # 一字/平盘：画细横线
            ax.plot([i - 0.30, i + 0.30], [ci, ci], color=col, lw=1.2,
                    alpha=a, zorder=3)
            continue
        face = 'white' if (hollow_up and ci >= oi) else col
        ax.add_patch(Rectangle((i - 0.32, bot), 0.64, top - bot, facecolor=face,
                               edgecolor=col, lw=1.0, alpha=a, zorder=4))


def _draw_volume_manual(ax, df, cols, alphas, vol_ma=5):
    """量柱与 K 线同色（量价同语言），叠加量能均线（放量/缩量的判定基准）。"""
    v = df['volume'].astype(float)
    for i, x in enumerate(v.values):
        ax.bar(i, float(x), width=0.64, color=cols[i], alpha=alphas[i], lw=0, zorder=3)
    if vol_ma and vol_ma > 1:
        ma = v.rolling(int(vol_ma), min_periods=1).mean()
        ax.plot(range(len(df)), ma.values, color='#546e7a', lw=1.2, ls='--',
                zorder=5, label=f'量MA{int(vol_ma)}')
    return float(v.max())


def _draw_trend_overlay(fig, ax1, ax2, df, trend, flips=True, hollow_up=True,
                        vol_ma=5, data_short=False):
    """EMA 双线 + 暖机区分隔 + 侧切换标记 + 图例（放在主图与量图之间的空白带）。"""
    import caisen_trend as T
    n = len(df)
    ax1.plot(range(n), trend['ema_fast'].values, color=T.EMA_FAST_COLOR,
             lw=1.4, zorder=6)
    # EMA50 用紫色：避免与「空头反弹蓝」同色混淆（原 Pine 脚本 slow 为 blue）
    ax1.plot(range(n), trend['ema_slow'].values, color=T.EMA_SLOW_COLOR,
             lw=1.6, zorder=6)

    wu = int(trend['warmup'])
    if 0 < wu < n:
        for ax in (ax1, ax2):
            ax.axvline(wu - 0.5, color='#9e9e9e', ls='--', lw=1.0, alpha=0.75, zorder=1)

    # 侧切换（多空阵营翻转，已过滤噪声）→ 分别在下方/上方空白带画三角，不压K线
    kl = float(df['low'].min()); kh = float(df['high'].max()); kr = max(kh - kl, 1e-9)
    if flips:
        for fp in trend['flips']:
            i = int(fp['i'])
            if i < 0 or i >= n:
                continue
            if fp['to'] == 'bull':
                ax1.scatter([i], [kl - kr * 0.085], marker='^', s=52,
                            facecolor=T.STATE_COLOR['R'], edgecolor='white',
                            lw=0.7, zorder=7)
            else:
                ax1.scatter([i], [kh + kr * 0.085], marker='v', s=52,
                            facecolor=T.STATE_COLOR['G'], edgecolor='white',
                            lw=0.7, zorder=7)

    # 图例带：主图与量图之间的空白（不压K线、不与其他标注争位）
    # 位置按真实版面算（fig 坐标），不靠拍脑袋的 axes 偏移，避免两行叠在一起
    p1, p2 = ax1.get_position(), ax2.get_position()
    gap_lo, gap_hi = p2.y1, p1.y0
    y1_ = gap_lo + (gap_hi - gap_lo) * 0.42
    y2_ = gap_lo + (gap_hi - gap_lo) * 0.02
    l1 = T.LEGEND_LINE.replace('─ EMA12  ─ EMA50', '─EMA12(橙) ─EMA50(紫)')
    fig.text(p1.x0 + 0.002, y1_, l1, fontsize=8.6, color='#37474f',
             va='bottom', ha='left')
    vm_ratio = f'｜量MA{int(vol_ma)}（灰虚线）为放量/缩量基准' if vol_ma and vol_ma > 1 else ''
    if data_short:
        l2 = (f'【警讯】数据仅 {n} 根 < EMA50 暖机需 {wu} 根：全线颜色仅示意，'
              f'建议取数 ≥ {wu + 120} 根{vm_ratio}')
        c2 = '#c62828'
    else:
        l2 = (f'│ 虚线以左 {wu} 根为 EMA50 暖机区（半透明，颜色仅供参考）'
              f'｜三角 = 多空阵营侧切换（已过滤 <3 根噪声）{vm_ratio}')
        c2 = '#78909c'
    fig.text(p1.x0 + 0.002, y2_, l2, fontsize=8.0, color=c2, va='bottom', ha='left')



def render(df, meta, levels, events, text_left, text_right, out,
           pad=40, ylim=None, figsize=(17, 16.2), panel_ratios=(6.3, 1.5, 6.5),
           vol_events=None, footer=None, dpi=250, measures=None, plain_arrows=None,
           return_fig=False, four_color=True, ema_fast=12, ema_slow=50,
           hollow_up=True, vol_ma=5, trend_flips=True, trend=None):
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

    四色层（作者 2026-09-20 定稿，默认开启，见 caisen_trend）：
    four_color  : True → 自绘 K 线/量柱并按 EMA12/EMA50 四色着色（默认）
                  False → 退回原 mplfinance 红绿路径（兼容旧图与回归测试）
    ema_fast/slow : 四色判定的两条 EMA 周期（默认与 Pine 脚本一致：12 / 50）
    hollow_up   : True → 阳线空心（白底描边）、阴线实心，保留「涨跌」维度
    vol_ma      : 量能均线周期（放量/缩量判定基准），0/None 关闭
    trend_flips : True → 在下方/上方空白带标注「多空阵营侧切换」三角（已过滤噪声）
    trend       : 可直接传入 caisen_trend.compute() 结果（如用更长历史算出的 EMA，
                  避免暖机失真）；None 则在 df 上现算

    ⚠ 版式微调（2026-09-20，为四色/量价节奏块腾行）：figsize 15.5→16.2、
    panel_ratios (6.4,1.5,6.0)→(6.3,1.5,6.5)。换算后**主图绝对高度不变**
    （6.4/13.9*15.5 ≈ 6.3/14.3*16.2 = 6.67in），只是文字副图加高 10%、画布加高 4.5%。
    这样不破坏「主图尺寸/标注避让」的既有约定，又装得下新增量价行。
    """
    n = len(df)
    pad = max(pad, max(40, int(0.25 * (n + 1)) + 1))   # P2-4：真实右侧留白占比≥20%（pad/(n+1+pad)），标签不压 K 线
    fig = plt.figure(figsize=figsize, facecolor='white')
    gs = fig.add_gridspec(3, 1, height_ratios=list(panel_ratios), hspace=0.10,
                          left=0.055, right=0.985, top=0.955, bottom=0.02)
    ax1, ax2, ax3 = fig.add_subplot(gs[0]), None, fig.add_subplot(gs[2])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    # ---- 四色趋势层：能算则用，算不出（依赖缺失/数据异常）自动退回原路径 ----
    _trend = None
    if four_color:
        try:
            import caisen_trend as _ct
            _trend = trend if trend is not None else _ct.compute(
                df, fast=int(ema_fast), slow=int(ema_slow))
            if len(_trend['state']) != n:
                _trend = None                     # 长度不匹配（如传入异源 trend）→ 退回
        except Exception:
            _trend = None

    if _trend is None:
        mc = mpf.make_marketcolors(up='#e2231a', down='#12a13f', edge='inherit', wick='inherit',
                                   volume={'up': '#e2231a', 'down': '#12a13f'})
        style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', gridcolor='#e0e0e0',
                                   facecolor='white', figcolor='white',
                                   rc={'font.sans-serif': CN_FONTS})
        mpf.plot(df, type='candle', ax=ax1, volume=ax2, style=style,
                 datetime_format='%m/%d', xrotation=0, warn_too_much_data=10 ** 6)
    else:
        import caisen_trend as _ct
        cols, alphas = _four_color_plan(df, _trend)
        vmax = _draw_volume_manual(ax2, df, cols, alphas, vol_ma=vol_ma)
        _draw_candles_manual(ax1, df, cols, alphas, hollow_up=hollow_up)
        for ax in (ax1, ax2):
            ax.grid(True, ls=':', color='#e0e0e0', lw=0.6)
            ax.set_axisbelow(True)
        ax2.set_ylim(0, vmax * 1.18)
        step = max(1, n // 8)
        _tk = list(range(0, n, step))
        ax2.set_xticks(_tk)
        ax2.set_xticklabels([pd.Timestamp(df.index[i]).strftime('%y/%m/%d')
                             for i in _tk], fontsize=9)

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

    # ---- 四色趋势覆盖层（EMA双线/暖机区/侧切换/图例），须在 ylim 定妥后画 ----
    if _trend is not None:
        _draw_trend_overlay(fig, ax1, ax2, df, _trend, flips=trend_flips,
                            hollow_up=hollow_up, vol_ma=vol_ma,
                            data_short=bool(_trend.get('data_short')))

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
                 ls=lv.get('ls', '--'), lw=lv.get('lw', 1.4), zorder=5)
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
    # ⚠ 别加 pil_kwargs={'compress_level':...}：实测会把 PNG 从 1.59MB 抬到 1.81MB
    #   （matplotlib 自带 _png 压缩滤镜比 PIL 更适配这类大量色块的图，2026-09-20 实测）
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
