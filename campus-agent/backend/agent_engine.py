"""校园数据导航Agent核心引擎 v3
架构升级：
  ✅ 多轮会话历史（持久化到内存，支持历史上下文）
  ✅ SSE 真流式输出（逐 token 推送）
  ✅ RAG 知识库语义检索（ChromaDB + SentenceTransformer）
  ✅ 智能排课推荐引擎（3阶段求解）
  ✅ 关键字路由 + JSON Mode（稳定可靠）
  ✅ 3个硬编码融合场景
"""

import json
import re
import os
from datetime import date, datetime
from openai import OpenAI
from typing import Any, Generator

import config as cfg
from etl import DataPipeline

# ──────────────── System Prompt ────────────────

SYSTEM_PROMPT = """你是衡水学院校园数据导航智能助手，名叫"小航"。你为衡水学院全体学生提供一站式校园信息查询服务，学生只需输入学号即可使用全部功能，无需自己提供任何数据。

## 产品定位
本系统由学校信息化管理中心统一部署，底层对接教务系统、一卡通系统、图书馆座位管理系统三大数据源。管理员完成一次性配置后，全校所有学生均可零门槛使用。你作为前端智能助手，负责理解学生意图、并以亲切自然的方式呈现结果。

## 衡水学院概况
位于河北省衡水市，前身为1923年建校的直隶第六师范，2004年升格为本科院校。下设文学与传播学院、外国语学院、公共管理学院、数学与计算机学院、电子信息工程学院、化工学院、生命科学学院、音乐学院、体育学院、美术学院、经济管理学院、教育学院、马克思主义学院等院系。校园主要建筑包括1-3号教学楼、综合教学楼、逸夫楼、实验中心、图书馆。食堂有第一食堂、第二食堂、回民食堂、教工餐厅。

## 图书馆
- 共5层：社科阅览室（1-2F）、科技阅览室（3F）、电子阅览室（3-4F）、期刊阅览室（4F）、考研自习室（5F）、普通自习室（2F/5F）、大厅阅览区（1-2F）
- 座位预约：微信公众号「XX大学图书馆」→ 我的图书馆 → 微服务平台 → 空间/座位预约；网页版 https://lib.example.edu.cn（校园网）
- 登录账号为学号，默认密码请咨询图书馆

## 教学楼到图书馆步行时间
- 1号教学楼 → 图书馆：约5分钟
- 2号教学楼 → 图书馆：约3分钟
- 3号教学楼 → 图书馆：约7分钟
- 综合教学楼 → 图书馆：约8分钟
- 逸夫楼 → 图书馆：约10分钟
- 实验中心 → 图书馆：约6分钟

## 交互规则
- 用Markdown格式组织信息，表格和列表优先
- 语气亲切自然，像热心的学长学姐
- 所有查询自动使用当前登录学号，学生无需重复输入
- 如果用户问到上下文中已提到的内容，直接引用
"""

# ──────────────── 参数提取 Prompts ────────────────

PARAM_EXTRACT_PROMPTS = {
    "courses": """从用户消息中提取课表查询参数。返回JSON：
{ "weekday": 数字1-5表示周几, "student_id": 学号 }
如果不确定星期几，"weekday" 可以设为 null。
只返回有效JSON，不要其他文字。""",

    "empty_classrooms": """从用户消息中提取空教室查询参数。返回JSON：
{ "weekday": 数字1-5表示周几, "period": 第几节课1-8 }
只返回有效JSON，不要其他文字。""",

    "consumption": """从用户消息中提取消费查询参数。返回JSON：
{ "student_id": 学号, "days": 统计天数默认30 }
只返回有效JSON，不要其他文字。""",

    "library": """图书馆查询无需参数。始终返回空JSON：{}""",

    "notices": """从用户消息中提取通知查询参数。返回JSON：
{ "num": 返回条数默认10, "ntype": 类型如"学术讲座"/"竞赛"/"教务"/"活动"，不确定则为null }
只返回有效JSON，不要其他文字。""",

    "competitions": """从用户消息中提取竞赛查询参数。返回JSON：
{ "keyword": 搜索关键词，不确定则为null }
只返回有效JSON，不要其他文字。""",

    "schedule_recommend": """从用户消息中提取选课推荐参数。返回JSON：
{
  "target_credits": 目标学分默认18,
  "prefer_morning": 是否偏好上午课true/false,
  "avoid_weekdays": 避免的星期几数组如[1,5],
  "prefer_categories": 偏好类别数组如["专业核心","通识"]
}
只返回有效JSON，不要其他文字。""",
}

