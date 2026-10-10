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

import cv2
import numpy as np
from PIL import Image, ImageTk


class TrafficGUI(tk.Tk):
    """交通视频监控系统主界面"""

    def __init__(self):
        super().__init__()
        self.title("交通视频监控系统")
        self.geometry("1000x660")
        self.minsize(820, 500)

        self.cap = None            # OpenCV 视频捕获对象
        self.fps = 25.0            # 视频帧率
        self.playing = False       # 播放状态
        self.after_id = None       # 定时器句柄
        self.status_var = tk.StringVar(value="请点击【打开视频】选择交通监控视频文件")
        self.info_var = tk.StringVar(value="帧: 0/0   帧率: -- fps   速度: 1x")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------- 界面搭建 -------------------------

    def _build_ui(self):
        # 视频显示区
        lf = tk.LabelFrame(self, text="监控画面")
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas = tk.Canvas(lf, width=900, height=460, bg="#111")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 信息栏
        info_bar = tk.Frame(self)
        info_bar.pack(fill=tk.X, padx=8)
        tk.Label(info_bar, textvariable=self.info_var, anchor="w",
                 font=("", 10)).pack(side=tk.LEFT, padx=4)

        # 控制栏
        bar = tk.Frame(self, bd=2, relief=tk.RAISED)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Button(bar, text="打开视频", width=12, command=self.open_video).pack(side=tk.LEFT, padx=6, pady=6)
        self.btn_play = tk.Button(bar, text="▶ 播放", width=10, command=self.toggle_play)
        self.btn_play.pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="停止", width=8, command=self.stop).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="快进×2", width=8, command=self.set_fast).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="慢放×0.5", width=9, command=self.set_slow).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="播放速度:").pack(side=tk.LEFT, padx=(16, 0))
        self.speed_var = tk.DoubleVar(value=1.0)
        tk.Scale(bar, from_=0.25, to=2.0, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=self.speed_var, length=220).pack(side=tk.LEFT, padx=4, pady=4)

        self.loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="循环播放", variable=self.loop_var).pack(side=tk.LEFT, padx=10)

        tk.Label(bar, textvariable=self.status_var, anchor="e", fg="#05a").pack(
            side=tk.RIGHT, padx=10)

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
            # 播放到结尾：循环或停止
            if self.loop_var.get():
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            else:
                self.playing = False
                self.btn_play.config(text="▶ 播放")
                self.status_var.set("播放结束")
                return
        if not ret:
            return
        self._show_frame(frame)
        # 播放速度越快，帧间隔越短（快进）；越慢，帧间隔越长（慢放）
        delay = max(1, int(round(1000.0 / max(self.fps, 1.0) / self.speed_var.get())))
        self.after_id = self.after(delay, self._tick)
        self._update_info()

    # ------------------------- 显示 -------------------------

    def _show_frame(self, bgr):
        """把 OpenCV 帧 (BGR) 转 PIL 图像并等比例居中显示到画布"""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        cw = self.canvas.winfo_width() or 900
        ch = self.canvas.winfo_height() or 460
        r = min(cw / pil.width, ch / pil.height)
        w = max(1, int(pil.width * r))
        h = max(1, int(pil.height * r))
        photo = ImageTk.PhotoImage(pil.resize((w, h), Image.LANCZOS))
        self.canvas.delete("all")
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