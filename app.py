# app.py
# 金融科技估值查询 — Streamlit 页面，只读 data/clean.csv，不爬数据

import streamlit as st
import pandas as pd
import plotly.express as px

# ============================================================
# 一、页面基础设置
# ============================================================
st.set_page_config(
    page_title="金融科技估值查询",
    page_icon="📊",
    layout="wide",              # 宽屏显示
)


# ============================================================
# 二、缓存读取数据（刷新页面不重复读盘）
# ============================================================
@st.cache_data
def load_data():
    """读取清洗后的数据，返回 DataFrame"""
    df = pd.read_csv("data/clean.csv", dtype={"code": str})
    # code 统一 6 位
    df["code"] = df["code"].str.zfill(6)
    # 确保数值列是浮点型
    for col in ["pe_ttm", "pb", "roe", "total_mv"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


df = load_data()

# 计算侧边栏所需信息
max_data_date = df["data_date"].dropna().max()
max_report_date = df["report_date"].dropna().max()

# ============================================================
# 三、侧边栏说明
# ============================================================
with st.sidebar:
    st.markdown("### 关于本工具")
    st.markdown(
        f"数据来源 **akshare**，仅供学习参考，不构成投资建议。\n\n"
        f"数据更新至 **{max_data_date}**，\n"
        f"部分财报期截至 **{max_report_date}**。"
    )
    st.divider()
    st.caption(f"共 {len(df)} 只成分股")

# ============================================================
# 四、顶部标题 + 个股检索卡片
# ============================================================
st.title("📊 金融科技估值查询")

# -- 下拉框：格式 "名称 (代码)" --
# 构建选项列表，按名称排序
df_sorted_for_select = df.sort_values("name")
options = df_sorted_for_select.apply(lambda r: f"{r['name']} ({r['code']})", axis=1).tolist()
# 默认选中东方财富（300059）
default_index = 0
for i, opt in enumerate(options):
    if "300059" in opt:
        default_index = i
        break

selected = st.selectbox("选择股票", options, index=default_index)

# 从选中文本中提取 code
selected_code = selected.split("(")[-1].replace(")", "").strip()
stock = df[df["code"] == selected_code].iloc[0]

# -- 4 列核心指标展示 --
col1, col2, col3, col4 = st.columns(4)

# PE(TTM)
pe = stock["pe_ttm"]
pe_flag = stock["pe_flag"]
if pd.isna(pe) or pe_flag == "缺失":
    col1.metric("PE(TTM)", "—", help="数据缺失")
elif pe < 0 or pe_flag == "亏损":
    col1.metric("PE(TTM)", "—", help="当前亏损，PE 无意义")
else:
    col1.metric("PE(TTM)", f"{pe:.2f}")

# PB
pb = stock["pb"]
pb_flag = stock["pb_flag"]
if pd.isna(pb) or pb_flag == "缺失":
    col2.metric("PB", "—", help="数据缺失")
elif pb < 0 or pb_flag == "净资产为负":
    col2.metric("PB", "—", help="净资产为负，PB 无意义")
else:
    col2.metric("PB", f"{pb:.2f}")

# ROE + 报告期
roe = stock["roe"]
rp = stock["report_date"]
if pd.isna(roe):
    col3.metric("ROE", "—", help="数据缺失")
else:
    roe_display = f"{roe:.2f}%"
    col3.metric("ROE", roe_display)
    if pd.notna(rp):
        col3.caption(f"报告期：{rp}")

# 总市值
mv = stock["total_mv"]
if pd.isna(mv):
    col4.metric("总市值", "—", help="数据缺失")
else:
    col4.metric("总市值", f"{mv:.2f} 亿元")

# -- PE 板块排名（从小到大排序，剔除空缺和亏损） --
pe_ranking = df[df["pe_ttm"].notna() & (df["pe_ttm"] >= 0)].sort_values("pe_ttm")
total_ranked = len(pe_ranking)
stock_rank = pe_ranking.index.get_loc(stock.name) + 1 if stock.name in pe_ranking.index else None
if stock_rank is not None:
    st.caption(f"该股 PE 在板块内排第 {stock_rank}/{total_ranked}（从小到大）")

# ============================================================
# 五、对比看板（标签页）
# ============================================================
st.divider()
st.subheader("板块对比看板")

tab1, tab2, tab3 = st.tabs(["📋 数据表格", "📊 PE 横向柱状图", "🎯 PB-ROE 散点图"])

# ------------------------------------------------------------------
# 标签页 1：数据表格
# ------------------------------------------------------------------
with tab1:
    # 准备展示用的 DataFrame，NaN 替换为 "-" 让前端干净
    df_show = df[["code", "name", "pe_ttm", "pb", "roe", "total_mv",
                   "report_date", "pe_flag"]].copy()
    # 数值列保留两位小数
    for col in ["pe_ttm", "pb", "roe", "total_mv"]:
        df_show[col] = df_show[col].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "-"
        )
    # report_date 缺失也显示 -
    df_show["report_date"] = df_show["report_date"].fillna("-")

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("代码"),
            "name": st.column_config.TextColumn("名称"),
            "pe_ttm": st.column_config.TextColumn("PE(TTM)"),
            "pb": st.column_config.TextColumn("PB"),
            "roe": st.column_config.TextColumn("ROE"),
            "total_mv": st.column_config.TextColumn("总市值(亿)"),
            "report_date": st.column_config.TextColumn("财报截止日"),
            "pe_flag": st.column_config.TextColumn("PE 标注"),
        },
    )