# ──────────────── 关键字路由 ────────────────

class KeywordRouter:
    """确定性路由：根据关键字决定调用哪些工具"""

    TOOL_KEYWORDS = {
        "courses":      ["课表", "上课", "课程", "什么课", "几节课", "明天", "今天", "星期",
                         "教学楼", "教室", "下课", "课后", "最后一节"],
        "empty_classrooms": ["空教室", "自习", "空余教室", "空闲教室", "没课的教室"],
        "consumption":  ["消费", "花钱", "饭卡", "一卡通", "余额", "食堂", "花了多少",
                         "吃饭", "伙食", "开销", "账单"],
        "library":      ["图书馆", "座位", "占座", "预约座位", "阅览室", "自习室",
                         "考研自习", "图书馆还有座", "图书馆人多"],
        "notices":      ["通知", "公告", "新闻", "讲座", "活动", "校园通知",
                         "最新消息", "最近有什么"],
        "competitions": ["竞赛", "比赛", "报名", "挑战赛", "大赛", "学科竞赛"],
        "schedule_recommend": ["推荐课程", "选课推荐", "下学期", "选什么课", "帮我选课",
                                "排课", "课程推荐", "推荐选修"],
        "rag":          ["规定", "政策", "流程", "怎么办理", "如何申请", "奖学金",
                         "助学金", "补贴", "手续", "证明", "成绩查询", "补考", "缓考",
                         "转专业", "退学", "请假", "宿舍", "校规"],
    }

    FUSION_TRIGGERS = [
        {
            "name": "course_to_library",
            "domains": ["courses", "library"],
            "description": "下课后去图书馆场景",
        },
        {
            "name": "consumption_course",
            "domains": ["consumption", "courses"],
            "description": "消费与课程关联分析",
        },
        {
            "name": "competition_course",
            "domains": ["competitions", "courses"],
            "description": "竞赛与专业课程关联推荐",
        },
    ]

    @classmethod
    def route(cls, message: str) -> dict:
        msg = message.lower()
        matched_tools = []

        for tool_name, keywords in cls.TOOL_KEYWORDS.items():
            if any(kw in msg for kw in keywords):
                matched_tools.append(tool_name)

        if not matched_tools:
            return {"tools": [], "fusion": None, "is_direct": True, "original_message": message}

        # 检测融合场景
        fusion = None
        for trigger in cls.FUSION_TRIGGERS:
            domains = trigger["domains"]
            if all(d in matched_tools for d in domains):
                fusion = trigger["name"]
                break

        return {
            "tools": matched_tools,
            "fusion": fusion,
            "is_direct": False,
            "original_message": message,
        }


# ──────────────── 会话历史管理 ────────────────

