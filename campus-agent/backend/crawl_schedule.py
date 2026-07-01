"""
爬取高校教师教务系统全校课表（教室课表视图）
输出: data/courses.csv (student_id, course_name, teacher, weekday, period_start, period_end, location, weeks)
"""

import requests
import csv
import random
import time
import os
import hashlib
from collections import defaultdict

import os
BASE = os.getenv("CRAWL_BASE_URL", "http://your-school-system.edu.cn")
COOKIES = {
    "admin.urpSoft.cn": os.getenv("CRAWL_COOKIE_ADMIN", ""),
    "selectionBar": os.getenv("CRAWL_COOKIE_BAR", "")
}
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/teacherIndex",
    "User-Agent": "Mozilla/5.0"
}
PLAN = "2025-2026-2-1"
CAMPUSES = [
    ("001", "本部"),
    ("003", "西校区"),
    ("004", "东校区"),
]

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "courses.csv")

def get_json(url, params=None):
    """发起请求并解析JSON"""
    try:
        r = requests.get(url, params=params, cookies=COOKIES, headers=HEADERS, timeout=30, verify=False)
        r.raise_for_status()
        if not r.text.strip():
            return None
        return r.json()
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None

def get_buildings(campus_code):
    """获取某校区所有教学楼"""
    url = f"{BASE}/{campus_code}/teachingBuildingJson"
    data = get_json(url)
    if not data:
        return []
    buildings = []
    for item in data:
        bn = item["id"]["teachingBuildingNumber"]
        name = item["teachingBuildingName"]
        buildings.append((bn, name))
    print(f"    > 教学楼共 {len(buildings)} 栋: {[n for _, n in buildings]}")
    return buildings

def get_classrooms(campus_code, building_code):
    """获取某教学楼某教室列表，排除虚拟教室"""
    url = f"{BASE}/{campus_code}/{building_code}/classroomJson"
    data = get_json(url)
    if not data:
        return []
    classrooms = []
    for item in data:
        cn = item["id"]["classroomNumber"]
        cname = item.get("classroomName") or ""
        ctype = item.get("classroomTypeCode", "")
        can_schedule = item.get("sfkjy", "否")
        place_num = item.get("placeNum", "0")
        # 排除虚拟教室
        if not cname or "虚拟" in cname or ctype == "21":
            continue
        classrooms.append((cn, cname, can_schedule, place_num))
    return classrooms

def get_schedule(campus_code, building_code, classroom_code):
    """获取某教室的完整课表"""
    url = f"{BASE}/searchCurriculum/callback"
    params = {
        "planNumber": PLAN,
        "campusNumber": campus_code,
        "teachingBuildingNumber": building_code,
        "classroomNumber": classroom_code
    }
    data = get_json(url, params=params)
    if not data:
        return []
    kb_info = data.get("kbInfo", [])
    if not kb_info:
        return []
    return kb_info[0] if isinstance(kb_info, list) and kb_info else []

def parse_weeks(skzc_str):
    """解析周次字符串 '111111111111111100000000' → 周次范围文本"""
    if not skzc_str:
        return ""
    # 找出连续的1的区间
    weeks = []
    i = 0
    while i < len(skzc_str):
        if skzc_str[i] == '1':
            start = i + 1
            while i < len(skzc_str) and skzc_str[i] == '1':
                i += 1
            end = i
            weeks.append((start, end))
        else:
            i += 1
    # 格式化
    parts = []
    for s, e in weeks:
        if s == e:
            parts.append(f"第{s}周")
        else:
            parts.append(f"{s}-{e}周")
    return ",".join(parts) if parts else ""

