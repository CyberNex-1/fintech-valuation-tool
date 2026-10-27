# 02_get_one.py
# 只验证单只股票 300059（东方财富）的 PE/PB/ROE/总市值 取数

import akshare as ak
import pandas as pd
import random
import time
import requests

code = "300059"
name = "东方财富"

# ============================================================
# 第一步：获取 PE(TTM)、PB、总市值
# ============================================================
print("=" * 50)
print("第一步：获取 PE(TTM)、PB、总市值")
print("=" * 50)
# stock_zh_a_spot_em 返回全 A 股实时行情，包含市盈率、市净率、总市值
# 注：市盈率为"市盈率-动态"，近似替代 PE(TTM)
# 网络偶发断开，加随机延时 + 3 次重试（用户建议）
print("正在调用 stock_zh_a_spot_em 接口，获取全 A 股实时行情...")
df_all = None
for attempt in range(1, 4):
    try:
        df_all = ak.stock_zh_a_spot_em()
        break
    except Exception as e:
        print(f"第 {attempt} 次尝试失败：{type(e).__name__}: {e}")
        if attempt < 3:
            wait = random.uniform(2, 5)
            print(f"等待 {wait:.1f} 秒后重试...")
            time.sleep(wait)

# 备选方案：若东方财富接口全部失败，改用腾讯财经 API（直接 HTTP，不经 akshare）
if df_all is None:
    print("stock_zh_a_spot_em 3 次重试均失败，改用腾讯财经 HTTP 接口...")
    # 腾讯股票行情 API，深圳股用 sz 前缀，上海股用 sh 前缀
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            raw = resp.text
            print(f"腾讯接口返回（前 200 字符）：{raw[:200]}")
            # 腾讯返回格式：v_sz300059="1~东方财富~300059~价格~..."
            # 按 ~ 分割取字段
            if "~" not in raw:
                raise ValueError("返回格式异常，不含 ~ 分隔符")
            fields = raw.split("~")
            # 打印所有字段索引，方便定位正确的 PE/PB/总市值 位置
            print(f"共 {len(fields)} 个字段：")
            for i in range(len(fields)):
                val = fields[i] if i < len(fields) else ""
                # 只打印可能有意义的字段（跳过买卖盘明细 9~28）
                if i < 9 or i > 28:
                    print(f"  [{i}] {val}")
            # 腾讯字段索引（从 0 开始，去掉 v_xxx=" 前缀）
            # 索引 1: 名称, 3: 最新价, 39: 市盈率(TTM), 45: 总市值(亿元), 46: 市净率
            stock_name = fields[1] if len(fields) > 1 else name
            price = float(fields[3]) if len(fields) > 3 else None
            pe_val = float(fields[39]) if len(fields) > 39 and fields[39] != "" else None
            mv_val = float(fields[45]) if len(fields) > 45 and fields[45] != "" else None
            pb_val = float(fields[46]) if len(fields) > 46 and fields[46] != "" else None
            # 组装成一行 DataFrame，列名与后续代码兼容
            df_all = pd.DataFrame([{
                "名称": stock_name,
                "最新价": price,
                "市盈率(TTM)": pe_val,
                "市净率": pb_val,
                "总市值": mv_val,
            }])
            break
        except Exception as e:
            print(f"腾讯接口第 {attempt} 次尝试失败：{type(e).__name__}: {e}")
            if attempt < 3:
                wait = random.uniform(2, 5)
                print(f"等待 {wait:.1f} 秒后重试...")
                time.sleep(wait)
            else:
                print("腾讯接口 3 次重试均失败")
                df_all = None

if df_all is None:
    print("所有接口均失败，无法获取 PE/PB/总市值，程序退出。")
    exit(1)

print("接口返回列名：", df_all.columns.tolist())
print("总行数：", len(df_all))

# 筛选 300059：如果是全 A 股接口则筛选，如果是雪球单只接口则直接使用
if '代码' in df_all.columns:
    df_indicator = df_all[df_all['代码'] == code]
    if len(df_indicator) == 0:
        print(f"错误：在全 A 股数据中未找到代码 {code}")
        exit(1)
else:
    # 腾讯接口/其他单只接口返回的已是该股数据，直接使用
    df_indicator = df_all
print(f"目标股票 {code} 的数据：")
print(df_indicator.to_string())

# 取第一行
latest = df_indicator.iloc[0]

# -- PE(TTM) --
# 腾讯接口列名是"市盈率(TTM)"，东方财富接口是"市盈率-动态"
pe_col = None
for col in df_indicator.columns:
    if '市盈率' in col and ('TTM' in col.upper() or '动态' in col):
        pe_col = col
        break
if pe_col is None:
    for col in df_indicator.columns:
        if '市盈率' in col:
            pe_col = col
            break
if pe_col is None:
    for col in df_indicator.columns:
        if 'pe' in col.lower():
            pe_col = col
            break