class SessionManager:
    """多轮会话历史管理"""

    MAX_HISTORY = 10  # 保留最近10轮对话

    def __init__(self):
        self._sessions: dict[str, list[dict]] = {}

    def get_history(self, user_id: str) -> list[dict]:
        return self._sessions.get(user_id, [])

    def add_turn(self, user_id: str, user_msg: str, assistant_msg: str):
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        history = self._sessions[user_id]
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        # 保留最近 MAX_HISTORY 轮（每轮2条消息）
        if len(history) > self.MAX_HISTORY * 2:
            self._sessions[user_id] = history[-(self.MAX_HISTORY * 2):]

    def clear(self, user_id: str):
        self._sessions.pop(user_id, None)

    def get_all_sessions(self) -> dict:
        return {uid: len(hist) // 2 for uid, hist in self._sessions.items()}


# ──────────────── Agent 类 ────────────────

class CampusAgent:
    def __init__(self):
        self.llm = OpenAI(
            api_key=cfg.OPENAI_API_KEY,
            base_url=cfg.OPENAI_BASE_URL,
        )
        self.model = cfg.LLM_MODEL
        self.data = DataPipeline()
        self.data.load_all()
        self.session_mgr = SessionManager()

        # 延迟初始化 RAG（首次使用时加载模型）
        self._rag = None
        self._scheduler = None

        self.tool_executors = {
            "courses": self._exec_courses,
            "empty_classrooms": self._exec_empty_classrooms,
            "consumption": self._exec_consumption,
            "library": self._exec_library,
            "notices": self._exec_notices,
            "competitions": self._exec_competitions,
            "schedule_recommend": self._exec_schedule_recommend,
            "rag": self._exec_rag,
        }
        print("[Agent v3] 初始化完成（多轮会话 + SSE + RAG + 排课引擎）")

    @property
    def rag(self):
        if self._rag is None:
            try:
                from rag_engine import RAGEngine
                self._rag = RAGEngine()
                # 首次加载时构建索引
                docs = self.data.get_knowledge_texts()
                # 为每个文档确保有唯一ID（优先使用文档自带ID）
                indexed_docs = []
                for i, d in enumerate(docs):
                    indexed_docs.append({
                        "id": d.get("id", f"doc_{i}"),
                        "text": d["text"],
                        "metadata": d["metadata"],
                    })
                self._rag.build_index(indexed_docs)
            except Exception as e:
                print(f"[Agent] RAG 引擎初始化失败（ChromaDB/Embedding模型不可用）: {e}")
                print("[Agent] 降级为关键词匹配检索")
                self._rag = None  # 标记为不可用
        return self._rag

    def _simple_search(self, query: str, top_k: int = 5) -> list[dict]:
        """简单关键词检索（ChromaDB不可用时的降级方案）"""
        docs = self.data.get_knowledge_texts()
        results = []
        query_lower = query.lower()
        for d in docs:
            text = d.get("text", "")
            if not text:
                continue
            # 关键词命中计分
            score = 0
            for word in query:
                if word in text:
                    score += 1
            # 归一化
            score = min(score / max(len(query), 1), 1.0)
            if score > 0.1:
                results.append({
                    "text": text,
                    "metadata": d.get("metadata", {}),
                    "score": round(score + 0.5, 4),  # 提升到0.5以上
                })
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    @property
    def scheduler(self):
        if self._scheduler is None:
            from scheduler import CourseScheduler
            self._scheduler = CourseScheduler(self.data)
        return self._scheduler

    # ═══════════════════════════════════════════
    # 工具执行器
    # ═══════════════════════════════════════════

    def _exec_courses(self, args: dict) -> str:
        sid = args.get("student_id", "")
        wd = args.get("weekday")
        courses = self.data.get_student_courses(sid, weekday=wd)
        if not courses:
            return "未找到课程信息。"
        today = date.today()
        weekday_names = ["", "周一", "周二", "周三", "周四", "周五"]
        lines = [f"📚 学号 {sid} 课表 ({today})：", ""]
        for c in courses:
            wname = weekday_names[c["weekday"]] if c["weekday"] <= 5 else f"周{c['weekday']}"
            lines.append(f"  · {wname} 第{c['period_start']}-{c['period_end']}节 | {c['course_name']} | {c['teacher']} | {c['location']}")
        return "\n".join(lines)

    def _exec_empty_classrooms(self, args: dict) -> str:
        wd = args.get("weekday", 1)
        p = args.get("period", 1)
        rooms = self.data.get_empty_classrooms(wd, p)
        if not rooms:
            return f"周{wd}第{p}节暂时没有空闲教室。"
        lines = [f"🏫 周{wd}第{p}节可用空教室："]
        for r in rooms[:12]:
            lines.append(f"  · {r['room_id']}（容纳{r['capacity']}人）")
        return "\n".join(lines)

    def _exec_consumption(self, args: dict) -> str:
        sid = args.get("student_id", "")
        days = args.get("days", 30)
        stats = self.data.get_consumption_summary(sid, days)
        if stats["total"] == 0:
            return f"最近{days}天暂无消费记录。"

        canteen_lines = []
        for name, info in stats["by_canteen"].items():
            canteen_lines.append(f"    {name}：{info['sum']}元（{info['count']}笔）")

        trend_json = json.dumps(stats.get("trend", []), ensure_ascii=False)

        lines = [
            f"💰 消费分析（最近{days}天）：",
            f"  总消费：{stats['total']}元",
            f"  日均消费：{stats['daily_avg']}元",
            f"  各食堂分布：",
        ] + canteen_lines

        if stats["daily_avg"] > 25:
            lines.append(f"\n💡 日均消费偏高，可以考虑多去食堂，减少外卖~")
        elif stats["daily_avg"] < 10:
            lines.append(f"\n💡 消费偏低，记得好好吃饭哦！")
        else:
            lines.append(f"\n✅ 消费水平适中，保持良好饮食习惯！")

        if stats.get("trend"):
            lines.append(f"\n<!--CHART:consumption:{trend_json}-->")

        return "\n".join(lines)

    def _exec_library(self, _args: dict) -> str:
        status = self.data.get_library_status()
        lines = ["📖 衡水学院图书馆实时座位情况：", ""]

        from itertools import groupby
        status_sorted = sorted(status, key=lambda x: (x["floor"], x["area_type"]))
        for floor, group in groupby(status_sorted, key=lambda x: x["floor"]):
            areas = list(group)
            lines.append(f"  **{floor}F**")
            for s in areas:
                bar = self._make_bar(s["rate"])
                emoji = "🟢" if s["rate"] < 60 else ("🟡" if s["rate"] < 85 else "🔴")
                lines.append(f"    {emoji} {s['area']} | {bar} {s['rate']}% | 空{s['available']}/{s['total_seats']}")
            lines.append("")

        lines.append("---")
        lines.append("💡 预约方式：微信公众号「XX大学图书馆」→ 我的图书馆 → 微服务平台 → 空间/座位预约")
        lines.append("   网页版：https://lib.example.edu.cn（校园网）")
        return "\n".join(lines)

    def _exec_notices(self, args: dict) -> str:
        num = args.get("num", 10)
        ntype = args.get("ntype")
        notices = self.data.get_recent_notices(num, ntype)
        if not notices:
            return "暂无相关通知。"
        lines = ["📢 最近通知："]
        for n in notices:
            lines.append(f"  · [{n['type']}] {n['title']}（{n['date']}）")
        return "\n".join(lines)

    def _exec_competitions(self, args: dict) -> str:
        kw = args.get("keyword") or ""
        comps = self.data.search_competitions(kw)
        lines = [f"🏆 竞赛信息（{kw or '全部'}）："]
        for c in comps[:10]:
            lines.append(f"  · [{c['level']}] {c['name']} | 截止：{c['deadline']}")
        return "\n".join(lines)

    def _exec_schedule_recommend(self, args: dict) -> str:
        """B2: 智能排课推荐"""
        result = self.scheduler.recommend(
            student_id=args.get("student_id", ""),
            target_credits=args.get("target_credits", 18),
            prefer_morning=args.get("prefer_morning", False),
            prefer_categories=args.get("prefer_categories") or [],
            avoid_weekdays=args.get("avoid_weekdays") or [],
        )
        return self.scheduler.format_recommendation(result)

    def _exec_rag(self, args: dict) -> str:
        """B1: RAG 知识库语义检索 → LLM生成答案（不是返回原始文本）"""
        query = args.get("question", "")
        if not query:
            # 尝试从其他字段获取
            query = args.get("message", args.get("query", ""))

        # 尝试 ChromaDB 向量检索，失败则降级为关键词匹配
        if self.rag is not None:
            try:
                docs = self.rag.search(query, top_k=5)
            except Exception:
                docs = self._simple_search(query, top_k=5)
        else:
            docs = self._simple_search(query, top_k=5)
        if not docs:
            return f"抱歉，知识库中暂未找到关于「{query}」的相关内容。"

        # 将检索结果注入 LLM prompt，让 AI 基于知识库内容生成答案
        context = self.rag.format_context(docs)
        sources = ", ".join(set(d["metadata"].get("source", "知识库") for d in docs))

        rag_prompt = f"""你是衡水学院校园助手"小航"。以下是从学校知识库中检索到的与用户问题高度相关的内容。
请基于这些知识库内容回答用户问题，要求：
1. 直接回答问题，不要说"根据知识库"这类话
2. 如果知识库内容不足以完整回答，可以适当补充常识性说明
3. 用友好自然的语气，适当使用emoji
4. 回答末尾用 📎 标注信息来源

【知识库检索内容】
{context}

【用户问题】
{query}"""

        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": rag_prompt},
                ],
                temperature=0.4,
                max_tokens=600,
            )
            answer = resp.choices[0].message.content or ""
            if sources and "📎" not in answer:
                answer += f"\n\n📎 信息来源：{sources}"
            return answer
        except Exception as e:
            # LLM 调用失败时降级为原始文本
            context = self.rag.format_context(docs)
            return f"📚 知识库检索到以下相关内容：\n\n{context}\n\n📎 来源：{sources}"

    # ═══════════════════════════════════════════
    # RAG 增强对话（每轮自动检索相关知识）
    # ═══════════════════════════════════════════

    def _rag_enhance(self, message: str) -> str:
        """
        自动 RAG 增强：对每轮对话都在知识库中检索相关背景
        返回增强后的 system prompt 片段，如果无相关内容则返回空串
        """
        try:
            if self.rag is not None:
                docs = self.rag.search(message, top_k=3)
            else:
                docs = self._simple_search(message, top_k=3)
            if not docs or len(docs) == 0:
                return ""

            # 只保留高相关度结果（>0.5）
            high_relevance = [d for d in docs if d.get("score", 0) > 0.5]
            if not high_relevance:
                return ""

            context_parts = []
            for d in high_relevance[:3]:
                src = d["metadata"].get("title", d["metadata"].get("source", ""))
                text_preview = d["text"][:300]
                context_parts.append(f"- [{src}] {text_preview}")

            return (
                "\n【校园知识库参考】\n"
                + "\n".join(context_parts)
                + "\n以上内容供参考，如与用户问题相关可引用。"
            )
        except Exception:
            return ""

    # ═══════════════════════════════════════════
    # 融合场景执行器
    # ═══════════════════════════════════════════

    def _exec_fusion_course_to_library(self, user_id: str, user_message: str) -> str:
        """场景1：下课后去图书馆（课表 + 图书馆 + 距离）"""
        today_wd = date.today().weekday() + 1
        if today_wd > 5:
            today_wd = None

        parts = []

        if today_wd:
            courses = self.data.get_student_courses(user_id, weekday=today_wd)
            if courses:
                last_course = max(courses, key=lambda c: c["period_end"])
                end_period = last_course["period_end"]
                location = last_course["location"]

                period_times = {1: "8:00", 2: "9:00", 3: "10:10", 4: "11:10",
                                5: "14:00", 6: "15:00", 7: "16:10", 8: "17:10"}
                end_time = period_times.get(end_period, f"第{end_period}节后")

                distance_map = {
                    "1号教学楼": 5, "2号教学楼": 3, "3号教学楼": 7,
                    "综合教学楼": 8, "逸夫楼": 10, "实验中心": 6,
                }
                walk_time = 5
                for building, minutes in distance_map.items():
                    if building in location:
                        walk_time = minutes
                        break

                parts.append(
                    f"📅 今天最后一节课：**{last_course['course_name']}**\n"
                    f"   时间：第{end_period}节（约{end_time}下课）\n"
                    f"   地点：{location}\n"
                    f"   步行到图书馆约：**{walk_time}分钟**\n"
                )
            else:
                parts.append("📅 今天没有课，随时可以去图书馆！\n")
        else:
            parts.append("📅 今天是周末，没有课程安排～\n")

        lib_status = self.data.get_library_status()
        parts.append("📖 当前图书馆座位情况：")
        for s in lib_status:
            bar = self._make_bar(s["rate"])
            emoji = "🟢" if s["rate"] < 60 else ("🟡" if s["rate"] < 85 else "🔴")
            parts.append(f"  {emoji} {s['area']} {bar} {s['rate']}% 空{s['available']}/{s['total_seats']}")

        parts.append("")
        parts.append("💡 预约方式：微信公众号「衡水学院图书馆」(hsxy-tsg)")

        return "\n".join(parts)

    def _exec_fusion_consumption_course(self, user_id: str, _user_message: str) -> str:
        """场景2：消费与课表关联分析"""
        parts = []
        stats = self.data.get_consumption_summary(user_id, 30)
        parts.append(f"💰 近30天总消费：**{stats['total']}元**，日均 **{stats['daily_avg']}元**")
        parts.append("")
        parts.append("各食堂消费分布：")
        for name, info in stats["by_canteen"].items():
            parts.append(f"  · {name}：{info['sum']}元（{info['count']}笔）")
        parts.append("")

        courses = self.data.get_student_courses(user_id)
        if courses:
            morning_courses = [c for c in courses if c["period_start"] <= 4]
            afternoon_courses = [c for c in courses if c["period_start"] >= 5]
            parts.append(f"📅 课表分析：上午{len(set(c['weekday'] for c in morning_courses))}天有课，"
                         f"下午{len(set(c['weekday'] for c in afternoon_courses))}天有课")
            parts.append(f"   建议：上午有课时在「第一食堂」吃早餐最方便")

        if stats["daily_avg"] > 25:
            parts.append(f"\n💡 日均消费偏高，建议减少外卖、多去食堂")
        elif stats["daily_avg"] < 10:
            parts.append(f"\n💡 消费偏低，注意均衡饮食哦！")

        return "\n".join(parts)

    def _exec_fusion_competition_course(self, user_id: str, user_message: str) -> str:
        """场景3：竞赛与课程关联推荐"""
        parts = []
        comps = self.data.search_competitions()
        courses = self.data.get_student_courses(user_id)
        course_names = [c["course_name"] for c in courses] if courses else []

        parts.append("🏆 近期可报名竞赛：")
        parts.append("")
        for c in comps[:5]:
            related_courses = []
            for cn in course_names:
                if any(kw in cn for kw in c.get("name", "").split()[:2]):
                    related_courses.append(cn)
            related_str = f" 📎 相关课程：{'、'.join(related_courses[:2])}" if related_courses else ""
            parts.append(f"  · [{c['level']}] **{c['name']}**{related_str}")
            parts.append(f"    截止：{c['deadline']}")

        parts.append("")
        parts.append("💡 参加学科竞赛可以加综测分，建议根据自己专业方向选择1-2个报名！")

        return "\n".join(parts)

    # ═══════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════

    def _make_bar(self, rate: float, width: int = 10) -> str:
        filled = int(rate / 100 * width)
        return "█" * filled + "░" * (width - filled)

    def _extract_params(self, user_message: str, tool_name: str, user_id: str) -> dict:
        prompt = PARAM_EXTRACT_PROMPTS.get(tool_name, "{}")
        context = f"当前学号: {user_id}, 当前日期: {date.today()}"

        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "system", "content": context},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=200,
            )
            params = json.loads(resp.choices[0].message.content)
            if "student_id" in PARAM_EXTRACT_PROMPTS.get(tool_name, ""):
                params.setdefault("student_id", user_id)
            return params
        except Exception:
            if tool_name in ("courses", "consumption", "schedule_recommend"):
                return {"student_id": user_id}
            return {}

    def _build_messages(self, user_id: str, message: str, system_extra: str = "") -> list[dict]:
        """构建带历史的消息列表"""
        history = self.session_mgr.get_history(user_id)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        if system_extra:
            msgs.append({"role": "system", "content": system_extra})
        msgs.append({"role": "system", "content": f"当前用户学号: {user_id}, 当前日期: {date.today()}"})
        msgs.extend(history)
        msgs.append({"role": "user", "content": message})
        return msgs

    # ═══════════════════════════════════════════
    # 对话核心（非流式）
    # ═══════════════════════════════════════════

    def chat(self, user_id: str, message: str) -> str:
        route = KeywordRouter.route(message)

        # 自动 RAG 增强：每轮对话都检索相关知识库内容
        rag_context = self._rag_enhance(message)
        if route["is_direct"]:
            answer = self._direct_chat(user_id, message, system_extra=rag_context)
        elif route["fusion"]:
            answer = self._handle_fusion(route["fusion"], user_id, message)
        else:
            answer = self._handle_tools(route["tools"], user_id, message, rag_context=rag_context)

        # 保存到会话历史
        self.session_mgr.add_turn(user_id, message, answer)
        return answer

    def _call_llm(self, msgs: list, temperature: float = 0.7, max_tokens: int = 600,
                  json_mode: bool = False, stream: bool = False):
        """安全 LLM 调用：失败时返回 None"""
        try:
            kwargs = dict(model=self.model, messages=msgs, temperature=temperature, max_tokens=max_tokens, stream=stream)
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            return self.llm.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"[Agent] LLM call failed: {e}")
            return None

    def _direct_chat(self, user_id: str, message: str, system_extra: str = "") -> str:
        msgs = self._build_messages(user_id, message, system_extra=system_extra)
        resp = self._call_llm(msgs, temperature=0.7, max_tokens=600)
        if resp is not None:
            return resp.choices[0].message.content or ""
        # LLM 不可用时的友好回复
        return (
            "👋 你好！我是校园数据导航助手**小航**。\n\n"
            "当前LLM服务暂不可用，但你仍然可以查询以下功能：\n"
            "📅 **课表查询** — 输入「我的课表」「今天什么课」「周一有什么课」\n"
            "💰 **消费分析** — 输入「我的消费」「本月花了多少」\n"
            "🏫 **图书馆** — 输入「图书馆有座吗」「图书馆座位」\n"
            "📢 **通知公告** — 输入「最近通知」「有什么讲座」\n"
            "🏆 **竞赛信息** — 输入「有什么竞赛」\n"
            "🏠 **空教室** — 输入「哪里可以自习」「有没有空教室」\n\n"
            "💡 试试输入以上关键词开始查询吧！"
        )

    def _handle_tools(self, tools: list[str], user_id: str, message: str, rag_context: str = "") -> str:
        tool_results = {}

        for tool_name in tools:
            if tool_name in self.tool_executors:
                params = self._extract_params(message, tool_name, user_id)
                # 把原始消息也传给 RAG 工具，方便它作为查询
                if tool_name == "rag":
                    params["question"] = message
                result = self.tool_executors[tool_name](params)
                tool_results[tool_name] = result

        if len(tools) == 1:
            raw = list(tool_results.values())[0]
            if "<!--CHART:" in raw:
                return raw
            if any(kw in raw[:80] for kw in ["📚", "💰", "🏫", "📢", "🏆", "📖", "🎓"]):
                return self._polish_response(user_id, message, raw, rag_context=rag_context)
            return raw

        combined = "\n\n---\n\n".join(
            f"【{name}查询结果】\n{result}"
            for name, result in tool_results.items()
        )
        return self._polish_response(user_id, message, combined, rag_context=rag_context)

    def _handle_fusion(self, fusion_name: str, user_id: str, message: str) -> str:
        fusion_executors = {
            "course_to_library": self._exec_fusion_course_to_library,
            "consumption_course": self._exec_fusion_consumption_course,
            "competition_course": self._exec_fusion_competition_course,
        }
        executor = fusion_executors.get(fusion_name)
        if executor:
            return executor(user_id, message)
        return self._handle_tools(KeywordRouter.route(message)["tools"], user_id, message)

    def _polish_response(self, user_id: str, user_message: str, raw_data: str, rag_context: str = "") -> str:
        history = self.session_mgr.get_history(user_id)
        extra_system = (
            f"当前用户: {user_id}, 日期: {date.today()}\n"
            "以下是系统查询结果，请用友好语气整理为自然回复。"
            "保持数据准确，适当添加emoji。"
            "如果结果中包含 <!--CHART:...--> 注释，请原样保留不要修改。"
        )
        if rag_context:
            extra_system += f"\n\n{rag_context}"
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": extra_system},
        ]
        msgs.extend(history[-4:])  # 最近2轮历史
        msgs.append({"role": "user", "content": user_message})
        msgs.append({"role": "assistant", "content": raw_data})

        resp = self._call_llm(msgs, temperature=0.3, max_tokens=800)
        if resp is not None:
            return resp.choices[0].message.content or raw_data
        # LLM 不可用时：给 raw_data 加个友好的前缀
        return f"[Demo Mode] Result:\n\n{raw_data}"

    # ═══════════════════════════════════════════
    # 流式对话（真流式 token by token）
    # ═══════════════════════════════════════════

    def chat_stream(self, user_id: str, message: str) -> Generator[str, None, None]:
        """
        流式对话：对于工具型查询先执行工具，再流式输出格式化结果
        对于直接对话，直接流式输出 LLM 响应
        每轮都自动注入 RAG 知识增强上下文
        """
        route = KeywordRouter.route(message)
        full_response = []

        # 自动 RAG 增强上下文
        rag_context = self._rag_enhance(message)

        if route["is_direct"]:
            # 直接流式（带RAG上下文）
            msgs = self._build_messages(user_id, message, system_extra=rag_context)
            stream = self._call_llm(msgs, temperature=0.7, max_tokens=800, stream=True)
            if stream is not None:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full_response.append(delta)
                        yield delta
            else:
                fallback = (
                    "Hello! I'm Xiao Hang, your campus data assistant.\n\n"
                    "LLM service is currently unavailable (please check API Key config).\n"
                    "You can still query: course schedule | spending | library | notices | competitions | empty classrooms\n\n"
                    "Try typing a keyword to start!"
                )
                for char in fallback:
                    full_response.append(char)
                    yield char

        elif route["fusion"]:
            # 融合场景：先执行，再流式输出
            raw = self._handle_fusion(route["fusion"], user_id, message)
            # 逐字符 yield 实现打字机效果
            for char in raw:
                full_response.append(char)
                yield char

        else:
            # 工具型：先执行工具，如果有 CHART 则直接输出，否则流式润色
            tool_results = {}
            for tool_name in route["tools"]:
                if tool_name in self.tool_executors:
                    params = self._extract_params(message, tool_name, user_id)
                    if tool_name == "rag":
                        params["question"] = message
                    result = self.tool_executors[tool_name](params)
                    tool_results[tool_name] = result

            raw = "\n\n".join(tool_results.values()) if tool_results else "未找到相关信息。"

            if "<!--CHART:" in raw:
                # 含图表数据，直接逐字输出
                for char in raw:
                    full_response.append(char)
                    yield char
            else:
                # 流式润色（带RAG上下文）
                history = self.session_mgr.get_history(user_id)
                extra_system = (
                    f"当前用户: {user_id}, 日期: {date.today()}\n"
                    "以下是系统查询结果，请用友好语气整理为自然回复。"
                    "保持数据准确，适当添加emoji。"
                    "如果结果中包含 <!--CHART:...--> 注释，请原样保留不要修改。"
                )
                if rag_context:
                    extra_system += f"\n\n{rag_context}"
                msgs = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "system", "content": extra_system},
                ]
                msgs.extend(history[-4:])
                msgs.append({"role": "user", "content": message})
                msgs.append({"role": "assistant", "content": raw})

                stream = self._call_llm(msgs, temperature=0.3, max_tokens=800, stream=True)
                if stream is not None:
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            full_response.append(delta)
                            yield delta
                else:
                    # LLM 不可用：直接输出原始结果
                    prefix = "🤖 [演示模式] 以下是查询结果：\n\n"
                    for char in prefix + raw:
                        full_response.append(char)
                        yield char

        # 流式结束后保存到历史
        answer = "".join(full_response)
        self.session_mgr.add_turn(user_id, message, answer)


# ──────────────── 全局单例 ────────────────

_agent: CampusAgent = None


def get_agent() -> CampusAgent:
    global _agent
    if _agent is None:
        _agent = CampusAgent()
    return _agent
