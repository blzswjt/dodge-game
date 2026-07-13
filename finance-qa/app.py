"""
FastAPI 主入口
"""
import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from load_data import init_db, DB_PATH, get_schema_text
from chat import chat, clear_history, get_history
from chart import build_chart_config

app = FastAPI(title="财报智能问数助手", version="1.0.0")

# 挂载静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class ChatRequest(BaseModel):
    session_id: str = ""
    question: str


@app.on_event("startup")
def startup():
    """启动时初始化数据库"""
    if not DB_PATH.exists():
        print("数据库不存在，正在初始化...")
        init_db()
    else:
        print(f"数据库已存在: {DB_PATH}")


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面"""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>finance-qa</h1><p>前端页面未找到</p>")


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    核心对话接口
    接收用户提问，返回结构化 JSON 响应
    """
    if not req.session_id:
        req.session_id = str(uuid.uuid4())
    
    result = chat(req.session_id, req.question)
    
    # 如果有图表和数据，构建 chart 配置
    if result.get("type") == "sql" and result.get("chart") and result.get("data"):
        chart_config = build_chart_config(result["chart"], result["data"])
        result["chart"] = chart_config
    
    result["session_id"] = req.session_id
    return JSONResponse(result)


@app.post("/chat/clear")
async def clear_chat(req: ChatRequest):
    """清除会话历史"""
    clear_history(req.session_id)
    return {"status": "ok"}


@app.get("/schema")
async def schema():
    """返回数据库表结构信息"""
    return {"schema": get_schema_text()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
