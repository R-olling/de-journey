# week1 NOTES

- 11/05 环境：本机装到 pandas 3.1.1 / pyarrow 26.0.1，而计划答案键基于 3.0.6 / 25.0.1（`pandas>=3.0,<4` 一周内出了新版）。已实测 `req.shape=(31801,13)`、缺失率 `closed_at 0.74%` / `citizen_rating 65.44%`、dtypes 7 str / 3 float / 1 int / 2 datetime、CSV 统计 `rows=12 mean=16.76 max=22.0 min=12.9` 四项与答案键完全一致，版本差异不影响本单元判据，故不降级（重下约 40 MB 代价过高）。周日验收清单里「版本 = 3.0.6」那条会红，属预期。
- 今天卡在哪、怎么出来的：卡在 `.loc[lambda s: s > 0]` 近一小时。真实原因是「函数被塞进方括号、参数 s 由 pandas 自动喂入」对新手不直观，反复用「临时小函数」解释无效；改用拆开的写法 `pct = ...; pct[pct > 0]` 后立刻跑通。结论：链式是压缩结果不是起点，以后遇到 callable 先拆中间变量，不硬啃。
- Q2 两句结论：① `citizen_rating` 缺 65.44%（20,809 行）**不是数据坏了，是「用户没评价」这件事没发生**；填进去等于编造用户意见，决策是保留 NaN。② `closed_at` 缺 0.74%（236 行）对应未结单，没有结束时间就算不出处理时长，这 236 行必须**过滤**而不是填。
- 附带认知：`describe()` 按 dtype 筛列、不扫值，异常值判断标准由人写进规则；DataFrame = 数据 + 行索引 + 列名，Series 的 index 来自原表列名，`to_frame()` 时变成行索引；`q2["rows_missing"] = ...` 靠索引按列名对齐，不是按顺序塞。

## 进度快照（11/05 13:04，学校停电检修，临时离开）

**已完成**
- ① 门槛自检：`week0/retest2.py` → `rows=12 mean=16.76 max=22.0 min=12.9`
- ② 装包：pandas 3.1.1 / pyarrow 26.0.1 / ipykernel 7.4.0；`requirements.txt`（UTF-8 无 BOM，31 个包）
- ③ `week1/rewrite_csv_stats.py`：8 行，输出与单元 0 一字不差
- ④ 两个 commit：`3c693ea` 锁依赖 / `bf38d15` 重写脚本 + 收编 retest2.py
- ⑤ `week1/data/raw/` 三份原始 CSV 齐（3625 / 1 / 0 KB）；`analysis.ipynb` 已建，kernel 注册为 `Python (de-journey .venv)`，第一屏 `sys.executable` 指向 `.venv\Scripts\python.exe`、版本 3.1.1
- Block B 体检：`req.shape = (31801, 13)` ✅

**回来第一步**
1. 停电会让 kernel 进程消失、内存里的 import 和 `req` 全没 → 打开 `analysis.ipynb` 先 **Restart & Run All**（Cell 1 import → Cell 2 读数据 → 确认 shape 仍是 `(31801, 13)`）。磁盘上的代码、数据、commit 都不受影响。
2. 跑完 `req.dtypes` / `req.head(3)` / `req.info()` / `req.describe()`
3. 对答案：7 str / 3 float64 / 1 int64 / 2 datetime；`describe()` 只有 6 列（想想为什么）
4. 然后进 Q2 缺失率：`citizen_rating 65.44%`、`closed_at 0.74%`

**未完成**：体检剩余四件套、Q2、缩版 `loc/iloc`、§2.2 正课（缺失判断 / 时间 month / groupby / Q3）。Q1 月度表按计划砍掉。
