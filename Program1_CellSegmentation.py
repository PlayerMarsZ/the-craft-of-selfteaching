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
import numpy as np
from PIL import Image, ImageTk
from scipy import ndimage

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
    p = hist / hist.sum()
    omega = np.cumsum(p)                    # 前景累积概率
    mu = np.cumsum(p * np.arange(256))      # 累积灰度均值
    mu_t = mu[-1]                           # 全局灰度均值
    sigma_b = np.zeros(256)
    for t in range(1, 256):
        w0 = omega[t]
        if w0 == 0.0 or w0 == 1.0:
            continue
        m0 = mu[t] / w0
        m1 = (mu_t - mu[t]) / (1.0 - w0)
        sigma_b[t] = w0 * (1.0 - w0) * (m0 - m1) ** 2
    T = int(np.argmax(sigma_b))
    binary = (g > T) * 255
    return binary.astype(np.uint8), T


def watershed_segment(img, fg_coef=0.35):
    """
    自适应分水岭分割：
    1) 用 Sobel 梯度幅值构造地形图；
    2) 形态学开运算+膨胀确定确定背景；
    3) 距离变换按最大值比例自适应确定前景标记（fg_coef 越大前景越少）；
    4) 分水岭变换，输出按区域随机着色的分割图，红色线为分割边界。
    """
    if not HAS_CV2:
        raise RuntimeError("分水岭分割需要 OpenCV：pip install opencv-python")
    gray = to_gray(img)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    gx = cv2.Sobel(blur, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_64F, 0, 1, ksize=3)
    grad = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255,
                         cv2.NORM_MINMAX).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    opening = cv2.morphologyEx(grad, cv2.MORPH_OPEN, kernel, iterations=2)
    sure_bg = cv2.dilate(opening, kernel, iterations=3)
    dist = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
    # 自适应阈值：按距离图最大值的比例确定前景，避免人为设定绝对阈值
    th = fg_coef * dist.max()
    _, sure_fg = cv2.threshold(dist, th, 1.0, cv2.THRESH_BINARY)
    sure_fg = np.uint8(sure_fg)
    unknown = cv2.subtract(sure_bg, sure_fg)
    n, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1                 # 背景标记为 1
    markers[unknown == 255] = 0           # 未知区域标记为 0
    color_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    markers = cv2.watershed(color_img, markers)

    labels = markers.copy()
    labels[labels == -1] = 0              # 分水岭脊线（边界）
    n_lab = int(labels.max())
    rng = np.random.default_rng(42)
    palette = {0: np.array([250, 250, 250])}
    for lab in range(1, n_lab + 1):
        palette[lab] = rng.integers(60, 230, 3)
    vis = np.zeros(gray.shape + (3,), np.uint8)
    for lab in range(n_lab + 1):
        vis[labels == lab] = palette[lab]
    vis[markers == -1] = (0, 0, 255)      # 边界用红色标出
    return vis, n_lab


def combined_segment(img, smax=7, fg_coef=0.35):
    """
    组合式自适应分割（创新方法）：
    自适应中值滤波去噪 → Otsu 粗分割得到前景掩膜 → 分水岭精修，
    并把 Otsu 判为背景的区域强制置为背景，抑制过分割。
    """
    den = adaptive_median_filter(img, smax)
    bin_otsu, _ = otsu_threshold(den)
    ws, n = watershed_segment(den, fg_coef)
    out = ws.copy()
    out[bin_otsu == 0] = (0, 0, 0)
    return out, n


# ===================== GUI 主界面 =====================

