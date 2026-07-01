"""FastAPI 主服务 - 校园数据导航Agent API"""

import json
import os
from datetime import date
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config as cfg
from etl import DataPipeline
from agent_engine import CampusAgent, get_agent

# ──── 全局状态（懒初始化）────
data_pipeline: DataPipeline = None
_agent: CampusAgent = None
_initialized = False


def ensure_initialized():
    """懒初始化：首次调用时加载数据和Agent"""
    global data_pipeline, _agent, _initialized
    if _initialized:
        return
    print("[Server] 初始化数据管线...")
    data_pipeline = DataPipeline()
    data_pipeline.load_all()
    print("[Server] 初始化Agent引擎...")
    _agent = get_agent()
    _initialized = True
    print("[Server] 初始化完成")


def get_agent_safe():
    """获取Agent实例（确保已初始化）"""
    ensure_initialized()
    return _agent


# ──── Request/Response Models ────

class ChatRequest(BaseModel):
    user_id: str = "20240001"
    message: str


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class ChatResponse(BaseModel):
    answer: str
    user_id: str
    today_summary: dict = None
    dashboard: dict = None


# ──── FastAPI App ────

app = FastAPI(title="校园数据导航Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──── API 路由 ────

@app.get("/api/health")
def health():
    return {"status": "ok", "initialized": _initialized, "date": str(date.today())}


@app.get("/api/debug")
def debug():
    """调试接口：查看服务器状态"""
    if data_pipeline is None:
        return {"error": "data_pipeline is None"}
    return {
        "courses_count": len(data_pipeline.courses),
        "student_ids_sample": list(data_pipeline.courses["student_id"].unique())[:5],
        "student_id_dtype": str(data_pipeline.courses["student_id"].dtype),
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    agent = get_agent_safe()
    answer = agent.chat(req.user_id, req.message)
    
    # Build dashboard data for frontend
    today_wd = date.today().weekday()  # 0=Mon => 1=Mon for our system
    today_wd = today_wd + 1 if today_wd < 5 else None
    
    lib_data = data_pipeline.get_library_status()
    lib_seats = sum(r.get("available", 0) for r in lib_data) if isinstance(lib_data, list) else 0
    lib_total = sum(r.get("total_seats", 0) for r in lib_data) if isinstance(lib_data, list) else 0
    lib_rate = round((1 - lib_seats / lib_total) * 100, 1) if lib_total else 0
    
    # Find best area (lowest occupancy)
    lib_best_area = "无"
    if isinstance(lib_data, list) and lib_data:
        best = min(lib_data, key=lambda x: x.get("rate", 100))
        lib_best_area = f"{best['area']}（{best['rate']}%）"
    
    dashboard = {
        "libSeats": lib_seats,
        "libTotal": lib_total,
        "libRate": lib_rate,
        "libBestArea": lib_best_area,
        "libAreas": lib_data[:5] if isinstance(lib_data, list) else [],
        "competitions": len(data_pipeline.search_competitions()),
        "todayCourses": 0,
        "nextClass": "暂无课程",
    }
    
    if today_wd:
        courses = data_pipeline.get_student_courses(req.user_id, today_wd)
        dashboard["todayCourses"] = len(courses) if courses else 0
        if courses:
            dashboard["nextClass"] = courses[0].get("course_name", "")
    
    # Get consumption
    try:
        cons = data_pipeline.get_consumption_summary(req.user_id, 7)
        dashboard["weeklySpend"] = round(cons.get("total", 0))
        dashboard["dailyAvg"] = round(cons.get("daily_avg", 0))
    except:
        dashboard["weeklySpend"] = 0
        dashboard["dailyAvg"] = 0
    
    today_summary = {"libSeats": dashboard["libSeats"]}
    if today_wd and courses:
        today_summary["courses"] = courses
    dashboard["nextCompetition"] = "暂无"
    comps = data_pipeline.search_competitions()
    if comps:
        dashboard["nextCompetition"] = comps[0].get("name", "")
    
    return {"answer": answer, "user_id": req.user_id, "today_summary": today_summary, "dashboard": dashboard}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """真流式对话（SSE）"""
    agent = get_agent_safe()

    async def generate():
        try:
            for chunk in agent.chat_stream(req.user_id, req.message):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/session/{user_id}")
def clear_session(user_id: str):
    """清除用户会话历史"""
    agent = get_agent_safe()
    agent.session_mgr.clear(user_id)
    return {"status": "cleared", "user_id": user_id}


@app.get("/api/session/{user_id}/history")
def get_session_history(user_id: str):
    """获取会话历史（调试用）"""
    agent = get_agent_safe()
    history = agent.session_mgr.get_history(user_id)
    return {"user_id": user_id, "turns": len(history) // 2, "history": history}


# ──── RAG 语义检索专用 API ────

@app.post("/api/rag/search")
def rag_search(req: RAGSearchRequest):
    """RAG 语义检索：基于 ChromaDB 向量搜索知识库（不可用时降级为关键词匹配）"""
    agent = get_agent_safe()
    if agent.rag is not None:
        try:
            docs = agent.rag.search(req.query, top_k=req.top_k)
        except Exception:
            docs = agent._simple_search(req.query, top_k=req.top_k)
    else:
        docs = agent._simple_search(req.query, top_k=req.top_k)
    if not docs:
        return {"results": [], "query": req.query, "total": 0}
    return {
        "results": [
            {
                "text": d["text"],
                "title": d["metadata"].get("title", d["metadata"].get("source", "")),
                "source": d["metadata"].get("source", ""),
                "type": d["metadata"].get("type", ""),
                "date": d["metadata"].get("date", ""),
                "score": round(d["score"], 4),
            }
            for d in docs
        ],
        "query": req.query,
        "total": len(docs),
    }


@app.post("/api/rag/ask")
def rag_ask(req: ChatRequest):
    """RAG 增强问答：检索知识库 + LLM 生成答案"""
    agent = get_agent_safe()
    answer = agent._exec_rag({"question": req.message})
    return {"answer": answer}


# ──── 仪表盘专用API（不走LLM，直接查CSV）────


@app.get("/api/dashboard/{student_id}")
def api_dashboard(student_id: str):
    """仪表盘聚合数据：课表+消费+图书馆+通知+竞赛 — 一次查询，不经过LLM"""
    ensure_initialized()
    today = date.today()
    today_wd = today.weekday()  # 0=Mon
    display_wd = today_wd + 1 if today_wd < 5 else None

    # 今日课表
    courses_today = []
    if display_wd:
        courses_today = data_pipeline.get_student_courses(student_id, display_wd)

    # 本周全部课表
    courses_week = []
    weekdays = [1, 2, 3, 4, 5]
    for wd in weekdays:
        courses_week.extend(data_pipeline.get_student_courses(student_id, wd))

    # 消费统计
    try:
        cons = data_pipeline.get_consumption_summary(student_id, 30)
        month_spend = round(cons.get("total", 0))
        daily_avg = round(cons.get("daily_avg", 0))
    except:
        month_spend = 0
        daily_avg = 0

    # 图书馆
    lib_data = data_pipeline.get_library_status()
    lib_total = sum(r.get("total_seats", 0) for r in lib_data) if isinstance(lib_data, list) else 0
    lib_used = sum(r.get("used", 0) for r in lib_data) if isinstance(lib_data, list) else 0
    lib_available = lib_total - lib_used
    lib_rate = round(lib_used / lib_total * 100, 1) if lib_total else 0

    # 通知
    notices = data_pipeline.get_recent_notices(10)
    # 竞赛
    competitions = data_pipeline.search_competitions()

    return {
        "student_id": student_id,
        "date": str(today),
        "weekday": display_wd,
        "courses_today": courses_today,
        "courses_week": courses_week,
        "courses_today_count": len(courses_today),
        "courses_week_count": len(courses_week),
        "consumption": {
            "month_total": month_spend,
            "daily_avg": daily_avg,
        },
        "library": {
            "total": lib_total,
            "used": lib_used,
            "available": lib_available,
            "rate": lib_rate,
            "zones": lib_data if isinstance(lib_data, list) else [],
        },
        "notices": notices[:6] if notices else [],
        "competitions": competitions[:6] if competitions else [],
    }


# ──── 数据API（给前端可视化用）────

@app.get("/api/courses/{student_id}")
def api_courses(student_id: str, weekday: int = None):
    ensure_initialized()
    return data_pipeline.get_student_courses(student_id, weekday)


@app.get("/api/consumption/{student_id}")
def api_consumption(student_id: str, days: int = 30):
    ensure_initialized()
    return data_pipeline.get_consumption_summary(student_id, days)


@app.get("/api/library")
def api_library():
    ensure_initialized()
    return data_pipeline.get_library_status()


@app.get("/api/classrooms/empty")
def api_empty_classrooms(weekday: int, period: int):
    ensure_initialized()
    return data_pipeline.get_empty_classrooms(weekday, period)


@app.get("/api/notices")
def api_notices(num: int = 10, type: str = None):
    ensure_initialized()
    return data_pipeline.get_recent_notices(num, type)


@app.get("/api/competitions")
def api_competitions(keyword: str = None):
    ensure_initialized()
    return data_pipeline.search_competitions(keyword)


# ──── 静态文件（前端）────

frontend_dir = cfg.BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def root():
        return FileResponse(str(frontend_dir / "index.html"))


# ──── 启动 ────

if __name__ == "__main__":
    import uvicorn
    # 预初始化（可选，设为 False 则懒加载）
    preload = os.getenv("PRELOAD", "false").lower() == "true"
    if preload:
        ensure_initialized()
    uvicorn.run(app, host=cfg.HOST, port=cfg.PORT, log_level="info")
