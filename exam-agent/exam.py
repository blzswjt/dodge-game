"""
考试生成与问答模块
"""
import json
import re
from llm import chat, chat_stream
from doc_processor import find_relevant_chunks


# ============================================================
# 智能问答
# ============================================================

def answer_question(question: str, modules: list[dict]) -> str:
    """
    基于文档内容回答用户问题。
    使用关键词检索找到相关段落，然后调用 LLM 生成答案。
    """
    relevant = find_relevant_chunks(question, modules, top_k=3)

    # 限制上下文长度，避免超出 token 限制
    if len(relevant) > 12000:
        relevant = relevant[:12000] + "\n...(内容已截断)"

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个专业的产品知识问答助手。请根据以下产品介绍文档内容回答用户的问题。\n"
                "要求：\n"
                "1. 只基于提供的文档内容回答，不要编造信息\n"
                "2. 回答要准确、简洁、有条理\n"
                "3. 如果文档中没有相关内容，请说明\n"
                "4. 回答时可以用 markdown 格式\n\n"
                f"以下是相关文档内容：\n{relevant}"
            )
        },
        {"role": "user", "content": question}
    ]

    return chat(messages, temperature=0.3)


def answer_question_stream(question: str, modules: list[dict]):
    """流式问答，逐步返回答案片段"""
    relevant = find_relevant_chunks(question, modules, top_k=3)

    if len(relevant) > 12000:
        relevant = relevant[:12000] + "\n...(内容已截断)"

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个专业的产品知识问答助手。请根据以下产品介绍文档内容回答用户的问题。\n"
                "要求：\n"
                "1. 只基于提供的文档内容回答，不要编造信息\n"
                "2. 回答要准确、简洁、有条理\n"
                "3. 如果文档中没有相关内容，请说明\n"
                "4. 回答时可以用 markdown 格式\n\n"
                f"以下是相关文档内容：\n{relevant}"
            )
        },
        {"role": "user", "content": question}
    ]

    yield from chat_stream(messages, temperature=0.3)


# ============================================================
# 考试生成
# ============================================================

def _build_exam_prompt(content: str, question_type: str, count: int) -> str:
    """构建考试题目生成的 prompt"""
    type_desc = {
        "single": f"生成 {count} 道单选题（每题4个选项A/B/C/D，只有1个正确答案）",
        "multiple": f"生成 {count} 道多选题（每题4个选项A/B/C/D，有2-4个正确答案）",
        "judge": f"生成 {count} 道判断题（只有对/错两个答案）",
        "short": f"生成 {count} 道简答题（需要给出参考答案）",
    }

    type_format = {
        "single": '''[
  {
    "question": "题目内容",
    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    "answer": "A",
    "explanation": "答案解析"
  }
]''',
        "multiple": '''[
  {
    "question": "题目内容",
    "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    "answer": ["A", "B"],
    "explanation": "答案解析"
  }
]''',
        "judge": '''[
  {
    "question": "题目内容",
    "answer": true,
    "explanation": "答案解析"
  }
]''',
        "short": '''[
  {
    "question": "题目内容",
    "answer": "参考答案"
  }
]''',
    }

    return f"""请根据以下产品介绍文档内容，{type_desc.get(question_type, "")}。

要求：
1. 题目必须基于文档内容，不能编造
2. 题目要有考察意义，覆盖文档中的关键知识点
3. 选项要合理，干扰项要有迷惑性
4. 解析要简要说明为什么这个答案是对的
5. 严格输出JSON格式，不要输出任何其他内容

输出格式（必须是合法JSON）：
{type_format.get(question_type, "")}

文档内容：
{content}
"""


