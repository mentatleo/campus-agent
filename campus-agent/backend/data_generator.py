"""校园多源数据生成器 - 衡水学院定制版
   
设计理念：
- 管理员一次性对接学校数据源（教务系统API / 图书馆系统 / 一卡通系统）
- 学生零门槛使用——登录学号即可获取全部个人数据
- 模拟数据尽可能贴近真实：课程名、教师、教学楼、上课时间等均对照衡水学院实际情况
"""

import csv
import json
import random
from datetime import datetime, timedelta, date
from pathlib import Path
import config as cfg


# ═══════════════════════════════════════════════════════════════
# 真实数据定义
# ═══════════════════════════════════════════════════════════════

# 教学楼（衡水学院实际）
BUILDINGS = {
    "1号教学楼": {"floors": 5, "rooms_per_floor": 6, "room_format": "{b} {f}0{r}"},
    "2号教学楼": {"floors": 5, "rooms_per_floor": 6, "room_format": "{b} {f}0{r}"},
    "3号教学楼": {"floors": 5, "rooms_per_floor": 5, "room_format": "{b} {f}0{r}"},
    "综合教学楼": {"floors": 5, "rooms_per_floor": 5, "room_format": "{b} {f}0{r}"},
    "逸夫楼": {"floors": 4, "rooms_per_floor": 4, "room_format": "{b} {f}0{r}"},
    "实验中心": {"floors": 4, "rooms_per_floor": 4, "room_format": "{b} 30{r}"},
}

# 食堂
CANTEENS = ["第一食堂", "第二食堂", "回民食堂", "教工餐厅"]

# 院系及对应专业课程
DEPARTMENT_COURSES = {
    "数学与计算机学院": {
        "核心课": [
            ("高等数学A（下）", 6, "1号教学楼"),
            ("线性代数", 4, "1号教学楼"),
            ("离散数学", 3, "2号教学楼"),
            ("概率论与数理统计", 3, "2号教学楼"),
            ("C语言程序设计", 4, "实验中心"),
            ("数据结构与算法", 4, "综合教学楼"),
            ("计算机组成原理", 3, "综合教学楼"),
            ("操作系统", 3, "综合教学楼"),
            ("数据库原理", 3, "2号教学楼"),
            ("计算机网络", 3, "综合教学楼"),
            ("Python程序设计", 3, "实验中心"),
            ("软件工程", 2, "逸夫楼"),
            ("数字逻辑", 3, "2号教学楼"),
            ("编译原理", 2, "逸夫楼"),
        ],
    },
    "电子信息工程学院": {
        "核心课": [
            ("高等数学A（下）", 6, "1号教学楼"),
            ("大学物理", 4, "2号教学楼"),
            ("模拟电子技术", 4, "实验中心"),
            ("数字电子技术", 3, "实验中心"),
            ("信号与系统", 3, "综合教学楼"),
            ("单片机原理", 3, "实验中心"),
            ("通信原理", 3, "逸夫楼"),
            ("嵌入式系统", 3, "实验中心"),
        ],
    },
    "文学与传播学院": {
        "核心课": [
            ("现代文学", 4, "逸夫楼"),
            ("古代汉语", 4, "3号教学楼"),
            ("新闻学概论", 3, "逸夫楼"),
            ("传播学概论", 3, "逸夫楼"),
            ("写作理论与实践", 3, "3号教学楼"),
            ("中国文学批评史", 2, "3号教学楼"),
        ],
    },
    "经济管理学院": {
        "核心课": [
            ("微观经济学", 4, "逸夫楼"),
            ("宏观经济学", 4, "逸夫楼"),
            ("管理学原理", 3, "3号教学楼"),
            ("会计学基础", 4, "3号教学楼"),
            ("市场营销学", 3, "逸夫楼"),
            ("计量经济学", 3, "2号教学楼"),
        ],
    },
    "外国语学院": {
        "核心课": [
            ("综合英语（4）", 6, "逸夫楼"),
            ("英语视听说", 4, "逸夫楼"),
            ("英汉翻译", 4, "逸夫楼"),
            ("英语写作", 3, "逸夫楼"),
            ("英美文学", 3, "3号教学楼"),
        ],
    },
    "化工学院": {
        "核心课": [
            ("高等数学A（下）", 6, "1号教学楼"),
            ("化工原理", 4, "实验中心"),
            ("无机化学", 4, "实验中心"),
            ("有机化学", 4, "实验中心"),
            ("分析化学", 3, "实验中心"),
            ("物理化学", 3, "2号教学楼"),
        ],
    },
    "生命科学学院": {
        "核心课": [
            ("生物化学", 4, "实验中心"),
            ("分子生物学", 4, "综合教学楼"),
            ("细胞生物学", 3, "综合教学楼"),
            ("遗传学", 3, "2号教学楼"),
        ],
    },
    "教育学院": {
        "核心课": [
            ("教育心理学", 4, "逸夫楼"),
            ("教育学原理", 3, "3号教学楼"),
            ("课程与教学论", 3, "逸夫楼"),
            ("教育技术学", 2, "综合教学楼"),
        ],
    },
}

