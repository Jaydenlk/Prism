# Scratchpad

> 临时共享状态。主 agent 和子 agent 都可以写入。
> 用于记录"发现了但当前不处理"的问题，避免打断当前任务流。
> 每个任务完成后由主 agent 清理：已处理的删除，需要跟进的转移到 plans 或 decisions。

## 格式

```
- [{日期}] [{发现者: main/implementer/reviewer/qa}] {内容}
```

---

<!-- 以下为实际记录 -->
