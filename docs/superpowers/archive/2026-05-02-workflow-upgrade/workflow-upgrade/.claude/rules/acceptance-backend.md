# 后端验收标准

---
applies_to: "backend/app/**/*.py,backend/app/api/**,backend/app/services/**,backend/app/models/**,executor/**/*.py,plugins/**/*.py"
stack: "Python 3.11+ / FastAPI / SQLAlchemy / Alembic / Pytest"
---

## 非 AI 类接口
- 预期正常结果测试
- 预期异常结果测试

## AI 类接口
带入复杂任务场景，测两种能力：

### 决策能力
- 提示词能否让 AI 完成复杂任务
- 上下文是否足够
- 约束条件是否合理

### 执行能力
- 工具调用后能否得到 AI 预期的结果

### 复杂场景
必须设计刁钻 prompt 测决策边界，不能只跑 happy path。

## 触发规则
- 涉及前端 → 跑前端 Playwright 验收
- 涉及后端 → 跑后端测试
- 模块级任务 → 两边都跑