class CellSegGUI(tk.Tk):
    """病理细胞图像分割系统主界面"""

    def __init__(self):
        super().__init__()
        self.title("病理细胞图像分割系统")
        self.geometry("1320x900")
        self.minsize(1100, 700)

        self.original = None        # 原始图像数组
        self.current = None         # 当前处理结果数组
        self.disp_info = {}         # 画布显示映射 {tag:(scale,offx,offy,iw,ih)}
        self.crop_mode = False      # 是否处于裁剪框选状态
        self.crop_start = None      # 裁剪起点（画布坐标）
        self.crop_rect = None       # 裁剪预览矩形
        self.result_text = tk.StringVar(value="提示：点击【生成示例细胞图】即可无图演示")

        self._build_toolbar()
        self._build_body()
        self._bind_crop()

    # ------------------------- 界面搭建 -------------------------

    def _build_toolbar(self):
        bar = tk.Frame(self, bd=2, relief=tk.RAISED)
        bar.pack(side=tk.TOP, fill=tk.X)
        tk.Button(bar, text="打开图像", width=12, command=self.open_image).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(bar, text="生成示例细胞图", width=14, command=self.load_sample).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(bar, text="保存当前结果", width=12, command=self.save_current).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(bar, text="保存前后对比图", width=14, command=self.save_compare).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(bar, text="重置", width=8, command=self.reset).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Label(bar, textvariable=self.result_text, fg="#0a5", anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=12)

    def _build_body(self):
        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        # ---------------- 左侧控制面板 ----------------
        ctrl = tk.Frame(body, width=340)
        ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        ctrl.pack_propagate(False)

        # ① 基础操作
        f1 = tk.LabelFrame(ctrl, text="① 基础操作")
        f1.pack(fill=tk.X, pady=3)
        tk.Button(f1, text="灰度化", width=18, command=lambda: self.apply_op(to_gray, "灰度化")).pack(pady=2)

        row = tk.Frame(f1); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="缩放:").pack(side=tk.LEFT)
        self.scale_var = tk.DoubleVar(value=1.0)
        tk.Scale(row, from_=0.25, to=2.0, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=self.scale_var, length=170).pack(side=tk.LEFT)
        tk.Button(f1, text="应用缩放", width=18, command=self.do_scale).pack(pady=2)

        row = tk.Frame(f1); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="旋转:").pack(side=tk.LEFT)
        self.rot_var = tk.DoubleVar(value=30.0)
        tk.Scale(row, from_=-180, to=180, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.rot_var, length=170).pack(side=tk.LEFT)
        tk.Button(f1, text="应用旋转", width=18, command=self.do_rotate).pack(pady=2)

        self.crop_btn = tk.Button(f1, text="裁剪（在原图上拖拽框选区域）", width=30, command=self.toggle_crop)
        self.crop_btn.pack(pady=2)

        tk.Label(f1, text="窗宽窗位调节（滑块实时预览）", fg="#36a").pack()
        row = tk.Frame(f1); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="窗位C:").pack(side=tk.LEFT)
        self.wc_var = tk.DoubleVar(value=128)
        tk.Scale(row, from_=0, to=255, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.wc_var, length=170, command=self._on_wl).pack(side=tk.LEFT)
        row = tk.Frame(f1); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="窗宽W:").pack(side=tk.LEFT)
        self.ww_var = tk.DoubleVar(value=256)
        tk.Scale(row, from_=1, to=512, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.ww_var, length=170, command=self._on_wl).pack(side=tk.LEFT)

        # ② 图像增强（去噪）
        f2 = tk.LabelFrame(ctrl, text="② 图像增强 / 去噪（3 种方法）")
        f2.pack(fill=tk.X, pady=3)
        tk.Button(f2, text="标准中值滤波", width=18,
                  command=lambda: self.apply_op(lambda im: median_denoise(im, self.smax_var.get() or 3),
                                                "标准中值滤波")).pack(pady=2)
        row = tk.Frame(f2); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="中值最大窗口:").pack(side=tk.LEFT)
        self.smax_var = tk.IntVar(value=7)
        tk.Scale(row, from_=3, to=11, resolution=2, orient=tk.HORIZONTAL,
                 variable=self.smax_var, length=150).pack(side=tk.LEFT)
        tk.Button(f2, text="自适应中值滤波", width=18,
                  command=lambda: self.apply_op(lambda im: adaptive_median_filter(im, self.smax_var.get()),
                                                "自适应中值滤波")).pack(pady=2)
        row = tk.Frame(f2); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="高斯σ:").pack(side=tk.LEFT)
        self.sigma_var = tk.DoubleVar(value=1.5)
        tk.Scale(row, from_=0.5, to=5.0, resolution=0.1, orient=tk.HORIZONTAL,
                 variable=self.sigma_var, length=150).pack(side=tk.LEFT)
        tk.Button(f2, text="高斯滤波去噪", width=18,
                  command=lambda: self.apply_op(lambda im: gaussian_denoise(im, self.sigma_var.get()),
                                                "高斯滤波去噪")).pack(pady=2)

        # ③ 边缘提取
        f3 = tk.LabelFrame(ctrl, text="③ 边缘提取（6 种算子）")
        f3.pack(fill=tk.X, pady=3)
        grid = tk.Frame(f3); grid.pack(padx=4)
        edges = [("Sobel", edge_sobel), ("Prewitt", edge_prewitt), ("Roberts", edge_roberts),
                 ("Laplacian", edge_laplacian), ("LoG", edge_log), ("Canny", edge_canny)]
        for i, (name, func) in enumerate(edges):
            tk.Button(grid, text=name, width=9,
                      command=lambda f=func, n=name: self.apply_op(f, n + " 边缘提取")
                      ).grid(row=i // 3, column=i % 3, padx=3, pady=2)
        tk.Button(f3, text="全部边缘结果对比", width=26, command=self.edge_compare).pack(pady=4)

        # ④ 图像分割
        f4 = tk.LabelFrame(ctrl, text="④ 图像分割")
        f4.pack(fill=tk.X, pady=3)
        tk.Button(f4, text="Otsu 阈值分割", width=18, command=self.do_otsu).pack(pady=2)
        row = tk.Frame(f4); row.pack(fill=tk.X, padx=4)
        tk.Label(row, text="分水岭前景系数:").pack(side=tk.LEFT)
        self.fgcoef_var = tk.DoubleVar(value=0.35)
        tk.Scale(row, from_=0.10, to=0.60, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=self.fgcoef_var, length=150).pack(side=tk.LEFT)
        tk.Button(f4, text="自适应分水岭分割", width=18, command=self.do_watershed).pack(pady=2)
        tk.Button(f4, text="组合式分割(创新)", width=18, command=self.do_combined).pack(pady=2)
        tk.Button(f4, text="分割方法结果对比", width=26, command=self.seg_compare).pack(pady=4)

        # ---------------- 右侧显示区 ----------------
        disp = tk.Frame(body)
        disp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        top = tk.Frame(disp)
        top.pack(fill=tk.BOTH, expand=True)
        lf1 = tk.LabelFrame(top, text="原始图像 / 处理前")
        lf1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
        self.canvas_orig = tk.Canvas(lf1, width=480, height=480, bg="#222")
        self.canvas_orig.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        lf2 = tk.LabelFrame(top, text="处理结果 / 处理后")
        lf2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
        self.canvas_res = tk.Canvas(lf2, width=480, height=480, bg="#222")
        self.canvas_res.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        cmp = tk.LabelFrame(disp, text="多算法结果对比区")
        cmp.pack(fill=tk.BOTH, expand=True, pady=4)
        self.cmp_frame = tk.Frame(cmp)
        self.cmp_frame.pack(fill=tk.BOTH, expand=True)

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
        th = max(a.height, b.height)
        ca = Image.new("RGB", (a.width, th), "white")
        ca.paste(a, (0, (th - a.height) // 2))
        cb = Image.new("RGB", (b.width, th), "white")
        cb.paste(b, (0, (th - b.height) // 2))
        gap = Image.new("RGB", (12, th), (255, 0, 0))
        out = Image.fromarray(np.hstack([np.array(ca), np.array(gap), np.array(cb)]))
        out.save(path)
        self.result_text.set("已保存处理前后对比图到: " + path)

    def reset(self):
        if self.original is None:
            return
        self.current = self.original.copy()
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
        """把 numpy 图像等比例缩放后绘制到指定画布中央"""
        cw = canvas.winfo_width() or fallback
        ch = canvas.winfo_height() or fallback
        pil = Image.fromarray(np.asarray(arr))
        r = min(cw / pil.width, ch / pil.height, 1.0)
        w = max(1, int(pil.width * r))
        h = max(1, int(pil.height * r))
        photo = ImageTk.PhotoImage(pil.resize((w, h), Image.LANCZOS))
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=photo)
        canvas.photo = photo          # 保持引用防止被回收
        self.disp_info[tag] = (r, (cw - w) // 2, (ch - h) // 2, pil.width, pil.height)

    # ------------------------- 各类操作 -------------------------

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
        self._clear_compare()
        self.update_display()

    def do_scale(self):
        self.apply_op(lambda im: image_resize(im, self.scale_var.get()),
                      "缩放 %.2f 倍" % self.scale_var.get())

    def do_rotate(self):
        self.apply_op(lambda im: image_rotate(im, self.rot_var.get()),
                      "旋转 %.0f°" % self.rot_var.get())

    def _on_wl(self, *_):
        """窗宽窗位滑块回调：实时预览"""
        if self.current is None:
            return
        try:
            out = window_level(self.current, self.wc_var.get(), self.ww_var.get())
            self._show(self.canvas_res, out, "res")
        except Exception:
            pass

    def do_otsu(self):
        if self.current is None:
            messagebox.showwarning("提示", "请先打开图像")
            return
        bw, T = otsu_threshold(self.current)
        self.current = bw
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
        self.result_text.set("组合式分割完成（自适应中值+Otsu+分水岭），%d 个区域" % n)
        self._clear_compare()
        self.update_display()

    # ------------------------- 多算法对比 -------------------------

    def _clear_compare(self):
        for w in self.cmp_frame.winfo_children():
            w.destroy()

    def _show_compare(self, entries):
        """entries: [(标题, 图像数组)]，以缩略图网格形式显示在对比区"""
        self._clear_compare()
        for i, (title, arr) in enumerate(entries):
            box = tk.Frame(self.cmp_frame, bd=1, relief=tk.SUNKEN)
            box.grid(row=i // 4, column=i % 4, padx=4, pady=4)
            tk.Label(box, text=title, font=("", 9)).pack()
            cv = tk.Canvas(box, width=200, height=200, bg="#333")
            cv.pack()
            self._show(cv, arr, "cmp%d" % i, fallback=200)

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
        """画布坐标 → 图像坐标"""
        r, ox, oy, iw, ih = self.disp_info.get(tag, (1, 0, 0, 1, 1))
        return int(np.clip((x - ox) / r, 0, iw - 1)), int(np.clip((y - oy) / r, 0, ih - 1))

    def _crop_press(self, e):
        if not self.crop_mode:
            return
        self.crop_start = (e.x, e.y)
        self.crop_rect = None

    def _crop_drag(self, e):
        if not (self.crop_mode and self.crop_start):
            return
        c = self.canvas_orig
        if self.crop_rect:
            c.delete(self.crop_rect)
        x0, y0 = self.crop_start
        self.crop_rect = c.create_rectangle(x0, y0, e.x, e.y, outline="#f33", width=2)

    def _crop_release(self, e):
        if not (self.crop_mode and self.crop_start):
            return
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
        if x1 - x0 < 5 or y1 - y0 < 5:
            self.result_text.set("框选区域过小，裁剪取消")
            return
        self.current = self.original[y0:y1 + 1, x0:x1 + 1].copy()
        self.result_text.set("裁剪完成（%d×%d）" % (self.current.shape[1], self.current.shape[0]))
        self._clear_compare()
        self.update_display()


def main():
    app = CellSegGUI()
    app.mainloop()


if __name__ == "__main__":
    main()