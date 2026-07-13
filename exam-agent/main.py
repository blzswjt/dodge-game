"""
FastAPI 主入口 - 产品知识考试与问答系统
"""
import os
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from doc_processor import load_document, find_relevant_chunks
from exam import answer_question_stream, generate_exam, grade_answer
from llm import chat

app = FastAPI(title="产品知识考试与问答系统", version="1.0.0")

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 文档存储路径
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 全局文档数据
_doc_data = {"full_text": "", "modules": []}
_current_doc_path = None


def get_doc_data() -> dict:
    return _doc_data


def set_doc_data(data: dict):
    global _doc_data
    _doc_data = data


# ============================================================
# 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>页面未找到</h1>")


# ============================================================
# 文档上传
# ============================================================

@app.post("/api/upload")
async def upload_doc(file: UploadFile = File(...)):
    """上传 docx 文件"""
    global _current_doc_path

    if not file.filename.endswith(".docx"):
        return JSONResponse({"error": "请上传 .docx 格式文件"}, status_code=400)

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 解析文档
    data = load_document(str(save_path))
    set_doc_data(data)
    _current_doc_path = str(save_path)

    return {
        "status": "ok",
        "filename": file.filename,
        "modules": len(data["modules"]),
        "total_chars": len(data["full_text"]),
        "module_names": [m["module"] for m in data["modules"]]
    }


@app.post("/api/load-default")
async def load_default_doc():
    """加载默认文档（同目录下的 docx）"""
    global _current_doc_path

    # 查找 docx 文件：优先本地 data/ 目录
    data_dir = Path(__file__).parent / "data"
    docx_files = list(data_dir.glob("*.docx")) if data_dir.exists() else []

    if not docx_files:
        # 兆底：父目录
        parent = Path(__file__).parent.parent
        docx_files = list(parent.glob("*.docx"))

    if not docx_files:
        # 也检查 uploads 目录
        docx_files = list(UPLOAD_DIR.glob("*.docx"))

    if not docx_files:
        return JSONResponse({"error": "未找到 docx 文件，请先上传"}, status_code=404)

    doc_path = str(docx_files[0])
    data = load_document(doc_path)
    set_doc_data(data)
    _current_doc_path = doc_path

    return {
        "status": "ok",
        "filename": docx_files[0].name,
        "modules": len(data["modules"]),
        "total_chars": len(data["full_text"]),
        "module_names": [m["module"] for m in data["modules"]]
    }


# ============================================================
# 智能问答
# ============================================================

class QARequest(BaseModel):
    question: str


@app.post("/api/qa")
async def qa_endpoint(req: QARequest):
    """智能问答（非流式）"""
    doc = get_doc_data()
    if not doc["modules"]:
        return JSONResponse({"error": "请先加载文档"}, status_code=400)

    from exam import answer_question
    answer = answer_question(req.question, doc["modules"])
    return {"answer": answer}


@app.post("/api/qa/stream")
async def qa_stream_endpoint(req: QARequest):
    """智能问答（流式）"""
    doc = get_doc_data()
    if not doc["modules"]:
        return JSONResponse({"error": "请先加载文档"}, status_code=400)

    def generate():
        for chunk in answer_question_stream(req.question, doc["modules"]):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
# 考试生成
# ============================================================

@app.post("/api/exam/generate")
async def generate_exam_endpoint():
    """生成试卷"""
    doc = get_doc_data()
    if not doc["modules"]:
        return JSONResponse({"error": "请先加载文档"}, status_code=400)

    try:
        exam = generate_exam(doc["modules"])
        counts = {k: len(v) for k, v in exam.items()}
        return {"status": "ok", "exam": exam, "counts": counts}
    except Exception as e:
        return JSONResponse({"error": f"生成试卷失败: {str(e)}"}, status_code=500)


# ============================================================
# 简答题评分
# ============================================================

class GradeRequest(BaseModel):
    question: str
    user_answer: str
    correct_answer: str


@app.post("/api/exam/grade")
async def grade_endpoint(req: GradeRequest):
    """评分简答题"""
    result = grade_answer(req.question, req.user_answer, req.correct_answer)
    return result


# ============================================================
# 状态检查
# ============================================================

@app.get("/api/status")
async def status():
    doc = get_doc_data()
    return {
        "loaded": bool(doc["modules"]),
        "modules": len(doc["modules"]),
        "total_chars": len(doc["full_text"]),
        "module_names": [m["module"] for m in doc["modules"]]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
