# 单元 1 闭卷小测：拿到陌生表，回答 4 个问题（≤12 行）
import pandas as pd
from pathlib import Path

DATA = Path(r"D:\Data_Visualization\Practice\class1.1\hubei_air_raw.csv")
df = pd.read_csv(DATA, parse_dates=["date"])

# Q1 形状 / 几个城市 / 日期范围
print("Q1", df.shape, df["city"].nunique(), df["date"].min().date(), df["date"].max().date())

# Q2 pm25 缺失率（只要这一列）
p = df["pm25"]
print("Q2", round(p.isna().mean() * 100, 2), "%", int(p.isna().sum()), "rows")

# Q3 物理上不可能的值（只问 pm25，别把别的污染物算进来）
print("Q3", int(((p < 0) | (p > 500)).sum()), "条 | min/max", p.min(), p.max())

# Q4 唯一键是 (city, date) 两列组合，不是 date 单列
print("Q4", int(df.duplicated(subset=["city", "date"]).sum()), "条重复")
