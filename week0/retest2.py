# 门槛自检（10 分钟）：不看笔记、不看旧代码，自己写
# 要干嘛：读同目录下 data/temps.csv，把 temp_c 这一列算成 4 个数，打印成一行
# 数据长相：表头 city,date,temp_c，下面 12 行，temp_c 是 21.5 这样的数
# 期望输出：rows=12 mean=16.76 max=22.0 min=12.9
#
# 三个别忘：encoding="utf-8"、newline=""、with open(...)
# 提示：csv 读出来的都是字符串，要先转 float 再算
#
# 把代码写在下面，然后改名为 retest2.py 运行
import csv
from pathlib import Path

data = Path(__file__).parent/"data"/"temps.csv"
with open(data,newline="",encoding="utf-8") as f:
    temps = [float(row["temp_c"]) for row in csv.DictReader(f)]

n = len(temps)
mean = sum(temps)/n
print(f"rows={n} mean={mean:.2f} max={max(temps):.1f} min={min(temps):.1f}")