def generate_student_ids(bjh_str, bm_str, bmrs_str, class_id_map):
    """
    根据班级名生成学生学号
    格式: 入学年份(2位) + 院系代码(2位) + 专业代码(2位) + 序号(3位)
    """
    if not bjh_str and not bm_str:
        return []
    
    # 解析班级名
    raw_classes = bjh_str.split(",") if bjh_str else bm_str.split(",") if bm_str else []
    classes = [c.strip() for c in raw_classes if c.strip()]
    
    # 解析人数
    student_counts = {}
    if bmrs_str:
        parts = bmrs_str.split(",")
        for p in parts:
            p = p.strip()
            if "人" in p:
                name = p.split("(")[0].strip()
                count_str = p.split("(")[1].replace("人", "").replace(")", "").strip()
                try:
                    student_counts[name] = int(count_str)
                except:
                    student_counts[name] = 30
    
    student_ids = []
    for cls in classes:
        if cls in class_id_map:
            student_ids.extend(class_id_map[cls])
            continue
        
        count = student_counts.get(cls, 30)
        # 生成确定性哈希作为班级种子
        h = int(hashlib.md5(cls.encode()).hexdigest()[:8], 16)
        # 入学年份从班级名解析 (如 "24级应用心理学1班" → 24)
        grade = "24"
        if cls[0:2].isdigit():
            grade = cls[0:2]
        
        new_ids = []
        for i in range(min(count, 50)):  # 每班最多50个学号
            dept = (h % 90) + 10  # 10-99
            major = (h // 100) % 90 + 10
            sid = f"{grade}{dept:02d}{major:02d}{i+1:03d}"
            new_ids.append(sid)
        
        class_id_map[cls] = new_ids
        student_ids.extend(new_ids)
    
    return student_ids

def main():
    print("=" * 60)
    print("衡水学院全校课表爬虫 (3校区)")
    print(f"来源: {BASE}")
    print(f"学期: {PLAN}")
    print("=" * 60)
    
    all_courses = []
    total_rooms = 0
    total_courses_count = 0
    skipped_empty = 0
    
    for campus_code, campus_name in CAMPUSES:
        # Step 1: 获取教学楼
        print(f"\n{'='*40}")
        print(f"[校区: {campus_name}] (代码={campus_code})")
        print(f"{'='*40}")
        buildings = get_buildings(campus_code)
        if not buildings:
            print(f"  未获取到教学楼列表，Cookie可能已过期")
            continue
        
        # Step 2: 遍历教室获取课表
        for bcode, bname in buildings:
            classrooms = get_classrooms(campus_code, bcode)
            room_count = len(classrooms)
            total_rooms += room_count
            print(f"\n  [{bname}] (代码={bcode}) - {room_count} 间教室")
            
            for ccode, cname, can_schedule, place_num in classrooms:
                courses = get_schedule(campus_code, bcode, ccode)
                if not courses:
                    skipped_empty += 1
                    continue
                
                for c in courses:
                    skxq = c.get("id", {}).get("skxq", 0)
                    skjc = c.get("id", {}).get("skjc", 0)
                    cxjc = c.get("cxjc", 1)
                    skzc = c.get("id", {}).get("skzc", "")
                    
                    course = {
                        "course_name": c.get("kcm", ""),
                        "teacher": c.get("jsm", ""),
                        "weekday": skxq,
                        "period_start": skjc,
                        "period_end": skjc + cxjc - 1 if skjc and cxjc else skjc,
                        "location": f"{bname} {ccode}",
                        "weeks": parse_weeks(skzc) if skzc else c.get("zcsm", ""),
                        "class_name": c.get("bm", c.get("bjh", "")),
                        "credit": c.get("xf", ""),
                        "exam_type": c.get("kslxmc", ""),
                        "student_count": c.get("xss", 0),
                        "department": c.get("kkxsm", ""),
                    }
                    all_courses.append(course)
                    total_courses_count += 1
                
            time.sleep(0.3)  # 礼貌间隔
    
    print(f"\n  共查询 {total_rooms} 间教室, {skipped_empty} 间无课, 获取 {total_courses_count} 条课程记录")
    
    # Step 3: 生成学生-课程映射 → CSV
    print("\n[3/3] 生成 courses.csv...")
    class_id_map = {}
    rows = []
    
    for course in all_courses:
        class_names = course.get("class_name", "")
        if not class_names:
            # 无班级信息的课(如公选课)也保留，学号用虚拟
            sid = f"990000{len(rows)+1:03d}"
            rows.append({
                "student_id": sid,
                "course_name": course["course_name"],
                "teacher": course["teacher"],
                "weekday": course["weekday"],
                "period_start": course["period_start"],
                "period_end": course["period_end"],
                "location": course["location"],
                "weeks": course["weeks"],
            })
            continue
        
        # 为每个班级生成学号
        student_ids = generate_student_ids(
            class_names, class_names, "", class_id_map
        )
        
        if not student_ids:
            sid = f"990000{len(rows)+1:03d}"
            rows.append({
                "student_id": sid,
                "course_name": course["course_name"],
                "teacher": course["teacher"],
                "weekday": course["weekday"],
                "period_start": course["period_start"],
                "period_end": course["period_end"],
                "location": course["location"],
                "weeks": course["weeks"],
            })
            continue
        
        for sid in student_ids:
            rows.append({
                "student_id": sid,
                "course_name": course["course_name"],
                "teacher": course["teacher"],
                "weekday": course["weekday"],
                "period_start": course["period_start"],
                "period_end": course["period_end"],
                "location": course["location"],
                "weeks": course["weeks"],
            })
    
    # 去重
    seen = set()
    unique_rows = []
    for r in rows:
        key = (r["student_id"], r["course_name"], r["weekday"], r["period_start"], r["period_end"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)
    
    # 写入CSV
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    fieldnames = ["student_id", "course_name", "teacher", "weekday", "period_start", "period_end", "location", "weeks"]
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_rows)
    
    # 统计
    unique_students = len(set(r["student_id"] for r in unique_rows))
    unique_courses = len(set(r["course_name"] for r in unique_rows))
    unique_teachers = len(set(r["teacher"] for r in unique_rows if r["teacher"]))
    
    print(f"\n{'='*60}")
    print(f"爬取完成!")
    print(f"  原始课程记录: {total_courses_count}")
    print(f"  去重后记录:   {len(unique_rows)}")
    print(f"  覆盖学生数:   {unique_students}")
    print(f"  不重复课程:   {unique_courses}")
    print(f"  不重复教师:   {unique_teachers}")
    print(f"  输出文件:     {OUTPUT}")
    print(f"{'='*60}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
