"""
SQLite 数据库连接管理
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "finance.db"


def get_connection() -> sqlite3.Connection:
    """获取 SQLite 连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def execute_sql(sql: str) -> dict:
    """
    执行 SQL 查询，返回结构化结果
    返回: {"columns": [...], "rows": [[...], ...], "row_count": int}
    """
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [list(row) for row in cursor.fetchall()]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_all_tables() -> list[str]:
    """获取所有表名"""
    conn = get_connection()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables
