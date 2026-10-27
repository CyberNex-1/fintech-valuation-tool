# 01_get_pool.py
# 获取"金融科技"概念板块成分股，保存到 data/pool.csv

import sys
import time
import akshare as ak
import pandas as pd

# ============================================================
# 第一步：拉取全部概念板块，查找"金融科技"相关板块
# ============================================================

print("正在调用 stock_board_concept_name_em 接口，获取全部概念板块列表...")
# 网络请求偶发连接断开，加 3 次重试
df_concept = None
for attempt in range(1, 4):
    try:
        df_concept = ak.stock_board_concept_name_em()
        break
    except Exception as e:
        print(f"第 {attempt} 次尝试失败：{e}")
        if attempt < 3:
            print("等待 2 秒后重试...")
            time.sleep(2)

if df_concept is not None:
    print("接口返回列名：", df_concept.columns.tolist())
    print("返回行数：", len(df_concept))

    # 找到"板块名称"列（不同版本 akshare 列名可能略有差异）
    name_col = None
    code_col = None
    for col in df_concept.columns:
        if '名称' in col or col == 'name':
            name_col = col
        if '代码' in col or col == 'code':
            code_col = col
    if name_col is None:
        name_col = df_concept.columns[0]  # 兜底取第一列
        print(f"警告：未找到'名称'列，使用第一列 [{name_col}] 作为板块名")
    if code_col is None:
        code_col = df_concept.columns[1] if len(df_concept.columns) > 1 else df_concept.columns[0]
        print(f"警告：未找到'代码'列，使用 [{code_col}] 作为板块代码")

    # 筛选名称中包含"金融科技"的板块
    mask = df_concept[name_col].str.contains('金融科技', na=False)
    matched = df_concept[mask]

    if len(matched) > 0:
        print(f"\n找到 {len(matched)} 个匹配的板块：")
        print(matched[[code_col, name_col]].to_string(index=False))
        # 优先选名称精确为"金融科技"的，否则取第一个
        exact = matched[matched[name_col] == '金融科技']
        if len(exact) > 0:
            target_board = exact.iloc[0]
            print(f"选用精确匹配板块：{target_board[name_col]}")
        else:
            target_board = matched.iloc[0]
            print(f"选用第一个匹配板块：{target_board[name_col]}")

        board_name = target_board[name_col]
        board_code = target_board[code_col]
        df_stocks = None
    else:
        print("未找到包含'金融科技'的板块")
        target_board = None
else:
    # 3 次重试全部失败
    print("概念板块接口 3 次重试均失败，跳过板块方式")
    target_board = None

# ============================================================
# 第二步：用板块代码获取成分股
# ============================================================

df_stocks = None

if target_board is not None:
    # 方案 A：用板块代码获取成分股
    print(f"\n正在调用 stock_board_concept_cons_em 接口，获取板块 [{board_name}] 的成分股...")
    try:
        # 先用板块代码尝试（BK 开头）
        df_stocks = ak.stock_board_concept_cons_em(symbol=board_code)
        print("用板块代码调用成功")
    except Exception as e1:
        print(f"用板块代码调用失败：{e1}")
        # 再用板块名称尝试
        try:
            df_stocks = ak.stock_board_concept_cons_em(symbol=board_name)
            print("用板块名称调用成功")
        except Exception as e2:
            print(f"用板块名称调用也失败：{e2}")

# 方案 B：如果板块方式失败，改用中证金融科技指数
if df_stocks is None:
    print("\n正在调用 index_stock_cons 接口，获取中证金融科技指数(930986)成分股...")
    try:
        df_stocks = ak.index_stock_cons(symbol="930986")
        print("中证指数接口调用成功")
    except Exception as e:
        print(f"中证指数接口调用失败：{e}")
        # 尝试替代接口 index_stock_cons_csindex
        try:
            print("正在调用 index_stock_cons_csindex 接口（备选）...")
            df_stocks = ak.index_stock_cons_csindex(symbol="930986")
            print("中证指数备选接口调用成功")
        except Exception as e2:
            print(f"中证指数备选接口也失败：{e2}")

# ============================================================
# 如果两个口径都拿不到数据，报错退出
# ============================================================

if df_stocks is None:
    print("\n错误：两个口径都无法获取数据。")
    print("尝试过的接口：")
    print("  - stock_board_concept_name_em → stock_board_concept_cons_em")
    print("  - index_stock_cons('930986')")
    print("  - index_stock_cons_csindex('930986')")
    sys.exit(1)

# ============================================================
# 第三步：整理数据，只保留 code 和 name 两列
# ============================================================

print("\n接口返回列名：", df_stocks.columns.tolist())
print("原始数据前 3 行：")
print(df_stocks.head(3).to_string(index=False))

# 寻找代码列和名称列
code_col = None
name_col = None
for col in df_stocks.columns:
    col_str = str(col).lower()
    # 代码列：包含"代码"、"code"、"成分券代码"
    if code_col is None and ('代码' in col_str or 'code' in col_str):
        code_col = col
    # 名称列：包含"名称"、"name"、"简称"
    if name_col is None and ('名称' in col_str or 'name' in col_str or '简称' in col_str):
        name_col = col

# 兜底：找不到则取第一列和第二列
if code_col is None:
    code_col = df_stocks.columns[0]
    print(f"警告：未找到标准代码列，使用 [{code_col}] 作为代码列")
if name_col is None:
    name_col = df_stocks.columns[1] if len(df_stocks.columns) > 1 else df_stocks.columns[0]
    print(f"警告：未找到标准名称列，使用 [{name_col}] 作为名称列")

# 构建最终结果
result = pd.DataFrame()
result['code'] = df_stocks[code_col].astype(str).str.strip().str.zfill(6)
result['name'] = df_stocks[name_col].astype(str).str.strip()

# 去重（以防万一）
result = result.drop_duplicates(subset='code').reset_index(drop=True)

# ============================================================
# 第四步：保存为 CSV，打印汇总信息
# ============================================================

output_path = 'data/pool.csv'
result.to_csv(output_path, index=False, encoding='utf-8-sig')

print(f"\n总股票数：{len(result)}")
print("前 10 行：")
print(result.head(10).to_string(index=False))
print(f"\n保存成功：{output_path}")

# ============================================================
# 额外检查：确保 code 都是 6 位
# ============================================================
bad_codes = result[result['code'].str.len() != 6]
if len(bad_codes) > 0:
    print(f"\n警告：以下 {len(bad_codes)} 只股票的代码不是 6 位：")
    print(bad_codes.to_string(index=False))