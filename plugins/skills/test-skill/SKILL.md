---
name: test-skill
description: "用于测试的示例 Skill"
triggers:
  - "测试"
  - "test"
hooks:
  PreToolUse:
    - type: command
      matcher: "web_search"
      command: "echo ok"
  SubAgentStart:
    - type: command
      command: "echo should be ignored in phase 1"
---

# Test Skill

这是测试 Skill 的完整内容。
