"""
核心对话引擎
管理多轮对话、意图解析、SQL执行和分析生成
"""
import json
import re
from collections import defaultdict

from db import execute_sql
from llm import chat_completion, chat_completion_stream
from prompts import get_system_prompt, ANALYSIS_PROMPT


# 会话历史存储 {session_id: [messages]}
_sessions = defaultdict(list)

# 最大历史轮数
MAX_HISTORY = 20


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON（兼容 markdown 代码块）"""
    # 尝试提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找第一个 { 到最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
    return {"type": "answer", "message": text}


def _format_result_for_llm(result: dict) -> str:
    """将查询结果格式化为 LLM 可读的文本"""
    if "error" in result:
        return f"查询出错: {result['error']}"
    
    columns = result["columns"]
    rows = result["rows"]
    if not rows:
        return "查询结果为空，没有找到匹配的数据。"
    
    lines = [" | ".join(str(c) for c in columns)]
    lines.append("-" * len(lines[0]))
    for row in rows[:50]:
        lines.append(" | ".join(str(v) for v in row))
    
    text = "\n".join(lines)
    if len(rows) > 50:
        text += f"\n... 共 {len(rows)} 行，仅展示前50行"
    return text


def get_history(session_id: str) -> list[dict]:
    """获取会话历史"""
    return _sessions[session_id]


def clear_history(session_id: str):
    """清除会话历史"""
    _sessions[session_id] = []


def chat(session_id: str, question: str) -> dict:
    """
    处理用户提问，返回结构化响应
    
    Returns:
        {
            "type": "clarify" | "sql" | "answer",
            "message": "回复文本",
            "data": {"columns": [...], "rows": [...]},  # type=sql 时有
            "chart": {...},  # type=sql 时有
            "sql": "...",  # type=sql 时有
        }
    """
    history = _sessions[session_id]
    
    # 添加用户消息到历史
    history.append({"role": "user", "content": question})
    
    # 裁剪历史
    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]
        _sessions[session_id] = history
    
    # 组装 messages
    system_prompt = get_system_prompt()
    messages = [{"role": "system", "content": system_prompt}] + history
    
    # 第一次调用 LLM：理解意图 + 生成 SQL
    llm_response = chat_completion(messages)
    parsed = _extract_json(llm_response)
    
    response_type = parsed.get("type", "answer")
    
    if response_type == "clarify":
        # 意图澄清
        msg = parsed.get("message", "请提供更多信息")
        history.append({"role": "assistant", "content": msg})
        return {"type": "clarify", "message": msg}
    
    elif response_type == "sql":
        sql = parsed.get("sql", "")
        chart = parsed.get("chart", None)
        thinking = parsed.get("thinking", "")
        
        # 安全检查
        sql_upper = sql.upper().strip()
        if any(kw in sql_upper for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]):
            msg = "抱歉，出于安全考虑，我只能执行查询操作。"
            history.append({"role": "assistant", "content": msg})
            return {"type": "answer", "message": msg}
        
        # 执行 SQL
        result = execute_sql(sql)
        
        if "error" in result:
            # SQL 执行失败，让 LLM 修正
            error_msg = f"SQL执行出错: {result['error']}\n原始SQL: {sql}\n请修正SQL后重新返回JSON格式。"
            history.append({"role": "assistant", "content": llm_response})
            history.append({"role": "user", "content": error_msg})
            
            retry_messages = [{"role": "system", "content": system_prompt}] + history
            retry_response = chat_completion(retry_messages)
            retry_parsed = _extract_json(retry_response)
            
            if retry_parsed.get("type") == "sql":
                sql = retry_parsed.get("sql", "")
                chart = retry_parsed.get("chart", chart)
                result = execute_sql(sql)
                if "error" in result:
                    msg = f"抱歉，查询仍然出错：{result['error']}，请尝试换一种问法。"
                    history.append({"role": "assistant", "content": msg})
                    return {"type": "answer", "message": msg}
            else:
                msg = retry_parsed.get("message", "查询出错，请换一种问法。")
                history.append({"role": "assistant", "content": msg})
                return {"type": "answer", "message": msg}
        
        # 第二次调用 LLM：生成分析结论
        result_text = _format_result_for_llm(result)
        analysis_prompt = ANALYSIS_PROMPT.format(sql=sql, result=result_text)
        analysis_messages = [
            {"role": "system", "content": "你是一个专业的财务数据分析师。"},
            {"role": "user", "content": analysis_prompt}
        ]
        analysis = chat_completion(analysis_messages, temperature=0.3)
        
        # 记录到历史
        history.append({"role": "assistant", "content": analysis})
        
        return {
            "type": "sql",
            "message": analysis,
            "data": result,
            "chart": chart,
            "sql": sql,
            "thinking": thinking,
        }
    
    else:
        # 直接回答
        msg = parsed.get("message", llm_response)
        history.append({"role": "assistant", "content": msg})
        return {"type": "answer", "message": msg}
