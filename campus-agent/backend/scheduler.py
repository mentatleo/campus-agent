"""智能排课推荐引擎 v1
根据学生已有课表 + 偏好，推荐下学期选课方案
算法：3阶段求解（精确满足 → 软约束松弛 → 贪心补足）
"""

import random
from datetime import date
from typing import Optional
import config as cfg


# ──────────────── 课程池（模拟选课库）────────────────

COURSE_POOL = [
    # 通识必修
    {"id": "GE001", "name": "大学英语四级精读", "credits": 3, "category": "通识", "weekday": 1, "period_start": 1, "period_end": 2, "location": "1号教学楼101", "teacher": "王英华", "max_students": 60, "enrolled": 45},
    {"id": "GE002", "name": "大学英语听说", "credits": 2, "category": "通识", "weekday": 3, "period_start": 3, "period_end": 4, "location": "语音实验室A", "teacher": "刘晓芸", "max_students": 40, "enrolled": 38},
    {"id": "GE003", "name": "体育（篮球）", "credits": 1, "category": "通识", "weekday": 2, "period_start": 5, "period_end": 6, "location": "体育馆", "teacher": "张强", "max_students": 30, "enrolled": 22},
    {"id": "GE004", "name": "体育（游泳）", "credits": 1, "category": "通识", "weekday": 4, "period_start": 5, "period_end": 6, "location": "游泳馆", "teacher": "陈静", "max_students": 25, "enrolled": 18},
    {"id": "GE005", "name": "马克思主义基本原理", "credits": 3, "category": "通识", "weekday": 2, "period_start": 1, "period_end": 2, "location": "综合教学楼301", "teacher": "李政远", "max_students": 120, "enrolled": 98},
    {"id": "GE006", "name": "形势与政策", "credits": 1, "category": "通识", "weekday": 5, "period_start": 7, "period_end": 8, "location": "综合教学楼201", "teacher": "赵明", "max_students": 120, "enrolled": 80},
    {"id": "GE007", "name": "心理健康教育", "credits": 2, "category": "通识", "weekday": 3, "period_start": 7, "period_end": 8, "location": "2号教学楼301", "teacher": "孙丽", "max_students": 80, "enrolled": 70},
    # 数学与计算机专业课
    {"id": "CS101", "name": "数据结构与算法", "credits": 4, "category": "专业核心", "weekday": 1, "period_start": 3, "period_end": 4, "location": "3号教学楼201", "teacher": "刘志强", "max_students": 50, "enrolled": 48},
    {"id": "CS102", "name": "操作系统原理", "credits": 3, "category": "专业核心", "weekday": 2, "period_start": 3, "period_end": 4, "location": "3号教学楼202", "teacher": "张伟", "max_students": 50, "enrolled": 42},
    {"id": "CS103", "name": "计算机网络", "credits": 3, "category": "专业核心", "weekday": 4, "period_start": 1, "period_end": 2, "location": "3号教学楼203", "teacher": "王海峰", "max_students": 50, "enrolled": 35},
    {"id": "CS104", "name": "数据库原理", "credits": 3, "category": "专业核心", "weekday": 3, "period_start": 1, "period_end": 2, "location": "3号教学楼204", "teacher": "陈晨", "max_students": 50, "enrolled": 30},
    {"id": "CS105", "name": "Python程序设计", "credits": 2, "category": "专业选修", "weekday": 5, "period_start": 1, "period_end": 2, "location": "实验中心机房A", "teacher": "林小红", "max_students": 40, "enrolled": 39},
    {"id": "CS106", "name": "机器学习导论", "credits": 3, "category": "专业选修", "weekday": 1, "period_start": 5, "period_end": 6, "location": "实验中心机房B", "teacher": "魏大勇", "max_students": 35, "enrolled": 20},
    {"id": "CS107", "name": "Web应用开发", "credits": 3, "category": "专业选修", "weekday": 4, "period_start": 3, "period_end": 4, "location": "实验中心机房C", "teacher": "孙培正", "max_students": 40, "enrolled": 28},
    {"id": "CS108", "name": "软件工程", "credits": 3, "category": "专业核心", "weekday": 5, "period_start": 3, "period_end": 4, "location": "3号教学楼301", "teacher": "赵伟", "max_students": 50, "enrolled": 44},
    # 数学课
    {"id": "MA101", "name": "高等数学A（下）", "credits": 5, "category": "专业基础", "weekday": 1, "period_start": 1, "period_end": 2, "location": "2号教学楼201", "teacher": "刘海涛", "max_students": 80, "enrolled": 75},
    {"id": "MA102", "name": "线性代数", "credits": 3, "category": "专业基础", "weekday": 3, "period_start": 5, "period_end": 6, "location": "2号教学楼202", "teacher": "张秀玲", "max_students": 80, "enrolled": 62},
    {"id": "MA103", "name": "概率论与数理统计", "credits": 3, "category": "专业基础", "weekday": 2, "period_start": 7, "period_end": 8, "location": "2号教学楼203", "teacher": "钱明", "max_students": 80, "enrolled": 55},
    # 人文素养选修
    {"id": "HU001", "name": "中国传统文化导论", "credits": 2, "category": "人文素养", "weekday": 1, "period_start": 7, "period_end": 8, "location": "综合教学楼101", "teacher": "周文博", "max_students": 100, "enrolled": 68},
    {"id": "HU002", "name": "艺术欣赏", "credits": 2, "category": "人文素养", "weekday": 3, "period_start": 3, "period_end": 4, "location": "综合教学楼102", "teacher": "胡晓丽", "max_students": 100, "enrolled": 55},
    {"id": "HU003", "name": "创新创业基础", "credits": 2, "category": "人文素养", "weekday": 4, "period_start": 7, "period_end": 8, "location": "综合教学楼201", "teacher": "叶亮", "max_students": 80, "enrolled": 72},
    {"id": "HU004", "name": "演讲与口才", "credits": 2, "category": "人文素养", "weekday": 5, "period_start": 5, "period_end": 6, "location": "逸夫楼201", "teacher": "唐颖", "max_students": 60, "enrolled": 52},
]


