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
import time

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
        self._x0, self._y = 8, height // 2          # 轨道范围与中心线
        self._moved = False
        # 按数值文本在该字体下的实际宽度预留右侧数值区，避免不同字体/DPI 下数字被截断
        try:
            _fnt = tkfont.Font(font=font)
        except Exception:
            _fnt = None

        def _m(t):
            return _fnt.measure(t) if _fnt is not None else len(t) * 8

        if self._res >= 1:
            sample = max(str(int(round(self._to))), str(int(round(self._frm))), key=len)
        else:
            sample = "%.2f" % max(abs(self._frm), abs(self._to))
        self._val_w = _m(sample) + 12
        super().__init__(master, width=self._len + 20 + self._val_w, height=height,
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
        # 圆形滑钮：底部浅灰衬影 + 白色主体 + 细描边（更有质感的小圆钮）
        tx = self._x0 + frac * self._len
        self.create_oval(tx - 8, cy - 6, tx + 8, cy + 10,
                         fill="#E4E4EA", outline="")
        self.create_oval(tx - 7, cy - 8, tx + 7, cy + 8,
                         fill="#FFFFFF", outline="#B9BAC5", width=1)
        # 右侧数值（分辨率 >=1 显示整数，否则两位小数；左对齐防止右侧被截断）
        if self._res >= 1:
            txt = "%d" % int(round(self.get()))
        else:
            txt = "%.2f" % self.get()
        self.create_text(x1 + 10, cy, text=txt, anchor="w",
                         fill=COLORS["SUB"], font=self._font)

class RoundRadio(tk.Canvas):
    """macOS 风格圆形单选钮（替代系统原生小黑点圆钮）：
    未选中 = 浅灰圆环；悬停 = 蓝色圆环；选中 = 蓝色实心圆 + 白色圆点；
    点击即选中并写入 variable（外部 set 时同步刷新），可携带 command 回调"""

    def __init__(self, master, text="", variable=None, value=0,
                 command=None, font=None, height=24):
        self._var = variable
        self._val = value
        self._cmd = command
        self._font = font
        self._text = text
        self._hover = False
        try:
            t_w = tkfont.Font(font=font).measure(text)
        except Exception:
            t_w = len(text) * 10
        width = 24 + t_w             # 圆圈(20px) + 文字（含间距留白）
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=master["bg"],
                         cursor="hand2")
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Configure>", lambda e: self._draw())
        if variable is not None:
            variable.trace_add("write", lambda *a: self._draw())   # 外部变更同步
        self._draw()

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _on_click(self, _e):
        if self._var is not None:
            self._var.set(self._val)
        if self._cmd is not None:
            self._cmd()

    def _draw(self):
        self.delete("all")
        h = max(self.winfo_height(), 24)
        cy = h // 2
        sel = self._var is not None and self._var.get() == self._val
        if self._hover:                          # 悬停：蓝色圆环
            self.create_oval(2, cy - 8, 18, cy + 8, outline="#4FA8FF", width=1.5)
        elif not sel:                            # 未选中：浅灰圆环
            self.create_oval(2, cy - 8, 18, cy + 8, outline="#C7C7CC", width=1.5)
        else:                                    # 选中：蓝色实心圆 + 白色圆点
            self.create_oval(2, cy - 8, 18, cy + 8, fill="#0A84FF", outline="")
            self.create_oval(7.5, cy - 2.5, 12.5, cy + 2.5, fill="#FFFFFF", outline="")
        self.create_text(24, cy, text=self._text, anchor="w",
                         fill=COLORS["TEXT"], font=self._font)