# 公共必修课（所有学生都有）
COMMON_COURSES = [
    ("大学英语（2）", 4, "逸夫楼"),
    ("马克思主义基本原理", 3, "逸夫楼"),
    ("中国近现代史纲要", 2, "3号教学楼"),
    ("大学体育（篮球）", 2, "操场"),
    ("形势与政策", 2, "逸夫楼"),
    ("大学生心理健康", 2, "逸夫楼"),
]

# 教师姓名（带职称，更真实）
TEACHERS = [
    ("张明华", "教授"), ("李志强", "副教授"), ("王丽", "讲师"),
    ("赵建国", "教授"), ("陈伟", "副教授"), ("刘洋", "讲师"),
    ("周晓燕", "讲师"), ("孙志刚", "副教授"), ("杨帆", "教授"),
    ("马文涛", "讲师"), ("吴建国", "讲师"), ("何芳", "副教授"),
    ("郭晓东", "教授"), ("林婷", "讲师"), ("韩博", "副教授"),
    ("沈洁", "讲师"), ("曹鹏", "教授"), ("邓丽华", "副教授"),
    ("彭伟", "讲师"), ("傅磊", "副教授"),
]

# 通知类型
NOTICE_TYPES = ["学术讲座", "竞赛通知", "社团活动", "教务通知", "就业信息", "奖学金", "活动预告", "考试通知"]

# 竞赛信息
COMPETITIONS = [
    ("全国大学生数学建模竞赛", "国家级", "数学与计算机学院", 50),
    ("蓝桥杯程序设计竞赛", "省级", "数学与计算机学院", 30),
    ("互联网+大学生创新创业大赛", "国家级", "教务处", 60),
    ("挑战杯全国大学生课外学术科技作品竞赛", "国家级", "团委", 55),
    ("外研社·国才杯英语演讲比赛", "省级", "外国语学院", 25),
    ("全国大学生化工设计竞赛", "国家级", "化工学院", 45),
    ("ACM-ICPC程序设计竞赛", "国际级", "数学与计算机学院", 35),
    ("全国大学生电子设计竞赛", "省级", "电子信息工程学院", 28),
    ("师范生教学技能大赛", "省级", "教育学院", 20),
    ("中国大学生计算机设计大赛", "国家级", "教务处", 40),
]


