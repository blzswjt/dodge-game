"""
文档处理器 - 解析 docx 文件并按模块/段落分块
"""
from docx import Document
from pathlib import Path
import re


def parse_docx(file_path: str) -> list[dict]:
    """
    解析 docx 文件，返回段落列表。
    每个段落: {"text": str, "style": str}
    """
    doc = Document(file_path)
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else "Normal"
        paragraphs.append({"text": text, "style": style})
    return paragraphs


def extract_modules(paragraphs: list[dict]) -> list[dict]:
    """
    将段落按"销售指导书"标题切分为模块。
    返回: [{"module": str, "content": str}]
    """
    modules = []
    current_module = "前言"
    current_lines = []

    module_keywords = [
        "智能经营解析", "合同/订单360", "合同订单360",
        "配置报价", "智能开票", "智能销售管理",
        "ISMP", "IBA", "CPQ", "IB&C"
    ]

    for para in paragraphs:
        text = para["text"]

        # 检测模块分隔 - "销售指导书" 通常出现在每个模块开头
        if "销售指导书" in text and len(text) < 20:
            if current_lines:
                modules.append({
                    "module": current_module,
                    "content": "\n".join(current_lines)
                })
            current_module = "未命名模块"
            current_lines = []
            continue

        # 检测产品名称标题
        for kw in module_keywords:
            if kw in text and len(text) < 30 and ("（" in text or "(" in text or kw == text):
                current_module = text
                break

        current_lines.append(text)

    if current_lines:
        modules.append({
            "module": current_module,
            "content": "\n".join(current_lines)
        })

    return modules


def merge_small_modules(modules: list[dict], min_length: int = 500) -> list[dict]:
    """合并过小的模块块"""
    if not modules:
        return modules
    merged = [modules[0]]
    for m in modules[1:]:
        if len(merged[-1]["content"]) < min_length:
            merged[-1]["content"] += "\n" + m["content"]
            merged[-1]["module"] += " & " + m["module"]
        else:
            merged.append(m)
    return merged


def load_document(file_path: str) -> dict:
    """
    加载文档，返回结构化内容。
    返回: {"full_text": str, "modules": [{"module", "content"}]}
    """
    path = Path(file_path)
    if not path.exists():
        return {"full_text": "", "modules": []}

    paragraphs = parse_docx(str(path))
    modules = extract_modules(paragraphs)
    modules = merge_small_modules(modules)

    full_text = "\n".join(p["text"] for p in paragraphs)

    return {
        "full_text": full_text,
        "modules": modules
    }


def find_relevant_chunks(query: str, modules: list[dict], top_k: int = 3) -> str:
    """
    根据查询关键词找到最相关的文档块。
    简单关键词匹配 + 加权评分。
    """
    if not modules:
        return ""

    query_lower = query.lower()
    scored = []

    for i, mod in enumerate(modules):
        content = mod["content"].lower()
        module_name = mod["module"].lower()

        # 计算关键词命中数
        score = 0
        query_words = re.findall(r'[\u4e00-\u9fa5a-zA-Z]+', query)
        for word in query_words:
            if len(word) < 2:
                continue
            count = content.count(word.lower())
            score += count
            # 模块名命中加权
            if word.lower() in module_name:
                score += 10

        scored.append((score, i, mod))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [s[2] for s in scored[:top_k] if s[0] > 0]

    if not selected:
        # 如果没有关键词命中，返回前 top_k 个模块
        selected = modules[:top_k]

    result = ""
    for mod in selected:
        result += f"\n【{mod['module']}】\n{mod['content']}\n"
    return result
