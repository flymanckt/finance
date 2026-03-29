# runtime

## 文件说明
- `finance_monitor.py`：抓取行情并生成盘前/盘中/收盘消息
- `run_finance_cycle.sh`：执行一次 finance 监控并通过 Feishu 发送结果
- `last_snapshot.json`：上次快照，用于识别显著变化
- `review-ledger-live.md`：运行期实时台账

## 用法
```bash
bash /home/kent/.openclaw/workspace/stock-agent/runtime/run_finance_cycle.sh 盘前
bash /home/kent/.openclaw/workspace/stock-agent/runtime/run_finance_cycle.sh 午间
bash /home/kent/.openclaw/workspace/stock-agent/runtime/run_finance_cycle.sh 收盘
```

## 当前限制
- 使用免费东财接口，适合作为信息辅助，不适合作为高频交易系统
- 当前规则仍以持仓监控和纪律提醒为主
