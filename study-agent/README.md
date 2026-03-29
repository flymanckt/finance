# study-agent（合规版）

## 结论
这个目录里原先包含大量**非合规自动刷课/批量代看**脚本。
现在起，本项目的推荐入口改为：`study_assistant.py`。

## 合规边界
允许：
- 登录状态检查
- 课程列表抓取
- 学习进度读取
- 打开单个课程页面让用户自己观看
- 本地学习计划/提醒/统计
- 考试准备清单

不允许：
- 伪造学习时长
- 批量自动播放并代替本人观看
- 自动提交/伪造进度
- 绕过平台限制或风控

## 推荐用法
### 1. 导出课程与进度
```bash
python3 study_assistant.py export
```
输出：
- `study_state.json`
- `study_report.md`

### 2. 打开某个课程页面（自己观看）
```bash
python3 study_assistant.py open --course P10001
```

### 3. 生成学习计划
```bash
python3 study_assistant.py plan --hours-per-day 2
```

## 说明
- 默认不保存密码到代码里。
- 账号密码建议通过环境变量传入：
  - `STUDY_USERNAME`
  - `STUDY_PASSWORD`
- 如果平台页面结构变了，需要重新适配选择器/正则。
