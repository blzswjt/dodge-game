"""
图表推荐模块
定义图表配置的数据结构和默认处理
"""


def build_chart_config(chart_info: dict, data: dict) -> dict:
    """
    根据 LLM 返回的 chart 建议和实际数据，构建前端可用的 ECharts 配置
    
    Args:
        chart_info: LLM 返回的 {"chart_type", "title", "x_field", "y_fields"}
        data: SQL 查询结果 {"columns", "rows"}
    
    Returns:
        前端可直接使用的 chart 配置
    """
    if not chart_info or not data or "error" in data:
        return None
    
    chart_type = chart_info.get("chart_type", "table")
    title = chart_info.get("title", "查询结果")
    x_field = chart_info.get("x_field", "")
    y_fields = chart_info.get("y_fields", [])
    
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    
    if not rows or not columns:
        return None
    
    # 获取字段索引
    col_index = {c: i for i, c in enumerate(columns)}
    
    x_idx = col_index.get(x_field)
    y_idxs = [col_index.get(f) for f in y_fields if f in col_index]
    
    if x_idx is None and chart_type != "table":
        # 如果 x_field 找不到，用第一列
        x_idx = 0
        x_field = columns[0]
    
    if not y_idxs and chart_type != "table":
        # 如果 y_fields 找不到，用所有数值列
        y_idxs = [i for i, c in enumerate(columns) if i != x_idx and _is_numeric_col(rows, i)]
        y_fields = [columns[i] for i in y_idxs]
    
    x_data = [str(row[x_idx]) for row in rows] if x_idx is not None else []
    
    if chart_type == "pie":
        # 饼图只用第一个 y_field
        y_idx = y_idxs[0] if y_idxs else 1
        pie_data = [
            {"name": str(row[x_idx]), "value": _safe_num(row[y_idx])}
            for row in rows
        ]
        return {
            "chart_type": "pie",
            "title": title,
            "data": pie_data,
        }
    
    elif chart_type in ("bar", "line"):
        series = []
        for y_idx, y_name in zip(y_idxs, y_fields):
            series.append({
                "name": y_name,
                "data": [_safe_num(row[y_idx]) for row in rows],
            })
        return {
            "chart_type": chart_type,
            "title": title,
            "x_data": x_data,
            "x_field": x_field,
            "series": series,
        }
    
    else:
        # table
        return {
            "chart_type": "table",
            "title": title,
            "columns": columns,
            "rows": rows,
        }


def _safe_num(val):
    """安全转数字"""
    if val is None:
        return 0
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return 0


def _is_numeric_col(rows, idx):
    """判断某列是否为数值类型"""
    for row in rows[:5]:
        v = row[idx]
        if v is not None:
            try:
                float(v)
                return True
            except (ValueError, TypeError):
                return False
    return False
