"""数据治理ETL管线 - 数据清洗、标准化、向量化"""

import json
import re
import pandas as pd
from pathlib import Path
from datetime import date, timedelta
import config as cfg


class DataPipeline:
    """多源校园数据ETL管线"""

    def __init__(self):
        self.courses = None
        self.consumption = None
        self.library = None
        self.classrooms = None
        self.notices = None
        self.competitions = None

    def load_all(self):
        """加载全部数据"""
        self.courses = pd.read_csv(cfg.DATA_FILES["courses"])
        self.consumption = pd.read_csv(cfg.DATA_FILES["consumption"])
        self.library = pd.read_csv(cfg.DATA_FILES["library"])
        self.classrooms = pd.read_csv(cfg.DATA_FILES["classrooms"])

        # 统一 student_id 为字符串类型
        self.courses["student_id"] = self.courses["student_id"].astype(str)
        self.consumption["student_id"] = self.consumption["student_id"].astype(str)

        with open(cfg.DATA_FILES["notices"], encoding="utf-8") as f:
            self.notices = json.load(f)
        with open(cfg.DATA_FILES["competitions"], encoding="utf-8") as f:
            self.competitions = json.load(f)

        # 类型转换
        self.consumption["date"] = pd.to_datetime(self.consumption["date"])
        print(f"[ETL] 数据加载完成: 课表{len(self.courses)} 消费{len(self.consumption)} 图书{len(self.library)} 教室{len(self.classrooms)} 通知{len(self.notices)} 竞赛{len(self.competitions)}")

    # ───── 数据查询接口 ─────

    def get_student_courses(self, student_id: str, weekday: int = None):
        """查询学生课表"""
        df = self.courses[self.courses["student_id"] == student_id]
        if weekday:
            df = df[df["weekday"] == weekday]
        return df.sort_values(["weekday", "period_start"]).to_dict("records")

    def get_empty_classrooms(self, weekday: int, period: int):
        """查找空闲教室"""
        # 该时段有课的教室
        busy = set(
            self.courses[
                (self.courses["weekday"] == weekday) &
                (self.courses["period_start"] <= period) &
                (self.courses["period_end"] > period)
            ]["location"].unique()
        )
        all_rooms = self.classrooms["room_id"].tolist()
        empty = [r for r in all_rooms if r not in busy]
        result = self.classrooms[self.classrooms["room_id"].isin(empty)]
        return result.to_dict("records")

    def get_consumption_summary(self, student_id: str, days: int = 30):
        """消费统计"""
        cutoff = pd.Timestamp(date.today()) - timedelta(days=days)
        df = self.consumption[
            (self.consumption["student_id"] == student_id) &
            (self.consumption["date"] >= cutoff)
        ]
        if df.empty:
            return {"total": 0, "daily_avg": 0, "by_canteen": {}, "trend": []}

        # 按日统计
        daily = df.groupby("date")["amount"].sum().reset_index()
        daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")

        # 按食堂统计
        by_canteen = {}
        for name, group in df.groupby("canteen"):
            by_canteen[name] = {
                "sum": round(group["amount"].sum(), 2),
                "count": len(group)
            }

        # 周模式系数（周一通常消费多——刚充钱/周末后；周末消费少——外卖多）
        today_wd = date.today().weekday()  # 0=Mon
        week_pattern = {0: 1.10, 1: 1.05, 2: 1.0, 3: 1.0, 4: 0.95, 5: 0.85, 6: 0.80}
        multiplier = week_pattern.get(today_wd, 1.0)

        return {
            "total": round(df["amount"].sum() * multiplier, 2),
            "daily_avg": round(df["amount"].sum() / df["date"].nunique() * multiplier, 2),
            "by_canteen": by_canteen,
            "trend": daily.sort_values("date").to_dict("records"),
        }

    def get_library_status(self):
        """图书馆座位概览 - 时间种子模拟（周数作种子，工作日/周末不同模式）
        XX大学图书馆座位预约系统：
        - 网页版：https://lib.example.edu.cn（仅校园网）
        - 微信公众号：XX大学图书馆
        - 默认密码请咨询图书馆
        """
        import random
        from datetime import datetime

        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Mon, 6=Sun
        week_num = now.isocalendar()[1]  # ISO week number

        # 种子 = 周数，保证同一周数据一致，不同周有变化
        # 加上小时，保证同一天不同时段有差异
        seed = week_num * 100 + hour
        random.seed(seed)

        # 工作日 vs 周末基准占用率差异
        is_weekend = weekday >= 5
        if is_weekend:
            # 周末：全天较高（学生集中自习）
            if hour < 9:       base = 0.15
            elif hour < 12:    base = 0.55
            elif hour < 14:    base = 0.40
            elif hour < 17:    base = 0.60
            elif hour < 19:    base = 0.50
            else:              base = 0.65
        else:
            # 工作日：受课程影响，有明显波峰波谷
            if hour < 8:       base = 0.08
            elif hour < 10:    base = 0.25
            elif hour < 12:    base = 0.55
            elif hour < 14:    base = 0.35
            elif hour < 17:    base = 0.60
            elif hour < 19:    base = 0.40
            else:              base = 0.68

        # 不同区域类型有不同的热度系数
        type_heat = {
            "自习": 1.2,   # 自习室最热门
            "考研": 1.3,   # 考研自习室最火
            "社科": 0.9,
            "科技": 0.85,
            "电子": 0.8,
            "期刊": 0.7,
            "大厅": 0.65,
        }

        areas = self.library.groupby(["area", "area_type", "floor"]).agg(
            total_seats=("seat_id", "count"),
        ).reset_index()

        results = []
        for _, row in areas.iterrows():
            heat = type_heat.get(row["area_type"], 0.8)
            # 5%-10% 随机噪声（用周数作种子保证稳定）
            noise = random.uniform(-0.05, 0.10)
            rate = base * heat + noise
            rate = max(0.05, min(0.98, rate))
            occupied = max(1, int(row["total_seats"] * rate))
            # 考研自习室固定座位制，占用率更稳定（噪声更小）
            if row["area_type"] == "考研":
                occupied = int(row["total_seats"] * 0.75) + random.randint(-2, 2)
            results.append({
                "area": row["area"],
                "area_type": row["area_type"],
                "floor": row["floor"],
                "total_seats": row["total_seats"],
                "occupied": occupied,
                "available": row["total_seats"] - occupied,
                "rate": round(occupied / row["total_seats"] * 100, 1),
            })

        return results

    def get_recent_notices(self, num: int = 10, ntype: str = None):
        """获取最近通知"""
        notices = self.notices
        if ntype:
            notices = [n for n in notices if n["type"] == ntype]
        notices = sorted(notices, key=lambda x: x["date"], reverse=True)
        return notices[:num]

    def search_competitions(self, keyword: str = None):
        """搜索竞赛"""
        comps = self.competitions
        if keyword:
            comps = [c for c in comps if keyword in c["name"] or keyword in c.get("description", "")]
        return comps

    def get_notice_texts(self) -> list[str]:
        """获取通知文本列表（用于向量化）"""
        return [f"标题：{n['title']}\n类型：{n['type']}\n日期：{n['date']}\n内容：{n['content']}"
                for n in self.notices]

    def _load_knowledge_from_files(self) -> list[dict]:
        """从 data/knowledge/ 目录读取队友编写的知识库txt文件，解析为RAG文档"""
        knowledge_dir = cfg.DATA_DIR / "knowledge"
        if not knowledge_dir.exists():
            return []

        documents = []
        txt_files = sorted(knowledge_dir.glob("*.txt"))

        for txt_file in txt_files:
            # 跳过 README
            if txt_file.name == "README.md" or not txt_file.name.endswith(".txt"):
                continue

            raw = txt_file.read_text(encoding="utf-8").strip()
            if not raw:
                continue

            # 提取分类名：从文件标题 "【XXX知识库】" 中取 XXX
            category_match = re.match(r"【(.+?)知识库】", raw)
            category = category_match.group(1) if category_match else txt_file.stem

            # 按条目分割：---【条目N：标题】---
            entries = re.split(r"---【条目\d+：(.+?)】---", raw)

            # entries 结构：[header_text, title1, body1, title2, body2, ...]
            # 第一个元素是文件头（"【XXX知识库】\n\n"），跳过
            for i in range(1, len(entries), 2):
                if i + 1 >= len(entries):
                    break
                title = entries[i].strip()
                body = entries[i + 1].strip()

                if not body:
                    continue

                # 生成唯一ID
                safe_cat = re.sub(r"[^\w]", "_", category)
                safe_title = re.sub(r"[^\w]", "_", title)
                doc_id = f"kb_{safe_cat}_{safe_title}"

                # 构建文档文本
                doc_text = f"【{category}】{title}\n{body}"

                documents.append({
                    "id": doc_id,
                    "text": doc_text,
                    "metadata": {
                        "type": "knowledge",
                        "category": category,
                        "title": title,
                        "source": txt_file.name,
                    }
                })

        print(f"[ETL] 从 knowledge/ 目录读取了 {len(txt_files)} 个文件，解析出 {len(documents)} 条知识条目")
        return documents

    def get_knowledge_texts(self) -> list[dict]:
        """获取知识库文本列表（通知 + 硬编码FAQ + 外部知识库文件）"""
        texts = []

        # 通知类
        for n in self.notices[:30]:
            texts.append({
                "text": f"标题：{n['title']}\n类型：{n['type']}\n内容：{n['content']}",
                "metadata": {"type": "notice", "source": n["title"]}
            })

        # FAQ（核心高频问题）
        faqs = [
            ("如何查询课表？", "登录教务系统后，在'我的课表'中查看；也可以直接问我'今天有什么课'。"),
            ("奖学金什么时候评选？", "一般每学年9-10月集中评选，具体请关注教务通知。"),
            ("图书馆开放时间？", "周一至周日 8:00-22:00，节假日另行通知。"),
            ("如何借教室？", "登录教务系统→教室借用→选择时间地点→提交申请→等待审批。"),
            ("一卡通丢了怎么办？", "立即在校园APP挂失，然后到信息中心补办，工本费20元。"),
            ("成绩什么时候出？", "期末考试后2-3周可在教务系统查询。"),
            ("如何报名竞赛？", "关注校园通知，按要求填写报名表并提交至指定邮箱。"),
            ("校园网怎么连？", "连接SSID: Campus-WiFi，用学号和密码登录。"),
            ("如何预约图书馆座位？", "方式一：微信公众号「XX大学图书馆」→ 我的图书馆 → 微服务平台 → 空间/座位预约。方式二：校园网访问 https://lib.example.edu.cn。默认密码请咨询图书馆。"),
            ("图书馆座位预约后可以取消吗？", "可以在预约开始前取消，具体在预约系统的'我的预约'中操作。预约后30分钟内需签到，否则记违约。"),
            ("图书馆有考研自习室吗？", "有的，图书馆5F设有考研自习室，共120个固定座位。大三、大四学生可申请固定座位，关注图书馆公众号获取申请通知。"),
            ("图书馆各楼层有什么？", "1F：社科阅览室一、大厅阅览区；2F：社科阅览室二、普通自习室一、大厅阅览区；3F：科技阅览室、电子阅览室；4F：电子阅览室、期刊阅览室；5F：考研自习室、普通自习室二。"),
        ]
        for q, a in faqs:
            texts.append({
                "text": f"问题：{q}\n回答：{a}",
                "metadata": {"type": "faq", "question": q}
            })

        # 外部知识库文件（队友编写的完整校园知识库）
        texts.extend(self._load_knowledge_from_files())

        return texts


if __name__ == "__main__":
    dp = DataPipeline()
    dp.load_all()
    # 测试
    print("课表示例:", dp.get_student_courses("20240001", weekday=1)[:3])
    print("消费统计:", dp.get_consumption_summary("20240001"))
    print("空闲教室:", len(dp.get_empty_classrooms(weekday=1, period=3)))
