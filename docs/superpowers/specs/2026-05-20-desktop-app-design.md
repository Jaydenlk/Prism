# Prism Desktop App Design Spec

> Date: 2026-05-20
> Status: Approved, pending implementation
> Framework: Tauri 2
> Platforms: Windows + macOS

## 架构

```
Tauri 2 Shell (Rust + React)
├── 系统托盘常驻
├── 前端: 现有 React dist/ 零改动加载
├── Docker 生命周期管理:
│   ├── 启动时: docker compose up -d
│   ├── 退出时: docker compose down
│   └── 健康监控: 轮询 /health/live
└── 首次引导向导 (React 页面):
    Step 1: 检测 Docker Desktop
    Step 2: 填 API Key
    Step 3: 创建管理员账户 + 邀请码
    Step 4: 自动拉取镜像 + 启动服务
    Step 5: 进入主界面
```

## 功能清单

| 功能 | 说明 |
|---|---|
| 安装器 | Windows .msi/.exe, macOS .dmg |
| 系统托盘 | 最小化到托盘，右键菜单 |
| Docker 管理 | 自动检测/拉起/停止/镜像拉取进度 |
| 首次向导 | 引导式配置 → .env 生成 → 服务启动 |
| 自动更新 | Tauri updater，GitHub Releases |
| 健康监控 | 定时检测，异常托盘变色+通知 |
| 日志查看 | 一键打开 docker compose logs |

## 不改什么

- 后端代码零改动
- 前端 React dist/ 零改动
- 数据库/Redis 全部容器化不变

## 新增文件

| 路径 | 说明 |
|---|---|
| desktop/src-tauri/src/main.rs | Docker 生命周期 + 托盘 + 健康检查 |
| desktop/src/SetupWizard.tsx | 首次引导向导 |
| CI/CD | GitHub Actions 构建 .msi + .dmg |

## 调研结论

Tauri 2 优于 Electron：包体 5MB vs 120MB，系统 WebView，Rust 代码量极少。
Docker 管理通过 shell 插件 Command.create("docker", [...]) 实现。
