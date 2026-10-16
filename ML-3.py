# -*- coding: utf-8 -*-
"""实验3  数据可视化库 Matplotlib 的使用"""

import os

# 1. 导入 matplotlib 库简写为 plt
import numpy as np
import matplotlib.pyplot as plt

# 图像保存目录（脚本运行后把所有图保存下来，便于查看结果）
FIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml3_figures")
os.makedirs(FIG_DIR, exist_ok=True)


def save(fig, name):
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=120, bbox_inches='tight')
    print(f"[图] 已保存 -> {path}")


print("=" * 60)
print("三、数据可视化库 Matplotlib 的使用")
print("=" * 60)

# 2. 用 scatter 画出 x=(0,10) 间 sin 的点图像
print("\n[2] scatter 绘制 sin 点图")
x = np.linspace(0, 10, 30)
fig = plt.figure()
plt.scatter(x, np.sin(x))
plt.title("2. scatter of sin(x)")
save(fig, "02_scatter_sin.png")

# 3. 绘制一组误差为 ±0.8 的数据的误差条图
print("[3] 误差条图 (±0.8)")
x = np.linspace(0, 10, 50)
dy = 0.8
y = np.sin(x) + dy * np.random.randn(50)
fig = plt.figure()
plt.errorbar(x, y, yerr=dy, fmt='.k')
plt.title("3. errorbar (+/-0.8)")
save(fig, "03_errorbar.png")

# 4. 绘制一个柱状图
print("[4] 柱状图")
x = [1, 2, 3, 4, 5, 6, 7, 8]
y = [3, 1, 4, 5, 8, 9, 7, 2]
label = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
fig = plt.figure()
plt.bar(x, y, tick_label=label)
plt.title("4. bar")
save(fig, "04_bar.png")

# 5. 绘制一个水平方向柱状图
print("[5] 水平柱状图")
fig = plt.figure()
plt.barh(x, y, tick_label=label)
plt.title("5. barh")
save(fig, "05_barh.png")

# 6. 绘制 1000 个随机值的直方图
print("[6] 1000 个随机值的直方图")
data = np.random.randn(1000)
fig = plt.figure()
plt.hist(data)
plt.title("6. hist")
save(fig, "06_hist.png")

# 7. 设置直方图分 30 个 bins，并设置为频率分布
print("[7] 30 个 bins 的频率分布直方图")
fig = plt.figure()
plt.hist(data, bins=30, histtype='stepfilled', density=True)
plt.title("7. hist 30 bins (density)")
save(fig, "07_hist_30bins.png")

# 8. 在一张图中绘制 3 组不同的直方图，并设置透明度
print("[8] 3 组直方图（带透明度）")
x1 = np.random.normal(0, 0.8, 1000)
x2 = np.random.normal(-2, 1, 1000)
x3 = np.random.normal(3, 2, 1000)
kwargs = dict(alpha=0.3, bins=40, density=True)
fig = plt.figure()
plt.hist(x1, **kwargs)
plt.hist(x2, **kwargs)
plt.hist(x3, **kwargs)
plt.title("8. three histograms")
save(fig, "08_three_hist.png")

# 9. sin 图像：虚线 / y 范围 / 轴标签 / 标题 / 网格 / y=0.8 水平参考线
print("[9] sin 图像（虚线、范围、标签、标题、网格、水平参考线）")
x = np.linspace(0, 10, 100)
fig = plt.figure()
plt.plot(x, np.sin(x), '--')
plt.ylim(-1.5, 1.5)
plt.xlabel('variable x')
plt.ylabel('value y')
plt.title('sin')
plt.grid()
plt.axhline(y=0.8, ls='--', c='r')
save(fig, "09_sin_styled.png")

# 10. sin 图像 + 垂直/水平参考区域
print("[10] sin 图像 + 参考区域")
x = np.linspace(0, 10, 100)
y = np.sin(x)
fig = plt.figure()
plt.plot(x, y)
plt.axvspan(xmin=4, xmax=6, facecolor='r', alpha=0.3)      # 垂直 x 轴区域
plt.axhspan(ymin=-0.2, ymax=0.2, facecolor='y', alpha=0.3)  # 垂直 y 轴区域
plt.title("10. span regions")
save(fig, "10_sin_spans.png")

# 11. sin 图像 + 注释文字 sin(x)
print("[11] sin 图像 + 注释文字")
x = np.linspace(0, 10, 100)
y = np.sin(x)
fig = plt.figure()
plt.plot(x, y)
plt.text(3.2, 0, 'sin(x)', weight='bold', color='r')
plt.title("11. text annotation")
save(fig, "11_sin_text.png")

