# -*- coding: utf-8 -*-
"""
============================================================================
 程序 2：语音采集及降噪系统
----------------------------------------------------------------------------
 开发环境：Python 3.x + Tkinter + NumPy / SciPy + sounddevice + PyWavelets
           + matplotlib（频谱图嵌入 GUI）
 依赖安装：pip install numpy scipy matplotlib sounddevice PyWavelets
           （Windows 下 sounddevice 自带 PortAudio，无需额外配置）
----------------------------------------------------------------------------
 功能清单（对照课程设计要求）：
  [1] 语音采集：麦克风录制（可选采样率 / 时长），生成测试音频，读 WAV / 存 WAV
  [2] 语音播放：正常播放、快进(最高2x)、慢放(最低0.25x)、停止，速度滑块可调
  [3] 加噪    ：高斯白噪声（信噪比可调）、脉冲(椒盐)噪声（密度可调）
  [4] 去噪    ：维纳滤波、卡尔曼滤波、小波软阈值去噪（自适应阈值）
  [5] 频谱分析：FFT 幅度谱（dB），原始/加噪/去噪三路频谱同图对比
  [6] 效果分析：SNR / MSE 定量评价 + 信噪比提升量
============================================================================
"""

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont

# =====================================================================
# macOS 风格 UI 主题组件（内置于本文件，无需外部依赖）
#   enable_hidpi()   高 DPI 屏幕适配（Windows 进程级 DPI 感知）
#   pick_fonts()     英文优先 Inter-Medium，中文优先苹方中等(PingFang SC)
#   round_rect()     画布圆角矩形绘制（smooth polygon 逼近）
#   RCard            圆角卡片容器（内容放到 card.inner 中）
#   RoundBtn         圆角扁平按钮（支持悬停/按下反馈、config(text=...)）
#   FlatSlider       扁平圆角滑块（细轨道 + 圆形滑钮 + 右侧数值）
# =====================================================================

import os

# macOS 设计规范：颜色
COLORS = dict(
    BG="#F2F2F7", CARD="#FFFFFF", TEXT="#1D1D1F", SUB="#8E8E93",
    ACCENT="#0A84FF", ACC_D="#0068DA", BTN="#E8E8ED", BTN_D="#D9D9E0",
    LINE="#E3E3E8", OK_GRN="#2FBF5F", CANVAS="#202024", GLASS="#FAFAFC",
)