import numpy as np
from scipy.io import wavfile
from scipy.signal import wiener, resample

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib import rcParams
from matplotlib.ticker import MaxNLocator

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
        # 按屏幕实际可用尺寸夹取窗口大小，避免窗口高于屏幕导致底部状态栏被挤出可视区
        self._scr_w = self.winfo_screenwidth()
        self._scr_h = self.winfo_screenheight()
        self.geometry("%dx%d" % (min(1500, self._scr_w - 40),
                                 min(880, self._scr_h - 90)))
        self.minsize(1100, 620)      # 最终最小尺寸在界面构建完成后按内容实际宽度重新设定
        # 按屏幕实际 DPI 设置 Tk 缩放，避免高分辨率屏界面发虚
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        # Tk 缩放系数（高分屏 >1）：winfo_width 给的是“Tk 单位”，
        # 换算成真实物理像素必须乘它，否则 matplotlib 图形会小于画布
        try:
            self._tk_scale = float(self.tk.call("tk", "scaling"))
        except Exception:
            self._tk_scale = 1.0
        self.configure(bg=self.C_BG)
        self._setup_fonts()
        self._btn_full = 400    # 左侧面板卡片内通栏按钮宽度（像素，构建完成后按面板实际宽度更新）
        self._full_btns = []    # 通栏按钮列表（面板宽度确定后统一调整宽度）
        self._fig_redraw_id = None   # 绘图区缩放重排防抖定时器

        self.fs = 16000            # 当前采样率
        self.original = None       # 原始语音 float64 数组
        self.noisy = None          # 加噪信号
        self.denoised = None       # 去噪信号
        self._rec_cancel = False   # 取消录音标志
        self._rec_timer_id = None   # 采集倒计时 after 句柄
        self._rec_until = 0.0       # 本段采集的结束时刻（time.time()）
        self._rec_var = tk.StringVar(value="采集空闲")   # ①卡片内采集状态提示（倒计时）
        self.status_var = tk.StringVar(value="请先【生成测试音频】/【开始采集】/【打开音频】")

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

    def _radio(self, parent, text, var, value, size=10, command=None):
        """macOS 风格圆形单选钮（Canvas 自绘，替代系统原生小黑点）"""
        return RoundRadio(parent, text=text, variable=var, value=value, command=command,
                          font=self.F(size))

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

        # ---------------- 左侧控制面板（可滚动，宽度按内容自动适配） ----------------
        # 面板可滚动：窗口缩小时内容不再被裁切，滚轮即可查看下半部分
        ctrl_wrap = tk.Frame(body, width=560, bg=self.C_BG)
        ctrl_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(12, 6), pady=10)
        ctrl_wrap.pack_propagate(False)
        self._ctrl_canvas = tk.Canvas(ctrl_wrap, bg=self.C_BG, highlightthickness=0)
        self._ctrl_scroll = tk.Scrollbar(ctrl_wrap, orient=tk.VERTICAL, width=10,
                                         command=self._ctrl_canvas.yview, bg="#D9D9E0",
                                         troughcolor=self.C_BG, bd=0, highlightthickness=0,
                                         activebackground=self.C_SUB)
        self._ctrl_canvas.configure(yscrollcommand=self._ctrl_scroll.set)
        self._ctrl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._ctrl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ctrl = tk.Frame(self._ctrl_canvas, bg=self.C_BG)
        self._ctrl_window = self._ctrl_canvas.create_window((0, 0), window=ctrl, anchor="nw")
        # 内容高度变化时更新滚动范围；画布宽度变化时内容窗口跟随
        ctrl.bind("<Configure>",
                  lambda e: self._ctrl_canvas.configure(scrollregion=self._ctrl_canvas.bbox("all")))
        self._ctrl_canvas.bind("<Configure>",
                               lambda e: self._ctrl_canvas.itemconfigure(
                                   self._ctrl_window, width=e.width))
        self._cards_ref = []    # 用于构建完成后测量内容实际需求宽度

        # ① 语音采集 / 文件读写
        f1 = self._card(ctrl, "①　语音采集 / 读写")
        f1.pack(fill=tk.X, pady=(0, 10))
        self._cards_ref.append(f1)
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
        # 采集状态提示（● 圆点 + 倒计时）：采集中红色闪烁并显示剩余秒数，替代被挤出的底部状态栏
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(4, 2))
        self._rec_dot = tk.Label(row, text="●", bg=self.C_CARD, fg="#C7C7CC",
                                 font=(self.f_cn, 8))
        self._rec_dot.pack(side=tk.LEFT)
        self._rec_lab = tk.Label(row, textvariable=self._rec_var, bg=self.C_CARD,
                                 fg=self.C_SUB, font=self.F(10))
        self._rec_lab.pack(side=tk.LEFT, padx=(4, 0))
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=11, pady=(2, 8))
        self._btn(row, "打开音频文件", self.open_audio).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "保存当前信号WAV", self.save_signal).pack(side=tk.LEFT, padx=6)
        self._btn(row, "生成测试音频", self.gen_test).pack(side=tk.LEFT, padx=6)

        # ② 语音播放
        f2 = self._card(ctrl, "②　语音播放")
        f2.pack(fill=tk.X, pady=(0, 12))
        self._cards_ref.append(f2)
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
        self._cards_ref.append(f3)
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
        _b = self._btn(f3.inner, "执行加噪", self.do_add_noise, width=self._btn_full)
        _b.pack(padx=11, pady=(4, 8))
        self._full_btns.append(_b)

        # ④ 去噪
        f4 = self._card(ctrl, "④　去噪（3 种算法）")
        f4.pack(fill=tk.X, pady=(0, 12))
        self._cards_ref.append(f4)
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
        _b = self._btn(f4.inner, "执行去噪", self.do_denoise, width=self._btn_full)
        _b.pack(padx=11, pady=(6, 8))
        self._full_btns.append(_b)

        # ⑤ 效果分析
        f5 = self._card(ctrl, "⑤　去噪效果分析（SNR / MSE）")
        f5.pack(fill=tk.X, pady=(0, 12))
        self._cards_ref.append(f5)
        # 指标记录区：加高文本框并配竖向滚动条，指标多行时滚动查看，不再被截断
        mrow = tk.Frame(f5.inner, bg=self.C_CARD)
        mrow.pack(fill=tk.X, padx=11, pady=(6, 0))
        self._metrics_scroll = tk.Scrollbar(mrow, orient=tk.VERTICAL, width=10,
                                            bg="#D9D9E0", troughcolor=self.C_CARD, bd=0,
                                            highlightthickness=0, activebackground=self.C_SUB)
        self._metrics_text = tk.Text(mrow, height=8, wrap="word", relief=tk.FLAT, bd=0,
                                     bg="#FAFAFC", fg=self.C_TEXT, font=self.F(10, eng=True),
                                     highlightthickness=0, padx=8, pady=6,
                                     state=tk.DISABLED, cursor="arrow",
                                     yscrollcommand=self._metrics_scroll.set)
        self._metrics_scroll.config(command=self._metrics_text.yview)
        self._metrics_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._metrics_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        _b = self._btn(f5.inner, "更新频谱对比图", self.update_plots, primary=True,
                      width=self._btn_full)
        _b.pack(padx=11, pady=(0, 8))
        self._full_btns.append(_b)

        # ---------------- 右侧绘图区 ----------------
        right = self._card(body, "时域波形与 FFT 频谱分析")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14), pady=12)
        fig_dpi = max(100, int(self.winfo_fpixels("1i")))   # 按屏幕 DPI 提高图表分辨率
        # 初始图形尺寸取偏小值：随后 <Configure> 回调会按画布真实大小重设，
        # 保证 2×2 子图（含全部坐标轴文字）始终完整可见、不再被画布裁掉下半部分
        self.fig = Figure(figsize=(6.0, 4.6), dpi=fig_dpi)
        self.axes = self.fig.subplots(2, 2)
        # 固定比例边距（分数制）：任何画布尺寸都按比例缩放、永远生效。
        # 不用 tight_layout —— 高缩放屏幕下其最小边距计算会失败(警告且不排版)，
        # 导致子图/刻度文字挤成一团
        self._apply_fig_margins()
        self.canvas = FigureCanvasTkAgg(self.fig, master=right.inner)
        self._fig_master = right.inner          # 画布重建时的父容器
        self.canvas.get_tk_widget().configure(bg=self.C_CARD, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        # 画布尺寸变化：图形按画布实际像素重设尺寸并防抖重排，子图随窗口缩放始终填满且完整
        self.canvas.get_tk_widget().bind("<Configure>", self._on_canvas_resize)

        # 状态栏（macOS 风格细线分隔）
        tk.Frame(self, bg=self.C_LINE, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(self, textvariable=self.status_var, anchor="w", bg=self.GLASS,
                 fg=self.C_OK, font=self.F(10), padx=12, pady=5).pack(side=tk.BOTTOM, fill=tk.X)

        # ---- 面板宽度按内容实际需求自适应（高 DPI 下字体变宽也不截断控件） ----
        self.update_idletasks()
        need = 470
        for _c in self._cards_ref:
            need = max(need, _c.winfo_reqwidth() + 2)
        ctrl_w = min(620, max(470, need))       # 面板宽度上限 620，避免挤压绘图区
        ctrl_wrap.configure(width=ctrl_w + 12)  # +12 = 竖向滚动条宽度
        self._btn_full = ctrl_w - 24 - 22       # 通栏按钮铺满卡片内容区
        self.update_idletasks()
        for _b in self._full_btns:
            _b.configure(width=self._btn_full)
            _b._draw(_b._fill)                  # 立即按新宽度重绘
        self.minsize(min(ctrl_w + 800, self._scr_w - 40),
                      min(640, self._scr_h - 90))   # 最小尺寸不超过屏幕可用范围
        # 面板内任意位置滚轮滚动（内容超过面板高度时）
        self._bind_wheel_recursive(ctrl)

        self.update_plots()
        # 首次布局完成后重建一次画布：首屏即以真实尺寸渲染，避免初始位图尺寸不匹配
        self.after(300, self._rebuild_fig_canvas)

    # ------------------------- 面板滚轮滚动 / 绘图区自适应 -------------------------

    def _bind_wheel_recursive(self, w):
        """给面板容器及其全部子孙控件绑定滚轮，悬停任意位置都能滚动面板"""
        w.bind("<MouseWheel>", self._on_panel_wheel)   # Windows / macOS
        w.bind("<Button-4>", self._on_panel_wheel)     # Linux 滚轮向上
        w.bind("<Button-5>", self._on_panel_wheel)     # Linux 滚轮向下
        for child in w.winfo_children():
            self._bind_wheel_recursive(child)

    def _on_panel_wheel(self, e):
        """滚轮滚动左侧控制面板"""
        if getattr(e, "num", None) == 5 or getattr(e, "delta", 0) < 0:
            steps = 2
        else:
            steps = -2
        self._ctrl_canvas.yview_scroll(steps, "units")

    def _on_canvas_resize(self, e):
        """画布尺寸变化：图形像素与画布物理像素不一致时，重设图形尺寸并防抖重建画布
        （重建后 matplotlib 首帧即生成正确尺寸的位图，兼容各版本，杜绝“显示不全/空白”）"""
        if e.width < 40 or e.height < 40:
            return
        if getattr(self, "_last_fig_px", None) == (e.width, e.height):
            return                       # 同尺寸重复事件直接跳过
        self._last_fig_px = (e.width, e.height)
        try:
            _dpi = self.fig.dpi
            _w_px = e.width * self._tk_scale   # Tk 单位 → 物理像素
            _h_px = e.height * self._tk_scale
            fig_w, fig_h = self.fig.get_size_inches()
            if abs(fig_w * _dpi - _w_px) < 3 and abs(fig_h * _dpi - _h_px) < 3:
                return                   # 已等大，无需重建
            self.fig.set_size_inches(_w_px / _dpi, _h_px / _dpi, forward=False)
        except Exception:
            pass
        if self._fig_redraw_id:
            try:
                self.after_cancel(self._fig_redraw_id)
            except Exception:
                pass
        self._fig_redraw_id = self.after(180, self._rebuild_fig_canvas)

    def _apply_fig_margins(self):
        """固定比例边距：左/右/上/下与行列间距均为图形分数，
        任何窗口尺寸下都按比例生效，刻度文字不会互相挤占"""
        self.fig.subplots_adjust(left=0.09, right=0.985, top=0.90, bottom=0.09,
                                 wspace=0.24, hspace=0.42)

    def _rebuild_fig_canvas(self):
        """重建绘图画布：销毁旧 TkAgg 部件后按当前图形尺寸新建并绑定。
        对比手动重建 PhotoImage，此方式在任何 matplotlib 版本下都稳定。"""
        self._fig_redraw_id = None
        try:
            old = self.canvas
            try:
                old.get_tk_widget().destroy()
            except Exception:
                pass
            self.canvas = FigureCanvasTkAgg(self.fig, master=self._fig_master)
            widget = self.canvas.get_tk_widget()
            widget.configure(bg=self.C_CARD, highlightthickness=0)
            widget.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
            widget.bind("<Configure>", self._on_canvas_resize)
            self._apply_fig_margins()
            self.canvas.draw()
        except Exception:
            pass        # 关窗等场景的残留回调忽略

    def _fig_tight(self):
        self._fig_redraw_id = None
        try:
            self._apply_fig_margins()
            self.canvas.draw()          # 同步完整重绘，避免部分子图残留未渲染
        except Exception:
            pass        # 窗口关闭等场景下的残留回调，忽略即可

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
        # ①卡片内启动倒计时提示：红点闪烁 + 剩余秒数实时刷新
        self._set_rec_state("准备采集…", "#FF9500")
        self._rec_until = time.time() + dur
        if self._rec_timer_id:
            try:
                self.after_cancel(self._rec_timer_id)
            except Exception:
                pass
        self._tick_record()
        # 后台线程录音，避免阻塞 GUI 主线程
        threading.Thread(target=self._record_worker, args=(fs, dur), daemon=True).start()

    # ---- 采集倒计时提示（①卡片内，替代容易被挤出屏幕的底部状态栏） ----

    def _set_rec_state(self, text, dot_color):
        """设置采集状态文字与●圆点颜色"""
        self._rec_var.set(text)
        try:
            self._rec_dot.config(fg=dot_color)
        except Exception:
            pass

    def _tick_record(self):
        """每 100ms 刷新一次剩余倒计时；采集中红点闪烁"""
        self._rec_timer_id = None
        if self._rec_cancel:
            return
        try:
            remain = self._rec_until - time.time()
            if remain <= 0:
                self._set_rec_state("收尾中…", "#FF9500")
                self._rec_timer_id = self.after(120, self._tick_record)
                return
            if int(remain * 2) % 2 == 0:          # 红点 0.5s 间隔闪烁
                dot = "#FF3B30"
            else:
                dot = "#FFD1CE"
            self._set_rec_state("采集中… 剩余 %.1f s" % remain, dot)
            self._rec_timer_id = self.after(100, self._tick_record)
        except Exception:
            pass        # 窗口关闭后的残留回调忽略

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
        if self._rec_timer_id:
            try:
                self.after_cancel(self._rec_timer_id)
            except Exception:
                pass
            self._rec_timer_id = None
        self._set_rec_state("采集已停止", "#FF9500")
        self.status_var.set("采集已停止")

    def _rec_idle_later(self, seconds=3.0):
        """倒计时结束一段时间后恢复空闲态（若期间又开始采集则跳过）"""
        try:
            self.after(int(seconds * 1000), self._rec_idle_after)
        except Exception:
            pass

    def _rec_idle_after(self):
        if self._rec_timer_id is None:
            self._set_rec_state("采集空闲", "#C7C7CC")

    def _apply_recorded(self, x, fs):
        self.original = np.asarray(x, np.float64)
        self.fs = fs
        self.noisy = self.denoised = None
        if self._rec_timer_id:
            try:
                self.after_cancel(self._rec_timer_id)
            except Exception:
                pass
            self._rec_timer_id = None
        self._set_rec_state("采集完成（%.1f s）" % (len(x) / float(fs)), "#2FBF5F")
        self._rec_idle_later(3.0)          # 3 秒后恢复“采集空闲”
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
            # 精简字号：刻度最小、坐标轴标签次之、标题略大，整体排版紧凑不拥挤
            ax.tick_params(axis="both", labelsize=7.5, pad=2, length=3)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.title.set_fontsize(9.5)
            ax.xaxis.label.set_fontsize(8.5)
            ax.yaxis.label.set_fontsize(8.5)
        if self.original is None:
            self.canvas.draw_idle()
            return
        t = np.arange(len(self.original)) / self.fs
        # 2x2 子图布局：上行 = 原始/加噪波形，下行 = 去噪波形/FFT 频谱对比
        ax1, ax2 = self.axes[0]
        ax3, ax4 = self.axes[1]

        ax1.plot(self._thin(t), self._thin(self.original), lw=0.6, color="#1f77b4")
        ax1.set_title("原始信号")
        ax1.set_xlabel("时间(s)")
        ax1.set_ylabel("幅值")

        if self.noisy is not None:
            ax2.plot(self._thin(t), self._thin(self.noisy), lw=0.6, color="#d62728")
        ax2.set_title("加噪信号" if self.noisy is not None else "加噪信号（未生成）")
        ax2.set_xlabel("时间(s)")
        ax2.set_ylabel("幅值")

        if self.denoised is not None:
            ax3.plot(self._thin(t), self._thin(self.denoised), lw=0.6, color="#2ca02c")
        ax3.set_title("去噪信号" if self.denoised is not None else "去噪信号（未生成）")
        ax3.set_xlabel("时间(s)")
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
        ax4.set_title("幅度谱对比")
        ax4.set_xlabel("频率(Hz)")
        ax4.set_ylabel("幅度(dB)")
        ax4.legend(loc="upper right", fontsize=7.5, frameon=False, handlelength=1.6)

        self._apply_fig_margins()   # 固定比例边距排版（任何尺寸稳定生效）
        self.canvas.draw()      # 强制完整重绘，保证全屏/缩放后全部子图渲染完整
        self._update_metrics()

    def _update_metrics(self):
        if self.original is None:
            self._set_metrics([])
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
        self._set_metrics(lines)

    def _set_metrics(self, lines):
        """把指标文本写入⑤卡片滚动记录区（只读文本控件，多行可滚）"""
        try:
            self._metrics_text.config(state=tk.NORMAL)
            self._metrics_text.delete("1.0", tk.END)
            if lines:
                self._metrics_text.insert("1.0", "\n".join(lines))
            self._metrics_text.config(state=tk.DISABLED)
        except Exception:
            pass


def main():
    app = SpeechGUI()
    app.mainloop()


if __name__ == "__main__":
    main()