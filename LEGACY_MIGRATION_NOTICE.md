# Legacy Migration Notice

## 状态
此仓库（`flymanckt/finance`）已不再作为主维护仓库。

原因：历史上该仓库混入了整个 OpenClaw workspace 结构，不再适合作为独立 agent 仓库继续维护。

## 新的主维护仓库
以后请改为使用：

```bash
git@github.com:flymanckt/main-agent.git
```

本地主维护目录：

```bash
/home/kent/repos/main-agent
```

## 迁移说明
- `finance` 仓库：保留为 legacy / 历史归档用途
- `main-agent` 仓库：作为后续主维护仓库
- 后续新增功能、修复、文档更新，默认只进入 `main-agent`

## 不建议继续做的事
不要再从以下目录将 workspace 根内容推到 `finance` 仓库：

```bash
/home/kent/.openclaw/workspace
```

## 建议操作
如需继续开发，请使用：

```bash
cd /home/kent/repos/main-agent
git pull --rebase
git status
```

## 备注
该 legacy 仓库保留现有历史，不做强制改写，以避免破坏已有提交记录。
