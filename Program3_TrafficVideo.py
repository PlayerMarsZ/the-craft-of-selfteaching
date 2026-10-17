# -*- coding: utf-8 -*-
"""
============================================================================
 程序 3：交通视频监控系统
----------------------------------------------------------------------------
 开发环境：Python 3.x + Tkinter + OpenCV-Python + Pillow + NumPy
 依赖安装：pip install opencv-python pillow numpy
----------------------------------------------------------------------------
 功能清单（对照课程设计要求）：
  [1] 打开本地交通监控视频文件（mp4 / avi 等，依赖系统解码器）
  [2] 视频播放控制：播放 / 暂停 / 停止 / 快进（最高 2x）/ 慢放（最低 0.25x）
  [3] 循环播放选项；当前帧号、总帧数、帧率、播放速度实时显示
  [4] 视频画面全部在 GUI 窗口内显示
============================================================================
"""

import tkinter as tk
from tkinter import filedialog, messagebox
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
import threading
import urllib.request

# macOS 设计规范：颜色
COLORS = dict(
    BG="#F2F2F7", CARD="#FFFFFF", TEXT="#1D1D1F", SUB="#8E8E93",
    ACCENT="#0A84FF", ACC_D="#0068DA", BTN="#E8E8ED", BTN_D="#D9D9E0",
    LINE="#E3E3E8", OK_GRN="#2FBF5F", CANVAS="#202024", GLASS="#FAFAFC",
)

# ===== YOLOv8n（ONNX, OpenCV DNN 推理，无需 torch）车辆检测配置 =====
# 该 ONNX 为 OpenCV 官方 DNN 示例引用的打包版本（输出 1x84x8400，DNN 完全兼容）；
# ultralytics 官方 assets 已清理 v8 系列 ONNX，故使用此长期稳定的发布源
YOLO_MODEL_URL = ("https://github.com/CVHub520/X-AnyLabeling/releases/"
                  "download/v0.1.0/yolov8n.onnx")
YOLO_MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "yolov8n.onnx")
YOLO_INPUT = 640            # 模型输入尺寸 640x640
YOLO_CONF = 0.35            # 置信度阈值
YOLO_COCO_4W = {2: "CAR", 5: "BUS", 7: "TRUCK"}       # 四轮车（COCO 类别）
YOLO_COCO_2W = {1: "BIKE", 3: "MOTO"}                  # 两轮车（COCO 类别）


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

import cv2
import numpy as np
from PIL import Image, ImageTk