if pe_col:
    pe_ttm = latest[pe_col]
    print(f"PE(TTM) 列名=[{pe_col}]，值={pe_ttm}")
else:
    pe_ttm = None
    print("PE(TTM) 取不到")

# -- PB --
pb_col = None
for col in df_indicator.columns:
    if '市净率' in col:
        pb_col = col
        break
if pb_col is None:
    for col in df_indicator.columns:
        if 'pb' in col.lower():
            pb_col = col
            break
if pb_col:
    pb = latest[pb_col]
    print(f"PB 列名=[{pb_col}]，值={pb}")
else:
    pb = None
    print("PB 取不到")

# -- 总市值 --
mv_col = None
for col in df_indicator.columns:
    if '总市值' in col and '流通' not in col:
        mv_col = col
        break
if mv_col is None:
    for col in df_indicator.columns:
        if '市值' in col and '流通' not in col:
            mv_col = col
            break
if mv_col:
    total_mv = latest[mv_col]
    print(f"总市值 列名=[{mv_col}]，值={total_mv}")
else:
    total_mv = None
    print("总市值 取不到")

# -- 数据日期 --
# stock_zh_a_spot_em 是实时数据，无日期列，用当天日期
from datetime import date
data_date = str(date.today())

# ============================================================
# 第二步：获取最近一期 ROE
# ============================================================
print("\n" + "=" * 50)
print("第二步：获取最近一期 ROE")
print("=" * 50)
print(f"正在调用 stock_financial_analysis_indicator 接口，股票代码 {code}...")
df_fin = ak.stock_financial_analysis_indicator(symbol=code)
print("接口返回列名：", df_fin.columns.tolist())
print("前 5 行：")
print(df_fin.head(5).to_string())

# 模糊匹配包含"净资产收益率"的列
roe_col = None
for col in df_fin.columns:
    if '净资产收益率' in col:
        roe_col = col
        break
if roe_col is None:
    print("ROE 取不到（未找到包含'净资产收益率'的列）")
    roe = None
else:
    # 取最近一期非空的 ROE（从后往前找）
    roe = None
    for i in range(len(df_fin) - 1, -1, -1):
        val = df_fin[roe_col].iloc[i]
        if pd.notna(val):
            roe = val
            # 顺便取 ROE 对应的报告期日期
            roe_date_col = None
            for c in df_fin.columns:
                if '日期' in c or 'date' in c.lower() or '报告期' in c:
                    roe_date_col = c
                    break
            if roe_date_col:
                roe_report_date = str(df_fin[roe_date_col].iloc[i])[:10]
                print(f"ROE 报告期：{roe_report_date}")
            print(f"ROE 列名=[{roe_col}]，值={roe}")
            break
    if roe is None:
        print("ROE 取不到（该列所有行均为空）")

# ============================================================
# 第三步：总结字段名和单位
# ============================================================
print("\n" + "=" * 50)
print("第三步：字段名与量级总结")
print("=" * 50)
print(f"PE(TTM) 列名: {pe_col}，值: {pe_ttm}")
print(f"PB 列名: {pb_col}，值: {pb}")
print(f"总市值 列名: {mv_col}，值: {total_mv}")
print(f"ROE 列名: {roe_col}，值: {roe}")

# 根据量级推断单位
print("\n--- 量级推断 ---")
print("300059 东方财富，当前总市值大约在几千亿元。")
if total_mv is not None:
    val = float(total_mv)
    if val > 1e12:
        print(f"总市值原始值={val}，量级约 {val/1e12:.2f} 万亿 → 单位可能是【元】，需除以 1e8 换算为亿")
    elif val > 1e10:
        print(f"总市值原始值={val}，量级约 {val/1e8:.2f} 亿 → 单位可能是【元】，需除以 1e8 换算为亿")
    elif val > 1e8:
        print(f"总市值原始值={val}，量级约 {val/1e4:.2f} 万 → 单位可能是【万】或数值较小")
    elif val > 1000:
        print(f"总市值原始值={val}，量级约 {val} → 单位很可能是【亿元】")
    else:
        print(f"总市值原始值={val}，需手动确认单位")

if roe is not None:
    val = float(roe)
    if val > 50:
        print(f"ROE 原始值={val}，量级偏大，可能是百分比形式（如 12.5 表示 12.5%）")
    elif val < 1:
        print(f"ROE 原始值={val}，量级 < 1，可能是小数形式（如 0.125 表示 12.5%）")
    else:
        print(f"ROE 原始值={val}，量级在 1~50，可能是百分比形式（如 {val}%）")

# ============================================================
# 第四步：整理成一行 DataFrame
# ============================================================
print("\n" + "=" * 50)
print("第四步：最终输出")
print("=" * 50)

result = pd.DataFrame([{
    'code': code,
    'name': name,
    'pe_ttm': pe_ttm,
    'pb': pb,
    'roe': roe,
    'total_mv': total_mv,
    'data_date': data_date,
}])
print(result.to_string(index=False))