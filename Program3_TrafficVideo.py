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

# 共享 macOS 主题组件（圆角卡片 / 圆角按钮 / 扁平滑块 / 高DPI适配）
from ui_theme import enable_hidpi, pick_fonts, round_rect, RCard, RoundBtn, FlatSlider

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