# ------------------------------------------------------------------
# 标签页 2：PE 横向柱状图
# ------------------------------------------------------------------
with tab2:
    # 剔除 PE 为空或为负的股票，按 PE 从小到大排序
    df_bar = df[df["pe_ttm"].notna() & (df["pe_ttm"] >= 0)].sort_values("pe_ttm")
    if len(df_bar) == 0:
        st.warning("没有可用于绘制 PE 柱状图的数据（全部缺失或亏损）")
    else:
        # 名称太长会导致 Y 轴拥挤，截断超过 8 个字符的名称，画布调高
        df_bar = df_bar.copy()
        df_bar["short_name"] = df_bar["name"].apply(
            lambda x: x[:8] + "…" if len(x) > 8 else x
        )
        # 画布高度 = 股票数 × 25 像素
        fig_bar = px.bar(
            df_bar,
            x="pe_ttm",
            y="short_name",
            orientation="h",                # 横向柱状图
            title="PE(TTM) 横向对比（从小到大，已剔除亏损/缺失）",
            labels={"pe_ttm": "PE(TTM)", "short_name": "股票"},
            color="pe_ttm",
            color_continuous_scale="Blues_r",
            height=max(400, len(df_bar) * 22),
        )
        fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_bar, use_container_width=True)

# ------------------------------------------------------------------
# 标签页 3：PB-ROE 散点图
# ------------------------------------------------------------------
with tab3:
    # 剔除 pb 或 roe 为空的数据
    df_scatter = df[df["pb"].notna() & df["roe"].notna()].copy()
    if len(df_scatter) == 0:
        st.warning("没有可用于绘制 PB-ROE 散点图的数据")
    else:
        fig_scatter = px.scatter(
            df_scatter,
            x="pb",
            y="roe",
            title="PB vs ROE 散点图",
            labels={"pb": "PB（市净率）", "roe": "ROE（%）"},
            hover_name="name",              # 悬浮显示名称
            hover_data={
                "pe_ttm": ":.2f",            # 悬浮也显示 PE
                "total_mv": ":.2f",          # 悬浮也显示总市值
                "pb": False,
                "roe": False,
            },
            color="total_mv",               # 按市值着色
            size="total_mv",                # 按市值调气泡大小
            color_continuous_scale="Viridis",
            height=500,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)