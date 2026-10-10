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
        self.status_var = tk.StringVar(value="请点击【打开视频】选择交通监控视频文件")
        self.info_var = tk.StringVar(value="帧: 0/0   帧率: -- fps   速度: 1x")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------- 主题（字体 / 控件工厂） -------------------------

    def _setup_fonts(self):
        """英文优先 Inter-Medium，中文优先苹方中等（PingFang SC Medium），未安装时逐级回退"""
        self.f_en, self.f_cn = pick_fonts(self)

    def F(self, size, bold=False, eng=False):
        """界面字体：eng=True 用英文族（Inter），否则用中文族（苹方）"""
        return (self.f_en if eng else self.f_cn, size, "bold" if bold else "normal")

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
        self.status_var.set("已打开视频：%s" % name)
        ok, frame = self.cap.read()
        if ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # 回到第一帧
            self._show_frame(frame)
        self.btn_play.config(text="▶ 播放")
        self._update_info()
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

    def _tick(self):
        """播放主循环：按帧率/速度调度下一帧"""
        if not self.playing or self.cap is None:
            return
        ret, frame = self.cap.read()
        if not ret:
            # 已播到结尾：循环则回到第一帧继续读，否则停止播放
            if self.loop_var.get():
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            else:
                self.playing = False
                self.btn_play.config(text="▶ 播放")
                self.status_var.set("播放结束")
                return
        if not ret:
            return      # 循环读取仍失败（损坏帧等），本帧直接跳过
        self._show_frame(frame)
        # 播放速度越快，帧间隔越短（快进）；越慢，帧间隔越长（慢放）
        delay = max(1, int(round(1000.0 / max(self.fps, 1.0) / self.speed_var.get())))
        self.after_id = self.after(delay, self._tick)
        self._update_info()

    # ------------------------- 显示 -------------------------

    def _show_frame(self, bgr):
        """把 OpenCV 帧 (BGR) 转 PIL 图像并等比例居中显示到画布（深色圆角底衬托画面）"""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)   # OpenCV 的 BGR 序转 PIL 用的 RGB 序
        pil = Image.fromarray(rgb)
        cw = self.canvas.winfo_width() or 900
        ch = self.canvas.winfo_height() or 460
        r = min(cw / pil.width, ch / pil.height)     # 等比缩放比例，画面不变形
        w = max(1, int(pil.width * r))
        h = max(1, int(pil.height * r))
        photo = ImageTk.PhotoImage(pil.resize((w, h), Image.LANCZOS))
        self.canvas.delete("all")
        # 圆角显示底色：画布本身与卡片同色，圆角外露区域融入卡片背景
        round_rect(self.canvas, 1, 1, cw, ch, 16, fill=self.C_CANVAS, outline="")
        self.canvas.create_image(cw // 2, ch // 2, image=photo)
        self.canvas.photo = photo      # 保持引用防止被回收

    def _update_info(self):
        if self.cap is None:
            return
        pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.info_var.set("帧: %d/%d   帧率: %.1f fps   速度: %.2fx" %
                          (pos, total, self.fps, self.speed_var.get()))

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