def _extract_json(text: str) -> list:
    """从 LLM 回复中提取 JSON 数组"""
    # 尝试直接解析
    text = text.strip()
    # 移除可能的 markdown 代码块标记
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    # 尝试找到 JSON 数组
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def generate_exam(modules: list[dict]) -> dict:
    """
    生成完整试卷：10单选 + 10多选 + 10判断 + 2简答
    每种题型从不同模块内容生成，确保覆盖面。
    """
    # 将所有模块内容拼接（限制总长度）
    all_content = "\n\n".join(
        f"【{m['module']}】\n{m['content']}" for m in modules
    )

    # 如果内容过长，截取前面部分（LLM 上下文有限）
    max_content_len = 10000
    if len(all_content) > max_content_len:
        all_content = all_content[:max_content_len]

    result = {
        "single": [],
        "multiple": [],
        "judge": [],
        "short": []
    }

    # 生成各题型
    for q_type, count in [("single", 10), ("multiple", 10), ("judge", 10), ("short", 2)]:
        prompt = _build_exam_prompt(all_content, q_type, count)
        messages = [{"role": "user", "content": prompt}]

        try:
            response = chat(messages, temperature=0.7)
            questions = _extract_json(response)
            result[q_type] = questions if questions else []
        except Exception as e:
            print(f"生成 {q_type} 题目失败: {e}")
            result[q_type] = []

    return result


def generate_exam_by_module(modules: list[dict]) -> dict:
    """
    分模块生成试卷，确保题目来自不同模块。
    每个模块生成若干题，然后汇总。
    """
    # 分配各模块的题目数量
    num_modules = len(modules)
    if num_modules == 0:
        return {"single": [], "multiple": [], "judge": [], "short": []}

    # 单选题：每个模块生成 10/num_modules 道
    single_per_module = max(1, 10 // num_modules)
    multiple_per_module = max(1, 10 // num_modules)
    judge_per_module = max(1, 10 // num_modules)

    all_single = []
    all_multiple = []
    all_judge = []
    all_short = []

    for mod in modules:
        content = mod["content"]
        if len(content) > 4000:
            content = content[:4000]

        # 单选
        prompt = _build_exam_prompt(content, "single", single_per_module)
        try:
            qs = _extract_json(chat([{"role": "user", "content": prompt}], temperature=0.7))
            for q in qs:
                q["source"] = mod["module"]
            all_single.extend(qs)
        except:
            pass

        # 多选
        prompt = _build_exam_prompt(content, "multiple", multiple_per_module)
        try:
            qs = _extract_json(chat([{"role": "user", "content": prompt}], temperature=0.7))
            for q in qs:
                q["source"] = mod["module"]
            all_multiple.extend(qs)
        except:
            pass

        # 判断
        prompt = _build_exam_prompt(content, "judge", judge_per_module)
        try:
            qs = _extract_json(chat([{"role": "user", "content": prompt}], temperature=0.7))
            for q in qs:
                q["source"] = mod["module"]
            all_judge.extend(qs)
        except:
            pass

    # 简答题从全部内容生成
    all_content = "\n\n".join(m["content"] for m in modules)
    if len(all_content) > 8000:
        all_content = all_content[:8000]
    prompt = _build_exam_prompt(all_content, "short", 2)
    try:
        all_short = _extract_json(chat([{"role": "user", "content": prompt}], temperature=0.7))
    except:
        all_short = []

    # 截取所需数量
    return {
        "single": all_single[:10],
        "multiple": all_multiple[:10],
        "judge": all_judge[:10],
        "short": all_short[:2]
    }


# ============================================================
# 答案评分
# ============================================================

def grade_answer(question: str, user_answer: str, correct_answer: str) -> dict:
    """
    评分简答题答案。
    """
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个考官，请评判学生的简答题答案。\n"
                "根据参考答案，给出评分（0-100分）和评语。\n"
                "输出JSON格式：{\"score\": 数字, \"comment\": \"评语\"}"
            )
        },
        {
            "role": "user",
            "content": (
                f"题目：{question}\n"
                f"学生答案：{user_answer}\n"
                f"参考答案：{correct_answer}\n"
                "请评分："
            )
        }
    ]

    response = chat(messages, temperature=0.2)
    try:
        result = _extract_json(response)
        if isinstance(result, list) and result:
            return result[0]
        elif isinstance(result, dict):
            return result
    except:
        pass

    return {"score": 0, "comment": "评分失败"}
