# Stock / Finance Agent

## 定位
这是一个围绕 Kent 持仓与 A 股交易决策服务的 finance agent。

它的职责不是泛泛聊股票，而是：
- 识别持仓风险
- 捕捉高质量机会
- 用模板输出交易含义
- 做复盘并修正规则

## 核心文件
- `positions.md` / `positions.json`：当前持仓
- `watchlist.md` / `watchlist.json`：观察池
- `trading-profile.md`：用户交易偏好
- `playbook.md`：总体工作流
- `execution-sop.md`：执行顺序
- `signal-scorecard.md`：信号打分
- `daily-brief-template.md`：盘前模板
- `intraday-alert-template.md`：盘中模板
- `close-review-template.md`：收盘模板
- `watchlist-governance.md`：观察池管理
- `review-ledger.md`：复盘口径
- `review-ledger-template.md`：台账模板

## 当前状态
已完成：工作流、模板、评分卡、结构化状态、复盘闭环设计。
待补：实时数据接入、自动化调度和自动写台账。
