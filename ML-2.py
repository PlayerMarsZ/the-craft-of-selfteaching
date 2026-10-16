# -*- coding: utf-8 -*-
"""实验2  数据分析处理库 Pandas 的使用"""

# 1. 导入 Pandas 库并简写为 pd
import numpy as np
import pandas as pd


def show(title, obj):
    print("\n" + "-" * 60)
    print(title)
    print(obj)


print("=" * 60)
print("二、数据分析处理库 Pandas 的使用")
print("=" * 60)

# 2. 从列表 arr = [0, 1, 2, 3, 4] 创建 Series
arr = [0, 1, 2, 3, 4]
s2 = pd.Series(arr)  # 不指定索引则默认从 0 开始
show("[2] 从列表创建 Series", s2)

# 3. 从字典 d = {'a':1,'b':2,'c':3,'d':4,'e':5} 创建 Series
d = {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5}
s3 = pd.Series(d)
show("[3] 从字典创建 Series", s3)

# 4. 从 NumPy 数组创建 DataFrame，列名 ['A','B','C','D']，行索引为默认
num_arr = np.random.randn(6, 4)
df4 = pd.DataFrame(num_arr, columns=['A', 'B', 'C', 'D'])
show("[4] 从 NumPy 数组创建 DataFrame", df4)

# 5. 从字典对象创建 DataFrame，并设置索引
data = {
    'animal':
    ['cat', 'cat', 'snake', 'dog', 'dog', 'cat', 'snake', 'cat', 'dog', 'dog'],
    'age': [2.5, 3, 0.5, np.nan, 5, 2, 4.5, np.nan, 7, 3],
    'visits': [1, 3, 2, 3, 2, 3, 1, 1, 2, 1],
    'priority':
    ['yes', 'yes', 'no', 'yes', 'no', 'no', 'no', 'yes', 'no', 'no']
}
labels = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
df = pd.DataFrame(data, index=labels)
show("[5] 定义 df", df)

# 5.1 展示 df 的前 3 行
show("[5.1] df 的前 3 行", df.head(3))

# 5.2 取出 df 的 animal 和 age 列
show("[5.2] animal 和 age 列", df[['animal', 'age']])

# 5.3 取出索引为 [3, 4, 8] 行的 animal 和 age 列
show("[5.3] 索引 [3, 4, 8] 行的 animal 和 age", df.loc[df.index[[3, 4, 8]], ['animal', 'age']])

# 5.4 取出 age 值大于 3 的行
show("[5.4] age 值大于 3 的行", df[df['age'] > 3])

# 5.5 取出 age 值缺失的行
show("[5.5] age 值缺失的行", df[df['age'].isna()])

# 5.6 取出 age 在 2,4 间的行（不含）
show("[5.6] age 在 (2, 4) 之间的行", df[(df['age'] > 2) & (df['age'] < 4)])

# 5.7 f 行的 age 改为 1.5
df.loc['f', 'age'] = 1.5
show("[5.7] f 行 age 改为 1.5", df.loc[['f']])

# 5.8 计算 visits 的总和
show("[5.8] visits 的总和", df['visits'].sum())

# 5.9 计算每个不同种类 animal 的 age 平均数
show("[5.9] 每种 animal 的 age 平均值", df.groupby('animal')['age'].mean())

# 5.10 插入新行 k，然后删除该行
df.loc['k'] = [5.5, 'dog', 'no', 2]
show("[5.10] 插入 k 行后的末尾 3 行", df.tail(3))
df = df.drop('k')
show("[5.10] 删除 k 行后的末尾 3 行", df.tail(3))

# 5.11 计算 df 中每个种类 animal 的数量
show("[5.11] 每种 animal 的数量", df['animal'].value_counts())

# 5.12 先按 age 降序排列，后按 visits 升序排列
show("[5.12] age 降序 + visits 升序",
     df.sort_values(by=['age', 'visits'], ascending=[False, True]))

# 5.13 将 priority 列中的 yes, no 替换为布尔值 True, False
df['priority'] = df['priority'].map({'yes': True, 'no': False})
show("[5.13] priority 替换为布尔值", df)

# 5.14 对每种 animal 的每种不同数量 visits，计算平均 age
show("[5.14] animal × visits 的平均 age",
     df.pivot_table(index='animal', columns='visits', values='age', aggfunc='mean'))
