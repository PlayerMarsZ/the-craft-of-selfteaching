# -*- coding: utf-8 -*-
"""
============================================================================
 程序 1：病理细胞图像分割系统
----------------------------------------------------------------------------
 开发环境：Python 3.x + Tkinter + NumPy / SciPy + OpenCV-Python + Pillow
 依赖安装：pip install numpy scipy opencv-python pillow
----------------------------------------------------------------------------
 功能清单（对照课程设计要求）：
  [1] 基础操作  ：灰度化、缩放、旋转、裁剪、窗宽窗位调节（滑块动态预览）
  [2] 图像增强  ：标准中值滤波、自适应中值滤波、高斯滤波去噪（3 种）
  [3] 边缘提取  ：Sobel、Prewitt、Roberts、Laplacian、LoG、Canny（6 种）
  [4] 图像分割  ：Otsu 阈值分割、自适应分水岭分割（2 种）
                 + 创新方法：组合式自适应分割（中值+Otsu+分水岭）
  [5] 结果输出  ：原图与处理结果同屏对比、多算法结果网格对比、
                 保存当前结果 / 保存处理前后对比图
============================================================================
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
import numpy as np
from PIL import Image, ImageTk
from scipy import ndimage

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
        # 白色圆形滑钮
        tx = self._x0 + frac * self._len
        self.create_oval(tx - 8, cy - 8, tx + 8, cy + 8,
                         fill="#FFFFFF", outline="#D0D0D7", width=1)
        # 右侧数值（分辨率 >=1 显示整数，否则两位小数；左对齐防止右侧被截断）
        if self._res >= 1:
            txt = "%d" % int(round(self.get()))
        else:
            txt = "%.2f" % self.get()
        self.create_text(x1 + 10, cy, text=txt, anchor="w",
                         fill=COLORS["SUB"], font=self._font)

try:
    import cv2          # Canny 边缘与分水岭分割依赖 OpenCV
    HAS_CV2 = True
except Exception:
    cv2 = None
    HAS_CV2 = False


# ===================== 图像处理算法层（与界面无关，可单独测试） =====================

def to_gray(img):
    """彩色图转灰度图：亮度加权平均法"""
    if img.ndim == 2:
        return img
    return (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.uint8)


def make_sample_cells(size=512, n_cells=16):
    """生成模拟细胞病理切片图（用于无图演示，纯 PIL 实现）"""
    from PIL import ImageDraw
    img = Image.new("RGB", (size, size), (232, 238, 244))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(1)
    for _ in range(n_cells):
        cx = float(rng.integers(60, size - 60))
        cy = float(rng.integers(60, size - 60))
        r = float(rng.integers(22, 52))
        # 细胞质（椭圆）
        d.ellipse([cx - r, cy - r * 0.85, cx + r, cy + r * 0.85],
                  outline=(95, 112, 152), fill=(152, 172, 202))
        # 细胞核（深色圆）
        nr = r * 0.45
        d.ellipse([cx - nr, cy - nr, cx + nr, cy + nr],
                  outline=(30, 42, 72), fill=(45, 58, 98))
    arr = np.array(img)
    # 加入少量脉冲噪点，贴近病理切片图像
    n_noise = 350
    yy = rng.integers(0, size, n_noise)
    xx = rng.integers(0, size, n_noise)
    arr[yy, xx] = rng.integers(0, 256, (n_noise, 3))
    return arr


def image_resize(img, scale):
    """按比例缩放图像（双三次插值）"""
    pil = Image.fromarray(img)
    w = max(1, int(pil.width * scale))
    h = max(1, int(pil.height * scale))
    return np.array(pil.resize((w, h), Image.BICUBIC))


def image_rotate(img, angle):
    """绕中心旋转 angle 度（自动扩展画布，空白处填黑）"""
    pil = Image.fromarray(img)
    return np.array(pil.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=0))


def window_level(img, center, width):
    """
    窗宽窗位调节（医学影像 CT 窗技术）：
    把灰度区间 [center-width/2, center+width/2]（窗）线性拉伸映射到 [0,255]。
    center 为窗位，width 为窗宽。
    """
    g = to_gray(img).astype(np.float64)
    low = center - width / 2.0
    high = center + width / 2.0
    out = (g - low) * 255.0 / max(high - low, 1e-6)
    return np.clip(out, 0, 255).astype(np.uint8)


def median_denoise(img, size=3):
    """标准中值滤波去噪（增强方法 1）"""
    if img.ndim == 3:
        return np.stack([ndimage.median_filter(img[..., c], size=size)
                         for c in range(3)], axis=2).astype(np.uint8)
    return ndimage.median_filter(img, size=size).astype(np.uint8)


def gaussian_denoise(img, sigma=1.5):
    """高斯低通滤波去噪（增强方法 2）"""
    if img.ndim == 3:
        return np.stack([ndimage.gaussian_filter(img[..., c], sigma)
                         for c in range(3)], axis=2).astype(np.uint8)
    return ndimage.gaussian_filter(img, sigma).astype(np.uint8)


def adaptive_median_filter(img, smax=7):
    """
    自适应中值滤波（增强方法 3）：
    A 级判断：窗口内 Zmin < Zmed < Zmax 成立则转 B 级，否则增大窗口尺寸；
              窗口达到最大 Smax 仍不满足时输出 Zmed（抑制强脉冲）。
    B 级判断：Zmin < Zxy < Zmax 成立则输出 Zxy（保留原像素细节），
              否则输出 Zmed（滤除脉冲噪声）。
    该算法在去噪的同时比标准中值滤波更好地保留边缘细节。
    """
    gray = to_gray(img)
    h, w = gray.shape
    pad = smax // 2
    p = np.pad(gray, pad, mode="reflect")
    out = np.empty_like(gray)
    sizes = list(range(3, smax + 1, 2))
    for i in range(h):
        for j in range(w):
            zxy = gray[i, j]
            result = zxy
            for s in sizes:
                r = s // 2
                win = p[i:i + s, j:j + s]
                zmin = win.min()
                zmed = np.median(win)
                zmax = win.max()
                if zmin < zmed < zmax:                 # A 级通过 → B 级
                    result = zxy if zmin < zxy < zmax else zmed
                    break
                else:                                   # 窗口继续增大
                    result = zmed
            out[i, j] = result
    return out.astype(np.uint8)


# --------------------------- 边缘提取（6 种） ---------------------------

def _convolve(gray, kernel):
    """2D 卷积（float64，无边界填充）"""
    return ndimage.convolve(gray, kernel)


def _norm8(x):
    return np.clip(x, 0, 255).astype(np.uint8)


def edge_sobel(img):
    """Sobel 算子：一阶微分，抗噪能力较强"""
    g = to_gray(img).astype(np.float64)
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], float)
    ky = kx.T
    return _norm8(np.hypot(_convolve(g, kx), _convolve(g, ky)))


def edge_prewitt(img):
    """Prewitt 算子：一阶微分，计算简单"""
    g = to_gray(img).astype(np.float64)
    kx = np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], float)
    ky = kx.T
    return _norm8(np.hypot(_convolve(g, kx), _convolve(g, ky)))


def edge_roberts(img):
    """Roberts 交叉梯度算子：2x2 模板，定位精度高、对噪声敏感"""
    g = to_gray(img).astype(np.float64)
    k1 = np.array([[1, 0], [0, -1]], float)
    k2 = np.array([[0, 1], [-1, 0]], float)
    return _norm8(np.abs(_convolve(g, k1)) + np.abs(_convolve(g, k2)))


def edge_laplacian(img):
    """Laplacian 二阶微分算子：各向同性，对孤立点响应强"""
    g = to_gray(img).astype(np.float64)
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], float)
    return _norm8(np.abs(_convolve(g, k)))


def edge_log(img, sigma=2.0):
    """LoG（高斯拉普拉斯）：先高斯平滑抑制噪声，再做二阶微分"""
    g = to_gray(img).astype(np.float64)
    lap = ndimage.gaussian_laplace(g, sigma)
    m = np.abs(lap)
    if m.max() > 0:
        lap = lap / m.max() * 255.0
    return _norm8(np.abs(lap))


def edge_canny(img, low=50, high=150):
    """Canny 边缘检测：高斯平滑+梯度非极大值抑制+双阈值连接"""
    if not HAS_CV2:
        raise RuntimeError("Canny 边缘检测需要 OpenCV：pip install opencv-python")
    return cv2.Canny(to_gray(img), low, high)


# --------------------------- 图像分割 ---------------------------

def otsu_threshold(img):
    """
    Otsu 最大类间方差法自动阈值分割：
    遍历 256 级灰度，取使前景/背景类间方差最大的灰度作为阈值 T。
    """
    g = to_gray(img)
    hist = np.bincount(g.ravel(), minlength=256).astype(np.float64)
    p = hist / hist.sum()                   # 各级灰度出现概率
    omega = np.cumsum(p)                    # 前景累积概率
    mu = np.cumsum(p * np.arange(256))      # 累积灰度期望
    mu_t = mu[-1]                           # 全局灰度均值
    sigma_b = np.zeros(256)
    for t in range(1, 256):
        w0 = omega[t]                       # 前景占比
        if w0 == 0.0 or w0 == 1.0:
            continue                        # 前后景为空时类间方差无意义
        m0 = mu[t] / w0                     # 前景均值
        m1 = (mu_t - mu[t]) / (1.0 - w0)    # 背景均值（1-w0 为背景占比）
        # 类间方差 σ_B² = w0·w1·(m0-m1)²，取最大值对应的灰度即为最佳阈值
        sigma_b[t] = w0 * (1.0 - w0) * (m0 - m1) ** 2
    T = int(np.argmax(sigma_b))
    binary = (g > T) * 255
    return binary.astype(np.uint8), T


def otsu_foreground(img):
    """
    Otsu 粗分割并自动选择前景极性：
    病理图像中细胞既可能是深色（H&E 染色）也可能是亮色（荧光/反相），
    对象通常占面积较小的那一侧，因此取面积小的一侧为前景（255=对象）。
    若两侧面积都太小（近纯色图）则取大的一侧，避免掩膜为空。
    """
    g = to_gray(img)
    _, T = otsu_threshold(g)
    bright = (g > T)
    dark = ~bright
    fg = dark if dark.mean() <= bright.mean() else bright
    if fg.mean() < 0.005:
        fg = ~fg
    return np.uint8(fg) * 255


def watershed_segment(img, fg_coef=0.35):
    """
    自适应分水岭分割（标准 marker-based 流程 + 噪声稳健性改进）：
    1) Otsu 自动极性粗分割得到对象掩膜（自适应，无需人工设阈值）；
    2) 开运算去细噪声 → 去除面积过小的碎块 → 膨胀确定背景（sure_bg）；
    3) 对【二值掩膜】做距离变换（对象中心距离最大），
       按距离最大值的比例自适应确定前景标记（fg_coef 越大标记越少）；
       若标记过多（纹理噪声强）则自动提高阈值，把种子数控制在合理范围；
    4) 分水岭变换在平滑灰度图上生长；合并面积过小的最终区域到相邻主区域；
    输出随机着色分割图，红色线为边界，背景为浅灰。
    """
    if not HAS_CV2:
        raise RuntimeError("分水岭分割需要 OpenCV：pip install opencv-python")
    gray = to_gray(img)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    mask = otsu_foreground(gray)        # 255=对象（Otsu 自适应极性）
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    opening = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)   # 去细噪声
    # 去除面积过小的碎块（与图像尺寸自适应），避免纹理噪声产生成百上千个小区域
    min_area = max(25, int(gray.size * 0.0001))
    n0, lab0, stats0, _ = cv2.connectedComponentsWithStats(opening, 8)
    filtered = np.zeros_like(opening)
    for i in range(1, n0):
        if stats0[i, cv2.CC_STAT_AREA] >= min_area:
            filtered[lab0 == i] = 255
    opening = filtered
    sure_bg = cv2.dilate(opening, kernel, iterations=3)                      # 确定背景
    # 对二值掩膜做距离变换：对象中心处距离最大，是可靠的前景标记位置
    dist = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
    if dist.max() <= 0:
        edge = cv2.Canny(mask, 80, 160)          # 掩膜为空：用 Otsu 轮廓兜底
        vis = np.zeros(gray.shape + (3,), np.uint8)
        vis[:] = (250, 250, 250)
        vis[edge > 0] = (0, 0, 255)
        return vis, 0
    # 自适应阈值：按距离图最大值的比例确定前景，避免人为设定绝对阈值
    th = fg_coef * dist.max()
    _, sure_fg = cv2.threshold(dist, th, 255, cv2.THRESH_BINARY)
    sure_fg = sure_fg.astype(np.uint8)
    # 标记数量自适应控制：种子过多说明纹理噪声强，二分提高阈值（至多 0.95）把种子数压到 64 以内
    n_seeds = cv2.connectedComponents(sure_fg)[0] - 1
    if n_seeds > 64:
        lo, hi = fg_coef, 0.95
        for _ in range(14):
            mid = (lo + hi) / 2.0
            _, sf = cv2.threshold(dist, mid * dist.max(), 255, cv2.THRESH_BINARY)
            # threshold 对 float32 距离图返回 float32，而 connectedComponents 要求 8 位整型
            cnt = cv2.connectedComponents(np.uint8(sf))[0] - 1
            if cnt > 64:
                lo = mid
            else:
                hi, sure_fg = mid, np.uint8(sf)
    n, markers = cv2.connectedComponents(sure_fg)
    if n <= 1:                  # 前景系数过高未找到标记时，用 Otsu 轮廓作兜底显示
        edge = cv2.Canny(mask, 80, 160)
        vis = np.zeros(gray.shape + (3,), np.uint8)
        vis[:] = (250, 250, 250)
        vis[edge > 0] = (0, 0, 255)
        return vis, 0
    unknown = cv2.subtract(sure_bg, sure_fg)   # 对象边缘带：待分水岭竞争分配
    markers = markers + 1                 # 背景标记为 1
    markers[unknown == 255] = 0           # 未知区域标记为 0
    # 在平滑灰度图上运行分水岭：未知区域由背景与各前景标记竞争生长
    markers = cv2.watershed(cv2.cvtColor(blur, cv2.COLOR_GRAY2BGR), markers)

    labels = markers.copy()
    labels[labels == -1] = 0              # 分水岭脊线（边界）
    # 合并过小区域：面积小于阈值的区域并入其边界邻域中出现最多的区域（小碎块 → 主区域）
    small_area = max(20, int(gray.size * 0.00005))
    areas = np.bincount(labels.ravel(), minlength=labels.max() + 1)
    dil_k = np.ones((3, 3), np.uint8)
    for lab in range(2, labels.max() + 1):
        if areas[lab] < small_area:
            m = (labels == lab)
            ring = cv2.dilate(m.astype(np.uint8), dil_k) & ~m
            nb = labels[ring]
            nb = nb[nb > 1]               # 不并入脊线(0)与背景(1)以外的统计
            if isinstance(nb, np.ndarray) and len(nb):
                rep = int(np.bincount(nb).argmax())   # 邻域主标签
            else:
                rep = 1                   # 无相邻区域时并入背景
            labels[m] = rep
    n_lab = int(labels.max()) - 1         # 前景区域个数（不含背景标记 1）
    rng = np.random.default_rng(42)
    palette = {0: np.array([0, 0, 255], np.uint8),      # 边界：红色
               1: np.array([240, 240, 240], np.uint8)}  # 背景：浅灰
    for lab in range(2, n_lab + 2):
        palette[lab] = rng.integers(60, 230, 3)
    vis = np.zeros(gray.shape + (3,), np.uint8)
    for lab in range(n_lab + 2):
        vis[labels == lab] = palette[lab]
    return vis, n_lab


def combined_segment(img, smax=7, fg_coef=0.35):
    """
    组合式自适应分割（创新方法）：
    自适应中值滤波去噪 → Otsu 自适应极性粗分割得到对象掩膜 → 分水岭精修，
    并把 Otsu 判为非对象的背景区域强制置黑，抑制背景过分割。
    """
    den = adaptive_median_filter(img, smax)
    mask = otsu_foreground(den)         # 对象掩膜（与分水岭内部一致的自适应极性）
    ws, n = watershed_segment(den, fg_coef)
    out = ws.copy()
    out[mask == 0] = (0, 0, 0)          # 背景（非对象区）强制置黑
    return out, n


# ===================== GUI 主界面 =====================

class CellSegGUI(tk.Tk):
    """病理细胞图像分割系统主界面（macOS 风格：浅灰底 + 白色卡片 + 扁平按钮 + 系统蓝强调色）"""

    # -------- macOS 设计规范：颜色 --------
    C_BG     = "#F2F2F7"   # 窗口底色（浅灰）
    C_CARD   = "#FFFFFF"   # 卡片 / 面板底色
    C_TEXT   = "#1D1D1F"   # 主文字
    C_SUB    = "#8E8E93"   # 次要文字 / 提示
    C_ACCENT = "#0A84FF"   # 强调色（macOS 系统蓝）
    C_ACC_D  = "#0068DA"   # 强调色按下
    C_BTN    = "#E8E8ED"   # 次级按钮底色
    C_BTN_D  = "#D9D9E0"   # 次级按钮按下
    C_LINE   = "#E3E3E8"   # 分隔线 / 描边
    C_OK     = "#2FBF5F"   # 成功状态文字（macOS 绿）
    C_CANVAS = "#202024"   # 图像画布底色（深灰，衬托病理图）
    GLASS    = "#FAFAFC"   # 工具栏底色

    def __init__(self):
        enable_hidpi()          # 高 DPI 适配（必须在创建根窗口之前）
        super().__init__()
        self.title("病理细胞图像分割系统")
        self.geometry("1320x900")
        self.minsize(1100, 700)
        # 按屏幕实际 DPI 设置 Tk 缩放，避免高分辨率屏界面发虚
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        self.configure(bg=self.C_BG)
        self._setup_fonts()     # 必须在创建任何带文字的控件前设置字体
        self._btn_full = 312    # 左侧面板卡片内通栏按钮宽度（像素）

        self.original = None        # 原始图像数组
        self.current = None         # 当前处理结果数组
        self.disp_info = {}         # 画布显示映射 {tag:(scale,offx,offy,iw,ih)}
        self.view = {"res": {"zoom": 1.0, "dx": 0, "dy": 0}}   # 结果区视图状态（倍率/平移量）
        self._res_view_arr = None  # 结果区最近一次绘制的图像（供缩放/平移即时重绘）
        self._res_drag = None      # 结果区拖动起点坐标
        self.crop_mode = False      # 是否处于裁剪框选状态
        self.crop_start = None      # 裁剪起点（画布坐标）
        self.crop_rect = None       # 裁剪预览矩形
        self._scale_base = None     # 缩放拖动时的基准图像
        self._scale_base_val = 1.0  # 基准图像对应的滑块值
        self._rot_base = None       # 旋转拖动时的基准图像
        self._rot_base_val = 0.0    # 基准图像对应的滑块角度
        self._edge_base = None      # 边缘算子的共同基准图（切换算子时替换上一个结果）
        self._last_entries = None   # 最近一次对比区内容（窗口尺寸变化时自动重排）
        self._cmp_reflow_id = None  # 对比区重排防抖定时器句柄
        self._cmp_laid_w = 0        # 最近一次排版时使用的画布宽度
        self.result_text = tk.StringVar(value="提示：点击【生成示例细胞图】即可无图演示")

        self._build_toolbar()
        self._build_body()
        self._bind_crop()
        self._bind_res_view()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """关闭窗口：先取消待执行的对比区重排定时器，避免退出时报无意义的定时器错误"""
        if self._cmp_reflow_id:
            try:
                self.after_cancel(self._cmp_reflow_id)
            except Exception:
                pass
        self.destroy()

    # ------------------------- 主题（字体 / 控件工厂） -------------------------

    def _setup_fonts(self):
        """选择界面字体：英文优先 Inter-Medium，中文优先苹方中等（PingFang SC Medium）；
        字体未安装时按候选列表自动回退，保证跨平台显示正常"""
        self.f_en, self.f_cn = pick_fonts(self)

    def F(self, size, bold=False, eng=False):
        """生成界面字体：整体缩小一档（×0.86 后取整），避免界面字号偏大"""
        s = max(7, int(round(size * 0.86)))
        return (self.f_en if eng else self.f_cn, s, "bold" if bold else "normal")

    def _btn(self, parent, text, command, primary=False, width=None, size=10,
             bold=False, height=30, padx=16):
        """macOS 风格圆角扁平按钮：primary=True 蓝底白字，否则浅灰底深字；width 为像素（None=自适应）"""
        return RoundBtn(parent, text=text, command=command, primary=primary,
                        font=self.F(size, bold), width=width, height=height, padx=padx)

    def _lab(self, parent, text, size=10, fg=None, bold=False):
        """文字标签：自动继承父面板底色，保持卡片内部一致"""
        return tk.Label(parent, text=text, bg=parent["bg"], fg=fg or self.C_TEXT,
                        font=self.F(size, bold))

    def _slider(self, parent, var, frm, to, res=1.0, length=170, command=None, size=9):
        """macOS 风格扁平圆角滑块：细轨道 + 白色圆滑钮 + 右侧数值"""
        return FlatSlider(parent, variable=var, from_=frm, to=to, resolution=res,
                          length=length, command=command, font=self.F(size, eng=True))

    def _card(self, parent, title=None):
        """白色圆角卡片面板（内容放到 card.inner 中），带可选粗体标题"""
        card = RCard(parent, fill=self.C_CARD, outline=self.C_LINE, radius=20, pad=12)
        if title:
            tk.Label(card.inner, text=title, bg=self.C_CARD, fg=self.C_TEXT,
                     font=self.F(11, True)).pack(anchor="w", padx=10, pady=(6, 2))
        return card

    # ------------------------- 界面搭建 -------------------------

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=self.GLASS, highlightthickness=0)
        bar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=self.C_LINE, height=1).pack(side=tk.TOP, fill=tk.X)   # 工具栏下细分隔线
        self._btn(bar, "打开图像", self.open_image, primary=True).pack(side=tk.LEFT, padx=(14, 6), pady=8)
        self._btn(bar, "生成示例细胞图", self.load_sample).pack(side=tk.LEFT, padx=6, pady=8)
        self._btn(bar, "保存当前结果", self.save_current).pack(side=tk.LEFT, padx=6, pady=8)
        self._btn(bar, "保存前后对比图", self.save_compare).pack(side=tk.LEFT, padx=6, pady=8)
        self._btn(bar, "重置", self.reset).pack(side=tk.LEFT, padx=6, pady=8)
        tk.Label(bar, textvariable=self.result_text, fg=self.C_OK, bg=self.GLASS,
                 font=self.F(10), anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=14)

    def _build_body(self):
        body = tk.Frame(self, bg=self.C_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # ---------------- 左侧控制面板（可滚动） ----------------
        ctrl_wrap = tk.Frame(body, width=370, bg=self.C_BG)
        ctrl_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(14, 6), pady=12)
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
                               lambda e: self._ctrl_canvas.itemconfigure(self._ctrl_window, width=e.width))
        FULL = self._btn_full        # 卡片内通栏按钮宽度（像素）

        # ① 基础操作
        f1 = self._card(ctrl, "①　基础操作")
        f1.pack(fill=tk.X, pady=(0, 12))
        self._btn(f1.inner, "灰度化", lambda: self.apply_op(to_gray, "灰度化"),
                  width=FULL).pack(padx=10, pady=(8, 4))

        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "缩放", size=9).pack(side=tk.LEFT)
        self.scale_var = tk.DoubleVar(value=1.0)
        self.scale_slider = self._slider(row, self.scale_var, 0.25, 2.0, 0.05, 150, self._on_scale)
        self.scale_slider.pack(side=tk.LEFT, padx=6)
        # 按下时锁定基准（此时值尚未被拖动改变）；拖动仅做预览，点【应用缩放】后才正式生效
        self.scale_slider.bind("<ButtonPress-1>", self._scale_begin)
        self._btn(f1.inner, "应用缩放", self.do_scale, width=FULL).pack(padx=10, pady=4)

        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "旋转", size=9).pack(side=tk.LEFT)
        self.rot_var = tk.DoubleVar(value=0.0)
        self.rot_slider = self._slider(row, self.rot_var, -180, 180, 1, 150, self._on_rotate)
        self.rot_slider.pack(side=tk.LEFT, padx=6)
        # 与缩放相同的交互：按下锁定基准，拖动仅预览，点【应用旋转】后才正式生效
        self.rot_slider.bind("<ButtonPress-1>", self._rot_begin)
        self._btn(f1.inner, "应用旋转", self.do_rotate, width=FULL).pack(padx=10, pady=4)

        self.crop_btn = self._btn(f1.inner, "裁剪（在原图上拖拽框选区域）", self.toggle_crop, width=FULL)
        self.crop_btn.pack(padx=10, pady=4)

        self._lab(f1.inner, "窗宽窗位调节（滑块实时预览）", size=9, fg=self.C_ACCENT).pack(
            anchor="w", padx=10, pady=(6, 2))
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "窗位C", size=9).pack(side=tk.LEFT)
        self.wc_var = tk.DoubleVar(value=128)
        self._slider(row, self.wc_var, 0, 255, 1, 140, self._on_wl).pack(side=tk.LEFT, padx=6)
        row = tk.Frame(f1.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "窗宽W", size=9).pack(side=tk.LEFT)
        self.ww_var = tk.DoubleVar(value=256)
        self._slider(row, self.ww_var, 1, 512, 1, 140, self._on_wl).pack(side=tk.LEFT, padx=6, pady=(0, 10))

        # ② 图像增强（去噪）
        f2 = self._card(ctrl, "②　图像增强 / 去噪")
        f2.pack(fill=tk.X, pady=(0, 12))
        self._btn(f2.inner, "标准中值滤波",
                  lambda: self.apply_op(lambda im: median_denoise(im, self.smax_var.get() or 3),
                                        "标准中值滤波"), width=FULL).pack(padx=10, pady=(8, 4))
        row = tk.Frame(f2.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "中值最大窗口", size=9).pack(side=tk.LEFT)
        self.smax_var = tk.IntVar(value=7)
        self._slider(row, self.smax_var, 3, 11, 2, 130).pack(side=tk.LEFT, padx=6)
        self._btn(f2.inner, "自适应中值滤波",
                  lambda: self.apply_op(lambda im: adaptive_median_filter(im, self.smax_var.get()),
                                        "自适应中值滤波"), width=FULL).pack(padx=10, pady=4)
        row = tk.Frame(f2.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        self._lab(row, "高斯σ", size=9).pack(side=tk.LEFT)
        self.sigma_var = tk.DoubleVar(value=1.5)
        self._slider(row, self.sigma_var, 0.5, 5.0, 0.1, 130).pack(side=tk.LEFT, padx=6)
        self._btn(f2.inner, "高斯滤波去噪",
                  lambda: self.apply_op(lambda im: gaussian_denoise(im, self.sigma_var.get()),
                                        "高斯滤波去噪"), width=FULL).pack(padx=10, pady=(4, 10))

        # ③ 边缘提取
        f3 = self._card(ctrl, "③　边缘提取（6 种算子）")
        f3.pack(fill=tk.X, pady=(0, 12))
        grid = tk.Frame(f3.inner, bg=self.C_CARD)
        grid.pack(fill=tk.X, padx=10, pady=(8, 0))
        for c in range(3):
            grid.columnconfigure(c, weight=1)
        edges = [("Sobel", edge_sobel), ("Prewitt", edge_prewitt), ("Roberts", edge_roberts),
                 ("Laplacian", edge_laplacian), ("LoG", edge_log), ("Canny", edge_canny)]
        GRID_W = (FULL - 16) // 3      # 3 列小按钮宽度
        for i, (name, func) in enumerate(edges):
            self._btn(grid, name, lambda f=func, n=name: self.do_edge(f, n + " 边缘提取"),
                      width=GRID_W, size=9, padx=6).grid(row=i // 3, column=i % 3, padx=2, pady=2)
        self._btn(f3.inner, "全部边缘结果对比", self.edge_compare, width=FULL).pack(padx=10, pady=(8, 10))

        # ④ 图像分割
        f4 = self._card(ctrl, "④　图像分割")
        f4.pack(fill=tk.X, pady=(0, 12))
        self._btn(f4.inner, "Otsu 阈值分割", self.do_otsu, width=FULL).pack(padx=10, pady=(8, 4))
        # 分水岭前景系数：标签换行显示（分水岭/前景系数），滑块左移紧贴标签，
        # 避免右侧数字倍数被挤出可视区域裁掉
        row = tk.Frame(f4.inner, bg=self.C_CARD); row.pack(fill=tk.X, padx=10)
        lab = tk.Frame(row, bg=self.C_CARD)
        lab.pack(side=tk.LEFT, padx=(0, 6))
        self._lab(lab, "分水岭", size=8).pack(anchor="w")
        self._lab(lab, "前景系数", size=8).pack(anchor="w")
        self.fgcoef_var = tk.DoubleVar(value=0.35)
        self._slider(row, self.fgcoef_var, 0.10, 0.60, 0.05, 130).pack(side=tk.LEFT)
        self._btn(f4.inner, "自适应分水岭分割", self.do_watershed, width=FULL).pack(padx=10, pady=4)
        self._btn(f4.inner, "组合式分割（创新）", self.do_combined, width=FULL).pack(padx=10, pady=4)
        self._btn(f4.inner, "分割方法结果对比", self.seg_compare, width=FULL).pack(padx=10, pady=(4, 10))

        # ---------------- 右侧显示区 ----------------
        disp = tk.Frame(body, bg=self.C_BG)
        disp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14), pady=12)

        top = tk.Frame(disp, bg=self.C_BG)
        top.pack(fill=tk.BOTH, expand=True)
        lf1 = self._card(top, "原始图像")
        lf1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.canvas_orig = tk.Canvas(lf1.inner, width=480, height=480, bg=self.C_CARD,
                                     highlightthickness=0, bd=0)
        self.canvas_orig.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        lf2 = self._card(top, "处理结果")
        lf2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        bar2 = tk.Frame(lf2.inner, bg=self.C_CARD)
        bar2.pack(fill=tk.X, padx=8, pady=(6, 0))
        self._btn(bar2, "放大", lambda: self._zoom_res(1.25), size=9, padx=10).pack(side=tk.LEFT, padx=2)
        self._btn(bar2, "缩小", lambda: self._zoom_res(0.8), size=9, padx=10).pack(side=tk.LEFT, padx=2)
        self._btn(bar2, "适应",
                  lambda: (self._reset_res_view(), self._redraw_all()), size=9, padx=10
                  ).pack(side=tk.LEFT, padx=2)
        self._lab(bar2, "滚轮=缩放  拖动=平移  双击=复位", size=8, fg=self.C_SUB).pack(side=tk.LEFT, padx=8)
        self.canvas_res = tk.Canvas(lf2.inner, width=480, height=480, bg=self.C_CARD,
                                    highlightthickness=0, bd=0)
        self.canvas_res.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        cmp = self._card(disp, "多算法结果对比区")
        cmp.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        # 可滚动容器：缩略图多于一屏时，用滚动条或鼠标滚轮滚动查看（纵向+横向）
        cmp_wrap = tk.Frame(cmp.inner, bg=self.C_CARD)
        cmp_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.cmp_canvas = tk.Canvas(cmp_wrap, bg=self.C_CARD, highlightthickness=0)
        self.cmp_scroll = tk.Scrollbar(cmp_wrap, orient=tk.VERTICAL, width=10,
                                       command=self.cmp_canvas.yview, bg="#D9D9E0",
                                       troughcolor=self.C_CARD, bd=0, highlightthickness=0,
                                       activebackground=self.C_SUB)
        self.cmp_scroll_h = tk.Scrollbar(cmp_wrap, orient=tk.HORIZONTAL, width=10,
                                         command=self.cmp_canvas.xview, bg="#D9D9E0",
                                         troughcolor=self.C_CARD, bd=0, highlightthickness=0,
                                         activebackground=self.C_SUB)
        self.cmp_canvas.configure(yscrollcommand=self.cmp_scroll.set,
                                  xscrollcommand=self.cmp_scroll_h.set)
        self.cmp_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cmp_scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
        self.cmp_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 缩略图内容框架放入画布窗口，作为滚动区域
        self.cmp_frame = tk.Frame(self.cmp_canvas, bg=self.C_CARD)
        self._cmp_window = self.cmp_canvas.create_window((0, 0), window=self.cmp_frame, anchor="nw")
        # 内容尺寸变化时更新滚动范围；画布宽度变化时内容窗口跟随
        self.cmp_frame.bind("<Configure>", self._on_cmp_configure)
        self.cmp_canvas.bind("<Configure>", self._on_cmp_resize)
        self._bind_scroll_wheel(self.cmp_canvas)
        # 左侧面板滚轮滚动：绑定到面板及其全部子控件，悬停任意位置都能滚动
        self._bind_ctrl_wheel(ctrl)

    # ------------------------- 图像读写 -------------------------

    def open_image(self):
        path = filedialog.askopenfilename(
            title="选择图像",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.original = np.array(Image.open(path).convert("RGB"))
        except Exception as e:
            messagebox.showerror("打开失败", str(e))
            return
        self._new_image_loaded()

    def load_sample(self):
        """生成模拟细胞病理图，便于无图演示"""
        self.original = make_sample_cells(512)
        self._new_image_loaded()

    def _new_image_loaded(self):
        self.current = self.original.copy()
        self._reset_preview_bases()     # 新图像：缩放/旋转滑块基准清零
        # 新图像把比例/角度滑块复位到“不缩放/不旋转”位置，保证滑块读数含义一致
        self.scale_var.set(1.0)
        self.rot_var.set(0.0)
        self._reset_preview_bases()     # 清除 set() 触发回调时锁定的临时基准
        self.crop_mode = False
        self.crop_btn.config(text="裁剪（在原图上拖拽框选区域）")
        self.canvas_orig.config(cursor="")
        self._clear_compare()
        self.result_text.set("图像加载成功  尺寸: %d x %d" %
                             (self.original.shape[1], self.original.shape[0]))
        self.update_display()

    def save_current(self):
        if self.current is None:
            messagebox.showwarning("提示", "还没有处理结果，请先打开图像")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG 图像", "*.png"), ("JPEG 图像", "*.jpg")])
        if path:
            Image.fromarray(self.current).save(path)
            self.result_text.set("已保存当前结果到: " + path)

    def save_compare(self):
        """保存『处理前 | 处理后』并排对比图"""
        if self.original is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG 图像", "*.png"), ("JPEG 图像", "*.jpg")])
        if not path:
            return
        a = Image.fromarray(self.original)
        b = Image.fromarray(self.current)
        # 两图高度可能不同：分别粘贴到等高白底画布并垂直居中，便于并排拼接
        th = max(a.height, b.height)
        ca = Image.new("RGB", (a.width, th), "white")
        ca.paste(a, (0, (th - a.height) // 2))
        cb = Image.new("RGB", (b.width, th), "white")
        cb.paste(b, (0, (th - b.height) // 2))
        gap = Image.new("RGB", (12, th), (255, 0, 0))   # 红色分隔线
        out = Image.fromarray(np.hstack([np.array(ca), np.array(gap), np.array(cb)]))
        out.save(path)
        self.result_text.set("已保存处理前后对比图到: " + path)

    def reset(self):
        if self.original is None:
            return
        self.current = self.original.copy()
        self._reset_preview_bases()
        self._clear_compare()
        self.result_text.set("已重置为原始图像")
        self.update_display()

    # ------------------------- 显示 -------------------------

    def update_display(self):
        if self.original is not None:
            self._show(self.canvas_orig, self.original, "orig")
        if self.current is not None:
            self._show(self.canvas_res, self.current, "res")

    def _show(self, canvas, arr, tag, fallback=480):
        """把 numpy 图像等比例缩放后绘制到指定画布中央；
        原图区(orig)与结果区(res)共享同一视图（同步缩放/平移），放大后图像可超出画布边框，
        被裁部分可拖动查看；对比区缩略图(cmp*)始终保持适应窗口显示"""
        # 注意：刚创建尚未完成布局的画布 winfo_width 返回 1（truthy），
        # 必须把它当作“尺寸未知”回退到预设尺寸，否则图像会被缩成 1 像素导致只见灰色背景
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw <= 1:
            cw = fallback
        if ch <= 1:
            ch = fallback
        pil = Image.fromarray(np.asarray(arr))
        # 基础适配比例：保证整图放入画布且不变形
        r0 = min(cw / pil.width, ch / pil.height, 1.0)
        shared = tag in ("res", "orig")            # 左右两框共享视图状态
        if shared:
            v = self.view.setdefault("res", {"zoom": 1.0, "dx": 0, "dy": 0})
            zoom = max(0.2, min(16.0, v["zoom"]))  # 1=适应窗口；>1 时图像超出画布边框
            dx, dy = v["dx"], v["dy"]
            if tag == "res":
                self._res_view_arr = arr           # 记录最近绘制的图像供缩放/平移重绘
        else:
            zoom, dx, dy = 1.0, 0, 0
        r = r0 * zoom
        # 完整显示尺寸只用于几何计算与坐标映射，不实际把整图缩放出来
        w = max(1, int(pil.width * r))
        h = max(1, int(pil.height * r))
        canvas.delete("all")
        if shared or tag.startswith("cmp"):
            # 圆角显示底色：画布本身与卡片同色，四个圆角外露区域自然融入卡片背景
            round_rect(canvas, 1, 1, cw, ch, 16 if shared else 10,
                       fill=self.C_CANVAS, outline="")
        if shared:
            # 仅按本画布限幅绘制，不回写共享状态（共享状态在缩放/平移处理器中统一限幅）
            max_dx = max(0.0, (w - cw) / 2.0 + 60.0)
            max_dy = max(0.0, (h - ch) / 2.0 + 60.0)
            dx = float(np.clip(dx, -max_dx, max_dx))
            dy = float(np.clip(dy, -max_dy, max_dy))
        if shared and (w > cw or h > ch):
            # 高倍预览：只裁取视野内的图像局部再缩放，避免对整幅大图超大尺寸重采样导致卡顿
            self._draw_viewport(canvas, pil, r, cw, ch, dx, dy, zoom)
        else:
            # 整图能放入画布：直接缩放到显示尺寸（尺寸有限，开销小）
            if zoom >= 2.0:
                resample = Image.NEAREST
            elif zoom >= 1.0:
                resample = Image.BILINEAR
            else:
                resample = Image.LANCZOS
            photo = ImageTk.PhotoImage(pil.resize((w, h), resample))
            canvas.create_image(cw // 2 + dx, ch // 2 + dy, image=photo)
            canvas.photo = photo          # 保持引用防止被回收
        # 记录缩放比例、偏移量与原图尺寸，供裁剪时做画布坐标→图像坐标换算
        self.disp_info[tag] = (r, (cw - w) // 2 + dx, (ch - h) // 2 + dy, pil.width, pil.height)

    def _draw_viewport(self, canvas, pil, r, cw, ch, dx, dy, zoom):
        """视野裁剪渲染：只把画布当前可见的图像局部裁剪并缩放到画布对应区域，
        绘制开销只与画布尺寸相关，与图像尺寸/放大倍率无关，保证高倍缩放平移流畅"""
        # 图像中心在画布上的位置（含平移偏移）
        cx = cw / 2.0 + dx
        cy = ch / 2.0 + dy
        # 画布四角经“画布坐标→图像坐标”逆映射，得到可见的源图像区域
        sx0 = (0.0 - cx) / r + pil.width / 2.0
        sy0 = (0.0 - cy) / r + pil.height / 2.0
        sx1 = (cw - cx) / r + pil.width / 2.0
        sy1 = (ch - cy) / r + pil.height / 2.0
        # 源区域取整并夹取到图像范围（图像边缘处可见区域小于画布）
        ix0 = max(int(np.floor(sx0)), 0)
        iy0 = max(int(np.floor(sy0)), 0)
        ix1 = min(int(np.ceil(sx1)), pil.width)
        iy1 = min(int(np.ceil(sy1)), pil.height)
        if ix0 >= ix1 or iy0 >= iy1:
            return          # 图像完全移出视野（正常情况下已被平移限幅避免）
        crop = pil.crop((ix0, iy0, ix1, iy1))
        tw = max(1, int(round((ix1 - ix0) * r)))
        th = max(1, int(round((iy1 - iy0) * r)))
        # 高倍观察用最近邻重采样，既快又便于观察像素；中低倍用双线性
        resample = Image.NEAREST if zoom >= 2.0 else Image.BILINEAR
        photo = ImageTk.PhotoImage(crop.resize((tw, th), resample))
        # 裁剪区左上角在画布上的精确位置，用左上角锚点贴回原位
        px = cx + (ix0 - pil.width / 2.0) * r
        py = cy + (iy0 - pil.height / 2.0) * r
        canvas.create_image(px, py, image=photo, anchor="nw")
        canvas.photo = photo

    # ------------------------- 各类操作 -------------------------

    def do_edge(self, func, name):
        """应用边缘提取：6 种算子互不叠加。
        第一次选算子时锁定当前图像（保留此前的前处理）作为共同基准，
        之后切换其它算子都作用在该基准上，自动取消上一个算子的效果。"""
        if self.original is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        base = self._edge_base if self._edge_base is not None else self.current
        try:
            self.current = func(base)
        except RuntimeError as e:
            messagebox.showerror("缺少依赖", str(e))
            return
        except Exception as e:
            messagebox.showerror("处理出错", str(e))
            return
        self._reset_preview_bases()
        self._edge_base = base            # 保留基准，供下一次切换算子时替换
        self.result_text.set("当前操作: %s（尺寸 %d×%d）" %
                             (name, self.current.shape[1], self.current.shape[0]))
        self._clear_compare()
        self.update_display()

    def apply_op(self, func, name):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        try:
            self.current = func(self.current)
        except RuntimeError as e:
            messagebox.showerror("缺少依赖", str(e))
            return
        except Exception as e:
            messagebox.showerror("处理出错", str(e))
            return
        self.result_text.set("当前操作: %s（尺寸 %d×%d）" %
                             (name, self.current.shape[1], self.current.shape[0]))
        self._reset_preview_bases()
        self._clear_compare()
        self.update_display()

    # --------------------- 缩放 / 旋转（滑块实时预览 + 按钮提交） ---------------------

    def _reset_preview_bases(self):
        """处理操作改变当前图像后调用：滑块基准清零，结果区视图复位到适应窗口，边缘基准作废"""
        self._scale_base = None
        self._rot_base = None
        self._edge_base = None
        self._reset_res_view()

    def _scale_begin(self, _e=None):
        """按下缩放滑块：锁定本轮拖动的基准图像与基准比例。
        该事件先于滑块值改变触发，因此记录的是拖动前的比例（绝对比例语义）"""
        if self.current is None:
            return
        self._scale_base = self.current.copy()
        self._scale_base_val = self.scale_var.get()

    def _on_scale(self, *_):
        """缩放滑块回调：按 v/拖动前基准 实时预览缩放效果"""
        if self.current is None:
            return
        try:
            if self._scale_base is None:      # 未锁定基准（如方向键调节）：以当前值作基准
                self._scale_base = self.current.copy()
                self._scale_base_val = self.scale_var.get()
            out = image_resize(self._scale_base, self.scale_var.get() / self._scale_base_val)
            self._show(self.canvas_res, out, "res")
        except Exception:
            pass        # 预览失败不影响主流程

    def _rot_begin(self, _e=None):
        """按下旋转滑块：锁定本轮拖动的基准图像与基准角度"""
        if self.current is None:
            return
        self._rot_base = self.current.copy()
        self._rot_base_val = self.rot_var.get()

    def _on_rotate(self, *_):
        """旋转滑块回调：按 (当前角度-拖动前角度) 实时预览旋转效果"""
        if self.current is None:
            return
        try:
            if self._rot_base is None:
                self._rot_base = self.current.copy()
                self._rot_base_val = self.rot_var.get()
            out = image_rotate(self._rot_base, self.rot_var.get() - self._rot_base_val)
            self._show(self.canvas_res, out, "res")
        except Exception:
            pass

    def do_scale(self):
        """应用缩放（点击按钮才生效）：把按下滑块后的预览结果提交为正式结果，
        滑块随后复位到 1.0（无变化位）。语义：拖到 v 即相对“拖动开始时看到的图像”缩放 v 倍；
        拖动只是预览，只有点击【应用缩放】才会改变处理结果；要回原尺寸请点工具栏【重置】"""
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        try:
            if self._scale_base is None:      # 未拖动滑块直接点按钮：以当前图像为基准
                self._scale_base = self.current.copy()
                self._scale_base_val = 1.0
            # 实际比例 = 当前滑块值 / 拖动起点值（起点即复位后的 1.0）
            ratio = self.scale_var.get() / self._scale_base_val
            self.current = image_resize(self._scale_base, ratio)
        except Exception as e:
            messagebox.showerror("处理出错", str(e))
            return
        applied = ratio
        self.scale_var.set(1.0)               # 滑块复位（set 触发的预览回调随后被基准清零覆盖）
        self._reset_preview_bases()
        self.result_text.set("缩放应用: %.2f 倍 → 尺寸 %d×%d（回原尺寸请点【重置】）" %
                             (applied, self.current.shape[1], self.current.shape[0]))
        self._clear_compare()
        self.update_display()

    def do_rotate(self):
        """应用旋转（点击按钮才生效）：把按下滑块后的预览结果提交为正式结果，
        滑块随后复位到 0°（无变化位）。语义：拖到 θ° 即相对“拖动开始时看到的图像”旋转 θ 度；
        拖动只是预览，只有点击【应用旋转】才会改变处理结果"""
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        try:
            if self._rot_base is None:        # 未拖动滑块直接点按钮：相对 0° 旋转
                self._rot_base = self.current.copy()
                self._rot_base_val = 0.0
            angle = self.rot_var.get() - self._rot_base_val
            self.current = image_rotate(self._rot_base, angle)
        except Exception as e:
            messagebox.showerror("处理出错", str(e))
            return
        applied = angle
        self.rot_var.set(0.0)                 # 滑块复位（set 触发的预览回调随后被基准清零覆盖）
        self._reset_preview_bases()
        self.result_text.set("旋转应用: %.0f° → 尺寸 %d×%d" %
                             (applied, self.current.shape[1], self.current.shape[0]))
        self._clear_compare()
        self.update_display()

    def _on_wl(self, *_):
        """窗宽窗位滑块回调：拖动滑块时把映射结果实时绘制到右侧画布，实现动态预览"""
        if self.current is None:
            return
        try:
            # 只做预览绘制，不修改 self.current，避免与其它处理操作相互干扰
            out = window_level(self.current, self.wc_var.get(), self.ww_var.get())
            self._show(self.canvas_res, out, "res")
        except Exception:
            pass        # 预览失败不影响主流程

    def do_otsu(self):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        bw, T = otsu_threshold(self.current)
        self.current = bw
        self._reset_preview_bases()
        self.result_text.set("Otsu 分割完成，自适应最佳阈值 T = %d" % T)
        self._clear_compare()
        self.update_display()

    def do_watershed(self):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        try:
            ws, n = watershed_segment(self.current, self.fgcoef_var.get())
        except RuntimeError as e:
            messagebox.showerror("缺少依赖", str(e))
            return
        self.current = ws
        self._reset_preview_bases()
        self.result_text.set("自适应分水岭分割完成，共分割出 %d 个区域" % n)
        self._clear_compare()
        self.update_display()

    def do_combined(self):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        try:
            out, n = combined_segment(self.current, self.smax_var.get(),
                                      self.fgcoef_var.get())
        except RuntimeError as e:
            messagebox.showerror("缺少依赖", str(e))
            return
        self.current = out
        self._reset_preview_bases()
        self.result_text.set("组合式分割完成（自适应中值+Otsu+分水岭），%d 个区域" % n)
        self._clear_compare()
        self.update_display()

    # ------------------------- 多算法对比 -------------------------

    def _clear_compare(self):
        """清空对比区：销毁全部缩略图并重建内容框架，滚动位置与滚动区域随之复位"""
        for w in self.cmp_frame.winfo_children():
            w.destroy()
        # 重建窗口项/框架，避免旧内容把画布窗口项的尺寸钉住导致滚动区域无法收缩
        self.cmp_canvas.delete(self._cmp_window)
        self.cmp_frame = tk.Frame(self.cmp_canvas, bg=self.C_CARD)
        self._cmp_window = self.cmp_canvas.create_window((0, 0), window=self.cmp_frame, anchor="nw")
        self.cmp_frame.bind("<Configure>", self._on_cmp_configure)
        self.cmp_canvas.yview_moveto(0)
        self.cmp_canvas.configure(scrollregion=(0, 0, 0, 0))

    def _update_cmp_region(self):
        """按当前内容重新计算对比区滚动范围（内容增减 / 窗口清空后调用）"""
        self.cmp_canvas.configure(scrollregion=self.cmp_canvas.bbox("all"))

    def _show_compare(self, entries, reschedule=True):
        """entries: [(标题, 图像数组)]，以缩略图网格自适应排版显示在对比区（可滚动查看全部）。
        reschedule=False 时不再安排后续重排（供 _reflow_compare 调用，防止自我触发死循环）"""
        self._clear_compare()
        self._last_entries = entries    # 记录内容，窗口尺寸变化时自动重排
        # ---- 自适应排版：选“宽度填充 ≥97% 且缩略图最大”的列布局，横向铺满整个对比区 ----
        # 旧版 420px 上限在宽窗口下会让所有列布局都不满足 90% 填充，退化成单列 + 大片空白，
        # 因此改为按画布真实宽度均分列宽（缩略图限幅 140~520px），保证横排铺满。
        avail = self.cmp_canvas.winfo_width()
        if not avail or avail <= 1:          # 画布尚未完成布局时按常规宽度估算
            avail = 960
        self._cmp_laid_w = avail            # 记录本次排版所用宽度，宽度无变化时不重排
        best_cols, best_thumb = 1, 0
        for c in (1, 2, 3, 4, 5):           # 最多 5 列；逐列计算均分后的缩略图宽度
            cost = 24 * c + 8 * (c - 1) + 8   # 卡片内外边距 + 网格间距 + 边框
            t = min((avail - cost) // c, 520)
            if t < 140:
                continue
            fill = (t * c + cost) / avail     # 该布局的宽度填充率
            if fill >= 0.97 and t > best_thumb:
                best_cols, best_thumb = c, t
        if best_thumb == 0:                  # 极小宽度兜底：单列也尽量铺满可用宽度
            best_cols = 1
            best_thumb = max(120, min(520, avail - 32))
        cols, thumb = best_cols, best_thumb
        # 布局定版后按真实画布宽度再核对一次（一次性，宽度无变化则跳过，避免反复重建）
        if reschedule:
            if self._cmp_reflow_id:
                try:
                    self.after_cancel(self._cmp_reflow_id)
                except Exception:
                    pass
            self._cmp_reflow_id = self.after(260, self._reflow_compare)
        boxes = []
        for i, (title, arr) in enumerate(entries):
            box = RCard(self.cmp_frame, fill=self.C_CARD, outline=self.C_LINE, radius=12, pad=5)
            box.grid(row=i // cols, column=i % cols, padx=4, pady=4)   # 按计算出的列数排布
            self._lab(box.inner, title, size=8).pack(padx=2, pady=(2, 0))
            cv = tk.Canvas(box.inner, width=thumb, height=thumb, bg=self.C_CARD,
                           highlightthickness=0, bd=0)
            cv.pack(padx=3, pady=(0, 3))
            # 滚轮悬停在缩略图上也能滚动对比区
            self._bind_scroll_wheel(box)
            self._bind_scroll_wheel(cv)
            boxes.append((cv, arr))
        # 先完成几何布局（update_idletasks），再绘制图像，确保能取到缩略图画布的真实尺寸
        self.update_idletasks()
        for i, (cv, arr) in enumerate(boxes):
            self._show(cv, arr, "cmp%d" % i, fallback=thumb)

    def _on_cmp_configure(self, _e):
        """对比区内容尺寸变化：更新滚动区域范围（缩略图增减时自动调整）"""
        self._update_cmp_region()

    def _on_cmp_resize(self, e):
        """对比区画布宽度变化：内容窗口至少铺满画布；内容更宽时保持自然宽度（配合横向滚动条）。
        窗口尺寸稳定后按新宽度自动重排缩略图（防抖）"""
        w = max(e.width, self.cmp_frame.winfo_reqwidth())
        self.cmp_canvas.itemconfigure(self._cmp_window, width=w)
        if getattr(self, "_last_entries", None):
            if self._cmp_reflow_id:
                self.after_cancel(self._cmp_reflow_id)
            self._cmp_reflow_id = self.after(180, self._reflow_compare)

    def _reflow_compare(self):
        """宽度确有变化时才按新宽度重排（不再自我调度，避免反复重建界面）"""
        self._cmp_reflow_id = None
        if not getattr(self, "_last_entries", None):
            return
        w = self.cmp_canvas.winfo_width()
        if not w or w <= 1:
            return
        if abs(w - getattr(self, "_cmp_laid_w", w)) < 16:
            return
        self._show_compare(self._last_entries, reschedule=False)

    def _bind_scroll_wheel(self, widget):
        """给对比区部件绑定滚轮，跨平台支持（Windows/macOS 与 Linux）"""
        widget.bind("<MouseWheel>", self._on_cmp_wheel)   # Windows / macOS
        widget.bind("<Button-4>", self._on_cmp_wheel)     # Linux 滚轮向上
        widget.bind("<Button-5>", self._on_cmp_wheel)     # Linux 滚轮向下

    def _on_cmp_wheel(self, e):
        """滚轮滚动对比区内容"""
        if getattr(e, "num", None) == 4:
            steps = -3
        elif getattr(e, "num", None) == 5:
            steps = 3
        else:
            steps = -3 if getattr(e, "delta", 0) > 0 else 3
        self.cmp_canvas.yview_scroll(steps, "units")

    def _bind_ctrl_wheel(self, widget):
        """给左侧控制面板及其全部子控件绑定滚轮：悬停任意位置都能滚动面板"""
        widget.bind("<MouseWheel>", self._on_ctrl_wheel)   # Windows / macOS
        widget.bind("<Button-4>", self._on_ctrl_wheel)     # Linux 滚轮向上
        widget.bind("<Button-5>", self._on_ctrl_wheel)     # Linux 滚轮向下
        for child in widget.winfo_children():
            self._bind_ctrl_wheel(child)

    def _on_ctrl_wheel(self, e):
        """滚轮滚动左侧控制面板"""
        if getattr(e, "num", None) == 4:
            steps = -3
        elif getattr(e, "num", None) == 5:
            steps = 3
        else:
            steps = -3 if getattr(e, "delta", 0) > 0 else 3
        self._ctrl_canvas.yview_scroll(steps, "units")

    def edge_compare(self):
        """6 种边缘提取算子结果同屏对比"""
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        entries = [("原图(灰度)", to_gray(self.current))]
        for name, f in [("Sobel", edge_sobel), ("Prewitt", edge_prewitt),
                        ("Roberts", edge_roberts), ("Laplacian", edge_laplacian),
                        ("LoG", edge_log), ("Canny", edge_canny)]:
            try:
                entries.append((name, f(self.current)))
            except RuntimeError as e:
                messagebox.showwarning("缺少依赖", str(e))
        self._show_compare(entries)
        self.result_text.set("已生成 6 种边缘提取算子结果对比")

    def seg_compare(self):
        """不同分割算法结果同屏对比"""
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        entries = [("原图(灰度)", to_gray(self.current))]
        bw, T = otsu_threshold(self.current)
        entries.append(("Otsu分割 T=%d" % T, bw))
        try:
            ws, n = watershed_segment(self.current, self.fgcoef_var.get())
            entries.append(("自适应分水岭 (%d区)" % n, ws))
            cb, n2 = combined_segment(self.current, self.smax_var.get(),
                                      self.fgcoef_var.get())
            entries.append(("组合式分割 (%d区)" % n2, cb))
        except RuntimeError as e:
            messagebox.showwarning("缺少依赖", str(e))
        self._show_compare(entries)
        self.result_text.set("已生成 Otsu / 分水岭 / 组合式分割结果对比")

    # ---------------- 左右框联动放大预览（滚轮缩放 / 拖动平移 / 双击复位） ----------------

    def _bind_res_view(self):
        """左右两个画布绑定共享视图事件：
        滚轮=缩放、左键拖动=平移、双击=复位；两框显示状态始终同步。
        左框的左键事件在裁剪模式下仍为框选（由 _crop_press 等按模式分流）"""
        self.canvas_res.bind("<ButtonPress-1>", self._on_view_press)
        self.canvas_res.bind("<B1-Motion>", self._on_view_drag)
        self.canvas_res.bind("<ButtonRelease-1>", self._on_view_release)
        for c in (self.canvas_res, self.canvas_orig):
            c.bind("<Enter>", lambda e: e.widget.focus_set())   # Windows 上滚轮事件需要焦点
            c.bind("<MouseWheel>", self._on_view_wheel)         # Windows / macOS 滚轮
            c.bind("<Button-4>", self._on_view_wheel)           # Linux 滚轮向上
            c.bind("<Button-5>", self._on_view_wheel)           # Linux 滚轮向下
            c.bind("<Double-Button-1>", self._on_view_dblclick)

    def _on_view_wheel(self, e):
        """滚轮缩放（左右框通用）：向上放大、向下缩小，以光标位置为缩放锚点"""
        if getattr(e, "num", None) == 4:
            factor = 1.2
        elif getattr(e, "num", None) == 5:
            factor = 1.0 / 1.2
        else:                                           # e.delta > 0 表示向上滚动
            factor = 1.2 if getattr(e, "delta", 0) > 0 else 1.0 / 1.2
        self._zoom_res(factor, e.x, e.y)

    def _zoom_res(self, factor, mx=None, my=None):
        """按 factor 调整共享视图倍率；mx/my 为锚点（缺省画布中心），缩放后锚点处图像保持不动"""
        arr = self._res_view_arr
        if arr is None:
            return
        v = self.view["res"]
        z_old = v["zoom"]
        z_new = min(16.0, max(0.2, z_old * factor))
        if abs(z_new - z_old) < 1e-9:
            return
        cw = self.canvas_res.winfo_width()
        ch = self.canvas_res.winfo_height()
        if cw <= 1:
            cw = 480
        if ch <= 1:
            ch = 480
        if mx is None:
            mx, my = cw / 2.0, ch / 2.0
        # 锚点不动条件：光标下图像点相对画布中心的偏移，在缩放前后按比例保持不变
        v["zoom"] = z_new
        v["dx"] = (mx - cw / 2.0) - ((mx - cw / 2.0) - v["dx"]) / z_old * z_new
        v["dy"] = (my - ch / 2.0) - ((my - ch / 2.0) - v["dy"]) / z_old * z_new
        self._clamp_view()
        self._redraw_all()

    def _clamp_view(self):
        """按结果区图像显示尺寸限幅共享平移量，防止把图像拖出视野"""
        v = self.view["res"]
        if self._res_view_arr is None:
            return
        cw = self.canvas_res.winfo_width()
        ch = self.canvas_res.winfo_height()
        if cw <= 1:
            cw = 480
        if ch <= 1:
            ch = 480
        h_img, w_img = self._res_view_arr.shape[:2]
        r0 = min(cw / w_img, ch / h_img, 1.0)
        zoom = v["zoom"]
        max_dx = max(0.0, (w_img * r0 * zoom - cw) / 2.0 + 60.0)
        max_dy = max(0.0, (h_img * r0 * zoom - ch) / 2.0 + 60.0)
        v["dx"] = float(np.clip(v["dx"], -max_dx, max_dx))
        v["dy"] = float(np.clip(v["dy"], -max_dy, max_dy))

    def _reset_res_view(self):
        """复位共享视图：左右两框都回到适应窗口、居中显示"""
        self.view["res"] = {"zoom": 1.0, "dx": 0, "dy": 0}

    def _redraw_all(self):
        """按共享视图同时重绘左右两框（左框与右框的缩放/平移保持同步）"""
        if self._res_view_arr is not None:
            self._show(self.canvas_res, self._res_view_arr, "res")
        if self.original is not None:
            self._show(self.canvas_orig, self.original, "orig")

    def _on_view_press(self, e):
        """按下左键：进入拖动平移状态，记录起点并切换光标"""
        self._res_drag = (e.x, e.y)
        e.widget.config(cursor="fleur")

    def _on_view_drag(self, e):
        """拖动平移：把放大后超出画布边框的部分拖入视野，左右两框同步移动"""
        if self._res_drag is None or self._res_view_arr is None:
            return
        v = self.view["res"]
        v["dx"] += e.x - self._res_drag[0]
        v["dy"] += e.y - self._res_drag[1]
        self._res_drag = (e.x, e.y)
        self._clamp_view()
        self._redraw_all()

    def _on_view_release(self, _e):
        """松开左键：结束平移"""
        self._res_drag = None
        self.canvas_res.config(cursor="")
        self.canvas_orig.config(cursor="")

    def _on_view_dblclick(self, _e):
        """双击：共享视图复位到适应窗口"""
        self._reset_res_view()
        self._redraw_all()

    # ------------------------- 裁剪交互 -------------------------

    def _bind_crop(self):
        c = self.canvas_orig
        c.bind("<ButtonPress-1>", self._crop_press)
        c.bind("<B1-Motion>", self._crop_drag)
        c.bind("<ButtonRelease-1>", self._crop_release)

    def toggle_crop(self):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        self.crop_mode = not self.crop_mode
        self.crop_btn.config(text="裁剪中…（拖拽框选，再点一次取消）" if self.crop_mode
                             else "裁剪（在原图上拖拽框选区域）")
        self.canvas_orig.config(cursor="crosshair" if self.crop_mode else "")

    def _cv2img(self, x, y, tag):
        """画布坐标 → 图像坐标：先减去居中偏移量，再除以缩放比例（逆映射），并夹取到图像范围内"""
        r, ox, oy, iw, ih = self.disp_info.get(tag, (1, 0, 0, 1, 1))
        return int(np.clip((x - ox) / r, 0, iw - 1)), int(np.clip((y - oy) / r, 0, ih - 1))

    def _crop_press(self, e):
        if not self.crop_mode:
            self._on_view_press(e)     # 非裁剪模式：在左框按下左键 = 左右联动平移
            return
        self.crop_start = (e.x, e.y)
        self.crop_rect = None

    def _crop_drag(self, e):
        if not self.crop_mode:
            self._on_view_drag(e)      # 非裁剪模式：左框拖动 = 左右联动平移
            return
        if not self.crop_start:
            return
        c = self.canvas_orig
        if self.crop_rect:
            c.delete(self.crop_rect)
        x0, y0 = self.crop_start
        self.crop_rect = c.create_rectangle(x0, y0, e.x, e.y, outline="#f33", width=2)

    def _crop_release(self, e):
        if not self.crop_mode:
            self._on_view_release(e)   # 非裁剪模式：结束平移
            return
        if not self.crop_start:
            return
        # 把框选矩形在画布上的两端点换算成图像坐标，并规范为左上/右下角
        x0, y0 = self.crop_start
        ix0, iy0 = self._cv2img(x0, y0, "orig")
        ix1, iy1 = self._cv2img(e.x, e.y, "orig")
        x0, x1 = sorted((ix0, ix1))
        y0, y1 = sorted((iy0, iy1))
        self.crop_mode = False
        self.crop_btn.config(text="裁剪（在原图上拖拽框选区域）")
        self.canvas_orig.config(cursor="")
        if self.crop_rect:
            self.canvas_orig.delete(self.crop_rect)
            self.crop_rect = None
        if x1 - x0 < 5 or y1 - y0 < 5:      # 误点击形成的过小区域，不裁剪
            self.result_text.set("框选区域过小，裁剪取消")
            return
        # 直接对原始图像做区域切片（数组行/列区间取子块）
        self.current = self.original[y0:y1 + 1, x0:x1 + 1].copy()
        self._reset_preview_bases()
        self.result_text.set("裁剪完成（%d×%d）" % (self.current.shape[1], self.current.shape[0]))
        self._clear_compare()
        self.update_display()


def main():
    app = CellSegGUI()
    app.mainloop()


if __name__ == "__main__":
    main()