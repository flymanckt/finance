#!/usr/bin/env python3
"""
study-agent 合规版学习助手

功能：
1. 登录平台
2. 导出课程列表与完成状态
3. 打开单个课程页面，由用户自行观看
4. 生成本地学习计划

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
from typing import List, Optional

import requests

BASE_URL = "https://stu.5zk.com.cn/zk8exam"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL + "/",
}
WORKDIR = Path(__file__).resolve().parent
STATE_FILE = WORKDIR / "study_state.json"
REPORT_FILE = WORKDIR / "study_report.md"


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

    # 尝试按局部片段推断状态
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


def write_report(courses: List[Course]) -> None:
    total = len(courses)
    completed = sum(1 for c in courses if c.status == "completed")
    in_progress = sum(1 for c in courses if c.status == "in_progress")
    unknown = total - completed - in_progress

    lines = [
        "# 学习进度报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 课程总数：{total}",
        f"- 已完成：{completed}",
        f"- 进行中：{in_progress}",
        f"- 未识别：{unknown}",
        "",
        "## 课程列表",
        "",
    ]

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
    return 0


def build_plan(courses: List[Course], hours_per_day: float) -> str:
    remaining = [c for c in courses if c.status != "completed"]
    per_course_hours = 1.0
    total_hours = len(remaining) * per_course_hours
    if hours_per_day <= 0:
        hours_per_day = 1
    days = max(1, int((total_hours + hours_per_day - 1) // hours_per_day))
    start = datetime.now().date()
    finish = start + timedelta(days=days - 1)

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
        "2. 看完后刷新课程页确认平台已记录。",
        "3. 每天结束前执行一次 export，更新报告。",
        "4. 全部课程完成后再进入考试准备。",
        "",
        "## 剩余课程",
        "",
    ]

    for i, c in enumerate(remaining, 1):
        lines.append(f"- {i}. {c.code} | {c.title} | {c.course_type} | {c.status}")

    return "\n".join(lines)


def require_creds() -> tuple[str, str]:
    username = os.getenv("STUDY_USERNAME")
    password = os.getenv("STUDY_PASSWORD")
    if not username or not password:
        print("缺少环境变量：STUDY_USERNAME / STUDY_PASSWORD", file=sys.stderr)
        sys.exit(2)
    return username, password


def main() -> int:
    parser = argparse.ArgumentParser(description="study-agent 合规版学习助手")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("export", help="导出课程状态")

    open_parser = sub.add_parser("open", help="打开单个课程页面")
    open_parser.add_argument("--course", required=True, help="课程代码，例如 P10001")

    plan_parser = sub.add_parser("plan", help="生成学习计划")
    plan_parser.add_argument("--hours-per-day", type=float, default=2.0)

    args = parser.parse_args()
    username, password = require_creds()

    session = make_session()
    if not login(session, username, password):
        print("登录失败，请检查账号密码。", file=sys.stderr)
        return 1

    courses = get_courses(session)
    save_state(courses)
    write_report(courses)

    if args.command == "export":
        print(f"已导出 {len(courses)} 门课程")
        print(f"- {STATE_FILE}")
        print(f"- {REPORT_FILE}")
        return 0

    if args.command == "open":
        return open_course(courses, args.course)

    if args.command == "plan":
        text = build_plan(courses, args.hours_per_day)
        plan_file = WORKDIR / "study_plan.md"
        plan_file.write_text(text, encoding="utf-8")
        print(text)
        print(f"\n计划已写入：{plan_file}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
