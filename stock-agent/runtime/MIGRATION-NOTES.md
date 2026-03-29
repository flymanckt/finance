# Migration Notes

## 背景
finance/stock 的真实运行层分成两部分：

1. **Workspace 设计层**
   - `/home/kent/.openclaw/workspace/stock-agent/*`
   - 存放工作流、模板、数据文件、运行脚本

2. **OpenClaw 运行层**
   - `/home/kent/.openclaw/agents/stock/agent/prompt.md`
   - `/home/kent/.openclaw/cron/jobs.json`
   - 真正决定 agent 提示词和定时任务

## 本次已完成迁移
- 已将新 finance prompt 写入运行层
- 已新增 runtime 脚本作为可调用执行器
- 已把盘前/午间/收盘任务写入 cron jobs

## 后续维护原则
1. 先改 workspace 下的 finance 文档与脚本
2. 再同步关键 prompt / 调度到 `~/.openclaw/agents` 与 `~/.openclaw/cron`
3. 每次改完至少做一次手动 dry-run
4. 若后续换数据源，优先改 `runtime/finance_monitor.py`