class TrafficGUI(tk.Tk):
    """交通视频监控系统主界面（macOS 风格：浅灰底 + 卡片 + 扁平按钮 + 系统蓝强调色）"""

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
    C_CANVAS = "#1C1C1E"
    GLASS    = "#FAFAFC"

    def __init__(self):
        enable_hidpi()          # 高 DPI 适配（必须在创建根窗口之前）
        super().__init__()
        self.title("交通视频监控系统")
        self.geometry("1040x700")
        self.minsize(820, 500)
        # 按屏幕实际 DPI 设置 Tk 缩放，避免高分辨率屏界面发虚
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        self.configure(bg=self.C_BG)
        self._setup_fonts()

        self.cap = None            # OpenCV 视频捕获对象
        self.fps = 25.0            # 视频帧率
        self.playing = False       # 播放状态
        self.after_id = None       # 定时器句柄
        self.status_var = tk.StringVar(value="【引擎 v3.2】请点击【打开视频】选择交通监控视频文件")
        self.info_var = tk.StringVar(value="已读帧: 0   元数据总帧: --   帧率: -- fps   速度: 1x")

        # -------- 车辆检测/计数状态 --------
        self.detect_on = False      # 检测开关
        self._bg = None             # MOG2 背景建模器（开启检测时创建）
        self._bg_vt = -1            # 建模器对应的灵敏度参数（变化时重建）
        self.tracks = {}            # 跟踪目标 {id: {c:(x,y), last:(x,y), counted, box, cls}}
        self._next_id = 0
        self.total_count = 0        # 跨线车辆总数（= total_cars + total_bikes）
        self.total_cars = 0         # 四轮车计数（跨线）
        self.total_bikes = 0        # 两轮车计数（跨线）
        self._line_y = None         # 检测线 y 坐标（按画面高度比例 0.6 设定）
        self._fps_manual = None     # 手动播放帧率（None=自动，见 fps_override）
        self._fps_est = None        # 播放中按时间戳实测的真实帧率（自动校准，优于容器元数据）
        self._ms_hist = []          # 最近若干帧的时间戳(ms)，用于实测帧率
        self._det_fast = True       # 经典检测隔帧运行，保证 30fps 视频播放流畅
        self._det_phase = 0         # 隔帧相位计数
        self._track_cache = None    # 最近一次跟踪结果缓存（隔帧重绘用）
        self._img_item = None       # 画布上的画面图像项（复用更新，减负）
        self._last_cv = None        # 画布尺寸缓存（round_rect 仅在尺寸变化时重画）

        # -------- YOLO 按车道检测状态 --------
        self.yolo_on = False        # YOLO 模式开关
        self._yolo_net = None       # cv2.dnn 网络（onnx 加载成功后）
        self._yolo_ready = False    # 模型是否可用
        self._yolo_cache = None     # 最近一次推理结果（隔帧复用，降低 CPU 占用）
        self._yolo_tick = 0         # 隔帧计数（每 3 帧推理一次）
        self._yolo_dl_pct = -1      # 模型下载进度百分比（-1 表示无下载任务）

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

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

    def _card(self, parent, title=None):
        """白色圆角卡片面板（内容放到 card.inner 中）"""
        card = RCard(parent, fill=self.C_CARD, outline=self.C_LINE, radius=20, pad=12)
        if title:
            tk.Label(card.inner, text=title, bg=self.C_CARD, fg=self.C_TEXT,
                     font=self.F(11, True)).pack(anchor="w", padx=10, pady=(6, 2))
        return card

    # ------------------------- 界面搭建 -------------------------

    def _build_ui(self):
        # 视频显示区（白色圆角卡片 + 深色圆角画布）
        lf = self._card(self, "监控画面")
        lf.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 6))
        self.canvas = tk.Canvas(lf.inner, width=900, height=460, bg=self.C_CARD,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 信息栏（白色圆角卡片内浅灰文字）
        info_card = RCard(self, fill=self.C_CARD, outline=self.C_LINE, radius=12, pad=8)
        info_card.pack(fill=tk.X, padx=14, pady=(6, 0))
        tk.Label(info_card.inner, textvariable=self.info_var, anchor="w", bg=self.C_CARD,
                 fg=self.C_SUB, font=self.F(10, eng=True), padx=6, pady=4).pack(fill=tk.X)

        # 控制栏（macOS 风格：细线分隔 + 浅色底）
        tk.Frame(self, bg=self.C_LINE, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        bar = tk.Frame(self, bg=self.GLASS, highlightthickness=0)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._btn(bar, "打开视频", self.open_video, primary=True).pack(
            side=tk.LEFT, padx=(14, 5), pady=9)
        self.btn_play = self._btn(bar, "▶ 播放", self.toggle_play, size=10, bold=True)
        self.btn_play.pack(side=tk.LEFT, padx=5, pady=9)
        self._btn(bar, "停止", self.stop).pack(side=tk.LEFT, padx=5, pady=9)
        self._btn(bar, "快进×2", self.set_fast).pack(side=tk.LEFT, padx=5, pady=9)
        self._btn(bar, "慢放×0.5", self.set_slow).pack(side=tk.LEFT, padx=5, pady=9)

        self._lab(bar, "播放速度", size=9).pack(side=tk.LEFT, padx=(16, 0))
        self.speed_var = tk.DoubleVar(value=1.0)
        FlatSlider(bar, variable=self.speed_var, from_=0.25, to=2.0, resolution=0.05,
                   length=180, font=self.F(9, eng=True)
                   ).pack(side=tk.LEFT, padx=8, pady=10)

        self.loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="循环播放", variable=self.loop_var,
                       bg=self.GLASS, fg=self.C_TEXT, activebackground=self.GLASS,
                       activeforeground=self.C_ACCENT, selectcolor=self.C_CARD,
                       highlightthickness=0, bd=0, font=self.F(10)
                       ).pack(side=tk.LEFT, padx=10, pady=9)

        tk.Label(bar, textvariable=self.status_var, anchor="e", bg=self.GLASS,
                 fg=self.C_OK, font=self.F(9)).pack(side=tk.RIGHT, padx=12)

        # 检测控制行（车辆检测 + 清空计数 + 灵敏度滑块 + 实时统计）
        bar2 = tk.Frame(self, bg=self.GLASS, highlightthickness=0)
        bar2.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_detect = self._btn(bar2, "车辆检测: 关", self.toggle_detect)
        self.btn_detect.pack(side=tk.LEFT, padx=(14, 5), pady=6)
        self._btn(bar2, "清空计数", self.reset_count).pack(side=tk.LEFT, padx=5, pady=6)

        self._lab(bar2, "检测灵敏度", size=9).pack(side=tk.LEFT, padx=(16, 0))
        self.sens_var = tk.DoubleVar(value=24.0)   # MOG2 varThreshold（越小越敏感）
        FlatSlider(bar2, variable=self.sens_var, from_=8.0, to=64.0, resolution=1.0,
                   length=140, font=self.F(9, eng=True)
                   ).pack(side=tk.LEFT, padx=8, pady=8)

        self.count_var = tk.StringVar(value="车辆总数: 0（四轮 0 / 两轮 0）  当前目标: 0")
        tk.Label(bar2, textvariable=self.count_var, anchor="e", bg=self.GLASS,
                 fg=self.C_ACCENT, font=self.F(10, True)
                 ).pack(side=tk.RIGHT, padx=14)

        # 播放帧率选择：视频元数据误报帧率时可手动指定（如确认原片 30fps 就选 30）
        self.fps_override = tk.StringVar(value="自动")
        self._fps_menu = tk.OptionMenu(bar2, self.fps_override, "自动",
                                       "24", "25", "30", "50", "60",
                                       command=self.apply_fps_override)
        self._fps_menu.config(bg=self.GLASS, fg=self.C_TEXT, font=self.F(9),
                              highlightthickness=0, bd=0, activebackground=self.C_BTN)
        self._lab(bar2, "播放帧率", size=9).pack(side=tk.LEFT, padx=(16, 0))
        self._fps_menu.pack(side=tk.LEFT, padx=5, pady=6)

        # YOLO 行（按车道识别的两轮/四轮分离统计）
        bar3 = tk.Frame(self, bg=self.GLASS, highlightthickness=0)
        bar3.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_yolo = self._btn(bar3, "YOLO 车道识别: 关", self.toggle_yolo)
        self.btn_yolo.pack(side=tk.LEFT, padx=(14, 5), pady=6)
        self._lab(bar3, "车道数", size=9).pack(side=tk.LEFT, padx=(16, 0))
        self.lane_var = tk.DoubleVar(value=3.0)      # 画面横向均分车道数 1~4
        FlatSlider(bar3, variable=self.lane_var, from_=1.0, to=4.0, resolution=1.0,
                   length=90, font=self.F(9, eng=True)
                   ).pack(side=tk.LEFT, padx=8, pady=8)
        self.yolo_var = tk.StringVar(value="YOLO 未开启（按车道统计 四轮/两轮）")
        tk.Label(bar3, textvariable=self.yolo_var, anchor="e", bg=self.GLASS,
                 fg=self.C_OK, font=self.F(10)
                 ).pack(side=tk.RIGHT, padx=14)

    # ------------------------- 视频开关 -------------------------

    def open_video(self, path=None):
        """打开视频文件；path 为空时弹出文件选择框（便于程序化测试）"""
        if path is None:
            path = filedialog.askopenfilename(
                title="选择交通监控视频",
                filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv"),
                           ("所有文件", "*.*")])
        if not path:
            return False
        self.playing = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            self.cap = None
            messagebox.showerror("打开失败", "无法打开该视频，请检查文件格式/编码")
            return False
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 0 < fps <= 240 else 25.0     # 异常帧率兜底
        name = path.replace("\\", "/").split("/")[-1]
        meta_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.status_var.set("已打开：%s（元数据 %d 帧 @ %.0f fps，播放中将自动实测校正）"
                            % (name, meta_frames, self.fps))
        ok, frame = self.cap.read()
        if ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # 回到第一帧
            self._show_frame(frame)
        self.btn_play.config(text="▶ 播放")
        self._update_info()
        # 新视频：清空检测统计（背景模型与跟踪目标一并重置）
        self.tracks = {}
        self.total_count = 0
        self.total_cars = 0
        self.total_bikes = 0
        self._line_y = None
        self._bg = None
        self._bg_vt = -1
        self._yolo_cache = None        # YOLO 隔帧缓存随视频重置
        self._fps_est = None           # 实测帧率随新视频重置
        self._ms_hist = []
        self._img_item = None          # 画布图像项随新视频重置
        self._last_cv = None
        self._track_cache = None       # 隔帧检测缓存随新视频重置
        self.count_var.set("车辆总数: 0（四轮 0 / 两轮 0）  当前目标: 0")
        return True

    # ------------------------- 播放控制 -------------------------

    def toggle_play(self):
        """播放 / 暂停切换"""
        if self.cap is None:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        if self.playing:
            self.playing = False
            if self.after_id:
                self.after_cancel(self.after_id)
                self.after_id = None
            self.btn_play.config(text="▶ 播放")
            self.status_var.set("已暂停")
        else:
            self.playing = True
            self.btn_play.config(text="⏸ 暂停")
            self.status_var.set("播放中…")
            self._tick()

    def stop(self):
        """停止播放并回到第一帧"""
        self.playing = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.cap is not None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if ok:
                self._show_frame(frame)
        self.btn_play.config(text="▶ 播放")
        self.status_var.set("已停止，回到第一帧")
        self._update_info()

    def set_fast(self):
        """快进 2 倍"""
        self.speed_var.set(2.0)
        self.status_var.set("速度设为 2x（快进）")

    def set_slow(self):
        """慢放 0.5 倍"""
        self.speed_var.set(0.5)
        self.status_var.set("速度设为 0.5x（慢放）")

    # ------------------------- 车辆检测 / 计数 -------------------------

    def toggle_detect(self):
        """开启/关闭经典车辆检测（MOG2 跨线计数）。与 YOLO 模式互斥。"""
        if self.cap is None:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        self.detect_on = not self.detect_on
        if self.detect_on:
            if self.yolo_on:            # 互斥：开启经典检测时关闭 YOLO
                self.yolo_on = False
                self.btn_yolo.config(text="YOLO 车道识别: 关")
                self.yolo_var.set("YOLO 未开启（按车道统计 四轮/两轮）")
            self.btn_detect.config(text="车辆检测: 开")
            self.status_var.set("车辆检测已开启：跨线计数（可调灵敏度）")
        else:
            self.btn_detect.config(text="车辆检测: 关")
            self.status_var.set("车辆检测已关闭")

    def reset_count(self):
        """清空车辆计数与当前跟踪目标（四轮/两轮分开清）"""
        self.total_count = 0
        self.total_cars = 0
        self.total_bikes = 0
        self.tracks = {}
        self.count_var.set("车辆总数: 0（四轮 0 / 两轮 0）  当前目标: 0")
        self.status_var.set("计数已清零")

    # ------------------------- YOLO 按车道识别（两轮/四轮分离） -------------------------

    def toggle_yolo(self):
        """开启/关闭 YOLO 车道识别模式（与经典检测互斥）：
        模型文件 yolov8n.onnx 放在脚本同目录即用；缺失时自动后台下载
        （约 13MB，OpenCV 官方示例同款发布源），下载完成后自动加载。"""
        if self.cap is None:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        self.yolo_on = not self.yolo_on
        if self.yolo_on:
            if self.detect_on:          # 互斥：关闭经典检测
                self.detect_on = False
                self.btn_detect.config(text="车辆检测: 关")
            if self._yolo_net is not None:
                self._yolo_ready = True
                self.btn_yolo.config(text="YOLO 车道识别: 开")
                self.status_var.set("YOLO 车道识别已开启（绿框=四轮 橙框=两轮）")
            elif os.path.exists(YOLO_MODEL_FILE):
                self._load_yolo_model()
            else:
                self.btn_yolo.config(text="YOLO 模型下载中…")
                self.status_var.set("首次使用：正在后台下载 yolov8n.onnx（约 13MB）…")
                self._download_yolo_model()
        else:
            self._yolo_cache = None
            self.btn_yolo.config(text="YOLO 车道识别: 关")
            self.yolo_var.set("YOLO 未开启（按车道统计 四轮/两轮）")
            self.status_var.set("YOLO 车道识别已关闭")

    def _load_yolo_model(self):
        """加载本地 yolov8n.onnx（OpenCV DNN，CPU 推理，无需 PyTorch）"""
        try:
            self._yolo_net = cv2.dnn.readNetFromONNX(YOLO_MODEL_FILE)
            self._yolo_ready = True
            self.btn_yolo.config(text="YOLO 车道识别: 开")
            self.status_var.set("YOLO 模型加载成功（绿框=四轮 橙框=两轮）")
        except Exception as e:
            self._yolo_ready = False
            self.yolo_on = False
            self.btn_yolo.config(text="YOLO 车道识别: 关")
            messagebox.showerror(
                "模型加载失败",
                "yolov8n.onnx 加载失败：%s\n\n请确认模型文件完整，"
                "或删除后重新开启（自动重新下载）" % e)

    def _download_yolo_model(self):
        """后台线程下载 yolov8n.onnx；下载完成后回到主线程加载"""

        def _dl():
            try:
                req = urllib.request.Request(YOLO_MODEL_URL,
                                             headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    total = int(r.headers.get("Content-Length") or 0)
                    done = 0
                    with open(YOLO_MODEL_FILE + ".part", "wb") as fp:
                        while True:
                            chunk = r.read(1 << 16)
                            if not chunk:
                                break
                            fp.write(chunk)
                            done += len(chunk)
                            self._yolo_dl_pct = (done * 100 // total) if total else -1
                os.replace(YOLO_MODEL_FILE + ".part", YOLO_MODEL_FILE)
                self._yolo_dl_pct = 100
            except Exception as e:
                self._yolo_dl_pct = -2          # -2 = 失败
                self._yolo_err = str(e)

        threading.Thread(target=_dl, daemon=True).start()
        self.after(300, self._poll_yolo_download)

    def _poll_yolo_download(self):
        """轮询模型下载进度：完成→加载模型；失败→提示手动放置"""
        pct = self._yolo_dl_pct
        if pct == -1:                       # 仍在下载（无长度信息）
            self.status_var.set("正在下载 yolov8n.onnx …")
            self.after(400, self._poll_yolo_download)
        elif pct == 100:
            self.status_var.set("模型下载完成，正在加载…")
            self._load_yolo_model()
        elif pct == -2:
            self.yolo_on = False
            self.btn_yolo.config(text="YOLO 车道识别: 关")
            messagebox.showerror(
                "下载失败", "模型自动下载失败：%s\n\n请手动下载 yolov8n.onnx 并"
                "放到本程序同目录（%s）：\n%s" %
                (getattr(self, "_yolo_err", "网络不可达"), os.path.dirname(YOLO_MODEL_FILE),
                 YOLO_MODEL_URL))
        else:
            self.status_var.set("正在下载 YOLO 模型 %d%%…" % pct)
            self.after(400, self._poll_yolo_download)

    def _lane_boxes(self, w, h):
        """车道划分：画面横向均分 lane_count 份，返回 (车道宽度, x 边界列表)"""
        n = max(1, min(4, int(self.lane_var.get())))
        return w / n, [int(w * i / n) for i in range(n + 1)]

    def _detect_yolo(self, frame):
        """YOLO 按车道检测：每 3 帧推理一次（640x640 CPU 推理，隔帧以保流畅），
        中间帧沿用上次结果。两轮/四轮用不同框区分，画面叠加车道虚线与分车道
        统计标签。"""
        h, w = frame.shape[:2]
        self._yolo_tick = (self._yolo_tick + 1) % 3
        if self._yolo_tick != 1 and self._yolo_cache is not None:
            self._draw_yolo(frame, self._yolo_cache)   # 隔帧：复用缓存结果重绘
            return frame
        if not self._yolo_ready or self._yolo_net is None:
            return frame

        dets = []          # [(cls_letter, conf, x, y, bw, bh)]
        try:
            blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (YOLO_INPUT, YOLO_INPUT),
                                         swapRB=True, crop=False)
            self._yolo_net.setInput(blob)
            out = self._yolo_net.forward()          # (1, 84, 8400)
            rows = out[0].T                          # (8400, 84): cx,cy,bw,bh + 80类分数
            boxes, scores, kinds = [], [], []
            for r in rows:
                cs = r[4:]
                i = int(np.argmax(cs))
                label, is_4w = None, False
                if i in YOLO_COCO_4W:
                    label, is_4w = YOLO_COCO_4W[i], True
                elif i in YOLO_COCO_2W:
                    label = YOLO_COCO_2W[i]
                else:
                    continue
                score = float(cs[i])
                if score < YOLO_CONF:
                    continue
                cx, cy, bw, bh = r[:4]
                x, y = (cx - bw / 2) * w, (cy - bh / 2) * h
                bw, bh = bw * w, bh * h
                boxes.append([x, y, bw, bh])
                scores.append(score)
                kinds.append((label, is_4w))
            idx = cv2.dnn.NMSBoxes(boxes, scores, YOLO_CONF, 0.45)
            for k in (idx.flatten() if len(idx) else []):
                x, y, bw, bh = boxes[k]
                dets.append((kinds[k][0], kinds[k][1], scores[k],
                             int(x), int(y), int(bw), int(bh)))
        except Exception:
            pass
        self._yolo_cache = dets
        self._draw_yolo(frame, dets)
        return frame

    def _draw_yolo(self, frame, dets):
        """把 YOLO 检测框 + 车道分隔虚线 + 分车道统计画到帧上（返回的帧直接显示）"""
        h, w = frame.shape[:2]
        lane_w, xs = self._lane_boxes(w, h)
        # 车道分隔虚线
        for x0 in xs[1:-1]:
            yy = 0
            while yy < h:
                cv2.line(frame, (x0, yy), (x0, min(yy + 18, h)), (240, 240, 240), 1)
                yy += 32
        # 每车道内 4 轮/2 轮统计
        cnt = [[0, 0] for _ in range(len(xs) - 1)]   # [四轮, 两轮] 按车道
        for (label, is_4w, conf, x, y, bw, bh) in dets:
            lane = max(0, min(len(cnt) - 1, int((x + bw / 2) // lane_w)))
            cnt[lane][0 if is_4w else 1] += 1
            color = (46, 199, 85) if is_4w else (0, 165, 255)   # 四轮绿 / 两轮橙
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
            if not is_4w:               # 两轮车：加内圈细框（双框样式区分）
                cv2.rectangle(frame, (x + 3, y + 3), (x + bw - 3, y + bh - 3), color, 1)
            cv2.putText(frame, "%s %.2f" % (label, conf), (x, max(38, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)
        # 顶部统计条 + 各车道标签（车道标签放条下方各自车道内，避免文字重叠）
        cv2.rectangle(frame, (0, 0), (w, 34), (28, 30, 40), -1)
        total4 = sum(c[0] for c in cnt); total2 = sum(c[1] for c in cnt)
        cv2.putText(frame, "YOLO 4W:%d  2W:%d  TOTAL:%d" % (total4, total2, total4 + total2),
                    (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2,
                    cv2.LINE_AA)
        for i, c in enumerate(cnt):
            cv2.putText(frame, "L%d 4W:%d 2W:%d" % (i + 1, c[0], c[1]),
                        (xs[i] + 6, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 2, cv2.LINE_AA)
        # GUI 底部统计栏（中文）
        parts = ["车道%d 四轮%d 两轮%d" % (i + 1, c[0], c[1])
                 for i, c in enumerate(cnt)]
        self.yolo_var.set(" | ".join(parts) + " | 合计 %d 辆" % (total4 + total2))

    def _merge_boxes(self, boxes):
        """重叠/包含框合并：消除同一辆车前后轮区域被拆成多个检测的问题。
        框格式 [x, y, w, h, cls]；合并时继承面积较大框的类别（两轮/四轮）。"""
        changed = True
        while changed and len(boxes) > 1:
            changed = False
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    x1, y1, w1, h1 = boxes[i][:4]
                    x2, y2, w2, h2 = boxes[j][:4]
                    ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                    iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                    inter = ix * iy
                    if inter > 0.35 * min(w1 * h1, w2 * h2):
                        ux = min(x1, x2); uy = min(y1, y2)
                        uw = max(x1 + w1, x2 + w2) - ux
                        uh = max(y1 + h1, y2 + h2) - uy
                        keep = i if w1 * h1 >= w2 * h2 else j
                        boxes[i] = [ux, uy, uw, uh, boxes[keep][4]]
                        boxes.pop(j)
                        changed = True
                        break
                if changed:
                    break
        return boxes

    def _detect(self, bgr):
        """对一帧做车辆检测+跟踪+绊线计数，返回叠加了标注的 BGR 帧。
        全程仅用 numpy/cv2 经典方法，速度快、依赖少（创新点见 toggle_detect）。"""
        h, w = bgr.shape[:2]
        if self._line_y is None:
            self._line_y = int(h * 0.6)          # 虚拟检测线：画面 60% 高度处
        vt = int(self.sens_var.get())
        if self._bg is None or vt != self._bg_vt:
            # 灵敏度滑块变化 → 重建背景模型，参数即时生效
            self._bg = cv2.createBackgroundSubtractorMOG2(
                history=400, varThreshold=vt, detectShadows=True)
            self._bg_vt = vt
        fg = self._bg.apply(bgr)
        # 阴影抑制：MOG2 的阴影标记为 127，阈值截断后只保留真实前景
        _, fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        min_area = max(60, int(w * h * 0.00012))          # 保留小目标（两轮车投影小）
        bike_big = int(w * h * 0.008)                      # 小于该面积的两轮车候选
        for c in cnts:
            x, y, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            if area < min_area:
                continue
            ar = bw / max(bh, 1)
            if not (0.25 <= ar <= 4.5):       # 放宽比例约束：自行车窄长也保留
                continue
            # 两轮/四轮启发式分类：
            # ① 窄长目标（自行车，ar<0.6）；② 目标投影小且近似方形（摩托车，
            # 面积小于画面 0.8% 且 ar<0.95）。其余按四轮汽车计。
            cls = "bike" if ((area < bike_big and ar < 0.95) or ar < 0.6) else "car"
            boxes.append([x, y, bw, bh, cls])
        boxes = self._merge_boxes(boxes)

        # ---- 质心最近邻跟踪 + EMA 平滑 ----
        cents = [(x + bw / 2.0, y + bh / 2.0) for (x, y, bw, bh, _c) in boxes]
        used = [False] * len(cents)
        for tid, t in self.tracks.items():
            best, bd = None, 1e9
            for i, c in enumerate(cents):
                if used[i]:
                    continue
                d = (c[0] - t["c"][0]) ** 2 + (c[1] - t["c"][1]) ** 2
                if d < bd:
                    bd, best = d, i
            if best is not None and bd <= 70.0 ** 2:
                used[best] = True
                nc = cents[best]
                t["last"], t["c"] = t["c"], t["c"]      # 旧质心记为上一帧位置
                t["c"] = (0.72 * nc[0] + 0.28 * t["c"][0],
                          0.72 * nc[1] + 0.28 * t["c"][1])   # EMA 平滑防抖动
                t["box"] = boxes[best][:4]
                t["cls"] = boxes[best][4]
                t["lost"] = 0
                # 虚拟检测线绊线计数（带方向，跨线只计一次；四轮/两轮分账）
                if not t["counted"]:
                    prev_y, cur_y = t["last"][1], t["c"][1]
                    if (prev_y - self._line_y) * (cur_y - self._line_y) < 0 or \
                            (prev_y != self._line_y and cur_y == self._line_y):
                        t["counted"] = True
                        if t["cls"] == "bike":
                            self.total_bikes += 1
                        else:
                            self.total_cars += 1
                        self.total_count = self.total_cars + self.total_bikes
                        self.status_var.set(
                            "检测到%s驶过检测线（四轮 %d / 两轮 %d）" %
                            ("两轮车" if t["cls"] == "bike" else "四轮车",
                             self.total_cars, self.total_bikes))
            else:
                t["lost"] += 1
        self.tracks = {tid: t for tid, t in self.tracks.items() if t["lost"] <= 4}
        for i, c in enumerate(cents):
            if not used[i]:                # 新出现目标 → 分配唯一 ID（类别随框）
                self.tracks[self._next_id] = {"c": c, "last": c, "box": boxes[i][:4],
                                              "cls": boxes[i][4],
                                              "counted": False, "lost": 0}
                self._next_id += 1

        # ---- 结果叠加到画面（GUI 内直接可见）----
        return self._draw_tracks(bgr)

    def _draw_tracks(self, bgr):
        """把当前跟踪结果 + 检测线 + 分账统计叠加到帧上（轻量，可每帧复用缓存）"""
        out = bgr
        h, w = out.shape[:2]
        if self._line_y is None:
            self._line_y = int(h * 0.6)
        cv2.line(out, (0, self._line_y), (w, self._line_y), (0, 200, 255), 2)
        for tid, t in self.tracks.items():
            if t["box"] is None:
                continue
            x, y, bw, bh = t["box"]
            if t["cls"] == "bike":                        # 两轮车：品红框/紫框
                color = (200, 60, 200) if t["counted"] else (255, 0, 220)
                tag = "BIKE %d" % tid
            else:                                          # 四轮车：绿=已计数 橙=未过线
                color = (46, 199, 85) if t["counted"] else (0, 150, 255)
                tag = "CAR %d" % tid
            cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
            cv2.circle(out, (int(t["c"][0]), int(t["c"][1])), 4, color, -1)
            cv2.putText(out, tag, (x, max(38, y - 6)),   # 38=顶部统计条下方，避免被遮挡
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
        cv2.rectangle(out, (0, 0), (w, 34), (28, 30, 40), -1)
        cv2.putText(out, "CARS: %d   BIKES: %d   TRACKING: %d   LINE" %
                    (self.total_cars, self.total_bikes, len(self.tracks)),
                    (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2,
                    cv2.LINE_AA)
        self.count_var.set("车辆总数: %d（四轮 %d / 两轮 %d）  当前目标: %d" %
                           (self.total_count, self.total_cars, self.total_bikes,
                            len(self.tracks)))
        return out

    # ------------------------- 播放主循环 -------------------------

    def _tick(self):
        """播放主循环：按帧率/速度调度下一帧"""
        if not self.playing or self.cap is None:
            return
        ret, frame = self.cap.read()
        bad = 0
        while not ret and bad < 8:
            # 坏帧/解码失败容错：跳到下一帧继续读，避免视频中途卡死提前"播放结束"
            pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos + 1)
            ret, frame = self.cap.read()
            bad += 1
        if not ret:
            # 已播到结尾：循环则回到第一帧继续读，否则停止播放
            if self.loop_var.get():
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            else:
                self.playing = False
                self.btn_play.config(text="▶ 播放")
                pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                meta = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
                note = ("，元数据 %d 帧不准（以实际为准）" % meta
                        if abs(pos - meta) > 3 else "，全长 %d 帧" % meta)
                self.status_var.set("播放结束：实际读到 %d 帧%s" % (pos, note))
                return
        if not ret:
            return      # 循环读取仍失败（损坏帧等），本帧直接跳过
        self._calibrate_fps()   # 播放中按时间戳实测真实帧率（元数据误报时自动纠正）
        if self.detect_on:
            self._det_phase = (self._det_phase + 1) % 2
            if self._det_fast and self._det_phase == 0 and self._track_cache:
                # 隔帧：本轮不跑 MOG2/跟踪，只复用上一帧结果重绘（省一半算力，
                # 保证 30fps 视频也能实时播放；帧间仅 1/30s 目标位移极小）
                frame = self._draw_tracks(frame)
            else:
                frame = self._detect(frame)
                self._track_cache = True
        if self.yolo_on:
            frame = self._detect_yolo(frame)   # YOLO：按车道两轮/四轮分离统计
        self._show_frame(frame)
        # 播放速度越快，帧间隔越短（快进）；越慢，帧间隔越长（慢放）
        delay = max(1, int(round(1000.0 / max(self._eff_fps(), 1.0) / self.speed_var.get())))
        self.after_id = self.after(delay, self._tick)
        self._update_info()

    # ------------------------- 显示 -------------------------

    def _show_frame(self, bgr):
        """把 OpenCV 帧 (BGR) 转 PIL 图像并等比例居中显示到画布。
        cv2 线性缩放 + 图像项复用更新（itemconfig），30fps 高分辨率视频也能
        实时刷新；深色圆角底仅在画布尺寸变化时重画。"""
        cw = self.canvas.winfo_width() or 900
        ch = self.canvas.winfo_height() or 460
        h0, w0 = bgr.shape[:2]
        r = min(cw / w0, ch / h0)                        # 等比缩放比例，画面不变形
        w = max(1, int(w0 * r))
        h = max(1, int(h0 * r))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)       # BGR → RGB
        small = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
        photo = ImageTk.PhotoImage(Image.fromarray(small), master=self.canvas)
        if (cw, ch) != self._last_cv:
            self.canvas.delete("all")                    # 尺寸变化：重建圆角底与图像项
            round_rect(self.canvas, 1, 1, cw, ch, 16, fill=self.C_CANVAS, outline="")
            self._img_item = self.canvas.create_image(cw // 2, ch // 2,
                                                      image=photo, anchor="center")
            self._last_cv = (cw, ch)
        else:
            self.canvas.itemconfig(self._img_item, image=photo)   # 只换图，最快路径
        self.canvas.photo = photo      # 保持引用防止被回收

    def _eff_fps(self):
        """有效播放帧率优先级：手动指定 > 播放中时间戳实测 > 视频元数据（兜底 25）"""
        if self._fps_manual:
            return self._fps_manual
        if self._fps_est:
            return self._fps_est
        return self.fps

    def _fps_tag(self):
        """信息栏里的帧率来源标注"""
        if self._fps_manual:
            return "手动"
        if self._fps_est is not None and abs(self._fps_est - self.fps) > 2.0:
            return "实测"     # 实测推翻了元数据
        return "视频"

    def _calibrate_fps(self):
        """用帧时间戳窗口的端点斜率自动实测真实帧率。
        不能取"相邻间隔中位数"：部分视频容器的时间戳按 1/12s 时间基量化
        （全部戳都是 83ms 整数倍），中位数恒为 83ms → 会误测成 12fps。
        端点斜率在 N 帧窗口上做平均，量化误差被摊平（如 12 帧戳前进 1000ms，
        斜率仍准确还原 30fps）。"""
        if self._fps_manual is not None:
            return
        try:
            self._ms_hist.append(float(self.cap.get(cv2.CAP_PROP_POS_MSEC)))
        except Exception:
            return
        self._ms_hist = self._ms_hist[-40:]          # 约 1.3s 窗口：足够长以摊平时间戳量化台阶
        if len(self._ms_hist) < 20:
            return
        d_total = self._ms_hist[-1] - self._ms_hist[0]
        if d_total <= 0:
            return
        est = 1000.0 * (len(self._ms_hist) - 1) / d_total     # 窗口端点斜率 → fps
        if not (1.0 <= est <= 240.0):
            return
        if abs(est - self.fps) <= 8.0:
            # 实测与元数据一致（含时间戳量化引入的 <20% 偏差）→ 采用更稳的元数据
            self._fps_est = self.fps
        else:
            # 差异巨大：元数据明显不可信（如 30fps 视频被报成 12），采用实测值
            if self._fps_est is None:
                self.status_var.set("已按实测时间戳校准帧率：%.0f fps（元数据 %.0f，差异过大）"
                                    % (est, self.fps))
            self._fps_est = round(est, 1)

    def apply_fps_override(self, _e=None):
        """播放帧率选择器：视频元数据误报时手动指定真实帧率"""
        v = self.fps_override.get()
        self._fps_manual = None if v == "自动" else float(v)
        self.status_var.set("播放帧率: %s（当前有效 %.0f fps）" %
                            (v, self._eff_fps()))

    def _update_info(self):
        if self.cap is None:
            return
        pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        # 元数据总帧数不可靠（常见误报为极小值，界面会出现"固定12帧"），
        # 以"已读帧数 + 元数据帧数"并列显示，绝不只依赖元数据
        meta = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.info_var.set("已读帧: %d   元数据总帧: %d   帧率: %.0f fps(%s)   速度: %.2fx"
                          % (pos, meta, self._eff_fps(), self._fps_tag(),
                             self.speed_var.get()))

    def on_close(self):
        """窗口关闭时释放视频资源"""
        self.playing = False
        if self.after_id:
            self.after_cancel(self.after_id)
        if self.cap is not None:
            self.cap.release()
        self.destroy()


def main():
    app = TrafficGUI()
    app.mainloop()


if __name__ == "__main__":
    main()