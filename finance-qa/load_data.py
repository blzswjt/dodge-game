"""
财务数据加载模块
读取 Excel 并导入 SQLite，同时生成 schema 描述供 LLM 使用
"""
import sqlite3
import pandas as pd
from pathlib import Path

EXCEL_PATH = Path(__file__).parent / "data" / "结构化财务数据库.xlsx"
DB_PATH = Path(__file__).parent / "finance.db"

# Sheet 名 -> SQLite 表名 映射
TABLE_MAP = {
    "核心业绩指标表": "core_metrics",
    "资产负债表": "balance_sheet",
    "现金流量表": "cash_flow",
    "利润表": "income_statement",
}

# 表的中文描述（供 prompt 使用）
TABLE_DESC = {
    "core_metrics": "核心业绩指标表：包含每股收益、营业总收入、净利润、ROE、毛利率等综合业绩指标",
    "balance_sheet": "资产负债表：包含货币资金、应收账款、存货、总资产、总负债、资产负债率、股东权益等",
    "cash_flow": "现金流量表：包含经营性/投资性/融资性现金流净额及占比、净现金流等",
    "income_statement": "利润表：包含净利润、营业总收入、各项费用（销售/管理/财务/研发）、营业利润等",
}


def load_excel() -> dict:
    """读取 Excel 所有 Sheet，返回 {sheet名: DataFrame}"""
    dfs = {}
    for sheet_name, table_name in TABLE_MAP.items():
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
        dfs[table_name] = df
    return dfs


def init_db(dfs: dict = None):
    """将 DataFrame 写入 SQLite"""
    if dfs is None:
        dfs = load_excel()

    conn = sqlite3.connect(str(DB_PATH))
    for table_name, df in dfs.items():
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  [OK] {table_name}: {len(df)} rows x {len(df.columns)} cols")
    conn.close()
    print(f"数据库已保存: {DB_PATH}")
    return dfs


def get_schema_text() -> str:
    """生成数据库 schema 描述文本（含样本值），供 System Prompt 使用"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    lines = []
    for table_name in TABLE_MAP.values():
        desc = TABLE_DESC.get(table_name, "")
        lines.append(f"## 表: {table_name}")
        lines.append(f"说明: {desc}")

        # 获取列信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        lines.append("字段列表:")
        col_names = []
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            col_names.append(col_name)
            lines.append(f"  - {col_name} ({col_type})")

        # 获取样本数据（前 2 行）
        cursor.execute(f'SELECT * FROM {table_name} LIMIT 2')
        rows = cursor.fetchall()
        if rows:
            lines.append("样本数据:")
            for row in rows:
                sample = {col_names[i]: row[i] for i in range(len(col_names))}
                lines.append(f"  {sample}")
        lines.append("")

    conn.close()
    return "\n".join(lines)


if __name__ == "__main__":
    print("正在加载 Excel 数据...")
    dfs = load_excel()
    print("正在写入 SQLite...")
    init_db(dfs)
    print("\n" + "=" * 60)
    print("Schema 描述:")
    print("=" * 60)
    print(get_schema_text())
