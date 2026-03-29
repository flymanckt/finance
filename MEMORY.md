# MEMORY.md - 长期记忆（索引）

按主题拆分，详见 `memory/` 目录：

| 文件 | 内容 |
|------|------|
| [user-profile.md](memory/user-profile.md) | 用户画像、Kent 偏好、贾维斯性格 |
| [system-config.md](memory/system-config.md) | 系统配置、记忆系统、Cron 调度、自选股 |
| [projects.md](memory/projects.md) | 项目进展、技能安装记录 |

---

## 当前应长期保留的重点

### 用户与风格
- 用户是 Kent，偏好全程中文、先结论后细节、少客套、实用优先。
- 助手身份是“贾维斯”，风格应冷静、直接、逻辑优先。

### 系统与自动化
- A 股监控已存在一套 finance agent 定时任务，交易时段按计划推送。
- DAILY_WRAPUP 曾因 isolated session 无法访问 `sessions_history` 失败，相关设计需调整。

### 投资相关
- 当前持仓与跟踪重点见 `memory/system-config.md` / 相关 daily memory。
- 嘉美包装（002969）在 2026-03-27 出现要约收购利好，止损位 23.5 元。

---

## 不应长期保留的内容处理原则
- 一次性任务、临时故障、短期项目过程，留在 `memory/YYYY-MM-DD.md`
- 稳定规则进入 `AGENTS.md` / 对应 skill
- 环境事实进入 `TOOLS.md`

---
*由贾维斯维护 | 2026-03-29 清理版*
