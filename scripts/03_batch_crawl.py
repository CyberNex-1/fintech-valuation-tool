# 03_batch_crawl.py
# 批量获取 pool.csv 中所有股票的 PE(TTM)/PB/ROE/总市值，保存到 data/raw.csv

import sys
import os
import random
import time
from datetime import date
import requests
import pandas as pd
import akshare as ak

# ============================================================
# 0. 准备工作：读 pool.csv、检查断点续传
# ============================================================
pool_path = "data/pool.csv"
raw_path = "data/raw.csv"
failed_path = "data/failed.csv"

# 读取成分股名单
df_pool = pd.read_csv(pool_path, dtype={"code": str})
codes_all = df_pool["code"].tolist()
names_all = dict(zip(df_pool["code"], df_pool["name"]))  # code → name 映射

# 断点续传：如果 raw.csv 已存在，跳过已完成的代码
done_codes = set()
if os.path.exists(raw_path):
    df_old = pd.read_csv(raw_path, dtype={"code": str})
    done_codes = set(df_old["code"].tolist())
    print(f"检测到 raw.csv 已有 {len(done_codes)} 条记录，将跳过这些代码")

codes_todo = [c for c in codes_all if c not in done_codes]
print(f"总股票数: {len(codes_all)}，已完成: {len(done_codes)}，待处理: {len(codes_todo)}")

if len(codes_todo) == 0:
    print("所有股票已处理完毕，无需运行。")
    sys.exit(0)

# ============================================================
# 1. 尝试走一次东财全量接口（一次拉全部股票，省去逐只重试）
# ============================================================
df_em_all = None  # 如果东财接口成功，这里缓存全部股票数据
print("尝试调用 stock_zh_a_spot_em 获取全 A 股实时行情...")
for attempt in range(1, 4):
    try:
        df_em_all = ak.stock_zh_a_spot_em()
        print("东财接口调用成功，将从中提取各股票数据")
        break
    except Exception as e:
        if attempt < 3:
            time.sleep(random.uniform(2, 5))

if df_em_all is None:
    print("东财接口不可用，后续全部走腾讯接口逐只获取")
else:
    print(f"东财全量数据共 {len(df_em_all)} 行")


# ============================================================
# 2. 单只股票取数函数
# ============================================================

def fetch_from_tencent(code, default_name):
    """通过腾讯财经 HTTP 接口获取 PE(TTM)、PB、总市值、名称。
    返回 dict 或 None。"""
    # 深圳股用 sz，上海股用 sh，北交所(8开头和92开头)用 bj
    if code.startswith("6"):
        prefix = "sh"                           # 上海主板 + 科创板(688)
    elif code.startswith(("0", "3")):
        prefix = "sz"                           # 深圳主板 + 创业板(300)
    elif code.startswith(("8", "92")):
        prefix = "bj"                           # 北交所
    else:
        prefix = "sz"                           # 兜底
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            raw = resp.text
            if "~" not in raw:
                raise ValueError("返回不含 ~ 分隔符")
            fields = raw.split("~")
            # 字段数必须足够（至少 47 个字段才能取到 PB）
            if len(fields) < 47:
                raise ValueError(f"字段数不足：{len(fields)}")
            # [1]=名称, [39]=PE(TTM), [45]=总市值, [46]=PB
            stock_name = fields[1] if len(fields) > 1 else default_name
            pe_val = float(fields[39]) if len(fields) > 39 and fields[39] != "" else None
            mv_val = float(fields[45]) if len(fields) > 45 and fields[45] != "" else None
            pb_val = float(fields[46]) if len(fields) > 46 and fields[46] != "" else None
            return {
                "name": stock_name,
                "pe_ttm": pe_val,
                "pb": pb_val,
                "total_mv": mv_val,
            }
        except Exception:
            if attempt < 3:
                time.sleep(random.uniform(2, 5))
    return None


def fetch_roe(code):
    """获取最近一期 ROE 及其报告期日期。
    优先取'加权净资产收益率(%)'（对应雪球"净资产收益率"），
    降级取'净资产收益率(%)'（对应雪球"净资产收益率-摊薄"）。
    返回 (roe, report_date) 或 (None, None)。"""
    try:
        df_fin = ak.stock_financial_analysis_indicator(symbol=code)
        # 优先匹配"加权净资产收益率"
        roe_col = None
        for col in df_fin.columns:
            if "加权净资产收益率" in col:
                roe_col = col
                break
        # 降级匹配"净资产收益率"（摊薄）
        if roe_col is None:
            for col in df_fin.columns:
                if "净资产收益率" in col:
                    roe_col = col
                    break
        if roe_col is None:
            return None, None
        # 定位日期列（用于提取财报截止日）
        date_col = None
        for col in df_fin.columns:
            if "日期" in col:
                date_col = col
                break
        # 从后往前找第一个非空 ROE
        for i in range(len(df_fin) - 1, -1, -1):
            val = df_fin[roe_col].iloc[i]
            if pd.notna(val):
                roe = float(val)
                report_date = str(df_fin[date_col].iloc[i])[:10] if date_col else ""
                return roe, report_date
    except Exception:
        pass
    return None, None


