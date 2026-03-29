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

## 现在已补齐的闭环能力
- 导出课程与状态
- 自动列出未完成课程
- 生成每日学习清单
- 打开单门课程
- 看完后生成复查清单
- 生成总体学习计划
- 生成考试准备清单

## 推荐用法
### 0. 先配置账号密码
```bash
export STUDY_USERNAME='你的账号'
export STUDY_PASSWORD='你的密码'
```

### 1. 导出课程与进度
```bash
python3 study_assistant.py export
```
输出：
- `study_state.json`
- `study_report.md`

### 2. 查看未完成课程
```bash
python3 study_assistant.py remaining
```

### 3. 生成今日学习清单
```bash
python3 study_assistant.py today --max-courses 3
```
输出：
- `study_today.md`

### 4. 打开某个课程页面（自己观看）
```bash
python3 study_assistant.py open --course P10001
```

### 5. 看完后做复查
```bash
python3 study_assistant.py review --course P10001
```
输出：
- `study_review_checklist.md`

### 6. 生成学习计划
```bash
python3 study_assistant.py plan --hours-per-day 2
```
输出：
- `study_plan.md`

### 7. 生成考试准备清单
```bash
python3 study_assistant.py exam
```
输出：
- `exam_prep.md`

## 建议工作流
```text
export -> remaining -> today -> open 某门 -> 自己看完 -> review -> export -> 下一门 -> exam
```

## 说明
- 默认不保存密码到代码里。
- 账号密码建议通过环境变量传入：
  - `STUDY_USERNAME`
  - `STUDY_PASSWORD`
- 如果平台页面结构变了，需要重新适配选择器/正则。
