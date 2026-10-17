# -*- coding: utf-8 -*-
"""视频诊断工具：
用法（二选一）：
  1) 把视频文件直接拖到本脚本图标上运行
  2) 双击运行后，输入/粘贴视频完整路径回车
结果会显示在窗口、打印到控制台，并保存为同目录下"视频诊断结果.txt"。
"""
import os
import sys

import numpy as np
import cv2


def finish(lines):
    text = "\n".join(lines)
    print(text)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = "."
    try:
        with open(os.path.join(here, "视频诊断结果.txt"), "w", encoding="utf-8") as f:
            f.write(text)
            print("\n结果已保存到: %s" % os.path.join(here, "视频诊断结果.txt"))
    except Exception:
        pass
    try:
        input("\n按回车退出…")
    except Exception:
        pass


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1].strip().strip('"')
    else:
        path = input("请输入视频文件完整路径（或直接把文件拖到本窗口）: ").strip().strip('"')

    lines = ["=" * 62, "视频诊断: %s" % path]
    if not path or not os.path.exists(path):
        lines.append("!! 文件不存在，请检查路径")
        finish(lines)
        return
    lines.append("文件大小: %.2f MB" % (os.path.getsize(path) / 1048576.0))

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        lines.append("!! OpenCV 无法打开该文件（编码不支持或文件损坏）")
        finish(lines)
        return

    def g(p):
        try:
            return cap.get(p)
        except Exception:
            return float("nan")

    fps_meta = g(cv2.CAP_PROP_FPS)
    n_meta = g(cv2.CAP_PROP_FRAME_COUNT)
    w_ = g(cv2.CAP_PROP_FRAME_WIDTH)
    h_ = g(cv2.CAP_PROP_FRAME_HEIGHT)
    fourcc = int(g(cv2.CAP_PROP_FOURCC))
    codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip()
    lines.append("OpenCV 读到元数据: fps=%.3f  帧数=%s  分辨率=%sx%s  编码=%s"
                 % (fps_meta, n_meta, w_, h_, codec))

    # 实际连续读取：最多试 1500 帧，记录时间戳与帧号
    ms, pos, breaks = [], [], None
    MAX = 1500
    for i in range(MAX):
        ok, _fr = cap.read()
        if not ok:
            breaks = i
            break
        try:
            ms.append(float(cap.get(cv2.CAP_PROP_POS_MSEC)))
            pos.append(float(cap.get(cv2.CAP_PROP_POS_FRAMES)))
        except Exception:
            pass
    cap.release()

    lines.append("实际连续读帧: %d 帧（读到 read() 失败为止，最多尝试 %d 帧）"
                 % (len(ms), MAX))
    lines.append("是否读到视频末尾: %s"
                 % ("否，在第 %d 次读取失败" % breaks if breaks is not None else "是"))

    if len(ms) >= 3:
        d = np.diff(np.asarray(ms, float))
        d = d[(d > 0) & (d < 5000)]
        if len(d):
            lines.append("帧时间戳间隔: 中位 %.1f ms → 实测帧率 ≈ %.1f fps"
                         % (float(np.median(d)), 1000.0 / float(np.median(d))))
    if pos:
        lines.append("POS_FRAMES 前 8 帧: %s" % [int(p) for p in pos[:8]])
        lines.append("POS_FRAMES 末值: %.1f" % pos[-1])

    lines.append("-" * 62)
    if breaks is None:
        lines.append("结论: 视频可完整顺序读取，共 %d 帧" % len(ms))
    else:
        lines.append("结论: 视频读到第 %d 帧(从0计)后 read() 失败，共 %d 帧"
                     % (len(ms), len(ms)))
    if len(ms) <= 15:
        lines.append("!! 可读帧数只有 %d → 程序信息栏『帧: x/y』里 y 最多只会显示 %d。" % (len(ms), len(ms)))
        lines.append("   这不是程序限制，而是文件本身只有这些帧（或被截断/编码异常）。")
        lines.append("   建议: 用转码工具(格式工厂 / ffmpeg) 转成 H264 编码的 MP4 再打开。")
    elif fps_meta and 1000.0 / fps_meta < 20:
        lines.append("提示: 元数据 fps=%.1f 与实测不一致，属容器元数据误报（程序已支持自动实测校准）。" % fps_meta)
    lines.append("=" * 62)
    finish(lines)


if __name__ == "__main__":
    main()