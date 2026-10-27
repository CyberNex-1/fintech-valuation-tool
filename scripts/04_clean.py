# 04_clean.py
# 数据清洗：读 data/raw.csv → 格式标准化、单位换算、异常标注 → 输出 data/clean.csv

import pandas as pd
import os

# ============================================================
# 1. 读取原始数据
# ============================================================
raw_path = "data/raw.csv"
clean_path = "data/clean.csv"

if not os.path.exists(raw_path):
    print(f"错误：{raw_path} 不存在，请先运行 03_batch_crawl.py 生成数据")
    exit(1)

df = pd.read_csv(raw_path, dtype={"code": str})
rows_before = len(df)
print(f"清洗前行数：{rows_before}")

# ============================================================
# 2. 代码格式化：统一 6 位，不足前面补零
# ============================================================
df["code"] = df["code"].str.zfill(6)

# ============================================================
# 3. 单位换算：total_mv → 亿元
# ============================================================
# 先计算清洗前的中位数，据此判断原始单位
total_mv_raw = pd.to_numeric(df["total_mv"], errors="coerce")
median_before = total_mv_raw.median()
print(f"清洗前 total_mv 中位数：{median_before}")

# 判断原始单位：
# - 如果中位数在 1e10 以上 → 单位是"元"，需除以 1e8 转为亿元
# - 如果中位数在 1e6 ~ 1e10 → 单位是"万元"，需除以 1e4 转为亿元
# - 如果中位数在 1 ~ 1e5（如 30~3000） → 已经是"亿元"，无需换算
# 经验参考：东方财富 total_mv=2935.02（亿元），中位数应在此附近
if median_before > 1e10:
    # 原始单位是"元"，例如 293502000000，除以 1e8 得到 2935.02 亿元
    df["total_mv"] = total_mv_raw / 1e8
    unit_note = "原始单位【元】→ 除以 1e8 →【亿元】"
elif median_before > 1e6:
    # 原始单位是"万元"，例如 29350200，除以 1e4 得到 2935.02 亿元
    df["total_mv"] = total_mv_raw / 1e4
    unit_note = "原始单位【万元】→ 除以 1e4 →【亿元】"
else:
    # 中位数在合理范围（几百~几千），已经是亿元，不做换算
    df["total_mv"] = total_mv_raw
    unit_note = "原始单位已是【亿元】，无需换算"

print(f"单位判断：{unit_note}")
median_after = df["total_mv"].median()
print(f"清洗后 total_mv 中位数：{median_after}")

# ============================================================
# 4. 数据类型转换：pe_ttm, pb, roe, total_mv → float
#    无法转换的（空字符串、'-' 等）→ NaN，绝不填 0
# ============================================================
numeric_cols = ["pe_ttm", "pb", "roe", "total_mv"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# ============================================================
# 5. 日期处理：data_date 和 report_date → YYYY-MM-DD 字符串
# ============================================================
# data_date：爬取当天，格式一般已是 YYYY-MM-DD，统一处理
df["data_date"] = pd.to_datetime(df["data_date"], errors="coerce").dt.strftime("%Y-%m-%d")

# report_date：财报截止日，可能为空字符串或异常值
df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
# pd.to_datetime 将空字符串转为 NaT，再 strftime 变为 NaN 字符串"NaT"，需修正
df["report_date"] = df["report_date"].replace("NaT", pd.NA)

# 统计 report_date 缺失数量
report_date_missing = df["report_date"].isna().sum()
if report_date_missing > 0:
    print(f"report_date 缺失数量：{report_date_missing} 只股票")

# ============================================================
# 6. 异常标注：新增 pe_flag 和 pb_flag
#    保留所有行，不删除
# ============================================================
def flag_pe(val):
    """PE 标注：空值→缺失，负值→亏损，其他→正常"""
    if pd.isna(val):
        return "缺失"
    if val < 0:
        return "亏损"
    return "正常"

def flag_pb(val):
    """PB 标注：负值→净资产为负，其他→正常"""
    if pd.isna(val):
        return "缺失"
    if val < 0:
        return "净资产为负"
    return "正常"

df["pe_flag"] = df["pe_ttm"].apply(flag_pe)
df["pb_flag"] = df["pb"].apply(flag_pb)

# ============================================================
# 7. 排序：按 total_mv 从大到小（空值排最后）
# ============================================================
df = df.sort_values("total_mv", ascending=False, na_position="last").reset_index(drop=True)

# ============================================================
# 8. 固定列顺序并保存
# ============================================================
columns = ["code", "name", "pe_ttm", "pb", "roe", "total_mv",
           "data_date", "report_date", "pe_flag", "pb_flag"]
df = df[columns]
df.to_csv(clean_path, index=False, encoding="utf-8-sig")
print(f"清洗后行数：{len(df)}")
print(f"结果已保存：{clean_path}")

# ============================================================
# 9. 终端汇总打印
# ============================================================
print(f"\n========== 清洗汇总 ==========")
print(f"清洗前行数：{rows_before}")
print(f"清洗后行数：{len(df)}")
print(f"行数变化：{'一致' if rows_before == len(df) else f'差异 {rows_before - len(df)} 行（异常！）'}")

print(f"\n--- 核心列缺失统计 ---")
for col in ["pe_ttm", "pb", "roe", "total_mv", "report_date"]:
    miss = df[col].isna().sum()
    print(f"  {col}: 缺失 {miss} / {len(df)}")

print(f"\n--- total_mv 换算前后中位数对比 ---")
print(f"  换算前（原始值）中位数：{median_before}")
print(f"  换算后（亿元）中位数：  {median_after:.4f}")
print(f"  换算逻辑：{unit_note}")

print(f"\n--- 最终数据前 5 行 ---")
print(df.head(5).to_string())