class CourseScheduler:
    """智能排课推荐引擎"""

    def __init__(self, data_pipeline=None):
        self.dp = data_pipeline
        self.course_pool = COURSE_POOL

    def recommend(
        self,
        student_id: str,
        target_credits: int = 18,
        prefer_morning: bool = False,
        prefer_categories: list[str] = None,
        avoid_weekdays: list[int] = None,
        existing_courses: list[dict] = None,
    ) -> dict:
        """
        智能排课推荐
        
        Args:
            student_id: 学号
            target_credits: 目标学分（默认18）
            prefer_morning: 是否偏好上午课（第1-4节）
            prefer_categories: 优先选择的课程类别
            avoid_weekdays: 避免的星期几（如[1,5]避开周一周五）
            existing_courses: 已选课程（用于检测冲突）
        
        Returns:
            {
                "phase": "exact"|"relaxed"|"greedy",  # 求解阶段
                "courses": [...],  # 推荐课程列表
                "total_credits": int,
                "schedule_matrix": dict,  # 按天分组的课表
                "conflicts_avoided": int,
                "explanation": str,
            }
        """
        if existing_courses is None and self.dp:
            existing_courses = self.dp.get_student_courses(student_id)
        if existing_courses is None:
            existing_courses = []

        avoid_weekdays = avoid_weekdays or []
        prefer_categories = prefer_categories or []

        # 已选课程的时间段（(weekday, period) 集合）
        busy_slots = set()
        for c in existing_courses:
            for p in range(c["period_start"], c["period_end"] + 1):
                busy_slots.add((c["weekday"], p))

        # ── Phase 1: 精确满足所有约束 ──
        result = self._phase_exact(
            target_credits, prefer_morning, prefer_categories,
            avoid_weekdays, busy_slots
        )
        phase = "exact"

        # ── Phase 2: 松弛软约束（时间偏好），仍满足硬约束 ──
        if result["total_credits"] < target_credits - 2:
            result = self._phase_relaxed(target_credits, avoid_weekdays, busy_slots)
            phase = "relaxed"

        # ── Phase 3: 贪心补足（只要不冲突就选）──
        if result["total_credits"] < target_credits - 4:
            result = self._phase_greedy(target_credits, busy_slots)
            phase = "greedy"

        courses = result["courses"]
        total_credits = sum(c["credits"] for c in courses)

        # 构建课表矩阵（按天）
        schedule_matrix = {}
        day_names = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五"}
        for c in courses:
            day = day_names.get(c["weekday"], f"周{c['weekday']}")
            if day not in schedule_matrix:
                schedule_matrix[day] = []
            schedule_matrix[day].append({
                "name": c["name"],
                "period": f"第{c['period_start']}-{c['period_end']}节",
                "location": c["location"],
                "credits": c["credits"],
                "category": c["category"],
            })

        # 按节次排序
        for day in schedule_matrix:
            schedule_matrix[day].sort(key=lambda x: int(x["period"].replace("第", "").split("-")[0]))

        # 生成说明文字
        phase_desc = {"exact": "精确匹配", "relaxed": "松弛时间偏好", "greedy": "贪心补足"}
        explanation = (
            f"采用**{phase_desc[phase]}**策略，共推荐 {len(courses)} 门课程，"
            f"合计 **{total_credits} 学分**。"
        )
        if phase == "relaxed":
            explanation += " 部分课程不完全满足时间偏好，但无冲突。"
        elif phase == "greedy":
            explanation += " 约束条件较严格，已用贪心算法补足学分。"

        return {
            "phase": phase,
            "courses": courses,
            "total_credits": total_credits,
            "schedule_matrix": schedule_matrix,
            "conflicts_avoided": len(existing_courses),
            "explanation": explanation,
        }

    # ─────────────────────────────────────────
    # 三阶段求解器
    # ─────────────────────────────────────────

    def _phase_exact(
        self, target_credits, prefer_morning, prefer_categories, avoid_weekdays, busy_slots
    ) -> dict:
        """Phase 1: 所有约束均满足"""
        selected = []
        total_credits = 0
        used_slots = set(busy_slots)

        candidates = [c for c in self.course_pool if c["enrolled"] < c["max_students"]]

        # 评分排序：偏好类别 > 上午偏好 > 避免星期
        def score(c):
            s = 0
            if c["category"] in prefer_categories:
                s += 10
            if prefer_morning and c["period_start"] <= 4:
                s += 5
            if c["weekday"] in avoid_weekdays:
                s -= 20
            s += c["credits"]  # 多学分优先
            s -= c["enrolled"] / c["max_students"] * 3  # 热门课扣分（容量紧张）
            return s

        candidates.sort(key=score, reverse=True)

        for c in candidates:
            if total_credits >= target_credits:
                break
            if c["weekday"] in avoid_weekdays:
                continue
            slots = set((c["weekday"], p) for p in range(c["period_start"], c["period_end"] + 1))
            if slots & used_slots:
                continue  # 时间冲突
            selected.append(c)
            used_slots |= slots
            total_credits += c["credits"]

        return {"courses": selected, "total_credits": total_credits}

    def _phase_relaxed(self, target_credits, avoid_weekdays, busy_slots) -> dict:
        """Phase 2: 忽略时间偏好，仅保留硬约束（无冲突、有空位）"""
        selected = []
        total_credits = 0
        used_slots = set(busy_slots)

        candidates = [c for c in self.course_pool if c["enrolled"] < c["max_students"]]
        candidates.sort(key=lambda c: -c["credits"])

        for c in candidates:
            if total_credits >= target_credits:
                break
            if c["weekday"] in avoid_weekdays:
                continue
            slots = set((c["weekday"], p) for p in range(c["period_start"], c["period_end"] + 1))
            if slots & used_slots:
                continue
            selected.append(c)
            used_slots |= slots
            total_credits += c["credits"]

        return {"courses": selected, "total_credits": total_credits}

    def _phase_greedy(self, target_credits, busy_slots) -> dict:
        """Phase 3: 贪心——只要无时间冲突就选，不管其他约束"""
        selected = []
        total_credits = 0
        used_slots = set(busy_slots)

        candidates = sorted(self.course_pool, key=lambda c: -c["credits"])

        for c in candidates:
            if total_credits >= target_credits:
                break
            slots = set((c["weekday"], p) for p in range(c["period_start"], c["period_end"] + 1))
            if slots & used_slots:
                continue
            selected.append(c)
            used_slots |= slots
            total_credits += c["credits"]

        return {"courses": selected, "total_credits": total_credits}

    def format_recommendation(self, result: dict) -> str:
        """将推荐结果格式化为 Markdown 文本 + ECharts 数据"""
        lines = []
        lines.append(f"## 🎓 选课推荐方案")
        lines.append(f"")
        lines.append(result["explanation"])
        lines.append(f"")

        # 按天展示
        day_order = ["周一", "周二", "周三", "周四", "周五"]
        matrix = result["schedule_matrix"]
        for day in day_order:
            if day in matrix:
                lines.append(f"**{day}**")
                for c in matrix[day]:
                    lines.append(f"- {c['period']} | {c['name']} | {c['location']} | {c['credits']}学分")
                lines.append("")

        # 学分汇总
        lines.append("---")
        lines.append(f"**学分汇总：** 共 {result['total_credits']} 学分")
        lines.append("")

        # 类别分布
        cat_count = {}
        for c in result["courses"]:
            cat_count[c["category"]] = cat_count.get(c["category"], 0) + c["credits"]
        lines.append("**各类别学分：**")
        for cat, credits in sorted(cat_count.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}：{credits} 学分")

        # 嵌入图表数据（饼图，显示学分分布）
        chart_data = [{"name": k, "value": v} for k, v in cat_count.items()]
        import json
        chart_json = json.dumps(chart_data, ensure_ascii=False)
        lines.append(f"\n<!--CHART:credits_pie:{chart_json}-->")

        return "\n".join(lines)


# ─────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────

_scheduler: CourseScheduler = None


def get_scheduler(data_pipeline=None) -> CourseScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CourseScheduler(data_pipeline)
    return _scheduler
