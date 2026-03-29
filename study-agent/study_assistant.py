#!/usr/bin/env python3
"""
study-agent 合规版学习助手

功能：
1. 登录平台
2. 导出课程列表与完成状态
3. 打开单个课程页面，由用户自行观看
4. 生成本地学习计划
5. 自动筛出未完成课程
6. 生成今日学习清单
7. 生成复查提醒与考试准备清单

明确不做：
- 伪造学习进度
- 自动代看视频
- 批量替代用户观看
- 自动提交学习时长
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import requests

BASE_URL = "https://stu.5zk.com.cn/zk8exam"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL + "/",
}
WORKDIR = Path(__file__).resolve().parent
STATE_FILE = WORKDIR / "study_state.json"
REPORT_FILE = WORKDIR / "study_report.md"
PLAN_FILE = WORKDIR / "study_plan.md"
TODAY_FILE = WORKDIR / "study_today.md"
REVIEW_FILE = WORKDIR / "study_review_checklist.md"
EXAM_FILE = WORKDIR / "exam_prep.md"


@dataclass
class Course:
    code: str
    title: str
    course_type: str
    status: str
    url: str


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def login(session: requests.Session, username: str, password: str) -> bool:
    resp = session.get(f"{BASE_URL}/login.php", timeout=20)
    resp.raise_for_status()

    form_data = {}
    for name in re.findall(r'<input[^>]+name="([^"]+)"[^>]*>', resp.text):
        form_data[name] = ""

    form_data.update({
        "admin_name": username,
        "admin_password": password,
        "s_or_t": "1",
        "auth_code": "",
    })

    login_resp = session.post(
        f"{BASE_URL}/check_login.php",
        data=form_data,
        headers={**HEADERS, "Referer": f"{BASE_URL}/login.php"},
        allow_redirects=True,
        timeout=20,
    )
    login_resp.raise_for_status()
    return "login.php" not in login_resp.url


def extract_title_near_code(html: str, code: str) -> str:
    patterns = [
        rf"{re.escape(code)}[^\n\r<]{{0,80}}",
        rf">\s*([^<]*{re.escape(code)}[^<]*)<",
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            text = m.group(0) if m.lastindex is None else m.group(1)
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                return text[:120]
    return code


def detect_status(fragment: str) -> str:
    text = fragment.lower()
    if any(x in text for x in ["已完成", "完成", "100%", "已学完"]):
        return "completed"
    if any(x in text for x in ["进行中", "学习中", "%"]):
        return "in_progress"
    return "unknown"


def get_courses(session: requests.Session) -> List[Course]:
    resp = session.get(f"{BASE_URL}/mycourse.php", timeout=20)
    resp.raise_for_status()
    html = resp.text

    courses: List[Course] = []
    seen = set()

    for code in re.findall(r"gotoxx\('1','([^']+)'\)", html):
        if code in seen or code.endswith("_L"):
            continue
        seen.add(code)
        title = extract_title_near_code(html, code)
        courses.append(Course(
            code=code,
            title=title,
            course_type="normal",
            status="unknown",
            url=f"{BASE_URL}/jp_wiki_study.php?kcdm={code}",
        ))

    for code in re.findall(r"live\.php\?kcdm=([^\"'<\s]+)", html):
        if code in seen:
            continue
        seen.add(code)
        title = extract_title_near_code(html, code)
        courses.append(Course(
            code=code,
            title=title,
            course_type="live",
            status="unknown",
            url=f"{BASE_URL}/live.php?kcdm={code}",
        ))

    enriched = []
    for course in courses:
        idx = html.find(course.code)
        fragment = html[max(0, idx - 120): idx + 240] if idx >= 0 else ""
        course.status = detect_status(fragment)
        enriched.append(course)

    return enriched


def save_state(courses: List[Course]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(courses),
        "courses": [asdict(c) for c in courses],
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def split_courses(courses: List[Course]):
    completed = [c for c in courses if c.status == "completed"]
    in_progress = [c for c in courses if c.status == "in_progress"]
    remaining = [c for c in courses if c.status != "completed"]
    unknown = [c for c in courses if c.status == "unknown"]
    return completed, in_progress, remaining, unknown


def course_line(c: Course) -> str:
    return f"- {c.code} | {c.title} | {c.course_type} | {c.status}"


def write_report(courses: List[Course]) -> None:
    total = len(courses)
    completed, in_progress, remaining, unknown = split_courses(courses)

    lines = [
        "# 学习进度报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 课程总数：{total}",
        f"- 已完成：{len(completed)}",
        f"- 进行中：{len(in_progress)}",
        f"- 未完成：{len(remaining)}",
        f"- 未识别：{len(unknown)}",
        "",
        "## 未完成课程（优先处理）",
        "",
    ]

    if remaining:
        lines.extend(course_line(c) for c in remaining)
    else:
        lines.append("- 无")

    lines.extend(["", "## 已完成课程", ""])
    if completed:
        lines.extend(course_line(c) for c in completed)
    else:
        lines.append("- 无")

    lines.extend(["", "## 全部课程详情", ""])
    for i, c in enumerate(courses, 1):
        lines.extend([
            f"### {i}. {c.code}",
            f"- 标题：{c.title}",
            f"- 类型：{c.course_type}",
            f"- 状态：{c.status}",
            f"- 链接：{c.url}",
            "",
        ])

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def open_course(courses: List[Course], code: str) -> int:
    target = next((c for c in courses if c.code == code), None)
    if not target:
        print(f"未找到课程：{code}")
        return 1
    webbrowser.open(target.url)
    print(f"已打开课程：{target.code} -> {target.url}")
    print("看完后建议执行：python3 study_assistant.py review --course " + target.code)
    return 0


def build_plan(courses: List[Course], hours_per_day: float) -> str:
    _, _, remaining, _ = split_courses(courses)
    per_course_hours = 1.0
    total_hours = len(remaining) * per_course_hours
    if hours_per_day <= 0:
        hours_per_day = 1
    days = max(1, int((total_hours + hours_per_day - 1) // hours_per_day))
    finish = datetime.now().date() + timedelta(days=days - 1)

    lines = [
        "# 学习计划",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 剩余课程数：{len(remaining)}",
        f"- 估算剩余学习时长：{total_hours:.1f} 小时（按每门约 1 小时粗估）",
        f"- 每天投入：{hours_per_day:.1f} 小时",
        f"- 预计完成日期：{finish.isoformat()}",
        "",
        "## 建议执行方式",
        "",
        "1. 每次只打开一门课程，完整观看。",
        "2. 看完后执行 review 命令做状态复查。",
        "3. 每天结束前执行一次 export，更新总体报告。",
        "4. 全部课程完成后再进入考试准备。",
        "",
        "## 剩余课程",
        "",
    ]

    if remaining:
        lines.extend(course_line(c) for c in remaining)
    else:
        lines.append("- 已全部完成")

    return "\n".join(lines)


def build_today(courses: List[Course], max_courses: int) -> str:
    _, in_progress, remaining, unknown = split_courses(courses)
    prioritized = in_progress + [c for c in remaining if c not in in_progress]
    selected = prioritized[:max_courses]

    lines = [
        "# 今日学习清单",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 今日建议学习门数：{len(selected)}",
        "",
        "## 今日优先顺序",
        "",
    ]

    if selected:
        for i, c in enumerate(selected, 1):
            lines.extend([
                f"### {i}. {c.code}",
                f"- 标题：{c.title}",
                f"- 类型：{c.course_type}",
                f"- 当前状态：{c.status}",
                f"- 打开命令：`python3 study_assistant.py open --course {c.code}`",
                f"- 看完复查：`python3 study_assistant.py review --course {c.code}`",
                "",
            ])
    else:
        lines.append("- 今天没有待学习课程")

    lines.extend([
        "## 复查提醒",
        "",
        "- 每看完一门，立刻运行 review 命令",
        "- 如果平台状态未更新，稍等几分钟后重新 export",
        "- 晚上统一再做一次 export，确认当天学习结果",
        "",
        "## 未识别状态课程",
        "",
    ])

    if unknown:
        lines.extend(course_line(c) for c in unknown)
    else:
        lines.append("- 无")

    return "\n".join(lines)


def build_review(courses: List[Course], code: str) -> str:
    target = next((c for c in courses if c.code == code), None)
    if not target:
        return f"未找到课程：{code}"

    lines = [
        "# 学习完成后复查清单",
        "",
        f"- 课程：{target.code} | {target.title}",
        f"- 当前识别状态：{target.status}",
        f"- 链接：{target.url}",
        "",
        "## 复查步骤",
        "",
        "1. 回到平台课程列表页面，手动刷新一次。",
        "2. 确认该课程是否显示已完成或进度变化。",
        "3. 运行 `python3 study_assistant.py export` 更新总报告。",
        "4. 若状态未更新，等待几分钟后再次 export。",
        "5. 若多次仍未更新，记录课程代码并手动排查平台记录问题。",
        "",
        "## 下一步",
        "",
        "- 如果已记录完成：开始下一门",
        "- 如果未完成：重新检查是否完整观看、是否平台未刷新",
    ]
    return "\n".join(lines)


def build_exam_prep(courses: List[Course]) -> str:
    completed, _, remaining, _ = split_courses(courses)
    lines = [
        "# 考试准备清单",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 已完成课程数：{len(completed)}",
        f"- 未完成课程数：{len(remaining)}",
        "",
        "## 进入考试前检查",
        "",
        "- [ ] 所有必修课程已显示完成",
        "- [ ] 再执行一次 export，确认最新状态",
        "- [ ] 准备稳定网络和可用浏览器",
        "- [ ] 预留完整考试时间，不中途切换任务",
        "- [ ] 准备纸笔/笔记记录重点",
        "",
        "## 复习建议",
        "",
        "- 先看未完全理解的课程",
        "- 回顾高频概念、关键定义、流程类知识点",
        "- 把每门课程整理成 3-5 条要点",
        "",
        "## 当前未完成课程",
        "",
    ]

    if remaining:
        lines.extend(course_line(c) for c in remaining)
    else:
        lines.append("- 当前看起来已全部完成，可进入考试准备")

    return "\n".join(lines)


def require_creds() -> tuple[str, str]:
    username = os.getenv("STUDY_USERNAME")
    password = os.getenv("STUDY_PASSWORD")
    if not username or not password:
        print("缺少环境变量：STUDY_USERNAME / STUDY_PASSWORD", file=sys.stderr)
        sys.exit(2)
    return username, password


def load_courses_with_login() -> List[Course]:
    username, password = require_creds()
    session = make_session()
    if not login(session, username, password):
        print("登录失败，请检查账号密码。", file=sys.stderr)
        sys.exit(1)
    courses = get_courses(session)
    save_state(courses)
    write_report(courses)
    return courses


def main() -> int:
    parser = argparse.ArgumentParser(description="study-agent 合规版学习助手")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("export", help="导出课程状态")

    open_parser = sub.add_parser("open", help="打开单个课程页面")
    open_parser.add_argument("--course", required=True, help="课程代码，例如 P10001")

    plan_parser = sub.add_parser("plan", help="生成学习计划")
    plan_parser.add_argument("--hours-per-day", type=float, default=2.0)

    today_parser = sub.add_parser("today", help="生成今日学习清单")
    today_parser.add_argument("--max-courses", type=int, default=3)

    review_parser = sub.add_parser("review", help="生成看完一门后的复查清单")
    review_parser.add_argument("--course", required=True)

    sub.add_parser("exam", help="生成考试准备清单")
    sub.add_parser("remaining", help="输出未完成课程")

    args = parser.parse_args()
    courses = load_courses_with_login()

    if args.command == "export":
        print(f"已导出 {len(courses)} 门课程")
        print(f"- {STATE_FILE}")
        print(f"- {REPORT_FILE}")
        return 0

    if args.command == "open":
        return open_course(courses, args.course)

    if args.command == "plan":
        text = build_plan(courses, args.hours_per_day)
        PLAN_FILE.write_text(text, encoding="utf-8")
        print(text)
        print(f"\n计划已写入：{PLAN_FILE}")
        return 0

    if args.command == "today":
        text = build_today(courses, args.max_courses)
        TODAY_FILE.write_text(text, encoding="utf-8")
        print(text)
        print(f"\n今日清单已写入：{TODAY_FILE}")
        return 0

    if args.command == "review":
        text = build_review(courses, args.course)
        REVIEW_FILE.write_text(text, encoding="utf-8")
        print(text)
        print(f"\n复查清单已写入：{REVIEW_FILE}")
        return 0

    if args.command == "exam":
        text = build_exam_prep(courses)
        EXAM_FILE.write_text(text, encoding="utf-8")
        print(text)
        print(f"\n考试准备清单已写入：{EXAM_FILE}")
        return 0

    if args.command == "remaining":
        _, _, remaining, _ = split_courses(courses)
        if remaining:
            for c in remaining:
                print(course_line(c))
        else:
            print("- 已全部完成")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
