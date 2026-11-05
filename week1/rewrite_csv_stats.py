# 用途：用 pandas 重写 week0 的 CSV 统计脚本，输出与单元 0 一字不差
import pandas as pd
from pathlib import Path 

data = Path(__file__).parent.parent/"week0"/"data"/"temps.csv"

df = pd.read_csv(data)

print(f"rows={len(df)} mean={df['temp_c'].mean():.2f} max={df['temp_c'].max():.1f} min={df['temp_c'].min():.1f}")