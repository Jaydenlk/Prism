# 前端验收标准

---
applies_to: "frontend/*.html,frontend/*.js,frontend/*.css,frontend/**/*.html,frontend/**/*.js"
stack: "Vanilla HTML5 + JavaScript (无框架);E2E 用 e2e/ 下的 @playwright/test runtime"
---

## 工具
Playwright，直接操作浏览器（不是写测试脚本）

## 设备覆盖
桌面端 + 移动端都要尽可能测，切换视口验证响应式

## 交互覆盖（完全模拟人）
- 每个按钮点一遍
- 每段输入敲一遍
- 每次跳转走一遍
- UI 看了 UX 也要看（文字/内容是否符合当前场景）

## 场景覆盖
1. **正常流程**：整条业务链路跑通
2. **边界/异常**：预期内的异常是否被正确拦截

## 找茬思维
搜罗失败，不是确认成功。文字内容场景错配也算 bug。
