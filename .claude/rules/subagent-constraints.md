# Subagent 约束与通信协议

## 派单规则

主 agent 向子 agent 派单时，**必须**附带以下信息：

```
任务描述: [一句话说清楚要做什么]
输入文件范围: [只列出子 agent 需要读的文件/目录]
禁止触碰: [明确列出不允许读写的范围]
产出预期: [期望子 agent 输出什么，写到哪里]
决策上下文: [从 decisions.md 中提炼出与本任务相关的已有决策，特别是已排除的方案]
```

**不允许**：
- 把完整 CLAUDE.md 或 decisions.md 丢给子 agent 自己读
- 让子 agent "先探索一下再说"
- 派单时不限定文件范围

## 通信机制：文件状态机

子 agent 之间**不通过上下文传递信息**，通过 `.claude/plans/` 下的文件通信。

### 流转状态
```
READY_FOR_ARCH → READY_FOR_IMPL → READY_FOR_REVIEW → READY_FOR_QA → DONE
```

### Handoff 文件格式

每个子任务在 `.claude/plans/` 下有一个 handoff 文件，命名规则：`handoff-{from}-to-{to}-{topic}.md`

```markdown
# Handoff: {from} → {to}

## 状态: READY_FOR_{NEXT}
## 任务: {一句话}
## 输入文件: {列表}
## 已完成:
- {完成项 1}
- {完成项 2}
## 产出物:
- {文件路径}: {简要说明}
## 遗留问题:
- {如有}
## 相关决策:
- DEC-{ID}: {摘要}（详见 decisions.md）
```

### 规则
1. 子 agent 启动时**只读自己的 handoff 文件**，不读其他 agent 的 handoff
2. 子 agent 完成后**必须更新自己的 handoff 文件**，写清楚产出物和遗留问题
3. 主 agent 在两个子 agent 之间做桥接——读上一个的产出，提炼后写入下一个的 handoff

## 文件读取纪律

1. **读文件前先用 Grep/Glob 确认目标**，不允许"先读再看有没有用"
2. **读超过 3 个不相关文件→停下来重新评估路径**，大概率已经偏离任务
3. **已读文件不重复读**。如果需要回看，引用之前的读取内容或向主 agent 请求
4. **大文件先看结构**。超过 200 行的文件，先读前 30 行了解结构，确认需要后再读具体段落

## 子 agent 行为红线

1. 不做任务描述之外的事。发现问题→记录到 handoff 文件的"遗留问题"里，不当场修
2. 不修改 `.claude/memory/decisions.md`。决策记录只有主 agent 有权写入
3. 不读其他子 agent 的 handoff 文件或产出物
4. 不启动新的子 agent（子 agent 不可嵌套）
5. 完成后输出精简摘要，不输出探索过程