# 12. sin 图像 + 箭头标出第一个峰值
print("[12] sin 图像 + 箭头标出第一个峰值")
x = np.linspace(0, 10, 100)
y = np.sin(x)
fig = plt.figure()
plt.plot(x, y)
plt.annotate('maximum', xy=(np.pi / 2, 1), xytext=(np.pi / 2 + 1, 1),
             weight='bold', color='r',
             arrowprops=dict(arrowstyle='->', connectionstyle='arc3', color='r'))
plt.title("12. arrow annotation")
save(fig, "12_sin_arrow.png")

# 13. 一张图绘制 sin, cos；图例放右上角且不显示边框
print("[13] sin/cos 图例（右上角、无边框）")
x = np.linspace(0, 10, 1000)
fig, ax = plt.subplots()
ax.plot(x, np.sin(x), label='sin')
ax.plot(x, np.cos(x), '--', label='cos')
ax.legend(loc='upper right', frameon=False)
ax.set_title("13. sin & cos")
save(fig, "13_sin_cos_legend.png")

# 14. 在 2 个子图中，显示 sin(x) 和 cos(x) 的图像
print("[14] 两个子图显示 sin(x) / cos(x)")
fig = plt.figure()
ax1 = fig.add_axes([0.1, 0.5, 0.8, 0.4], ylim=(-1.2, 1.2))
ax2 = fig.add_axes([0.1, 0.1, 0.8, 0.4], ylim=(-1.2, 1.2))
x = np.linspace(0, 10)
ax1.plot(np.sin(x))
ax2.plot(np.cos(x))
save(fig, "14_subplots.png")

# 15. 二维数据的频度分布，并在 x, y 轴上显示各维度的频度分布
print("[15] 二维数据联合分布 + 边缘频度分布")
mean = [0, 0]
cov = [[1, 1], [1, 2]]
x, y = np.random.multivariate_normal(mean, cov, 3000).T
fig = plt.figure(figsize=(6, 6))
grid = plt.GridSpec(4, 4, hspace=0.2, wspace=0.2)
main_ax = fig.add_subplot(grid[:-1, 1:])
y_hist = fig.add_subplot(grid[:-1, 0], xticklabels=[], sharey=main_ax)
x_hist = fig.add_subplot(grid[-1, 1:], yticklabels=[], sharex=main_ax)
main_ax.scatter(x, y, s=3, alpha=0.2)
x_hist.hist(x, 40, histtype='stepfilled', orientation='vertical')
x_hist.invert_yaxis()
y_hist.hist(y, 40, histtype='stepfilled', orientation='horizontal')
y_hist.invert_xaxis()
save(fig, "15_joint_dist.png")

# 16. 绘制一组三维点
print("[16] 三维散点图")
fig = plt.figure()
ax = fig.add_subplot(projection='3d')
zdata = 15 * np.random.random(100)
xdata = np.sin(zdata) + 0.1 * np.random.randn(100)
ydata = np.cos(zdata) + 0.1 * np.random.randn(100)
ax.scatter3D(xdata, ydata, zdata, c=zdata, cmap='Greens')
save(fig, "16_3d_scatter.png")

# 17. 宝可梦数据集可视化
print("[17] 宝可梦数据集可视化")
import pandas as pd  # noqa: E402

csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Pokemon.csv')
df = pd.read_csv(csv_path)

# 17.1 用 scatter 的 x, y, c 属性展示宝可梦的 Defense, Attack, HP 数据
fig = plt.figure(figsize=(8, 6))
plt.scatter(df['Attack'], df['Defense'], c=df['HP'], alpha=0.5)
plt.title('17.1 Pokemon: Attack vs Defense (color = HP)')
plt.xlabel('Attack')
plt.ylabel('Defense')
plt.colorbar(label='HP')
save(fig, "17_1_pokemon_scatter.png")

# 17.2 展示所有宝可梦攻击力的分布直方图，bins=10
fig = plt.figure()
n, bins, patches = plt.hist(df['Attack'], bins=10, facecolor='blue', alpha=0.5)
plt.title('17.2 Attack distribution (bins=10)')
plt.xlabel('Attack')
plt.ylabel('Value')
save(fig, "17_2_pokemon_attack_hist.png")

print("\n全部图像已生成，位于:", FIG_DIR)
plt.show()