def enable_hidpi():
    """Windows 高 DPI 屏：设置进程级 DPI 感知，避免 Tk 界面模糊发虚
    （必须在创建 Tk 根窗口之前调用）"""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def pick_fonts(root):
    """返回 (f_en, f_cn)：
    英文优先 Inter-Medium，中文优先苹方中等（PingFang SC Medium），
    字体未安装时按候选列表自动回退"""
    avail = set(tkfont.families(root))

    def pick(candidates, fallback):
        for c in candidates:
            if c in avail:
                return c
        return fallback

    f_en = pick(["Inter-Medium", "Inter Medium", "Inter",
                 "SF Pro Text", "Helvetica Neue", "Segoe UI"], "Arial")
    f_cn = pick(["PingFang SC Medium", "PingFangSC-Medium", "PingFang SC",
                 "Microsoft YaHei UI", "Microsoft YaHei",
                 "Noto Sans CJK SC", "WenQuanYi Micro Hei"], "SimHei")
    return f_en, f_cn


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """在画布上绘制圆角矩形（smooth polygon 逼近圆角）"""
    r = max(2, min(int(r), abs(x2 - x1) // 2, abs(y2 - y1) // 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RCard(tk.Canvas):
    """圆角卡片容器：
    画布底色与父容器一致，白色内容框架带内边距放置其中；
    圆角外露区域透明（露出父底色），视觉上是真正的圆角卡片。
    内容一律加入 card.inner。"""

    def __init__(self, master, fill="#FFFFFF", outline="#E3E3E8",
                 radius=20, pad=12):
        super().__init__(master, highlightthickness=0, bd=0, bg=master["bg"])
        self._fill = fill
        self._outline = outline
        self._rad = radius
        self._pad = pad
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window((pad, pad), window=self.inner, anchor="nw")
        self.bind("<Configure>", self._redraw)
        # 让画布期望尺寸跟随内部内容（Canvas 默认期望约 396x254，否则 grid 布局会被撑大）
        self.inner.bind("<Configure>", self._sync_size)

    def _sync_size(self, _e=None):
        """画布期望尺寸 = 内容框架需求尺寸 + 内边距（供 grid 等按需布位）"""
        self.config(width=self.inner.winfo_reqwidth() + 2 * self._pad,
                    height=self.inner.winfo_reqheight() + 2 * self._pad)

    def _redraw(self, _e=None):
        """画布尺寸变化：重绘圆角背景并同步内容框架尺寸（window item 始终在上层）"""
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        self.delete("rcard_bg")
        round_rect(self, 1, 1, w - 2, h - 2, self._rad,
                   fill=self._fill, outline=self._outline, width=1, tags=("rcard_bg",))
        self.tag_lower("rcard_bg")
        self.coords(self._win, self._pad, self._pad)
        self.itemconfigure(self._win, width=w - 2 * self._pad, height=h - 2 * self._pad)


class RoundBtn(tk.Canvas):
    """圆角扁平按钮（Canvas 绘制）：
    支持主体色/按下色/悬停反馈；config(text=...) 可动态修改文字（如播放/暂停切换）"""

    def __init__(self, master, text="", command=None, primary=False, font=None,
                 width=None, height=30, radius=9, padx=16,
                 fill=None, fill_d=None, fg=None, bold=False):
        if width is None:                       # 未指定宽度：按文字宽度自适应
            try:
                w0 = tkfont.Font(font=font).measure(text)
            except Exception:
                w0 = len(text) * 12
            width = max(44, w0 + 2 * padx)
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=master["bg"],
                         cursor="hand2")
        self._text = text
        self._cmd = command
        self._fill = fill or (COLORS["ACCENT"] if primary else COLORS["BTN"])
        self._fill_d = fill_d or (COLORS["ACC_D"] if primary else COLORS["BTN_D"])
        self._fg = fg or ("#FFFFFF" if primary else COLORS["TEXT"])
        self._font = font
        self._rad = radius
        self._pressed = False
        self.bind("<Enter>", lambda e: self._draw(self._fill_d if self._pressed else self._fill))
        self.bind("<Leave>", lambda e: self._draw(self._fill))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        # 画布首次布局 / 尺寸变化时按真实尺寸重绘；否则创建时画布尚未映射
        # （winfo_width=1），文字会画在左上角出现错位，悬停触发重绘才恢复正常
        self.bind("<Configure>", self._on_configure)
        self._draw(self._fill)

    # ---- 绘制 ----
    def _draw(self, fill):
        self.delete("all")
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        round_rect(self, 1, 1, w - 2, h - 2, self._rad, fill=fill, outline="")
        self.create_text(w // 2, h // 2, text=self._text,
                         fill=self._fg, font=self._font)

    # ---- 尺寸联动 ----
    def _on_configure(self, _e=None):
        """画布尺寸变化（首次布局或窗口缩放）：按当前按压状态用真实尺寸重绘"""
        self._draw(self._fill_d if self._pressed else self._fill)

    # ---- 交互 ----
    def _on_press(self, _e):
        self._pressed = True
        self._draw(self._fill_d)

    def _on_release(self, e):
        was = self._pressed
        self._pressed = False
        self._draw(self._fill)
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            if self._cmd is not None:           # 在按钮范围内松开才触发
                self._cmd()

    def config(self, **kw):
        """支持动态修改 text / command / 配色（tk.config 的使用习惯）"""
        if "text" in kw:
            self._text = kw.pop("text")
        if "command" in kw:
            self._cmd = kw.pop("command")
        if "fg" in kw:
            self._fg = kw.pop("fg")
        if "fill" in kw:
            self._fill = kw.pop("fill")
            if "fill_d" not in kw:
                self._fill_d = self._fill
        if "fill_d" in kw:
            self._fill_d = kw.pop("fill_d")
        self._draw(self._fill)


class FlatSlider(tk.Canvas):
    """扁平圆角滑块：
    细圆头轨道（已走部分为强调蓝）+ 白色圆形滑钮 + 右侧数值；
    拖动实时回写 variable 并触发 command(v)；variable 被外部修改时同步刷新。
    按下事件不做取值（供外部在 ButtonPress 里锁定“拖动前基准值”）"""

    def __init__(self, master, variable=None, from_=0.0, to=1.0, resolution=0.1,
                 length=150, command=None, font=None,
                 track=None, active=None, height=24):
        self._var = variable
        self._frm = float(from_)
        self._to = float(to)
        self._res = float(resolution)
        self._len = int(length)
        self._cmd = command
        self._track = track or COLORS["LINE"]
        self._act = active or COLORS["ACCENT"]
        self._font = font
        self._h = height
        self._x0, self._y = 6, height // 2          # 轨道范围与中心线
        self._moved = False
        super().__init__(master, width=self._len + 56, height=height,
                         highlightthickness=0, bd=0, bg=master["bg"],
                         cursor="hand2")
        if self._var is not None:
            self._var.trace_add("write", lambda *a: self._draw())   # 外部 set 时同步
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self._draw())   # 布局完成后按真实尺寸重绘
        self._draw()

    # ---- 数值换算 ----
    def get(self):
        return float(self._var.get()) if self._var is not None else self._frm

    def _frac(self, x):
        t = (x - self._x0) / max(self._len, 1)
        return min(1.0, max(0.0, t))

    def _commit(self, x):
        frac = self._frac(x)
        v = self._frm + frac * (self._to - self._frm)
        v = min(self._to, max(self._frm, round(v / self._res) * self._res))
        if self._var is not None:
            self._var.set(v)                         # trace 回调负责重绘
        else:
            self._draw()
        if self._cmd is not None:
            self._cmd(v)

    # ---- 交互 ----
    def _on_press(self, e):
        self._moved = False                          # 按下仅记录，不取值（保留拖动前基准）

    def _on_motion(self, e):
        self._moved = True
        self._commit(e.x)

    def _on_release(self, e):
        if not self._moved:                          # 原地点击（无拖动）也定位取值
            self._commit(e.x)
        self._moved = False

    # ---- 绘制 ----
    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), 2)
        frac = (self.get() - self._frm) / max(self._to - self._frm, 1e-9)
        frac = min(1.0, max(0.0, frac))
        x1 = self._x0 + self._len
        cy = self._h // 2
        # 轨道（圆头细条）与已走部分
        round_rect(self, self._x0, cy - 2, x1, cy + 2, 2, fill=self._track, outline="")
        if frac > 1e-4:
            ex = self._x0 + frac * self._len
            round_rect(self, self._x0, cy - 2, ex, cy + 2, 2, fill=self._act, outline="")
        # 白色圆形滑钮
        tx = self._x0 + frac * self._len
        self.create_oval(tx - 8, cy - 8, tx + 8, cy + 8,
                         fill="#FFFFFF", outline="#D0D0D7", width=1)
        # 右侧数值（分辨率 >=1 显示整数，否则两位小数）
        if self._res >= 1:
            txt = "%d" % int(round(self.get()))
        else:
            txt = "%.2f" % self.get()
        self.create_text(x1 + 26, cy, text=txt, anchor="center",
                         fill=COLORS["SUB"], font=self._font)