class CampusDataGenerator:
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.my_student_id = "DEMO_USER"  # 替换为你的学号
        self.my_dept = "数学与计算机学院"

        # 所有学生：主用户 + 其他随机学生
        self.students = [self.my_student_id] + [f"2024{i:04d}" for i in range(1, 51) if f"2024{i:04d}" != self.my_student_id]

        # 分配院系
        dept_names = list(DEPARTMENT_COURSES.keys())
        self.student_dept = {}
        for sid in self.students:
            if sid == self.my_student_id:
                self.student_dept[sid] = self.my_dept
            else:
                self.student_dept[sid] = random.choice(dept_names)

    # ═══════════════════ 课表 ═══════════════════

    def generate_courses(self):
        rows = []
        course_id = 1

        for sid in self.students:
            dept = self.student_dept[sid]

            if sid == self.my_student_id:
                # ── 固定真实课表（数学与计算机学院大二下学期）──
                schedule = [
                    # 周一
                    ("高等数学A（下）", "张明华", "1号教学楼 301", 1, 1, 2, "1-16周"),
                    ("数据结构与算法", "李志强", "综合教学楼 201", 1, 3, 4, "1-16周"),
                    ("数据库原理", "赵建国", "2号教学楼 102", 1, 5, 6, "1-12周"),
                    ("大学英语（2）", "王丽", "逸夫楼 305", 1, 7, 8, "1-16周"),
                    # 周二
                    ("线性代数", "杨帆", "1号教学楼 205", 2, 1, 2, "1-16周"),
                    ("C语言程序设计", "陈伟", "实验中心 301", 2, 3, 4, "1-16周"),
                    ("数字逻辑", "马文涛", "2号教学楼 305", 2, 5, 6, "1-16周"),
                    ("大学体育（篮球）", "刘洋", "操场", 2, 7, 8, "1-16周"),
                    # 周三
                    ("高等数学A（下）", "张明华", "1号教学楼 301", 3, 1, 2, "1-16周"),
                    ("马克思主义基本原理", "周晓燕", "逸夫楼 201", 3, 3, 4, "1-16周"),
                    ("Python程序设计", "孙志刚", "实验中心 201", 3, 5, 6, "1-16周"),
                    # 周四
                    ("数据结构与算法", "李志强", "综合教学楼 201", 4, 1, 2, "1-16周"),
                    ("概率论与数理统计", "何芳", "2号教学楼 301", 4, 3, 4, "1-16周"),
                    ("数据库原理", "赵建国", "2号教学楼 102", 4, 5, 6, "1-12周"),
                    ("大学生心理健康", "林婷", "逸夫楼 阶梯教室", 4, 7, 8, "1-8周"),
                    # 周五
                    ("C语言程序设计", "陈伟", "实验中心 301", 5, 1, 2, "1-16周"),
                    ("线性代数", "杨帆", "1号教学楼 205", 5, 3, 4, "1-16周"),
                    ("形势与政策", "吴建国", "逸夫楼 阶梯教室", 5, 5, 6, "1-8周"),
                ]
                for (cn, tn, loc, wd, ps, pe, wks) in schedule:
                    rows.append({
                        "course_id": f"C{course_id:04d}", "student_id": sid,
                        "course_name": cn, "teacher": tn,
                        "weekday": wd, "period_start": ps, "period_end": pe,
                        "location": loc, "weeks": wks,
                    })
                    course_id += 1

            else:
                # ── 其他学生：根据院系分配课程 ──
                core = DEPARTMENT_COURSES.get(dept, list(DEPARTMENT_COURSES.values())[0])["核心课"]
                selected = random.sample(core, min(len(core), random.randint(5, 7)))
                # 加公共课
                selected += random.sample(COMMON_COURSES, random.randint(2, 3))

                # 分配时间段，避免冲突
                used_slots = set()
                for (cn, _credits, _bldg) in selected:
                    for _retry in range(20):
                        wd = random.randint(1, 5)
                        ps = random.choice([1, 3, 5, 7])
                        slot_key = (wd, ps)
                        if slot_key not in used_slots:
                            used_slots.add(slot_key)
                            break
                    else:
                        wd = random.randint(1, 5)
                        ps = random.choice([1, 3, 5, 7])

                    teacher_info = random.choice(TEACHERS)
                    tn = teacher_info[0]
                    bldg = _bldg
                    room = f"{random.randint(1,4)}0{random.randint(1,5)}"
                    weeks = f"{random.randint(1,4)}-{random.randint(9,16)}周"

                    rows.append({
                        "course_id": f"C{course_id:04d}", "student_id": sid,
                        "course_name": cn, "teacher": tn,
                        "weekday": wd, "period_start": ps, "period_end": ps + 1,
                        "location": f"{bldg} {room}", "weeks": weeks,
                    })
                    course_id += 1

        self._write_csv(cfg.DATA_FILES["courses"], rows)
        print(f"[OK] 课表数据: {len(rows)} 条 | 用户 {self.my_student_id} 共 {len([r for r in rows if r['student_id']==self.my_student_id])} 门课")

    # ═══════════════════ 消费 ═══════════════════

    def generate_consumption(self):
        rows = []
        today = date.today()
        for sid in self.students:
            for day_offset in range(90):
                d = today - timedelta(days=day_offset)
                # 周末消费少
                if d.weekday() >= 5 and random.random() < 0.4:
                    continue
                meal_count = random.choices([1, 2, 3], weights=[0.15, 0.5, 0.35])[0]
                for _ in range(meal_count):
                    hour = random.choice([7, 8, 12, 13, 18, 19])
                    minute = random.randint(0, 59)
                    canteen = random.choice(CANTEENS)
                    # 早餐便宜，午晚餐贵
                    if hour <= 9:
                        amount = round(random.uniform(3.0, 10.0), 2)
                        category = "早餐"
                    elif hour <= 14:
                        amount = round(random.uniform(8.0, 22.0), 2)
                        category = "午餐"
                    else:
                        amount = round(random.uniform(8.0, 25.0), 2)
                        category = "晚餐"

                    rows.append({
                        "student_id": sid, "date": str(d),
                        "time": f"{hour:02d}:{minute:02d}:00",
                        "canteen": canteen, "amount": amount, "category": category,
                    })

        self._write_csv(cfg.DATA_FILES["consumption"], rows)
        print(f"[OK] 消费数据: {len(rows)} 条流水")

    # ═══════════════════ 教室 ═══════════════════

    def generate_classrooms(self):
        rows = []
        for bldg, info in BUILDINGS.items():
            for f in range(1, info["floors"] + 1):
                for r in range(1, info["rooms_per_floor"] + 1):
                    room = info["room_format"].format(b=bldg, f=f, r=r)
                    # 不同教学楼不同容量
                    if "实验" in bldg:
                        capacity = random.choice([30, 50, 60])
                    elif bldg == "逸夫楼":
                        capacity = random.choice([60, 90, 120, 200])
                    elif "综合" in bldg:
                        capacity = random.choice([90, 120, 200])
                    else:
                        capacity = random.choice([30, 60, 90, 120])

                    rows.append({
                        "room_id": room, "building": bldg, "floor": f,
                        "capacity": capacity,
                        "has_projector": random.choices([True, False], [0.85, 0.15])[0],
                        "has_ac": random.choices([True, False], [0.7, 0.3])[0],
                    })

        self._write_csv(cfg.DATA_FILES["classrooms"], rows)
        print(f"[OK] 教室数据: {len(rows)} 间")

    # ═══════════════════ 通知 ═══════════════════

    def generate_notices(self):
        notices = []
        today = date.today()
        titles = [
            ("学术讲座", ["张明华教授：《人工智能前沿与数学基础》学术报告",
                          "清华大学刘云浩教授来校作《物联网与边缘计算》讲座",
                          "中国社科院李教授：《数字时代的文化传播》"]),
            ("竞赛通知", ["关于举办2026年全国大学生数学建模竞赛校内选拔赛的通知",
                          "蓝桥杯程序设计竞赛报名通知", "互联网+创新创业大赛校内赛通知"]),
            ("教务通知", ["关于2026年春季学期期末考试安排的通知",
                          "2025-2026学年第二学期选课通知", "关于辅修专业报名的通知"]),
            ("社团活动", ["计算机协会：Python数据分析工作坊报名",
                          "数学建模社第一次培训通知", "英语角：外教口语交流活动"]),
            ("活动预告", ["衡水学院校园文化艺术节活动预告", "五四青年节系列活动安排",
                          "毕业季跳蚤市场活动通知"]),
            ("奖学金", ["关于评选2026年国家奖学金的通知", "省政府奖学金评审结果公示"]),
            ("考试通知", ["全国大学英语四六级考试报名通知", "2026年考研公共课辅导班开班通知"]),
        ]

        for i in range(40):
            ntype, tlist = random.choice(titles)
            title = random.choice(tlist)
            notice_date = today - timedelta(days=random.randint(0, 60))
            notices.append({
                "id": f"N{i:04d}", "title": title, "type": ntype,
                "date": str(notice_date),
                "source": random.choice(["教务处", "学生处", "团委", "各学院", "图书馆"]),
                "content": f"请同学们及时关注。详情请查看学校官网或相关通知公告栏。",
            })

        with open(cfg.DATA_FILES["notices"], "w", encoding="utf-8") as f:
            json.dump(notices, f, ensure_ascii=False, indent=2)
        print(f"[OK] 通知数据: {len(notices)} 条")

    # ═══════════════════ 竞赛 ═══════════════════

    def generate_competitions(self):
        comps = []
        today = date.today()
        for i, (name, level, org, days) in enumerate(COMPETITIONS):
            comps.append({
                "id": f"COMP{i:04d}", "name": name, "level": level,
                "organizer": org,
                "deadline": str(today + timedelta(days=days)),
                "tags": random.sample(["编程", "数学", "英语", "创新", "团队", "个人", "实验", "演讲", "设计"], 3),
                "description": f"2026年{name}现已启动报名",
            })

        with open(cfg.DATA_FILES["competitions"], "w", encoding="utf-8") as f:
            json.dump(comps, f, ensure_ascii=False, indent=2)
        print(f"[OK] 竞赛数据: {len(comps)} 条")

    # ═══════════════════ 运行 ═══════════════════

    def generate_all(self):
        print("=" * 50)
        print("衡水学院 校园数据生成器")
        print("=" * 50)
        self.generate_courses()
        self.generate_consumption()
        self.generate_classrooms()
        self.generate_notices()
        self.generate_competitions()
        print("=" * 50)
        print("全部生成完成。学生登录后无需提供任何数据。")

    def _write_csv(self, path: Path, rows: list[dict]):
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    gen = CampusDataGenerator()
    gen.generate_all()
