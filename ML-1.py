# -*- coding: utf-8 -*-
"""实验1  科学计算库 NumPy 的使用"""

import numpy as np

print("=" * 60)
print("一、科学计算库 NumPy 的使用")
print("=" * 60)

# 1. 创建一个全零的二维数组，数组的 shape 为 (3, 4)
print("\n[1] 全零二维数组，shape=(3, 4)")
z1 = np.zeros((3, 4))
print(z1)

# 2. 创建一个 10-49 的一维数组，并将其倒序排列
print("\n[2] 10-49 的一维数组，并倒序排列")
z2 = np.arange(10, 50, 1)
z2 = z2[::-1]
print(z2)

# 3. 创建二维数组 [[1,2,3],[4,5,6]]，沿 axis=0 轴求和
print("\n[3] 二维数组沿 axis=0 求和")
z3 = np.array([[1, 2, 3], [4, 5, 6]])
print("原数组:\n", z3)
print("axis=0 求和:", np.sum(z3, axis=0))

# 4. 创建二维数组 [[11,2,3],[4,5,6]]，沿 axis=1 轴元素累乘
print("\n[4] 二维数组沿 axis=1 元素累乘")
z4 = np.array([[11, 2, 3], [4, 5, 6]])
print("原数组:\n", z4)
print("axis=1 累乘:", z4.prod(axis=1))

# 5. 随机创建二维数组，shape 为 (3, 4)，打印数组、最大值和最大值的索引
print("\n[5] 随机二维数组 (3,4)：数组 / 最大值 / 最大值索引")
z5 = np.random.random((3, 4))
print(z5)
print("最大值:", z5.max())
print("最大值索引:", np.unravel_index(z5.argmax(), z5.shape))

# 6. 随机创建二维数组，shape 为 (3, 4)，并对数组做归一化操作
print("\n[6] 随机二维数组 (3,4) 归一化")
z6 = np.random.random((3, 4))
z6 = (z6 - z6.min()) / (z6.max() - z6.min())
print(z6)

# 7. 创建二维数组 [[1.5,1.3,7.5],[5.6,7.8,1.2]]，对每列元素进行升序排序
print("\n[7] 每列元素升序排序")
z7 = np.array([[1.5, 1.3, 7.5],
               [5.6, 7.8, 1.2]])
print(np.sort(z7, axis=0))

# 8. 创建 1-12 的一维数组，变形为 (3,4)，并转置
print("\n[8] 1-12 数组变形为 (3,4) 并转置")
z8 = np.arange(1, 13, 1)
z8 = z8.reshape(3, 4)
print("原数组:\n", z8)
print("转置:\n", z8.T)

# 9. 创建两个数组，并沿 axis=0 轴连接
print("\n[9] 两数组沿 axis=0 连接")
a = np.array([[123, 456, 678], [3214, 456, 134]])
b = np.array([[1235, 3124, 432], [43, 13, 134]])
print(np.concatenate((a, b), axis=0))

# 10. 创建文件（内容为本人学号，文件名 "ml"），并用 np.loadtxt 读取
#     说明：%%writefile 是 Jupyter 的魔法指令，在 .py 脚本中等价于直接用文件写入
print("\n[10] 写文件 ml.txt（内容为学号）并读取")
student_id = "20214152"  # 请替换成本人学号
with open("ml.txt", "w", encoding="utf-8") as f:
    f.write(student_id + "\n")
data = np.loadtxt("ml.txt", dtype=int)
print("np.loadtxt 读取内容:", data)