import numpy as np
from scipy.io import wavfile
from scipy.signal import wiener, resample

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib import rcParams

# macOS 风格绘图字体：中文优先苹方中等、英文优先 Inter-Medium，逐级回退保证跨平台
rcParams["font.sans-serif"] = ["PingFang SC Medium", "PingFang SC", "Inter Medium",
                               "Inter", "Microsoft YaHei", "Noto Sans CJK SC",
                               "WenQuanYi Micro Hei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False
rcParams["axes.facecolor"] = "#FFFFFF"
rcParams["figure.facecolor"] = "#FFFFFF"
rcParams["axes.edgecolor"] = "#E3E3E8"
rcParams["axes.labelcolor"] = "#1D1D1F"
rcParams["text.color"] = "#1D1D1F"
rcParams["xtick.color"] = "#8E8E93"
rcParams["ytick.color"] = "#8E8E93"

try:
    import sounddevice as sd
    HAS_SD = True
except Exception:
    sd = None
    HAS_SD = False

try:
    import pywt
    HAS_PYWT = True
except Exception:
    pywt = None
    HAS_PYWT = False


# ===================== 信号处理算法层（与界面无关，可单独测试） =====================

def add_gaussian_noise(x, snr):
    """按指定信噪比 SNR(dB) 叠加高斯白噪声"""
    p_sig = np.mean(x ** 2)
    p_noise = p_sig / (10.0 ** (snr / 10.0))
    return x + np.sqrt(p_noise) * np.random.randn(len(x))


def add_impulse_noise(x, density):
    """脉冲（椒盐）噪声：随机位置替换为正/负信号峰值"""
    y = x.copy()
    n = len(y)
    idx = np.random.choice(n, int(n * density), replace=False)
    amp = np.abs(y).max()
    y[idx] = amp * np.random.choice([-1.0, 1.0], len(idx))
    return y


def wiener_denoise(x, win=9):
    """
    维纳滤波：最小均方误差准则下的线性滤波（win 为窗长，取奇数），
    输出做增益补偿（保持与原信号相同能量），避免幅度过度衰减。
    """
    win = max(3, int(win) // 2 * 2 + 1)
    y = wiener(x, mysize=win)
    e_in = np.linalg.norm(x)
    e_out = np.linalg.norm(y)
    if e_out > 1e-12:
        y = y * (e_in / e_out)
    return y


def kalman_denoise(x, q=1e-2, r=1e-2):
    """
    一维标量卡尔曼滤波：
    状态模型 x[k]=x[k-1]（信号缓变，平滑先验），观测为带噪信号 z[k]=x[k]+v[k]；
    q 为过程噪声方差（越大越信任观测），r 为观测噪声方差（越大平滑越强）。
    """
    n = len(x)
    out = np.empty(n)
    x_est = 0.0
    p = 1.0
    for k in range(n):
        p = p + q                       # 预测误差协方差
        k_gain = p / (p + r)            # 卡尔曼增益
        x_est = x_est + k_gain * (x[k] - x_est)   # 状态更新
        p = (1.0 - k_gain) * p          # 协方差更新
        out[k] = x_est
    return out


def wavelet_denoise(x, level=3, thr_mult=0.8, wavelet="db4"):
    """
    小波软阈值去噪（自适应阈值）：
    噪声标准差由最高频细节系数中位数估计（σ = MAD/0.6745），
    阈值采用通用阈值 thr = k·σ·√(2lnN) 并乘可调系数 k，逐层软阈值处理。
    """
    # 分解层数不能超过信号长度允许的最大层数，否则 wavedec 会报错
    level = int(min(level, pywt.dwt_max_level(len(x), pywt.Wavelet(wavelet))))
    coeffs = pywt.wavedec(x, wavelet, level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745
    thr = thr_mult * sigma * np.sqrt(2.0 * np.log(len(x)))
    coeffs[1:] = [pywt.threshold(c, thr, mode="soft") for c in coeffs[1:]]
    y = pywt.waverec(coeffs, wavelet)
    return y[:len(x)]


def fft_spectrum(x, fs):
    """FFT 单边幅度谱：返回频率轴 (Hz) 与幅度 (dB)"""
    X = np.fft.rfft(x)
    mag = 20.0 * np.log10(np.abs(X) + 1e-12)
    f = np.fft.rfftfreq(len(x), d=1.0 / fs)
    return f, mag


def snr_db(clean, est):
    """信噪比 (dB)：噪声能量为 0 时返回 999 表示完全恢复"""
    num = np.sum(clean ** 2)
    den = np.sum((clean - est) ** 2)
    return 999.0 if den == 0 else 10.0 * np.log10(num / den)


def mse(clean, est):
    """均方误差"""
    return float(np.mean((clean - est) ** 2))


# ===================== GUI 主界面 =====================

class SpeechGUI(tk.Tk):
    """语音采集及降噪系统主界面（macOS 风格：浅灰底 + 白色卡片 + 扁平按钮 + 系统蓝强调色）"""

    # -------- macOS 设计规范：颜色 --------
    C_BG     = "#F2F2F7"
    C_CARD   = "#FFFFFF"
    C_TEXT   = "#1D1D1F"
    C_SUB    = "#8E8E93"
    C_ACCENT = "#0A84FF"
    C_ACC_D  = "#0068DA"
    C_BTN    = "#E8E8ED"
    C_BTN_D  = "#D9D9E0"
    C_LINE   = "#E3E3E8"
    C_OK     = "#2FBF5F"
    GLASS    = "#FAFAFC"

    def __init__(self):
        enable_hidpi()          # 高 DPI 适配（必须在创建根窗口之前）
        super().__init__()
        self.title("语音采集及降噪系统")
        self.geometry("1500x880")
        self.minsize(1200, 700)
        # 按屏幕实际 DPI 设置 Tk 缩放，避免高分辨率屏界面发虚
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        self.configure(bg=self.C_BG)
        self._setup_fonts()
        self._btn_full = 400    # 左侧面板卡片内通栏按钮宽度（像素）

        self.fs = 16000            # 当前采样率
        self.original = None       # 原始语音 float64 数组
        self.noisy = None          # 加噪信号
        self.denoised = None       # 去噪信号
        self._rec_cancel = False   # 取消录音标志
        self.status_var = tk.StringVar(value="请先【生成测试音频】/【开始采集】/【打开音频】")
        self.metric_var = tk.StringVar(value="")

        self._build_ui()

    # ------------------------- 主题（字体 / 控件工厂） -------------------------

    def _setup_fonts(self):
        """英文优先 Inter-Medium，中文优先苹方中等（PingFang SC Medium），未安装时逐级回退"""
        self.f_en, self.f_cn = pick_fonts(self)

    def F(self, size, bold=False, eng=False):
        """界面字体：整体缩小一档（×0.86 后取整），避免界面字号偏大"""
        s = max(7, int(round(size * 0.86)))
        return (self.f_en if eng else self.f_cn, s, "bold" if bold else "normal")

    def _btn(self, parent, text, command, primary=False, width=None, size=10,
             bold=False, height=30, padx=16):
        """macOS 风格圆角扁平按钮：width 为像素（None=按文字自适应）"""
        return RoundBtn(parent, text=text, command=command, primary=primary,
                        font=self.F(size, bold), width=width, height=height, padx=padx)

    def _lab(self, parent, text, size=10, fg=None, bold=False):
        """文字标签：自动继承父面板底色"""
        return tk.Label(parent, text=text, bg=parent["bg"], fg=fg or self.C_TEXT,
                        font=self.F(size, bold))

    def _slider(self, parent, var, frm, to, res=1.0, length=170, command=None, size=9):
        """macOS 风格扁平圆角滑块：细轨道 + 白色圆滑钮 + 右侧数值"""
        return FlatSlider(parent, variable=var, from_=frm, to=to, resolution=res,
                          length=length, command=command, font=self.F(size, eng=True))

    def _radio(self, parent, text, var, value, size=10):
        """白底单选按钮（卡片内使用）"""
        return tk.Radiobutton(parent, text=text, variable=var, value=value,
                              bg=self.C_CARD, fg=self.C_TEXT, activebackground=self.C_CARD,
                              activeforeground=self.C_ACCENT, selectcolor=self.C_CARD,
                              highlightthickness=0, bd=0, font=self.F(size))

    def _card(self, parent, title=None):
        """白色圆角卡片面板（内容放到 card.inner 中）"""
        card = RCard(parent, fill=self.C_CARD, outline=self.C_LINE, radius=20, pad=12)
        if title:
            tk.Label(card.inner, text=title, bg=self.C_CARD, fg=self.C_TEXT,
                     font=self.F(11, True)).pack(anchor="w", padx=10, pady=(6, 2))
        return card

    # ------------------------- 界面搭建 -------------------------

    def _build_ui(self):
        body = tk.Frame(self, bg=self.C_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # ---------------- 左侧控制面板 ----------------
        ctrl = tk.Frame(body, width=452, bg=self.C_BG)
        ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=(12, 6), pady=10)
        ctrl.pack_propagate(False)

        # ① 语音采集 / 文件读写
        f1 = self._card(ctrl, "①　语音采集 / 读写")
        f1.pack(fill=tk.X, pady=(0, 10))
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(6, 2))
        self._lab(row, "采样率", size=9).pack(side=tk.LEFT)
        self.fs_combo = ttk.Combobox(row, values=["8000", "16000", "44100"],
                                     width=8, state="readonly",
                                     font=self.F(10, eng=True))
        self.fs_combo.current(1)
        self.fs_combo.pack(side=tk.LEFT, padx=8)
        self._lab(row, "时长(s)", size=9).pack(side=tk.LEFT)
        self.dur_var = tk.StringVar(value="3")
        tk.Entry(row, textvariable=self.dur_var, width=6, relief=tk.FLAT, bd=0,
                 highlightthickness=0, bg="#EEEEF2", fg=self.C_TEXT,
                 font=self.F(10, eng=True), insertbackground=self.C_TEXT
                 ).pack(side=tk.LEFT, padx=8, ipady=2)

        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=2)
        self._btn(row, "开始采集", self.start_record, primary=True).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "停止采集", self.stop_record).pack(side=tk.LEFT, padx=6)
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(2, 8))
        self._btn(row, "打开音频文件", self.open_audio).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "保存当前信号WAV", self.save_signal).pack(side=tk.LEFT, padx=6)
        self._btn(row, "生成测试音频", self.gen_test).pack(side=tk.LEFT, padx=6)

        # ② 语音播放
        f2 = self._card(ctrl, "②　语音播放")
        f2.pack(fill=tk.X, pady=(0, 12))
        row = tk.Frame(f2.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(6, 0))
        self._lab(row, "播放源", size=9).pack(side=tk.LEFT)
        self.play_src = tk.IntVar(value=0)
        self._radio(row, "原始", self.play_src, 0).pack(side=tk.LEFT, padx=6)
        self._radio(row, "加噪", self.play_src, 1).pack(side=tk.LEFT, padx=6)
        self._radio(row, "去噪", self.play_src, 2).pack(side=tk.LEFT, padx=6)

        row = tk.Frame(f2.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11)
        self._lab(row, "速度", size=9).pack(side=tk.LEFT)
        self.speed_var = tk.DoubleVar(value=1.0)
        self._slider(row, self.speed_var, 0.25, 2.0, 0.05, 190).pack(side=tk.LEFT, padx=8)

        row = tk.Frame(f2.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(0, 8))
        self._btn(row, "播放", lambda: self._play(self.speed_var.get()), primary=True
                  ).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "停止", self.stop_play).pack(side=tk.LEFT, padx=6)
        self._btn(row, "快进×2", self.play_fast).pack(side=tk.LEFT, padx=6)
        self._btn(row, "慢放×0.5", self.play_slow).pack(side=tk.LEFT, padx=6)

        # ③ 加噪
        f3 = self._card(ctrl, "③　加噪（2 种噪声）")
        f3.pack(fill=tk.X, pady=(0, 12))
        self.noise_type = tk.IntVar(value=0)
        row = tk.Frame(f3.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(6, 0))
        self._radio(row, "高斯白噪声", self.noise_type, 0).pack(side=tk.LEFT)
        self._lab(row, "SNR(dB)", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.snr_var = tk.DoubleVar(value=10.0)
        self._slider(row, self.snr_var, -10, 60, 1, 150).pack(side=tk.LEFT, padx=6)
        row = tk.Frame(f3.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11)
        self._radio(row, "脉冲噪声", self.noise_type, 1).pack(side=tk.LEFT)
        self._lab(row, "密度(%)", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.dens_var = tk.DoubleVar(value=5.0)
        self._slider(row, self.dens_var, 0, 50, 0.5, 150).pack(side=tk.LEFT, padx=6)
        self._btn(f3.inner, "执行加噪", self.do_add_noise, width=self._btn_full).pack(padx=11, pady=(4, 8))

        # ④ 去噪
        f4 = self._card(ctrl, "④　去噪（3 种算法）")
        f4.pack(fill=tk.X, pady=(0, 12))
        self.denoise_type = tk.IntVar(value=0)
        row = tk.Frame(f4.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(6, 0))
        self._radio(row, "维纳", self.denoise_type, 0).pack(side=tk.LEFT)
        self._lab(row, "窗长", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.win_var = tk.IntVar(value=9)
        self._slider(row, self.win_var, 3, 101, 2, 130).pack(side=tk.LEFT, padx=6)
        row = tk.Frame(f4.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11)
        self._radio(row, "卡尔曼", self.denoise_type, 1).pack(side=tk.LEFT)
        self._lab(row, "lgQ", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.kfq_var = tk.DoubleVar(value=-2.0)
        self._slider(row, self.kfq_var, -6.0, -2.0, 0.1, 80).pack(side=tk.LEFT, padx=4)
        self._lab(row, "lgR", size=9).pack(side=tk.LEFT, padx=(8, 0))
        self.kfr_var = tk.DoubleVar(value=-2.0)
        self._slider(row, self.kfr_var, -3.0, 0.0, 0.1, 80).pack(side=tk.LEFT, padx=4)
        row = tk.Frame(f4.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11)
        self._radio(row, "小波", self.denoise_type, 2).pack(side=tk.LEFT)
        self._lab(row, "层数", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.wl_lvl_var = tk.IntVar(value=3)
        self._slider(row, self.wl_lvl_var, 1, 6, 1, 70).pack(side=tk.LEFT, padx=4)
        self._lab(row, "阈值系数", size=9).pack(side=tk.LEFT, padx=(6, 0))
        self.wl_thr_var = tk.DoubleVar(value=0.5)
        self._slider(row, self.wl_thr_var, 0.1, 2.0, 0.1, 80).pack(side=tk.LEFT, padx=4)
        self._btn(f4.inner, "执行去噪", self.do_denoise, width=self._btn_full).pack(padx=11, pady=(6, 8))

        # ⑤ 效果分析
        f5 = self._card(ctrl, "⑤　去噪效果分析（SNR / MSE）")
        f5.pack(fill=tk.X, pady=(0, 12))
        tk.Label(f5.inner, textvariable=self.metric_var, justify=tk.LEFT, anchor="w",
                 bg=self.C_CARD, fg=self.C_TEXT, font=self.F(10, eng=True)
                 ).pack(fill=tk.X, padx=12, pady=6)
        self._btn(f5.inner, "更新频谱对比图", self.update_plots, primary=True,
                  width=self._btn_full).pack(padx=11, pady=(0, 8))

        # ---------------- 右侧绘图区 ----------------
        right = self._card(body, "时域波形与 FFT 频谱分析")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14), pady=12)
        fig_dpi = max(100, int(self.winfo_fpixels("1i")))   # 按屏幕 DPI 提高图表分辨率
        self.fig = Figure(figsize=(9.0, 7.6), dpi=fig_dpi)
        self.axes = self.fig.subplots(2, 2)
        self.fig.subplots_adjust(left=0.07, right=0.97, top=0.93, bottom=0.07,
                                 wspace=0.22, hspace=0.38)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right.inner)
        self.canvas.get_tk_widget().configure(bg=self.C_CARD, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 状态栏（macOS 风格细线分隔）
        tk.Frame(self, bg=self.C_LINE, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(self, textvariable=self.status_var, anchor="w", bg=self.GLASS,
                 fg=self.C_OK, font=self.F(10), padx=12, pady=5).pack(side=tk.BOTTOM, fill=tk.X)

        self.update_plots()

    # ------------------------- 语音采集 -------------------------

    def start_record(self):
        if not HAS_SD:
            messagebox.showerror("缺少依赖", "未安装 sounddevice：pip install sounddevice")
            return
        try:
            fs = int(self.fs_combo.get())
            dur = float(self.dur_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "采集时长必须是数字（秒）")
            return
        self._rec_cancel = False
        self.status_var.set("采集中……（点击【停止采集】结束）")
        # 后台线程录音，避免阻塞 GUI 主线程
        threading.Thread(target=self._record_worker, args=(fs, dur), daemon=True).start()

    def _record_worker(self, fs, dur):
        """录音线程：录完后必须经 after() 回到主线程更新界面（Tk 非线程安全）"""
        try:
            rec = sd.rec(int(dur * fs), samplerate=fs, channels=1, dtype="float32")
            sd.wait()                       # 阻塞直到录满指定时长
            if self._rec_cancel:
                return
            self.after(0, lambda: self._apply_recorded(rec[:, 0], fs))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("采集出错", str(e)))

    def stop_record(self):
        self._rec_cancel = True
        if HAS_SD:
            try:
                sd.stop()
            except Exception:
                pass
        self.status_var.set("采集已停止")

    def _apply_recorded(self, x, fs):
        self.original = np.asarray(x, np.float64)
        self.fs = fs
        self.noisy = self.denoised = None
        self.status_var.set("采集完成：%d 个采样点 @ %d Hz" % (len(x), fs))
        self.update_plots()

    # ------------------------- 文件读写 / 测试音频 -------------------------

    def open_audio(self):
        path = filedialog.askopenfilename(title="选择音频文件",
                                          filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            fs, d = wavfile.read(path)
            if d.ndim > 1:
                d = d.mean(axis=1)          # 立体声转单声道
            x = d.astype(np.float64)
            self.original = x / max(np.abs(x).max(), 1.0)   # 归一化到 [-1,1]
            self.fs = fs
            self.fs_combo.set(str(fs))
            self.noisy = self.denoised = None
            self.status_var.set("已打开: %s（%d 点 @ %d Hz）" %
                                (path.split("/")[-1].split("\\")[-1], len(x), fs))
            self.update_plots()
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def save_signal(self):
        x = self._current_data()
        if x is None:
            messagebox.showwarning("提示", "该信号尚未生成，请先执行相应操作")
            return
        path = filedialog.asksaveasfilename(defaultextension=".wav",
                                            filetypes=[("WAV 音频", "*.wav")])
        if not path:
            return
        y = np.clip(x, -1.0, 1.0)
        wavfile.write(path, self.fs, (y * 32767).astype(np.int16))
        self.status_var.set("已保存: " + path)

    def gen_test(self):
        """合成测试语音：440Hz 基频 + 2/3 次谐波 + 方波 + 轻微噪声"""
        fs = int(self.fs_combo.get())
        dur = 2.0
        t = np.linspace(0, dur, int(fs * dur), endpoint=False)
        s = (0.35 * np.sin(2 * np.pi * 440 * t)
             + 0.25 * np.sin(2 * np.pi * 880 * t)
             + 0.15 * np.sin(2 * np.pi * 1320 * t)
             + 0.10 * np.sign(np.sin(2 * np.pi * 220 * t))
             + 0.02 * np.random.randn(len(t)))
        self.original = s / np.abs(s).max() * 0.8   # 归一化到峰值 0.8，留出响度余量
        self.fs = fs
        self.noisy = self.denoised = None
        self.status_var.set("已生成测试音频（440Hz 基频+谐波+方波）@ %d Hz" % fs)
        self.update_plots()

    # ------------------------- 播放控制 -------------------------

    def _current_data(self):
        """按“播放源”选择返回对应信号"""
        return [self.original, self.noisy, self.denoised][self.play_src.get()]

    def _play(self, speed):
        x = self._current_data()
        if x is None:
            messagebox.showwarning("提示", "该信号尚未生成，请切换播放源或先生成信号")
            return
        if not HAS_SD:
            messagebox.showerror("缺少依赖", "未安装 sounddevice，无法播放")
            return
        try:
            speed = max(0.25, min(2.0, speed))   # 速度限幅在 0.25~2.0 之间（快进/慢放均有上限）
            if speed >= 1:                       # 快进：按整数倍抽点播放，时长缩短
                step = int(round(speed))
                y = x[::step] if step > 1 else x
            else:                                # 慢放：插值重采样拉长信号，时长增加
                y = resample(x, int(len(x) / speed))
            sd.stop()                            # 先停掉上一段声音，避免与本次播放重叠
            sd.play(y.astype(np.float32), self.fs)
            self.status_var.set("正在播放（%.2fx）…" % speed)
        except Exception as e:
            messagebox.showerror("播放出错", str(e))

    def stop_play(self):
        if HAS_SD:
            try:
                sd.stop()
            except Exception:
                pass
        self.status_var.set("已停止播放")

    def play_fast(self):
        self.speed_var.set(2.0)
        self._play(2.0)

    def play_slow(self):
        self.speed_var.set(0.5)
        self._play(0.5)

    # ------------------------- 加噪 / 去噪 -------------------------

    def do_add_noise(self):
        if self.original is None:
            messagebox.showwarning("提示", "请先采集 / 生成 / 打开语音")
            return
        if self.noise_type.get() == 0:
            self.noisy = add_gaussian_noise(self.original, self.snr_var.get())
            self.status_var.set("已加入高斯白噪声（SNR = %.0f dB）" % self.snr_var.get())
        else:
            self.noisy = add_impulse_noise(self.original, self.dens_var.get() / 100.0)
            self.status_var.set("已加入脉冲噪声（密度 = %.1f%%）" % self.dens_var.get())
        self.denoised = None
        self.update_plots()

    def do_denoise(self):
        x = self.noisy if self.noisy is not None else self.original
        if x is None:
            messagebox.showwarning("提示", "请先采集 / 生成 / 打开语音")
            return
        t = self.denoise_type.get()
        try:
            if t == 0:
                self.denoised = wiener_denoise(x, self.win_var.get())
                name = "维纳滤波（窗长 %d）" % self.win_var.get()
            elif t == 1:
                # 滑块显示的是对数刻度 lgQ/lgR，这里换算回线性方差值
                q = 10 ** self.kfq_var.get()
                r = 10 ** self.kfr_var.get()
                self.denoised = kalman_denoise(x, q, r)
                name = "卡尔曼滤波（q=%.0e, r=%.0e）" % (q, r)
            else:
                if not HAS_PYWT:
                    messagebox.showerror("缺少依赖", "未安装 PyWavelets：pip install PyWavelets")
                    return
                self.denoised = wavelet_denoise(x, self.wl_lvl_var.get(),
                                                self.wl_thr_var.get())
                name = "小波去噪（db4, %d 层）" % self.wl_lvl_var.get()
        except Exception as e:
            messagebox.showerror("去噪出错", str(e))
            return
        self.status_var.set(name + " 完成")
        self.update_plots()

    # ------------------------- 绘图与指标 -------------------------

    def _thin(self, x, maxn=4000):
        """波形过长时抽点显示，防止绘图卡顿"""
        s = max(1, len(x) // maxn)
        return x[::s]

    def update_plots(self):
        for ax in self.axes.ravel():
            ax.clear()
            # macOS 风格：白底、浅灰细网格、去掉上/右边框线
            ax.set_facecolor("#FFFFFF")
            ax.grid(True, color="#E3E3E8", linewidth=0.6, alpha=0.7)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        if self.original is None:
            self.canvas.draw_idle()
            return
        t = np.arange(len(self.original)) / self.fs
        # 2x2 子图布局：上行 = 原始/加噪波形，下行 = 去噪波形/FFT 频谱对比
        ax1, ax2 = self.axes[0]
        ax3, ax4 = self.axes[1]

        ax1.plot(self._thin(t), self._thin(self.original), lw=0.6, color="#1f77b4")
        ax1.set_title("原始信号时域波形")
        ax1.set_xlabel("时间 (s)")
        ax1.set_ylabel("幅值")

        if self.noisy is not None:
            ax2.plot(self._thin(t), self._thin(self.noisy), lw=0.6, color="#d62728")
        ax2.set_title("加噪信号时域波形" if self.noisy is not None else "加噪信号（未生成）")
        ax2.set_xlabel("时间 (s)")
        ax2.set_ylabel("幅值")

        if self.denoised is not None:
            ax3.plot(self._thin(t), self._thin(self.denoised), lw=0.6, color="#2ca02c")
        ax3.set_title("去噪信号时域波形" if self.denoised is not None else "去噪信号（未生成）")
        ax3.set_xlabel("时间 (s)")
        ax3.set_ylabel("幅值")

        # FFT 频谱对比（去噪前后）
        f, mag = fft_spectrum(self.original, self.fs)
        ax4.plot(f, mag, lw=0.8, color="#1f77b4", label="原始")
        if self.noisy is not None:
            f2, mag2 = fft_spectrum(self.noisy, self.fs)
            ax4.plot(f2, mag2, lw=0.6, color="#d62728", alpha=0.8, label="加噪")
        if self.denoised is not None:
            f3, mag3 = fft_spectrum(self.denoised, self.fs)
            ax4.plot(f3, mag3, lw=0.6, color="#2ca02c", alpha=0.9, label="去噪后")
        ax4.set_title("FFT 幅度谱对比（去噪前后）")
        ax4.set_xlabel("频率 (Hz)")
        ax4.set_ylabel("幅度 (dB)")
        ax4.legend(loc="upper right", fontsize=8)

        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()
        self._update_metrics()

    def _update_metrics(self):
        if self.original is None:
            self.metric_var.set("")
            return
        lines = ["采样率: %d Hz   点数: %d" % (self.fs, len(self.original))]
        if self.noisy is not None:
            lines.append("加噪后  SNR = %7.2f dB   MSE = %.5f" %
                         (snr_db(self.original, self.noisy), mse(self.original, self.noisy)))
        if self.denoised is not None:
            sn2 = snr_db(self.original, self.denoised)
            lines.append("去噪后  SNR = %7.2f dB   MSE = %.5f" %
                         (sn2, mse(self.original, self.denoised)))
            if self.noisy is not None:
                lines.append("信噪比提升 = %+6.2f dB" % (sn2 - snr_db(self.original, self.noisy)))
        elif self.noisy is not None:
            lines.append("（去噪后效果：请先执行去噪）")
        self.metric_var.set("\n".join(lines))


def main():
    app = SpeechGUI()
    app.mainloop()


if __name__ == "__main__":
    main()