def extract_from_em(df_em, code):
    """从东财全量 DataFrame 中提取单只股票数据。
    返回 dict 或 None。"""
    if "代码" not in df_em.columns:
        return None
    row = df_em[df_em["代码"] == code]
    if len(row) == 0:
        return None
    latest = row.iloc[0]
    # PE 列模糊匹配：优先 TTM，次选动态，最后任意市盈率
    pe_ttm = None
    # 第一轮：找含 TTM 的（如"市盈率-动态"实际是 TTM？东财列名需核实）
    for col in row.columns:
        if "市盈率" in col and "TTM" in col.upper():
            v = latest[col]
            if pd.notna(v):
                pe_ttm = float(v)
            break
    # 第二轮：TTM 没找到，找含"动态"的
    if pe_ttm is None:
        for col in row.columns:
            if "市盈率" in col and "动态" in col:
                v = latest[col]
                if pd.notna(v):
                    pe_ttm = float(v)
                break
    # 第三轮：兜底，任意包含"市盈率"的列
    if pe_ttm is None:
        for col in row.columns:
            if "市盈率" in col:
                v = latest[col]
                if pd.notna(v):
                    pe_ttm = float(v)
                break
    # PB 列
    pb = None
    for col in row.columns:
        if "市净率" in col:
            v = latest[col]
            if pd.notna(v):
                pb = float(v)
            break
    # 总市值列
    total_mv = None
    for col in row.columns:
        if "总市值" in col and "流通" not in col:
            v = latest[col]
            if pd.notna(v):
                total_mv = float(v)
            break
    name = latest.get("名称", names_all.get(code, ""))
    return {"name": name, "pe_ttm": pe_ttm, "pb": pb, "total_mv": total_mv}


# ============================================================
# 3. 主循环：逐只处理
# ============================================================
results = []      # 成功结果列表
failed_list = []  # 失败代码列表
data_date_str = str(date.today())

total = len(codes_todo)

for idx, code in enumerate(codes_todo):
    default_name = names_all.get(code, "")
    try:
        # -- 获取 PE/PB/总市值 --
        indicator = None
        if df_em_all is not None:
            # 东财全量数据可用，直接提取
            indicator = extract_from_em(df_em_all, code)
        if indicator is None:
            # 东财不可用或未找到，走腾讯接口
            indicator = fetch_from_tencent(code, default_name)

        if indicator is None:
            raise RuntimeError("PE/PB/总市值获取失败")

        # -- 获取 ROE（含报告期日期）--
        roe, report_date = fetch_roe(code)

        # -- 组装结果 --
        results.append({
            "code": code,
            "name": indicator.get("name", default_name),
            "pe_ttm": indicator.get("pe_ttm"),
            "pb": indicator.get("pb"),
            "roe": roe,
            "total_mv": indicator.get("total_mv"),
            "data_date": data_date_str,
            "report_date": report_date,
        })

        # -- 进度打印 --
        done_count = len(results) + len(done_codes)
        if (done_count % 5 == 0) or (idx == total - 1):
            print(f"已完成 {done_count}/{len(codes_all)}")

    except Exception as e:
        print(f"代码 {code} 获取失败: {type(e).__name__}: {e}")
        failed_list.append(code)

    # 每只股票之间随机休眠
    if idx < total - 1:
        time.sleep(random.uniform(2, 4))

# ============================================================
# 4. 保存结果
# ============================================================
# 合并新结果到已有数据（断点续传）
if os.path.exists(raw_path):
    df_old = pd.read_csv(raw_path, dtype={"code": str})
    # 兼容旧版 raw.csv 缺少 report_date 列的情况
    if "report_date" not in df_old.columns:
        df_old["report_date"] = ""
    df_new = pd.DataFrame(results)
    df_all = pd.concat([df_old, df_new], ignore_index=True)
else:
    df_all = pd.DataFrame(results)

# 固定列顺序
columns = ["code", "name", "pe_ttm", "pb", "roe", "total_mv", "data_date", "report_date"]
df_all = df_all[columns]
df_all.to_csv(raw_path, index=False, encoding="utf-8-sig")

# 保存失败清单
if failed_list:
    pd.DataFrame({"code": failed_list}).to_csv(
        failed_path, index=False, encoding="utf-8-sig"
    )

# ============================================================
# 5. 汇总报告
# ============================================================
print(f"\n===== 批量爬取完成 =====")
print(f"成功数量: {len(results)}")
print(f"失败数量: {len(failed_list)}")
if failed_list:
    print(f"失败代码: {', '.join(failed_list)}")
    print(f"失败清单已保存: {failed_path}")
print(f"结果已保存: {raw_path}")