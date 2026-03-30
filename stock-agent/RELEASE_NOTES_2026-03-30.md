# Finance Release Notes — 2026-03-30

## 版本结论
本次版本将 finance 从“可运行原型”升级为“可用的实盘辅助版”。

## 主要更新

### 1. Feishu 推送链路修复
- 修复 finance 与 main 混用导致的错误路由
- 修复 Feishu 跨应用 `open_id` 问题
- finance 机器人私聊链路验证通过

### 2. 数据质量修复
- 修复东财价格字段归一化问题
- 增加行情异常值识别与数据质量分级
- 避免脏数据直接触发强结论

### 3. 双数据源框架
- 保留 Eastmoney 作为快路径数据源
- 接入 AkShare 作为增强数据源
- 支持按模式启用数据源

### 4. 模型解释层接入
- 接入 `minimax/MiniMax-M2.7` 作为摘要/解释层
- 保持规则先行，模型不直接裸做行情判断
- `openai-codex/gpt-5.2` 作为深度复盘推荐模型

### 5. 性能优化
- 巡检/午间默认禁用重型 AkShare 路径
- 仅在盘前/收盘启用 AkShare 与 LLM 总结
- 增加 AkShare 本地缓存文件
- 巡检实测耗时已压到约 1.8 秒

## 当前能力边界
### 已具备
- 持仓风险监控
- 盘前/午间/收盘结构化输出
- 止损优先的风控提醒
- 数据质量提示
- Finance 私聊机器人推送

### 暂未具备
- 公告/新闻自动抓取
- 板块/资金流联动判断
- 高频盘中秒级响应
- 全自动交易执行

## 推荐使用方式
- 巡检/午间：走快路径，优先风险提醒
- 盘前/收盘：走完整路径，允许 AkShare + MiniMax 总结
- 深度复盘：建议单独使用 `openai-codex/gpt-5.2`

## 相关提交
- `ae1c636` fix(finance): send finance alerts via finance account
- `7a9ede3` fix(finance): point finance cycle to finance-app user id
- `747f65d` feat(finance): improve quote validation and model strategy
- `0a97ff3` feat(finance): add akshare source and minimax summary layer
- `bdae1dc` perf(finance): gate akshare and llm by mode and risk
- `29e6938` perf(finance): cache akshare data and trim runtime latency

## 下一阶段建议
1. 接入公告/新闻源
2. 加板块强弱与资金流
3. 优化收盘复盘口径
4. 将 workspace 根仓库与 finance 仓库彻底拆分，避免误推
