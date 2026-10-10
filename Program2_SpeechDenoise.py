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

import numpy as np
from scipy.io import wavfile
from scipy.signal import wiener, resample

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib import rcParams

# 中文字体兼容设置（Windows 下 SimHei，Linux 下常见中文字体）
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Noto Sans CJK SC",
                               "WenQuanYi Micro Hei", "Arial Unicode MS", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False

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
    """语音采集及降噪系统主界面"""

    def __init__(self):
        super().__init__()
        self.title("语音采集及降噪系统")
        self.geometry("1460x860")
        self.minsize(1200, 700)

        self.fs = 16000            # 当前采样率
        self.original = None       # 原始语音 float64 数组
        self.noisy = None          # 加噪信号
        self.denoised = None       # 去噪信号
        self._rec_cancel = False   # 取消录音标志
        self.status_var = tk.StringVar(value="请先【生成测试音频】/【开始采集】/【打开音频】")
        self.metric_var = tk.StringVar(value="")

        self._build_ui()

    # ------------------------- 界面搭建 -------------------------

    def _build_ui(self):
        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        # ---------------- 左侧控制面板 ----------------
        ctrl = tk.Frame(body, width=430)
        ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        ctrl.pack_propagate(False)

        # ① 语音采集 / 文件读写
        f1 = tk.LabelFrame(ctrl, text="① 语音采集 / 读写")
        f1.pack(fill=tk.X, pady=3)
        row = tk.Frame(f1); row.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(row, text="采样率:").pack(side=tk.LEFT)
        self.fs_combo = ttk.Combobox(row, values=["8000", "16000", "44100"],
                                     width=8, state="readonly")
        self.fs_combo.current(1)
        self.fs_combo.pack(side=tk.LEFT, padx=4)
        tk.Label(row, text="时长(s):").pack(side=tk.LEFT)
        self.dur_var = tk.StringVar(value="3")
        tk.Entry(row, textvariable=self.dur_var, width=6).pack(side=tk.LEFT, padx=4)

        row = tk.Frame(f1); row.pack(fill=tk.X, padx=6)
        tk.Button(row, text="开始采集", width=10, command=self.start_record).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="停止采集", width=10, command=self.stop_record).pack(side=tk.LEFT, padx=3)
        row = tk.Frame(f1); row.pack(fill=tk.X, padx=6)
        tk.Button(row, text="打开音频文件", width=10, command=self.open_audio).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="保存当前信号WAV", width=14, command=self.save_signal).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="生成测试音频", width=10, command=self.gen_test).pack(side=tk.LEFT, padx=3)

        # ② 语音播放
        f2 = tk.LabelFrame(ctrl, text="② 语音播放")
        f2.pack(fill=tk.X, pady=3)
        row = tk.Frame(f2); row.pack(fill=tk.X, padx=6)
        tk.Label(row, text="播放源:").pack(side=tk.LEFT)
        self.play_src = tk.IntVar(value=0)
        tk.Radiobutton(row, text="原始", variable=self.play_src, value=0).pack(side=tk.LEFT)
        tk.Radiobutton(row, text="加噪", variable=self.play_src, value=1).pack(side=tk.LEFT)
        tk.Radiobutton(row, text="去噪", variable=self.play_src, value=2).pack(side=tk.LEFT)

        row = tk.Frame(f2); row.pack(fill=tk.X, padx=6)
        tk.Label(row, text="速度:").pack(side=tk.LEFT)
        self.speed_var = tk.DoubleVar(value=1.0)
        tk.Scale(row, from_=0.25, to=2.0, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=self.speed_var, length=200).pack(side=tk.LEFT)

        row = tk.Frame(f2); row.pack(fill=tk.X, padx=6)
        tk.Button(row, text="播放", width=8, command=lambda: self._play(self.speed_var.get())).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="停止", width=8, command=self.stop_play).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="快进×2", width=8, command=self.play_fast).pack(side=tk.LEFT, padx=3)
        tk.Button(row, text="慢放×0.5", width=9, command=self.play_slow).pack(side=tk.LEFT, padx=3)

        # ③ 加噪
        f3 = tk.LabelFrame(ctrl, text="③ 加噪（2 种噪声）")
        f3.pack(fill=tk.X, pady=3)
        self.noise_type = tk.IntVar(value=0)
        row = tk.Frame(f3); row.pack(fill=tk.X, padx=6)
        tk.Radiobutton(row, text="高斯白噪声", variable=self.noise_type, value=0).pack(side=tk.LEFT)
        tk.Label(row, text="SNR(dB):").pack(side=tk.LEFT)
        self.snr_var = tk.DoubleVar(value=10.0)
        tk.Scale(row, from_=-10, to=60, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.snr_var, length=140).pack(side=tk.LEFT)
        row = tk.Frame(f3); row.pack(fill=tk.X, padx=6)
        tk.Radiobutton(row, text="脉冲噪声", variable=self.noise_type, value=1).pack(side=tk.LEFT)
        tk.Label(row, text="密度(%):").pack(side=tk.LEFT)
        self.dens_var = tk.DoubleVar(value=5.0)
        tk.Scale(row, from_=0, to=50, resolution=0.5, orient=tk.HORIZONTAL,
                 variable=self.dens_var, length=140).pack(side=tk.LEFT)
        tk.Button(f3, text="执行加噪", width=14, command=self.do_add_noise).pack(pady=3)

        # ④ 去噪
        f4 = tk.LabelFrame(ctrl, text="④ 去噪（3 种算法）")
        f4.pack(fill=tk.X, pady=3)
        self.denoise_type = tk.IntVar(value=0)
        row = tk.Frame(f4); row.pack(fill=tk.X, padx=6)
        tk.Radiobutton(row, text="维纳", variable=self.denoise_type, value=0).pack(side=tk.LEFT)
        tk.Label(row, text="窗长:").pack(side=tk.LEFT)
        self.win_var = tk.IntVar(value=9)
        tk.Scale(row, from_=3, to=101, resolution=2, orient=tk.HORIZONTAL,
                 variable=self.win_var, length=110).pack(side=tk.LEFT)
        row = tk.Frame(f4); row.pack(fill=tk.X, padx=6)
        tk.Radiobutton(row, text="卡尔曼", variable=self.denoise_type, value=1).pack(side=tk.LEFT)
        tk.Label(row, text="lgQ:").pack(side=tk.LEFT)
        self.kfq_var = tk.DoubleVar(value=-2.0)
        tk.Scale(row, from_=-6.0, to=-2.0, resolution=0.1, orient=tk.HORIZONTAL,
                 variable=self.kfq_var, length=80).pack(side=tk.LEFT)
        tk.Label(row, text="lgR:").pack(side=tk.LEFT)
        self.kfr_var = tk.DoubleVar(value=-2.0)
        tk.Scale(row, from_=-3.0, to=0.0, resolution=0.1, orient=tk.HORIZONTAL,
                 variable=self.kfr_var, length=80).pack(side=tk.LEFT)
        row = tk.Frame(f4); row.pack(fill=tk.X, padx=6)
        tk.Radiobutton(row, text="小波", variable=self.denoise_type, value=2).pack(side=tk.LEFT)
        tk.Label(row, text="层数:").pack(side=tk.LEFT)
        self.wl_lvl_var = tk.IntVar(value=3)
        tk.Scale(row, from_=1, to=6, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.wl_lvl_var, length=80).pack(side=tk.LEFT)
        tk.Label(row, text="阈值系数:").pack(side=tk.LEFT)
        self.wl_thr_var = tk.DoubleVar(value=0.5)
        tk.Scale(row, from_=0.1, to=2.0, resolution=0.1, orient=tk.HORIZONTAL,
                 variable=self.wl_thr_var, length=80).pack(side=tk.LEFT)
        tk.Button(f4, text="执行去噪", width=14, command=self.do_denoise).pack(pady=3)

        # ⑤ 效果分析
        f5 = tk.LabelFrame(ctrl, text="⑤ 去噪效果分析（SNR / MSE）")
        f5.pack(fill=tk.X, pady=3)
        tk.Label(f5, textvariable=self.metric_var, justify=tk.LEFT,
                 anchor="w", font=("", 10)).pack(fill=tk.X, padx=6, pady=4)
        tk.Button(f5, text="更新频谱对比图", width=18, command=self.update_plots).pack(pady=3)

        # ---------------- 右侧绘图区 ----------------
        right = tk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.fig = Figure(figsize=(9.0, 7.6), dpi=100)
        self.axes = self.fig.subplots(2, 2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 状态栏
        tk.Label(self, textvariable=self.status_var, anchor="w", bd=1,
                 relief=tk.SUNKEN, fg="#05a").pack(side=tk.BOTTOM, fill=tk.X)

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