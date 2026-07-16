---
name: deepin-autopack
description: Deepin项目自动打包工具。当用户要求打包Deepin项目（如dde-shell、deepin-music等）、查询打包状态、查看提交监控、CRP主题管理时使用。支持指定版本、架构和CRP主题。
metadata: {"openclaw": {"emoji": "📦", "homepage": "http://localhost:5000"}}
---

# Deepin Autopack Skill

通过 REST API 与 Deepin Autopack 系统交互。**所有操作必须通过 API 完成，禁止读取或执行 autopack 源代码。**

API 基础地址: `http://localhost:5000/api/v1`

## 约束规则

1. **只用 API**: 所有查询和操作都通过下面的 REST API 进行，用 `curl` 调用
2. **别看源码**: 不要读取 `/home/ut005580@uos/Dev/deepin-autopack/` 下的任何源文件
3. **不要直接操作数据库**: 不要导入 Flask app 或直接操作 SQLAlchemy
4. **字段名以实际 API 返回为准**: 本文档列出的字段名是实际 API 返回的字段
5. **默认架构**: 不指定架构时使用 `amd64`, `arm64`, `loong64`, `sw64`, `mips64el`
6. **自动选择最新 CRP 主题**: 用户没有明确指定 CRP 主题时，自动选择最新的（列表第一个）
7. **必须返回 PR 链接**: 创建打包任务后，必须轮询状态直到获取 `github_pr_url`，并将 PR 链接告知用户
8. **Changelog PR 需手动合并**: `normal` 和 `changelog_only` 模式会产生 changelog PR，**必须提醒用户去审核并手动合并该 PR**，合并后系统会自动继续后续打包步骤。`crp_only` 和 `github_action` 模式不需要此步骤。告知用户后续可通过 `GET /api/v1/packages/<id>/status` 查询状态
9. **告知版本号**: 创建打包任务时，**必须将版本号告知用户**（无论自动生成还是用户指定），让用户明确知道本次打包使用的版本
10. **不要暴露内部地址**: 回复用户时**禁止**暴露内部 IP、`localhost`、内网 URL（如 `http://localhost:5000`、shuttle 内部地址等）。API 调用在内部完成，但对用户只展示公开可访问的链接（如 GitHub PR 链接、CRP 公开页面等）

---

## API 端点清单

### 监控组

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/monitor/status` | GET | 系统概览（项目数、新增提交数） |
| `/api/v1/monitor/projects` | GET | 所有就绪项目及提交详情 |
| `/api/v1/monitor/refresh` | POST | 后台刷新所有仓库 |

### 打包组

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/packages/create` | POST | 创建并启动打包任务 |
| `/api/v1/packages/<id>/status` | GET | 查询任务状态 |
| `/api/v1/packages/<id>/retry` | POST | 重试失败任务 |
| `/api/v1/packages/list` | GET | 打包任务列表 |

### CRP 主题组

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/crp/topics` | GET | CRP 主题列表（含详情字段） |
| `/api/v1/crp/topics/<id>` | GET | 主题详情 + 包构建列表 |
| `/api/v1/crp/releases/<id>/retry` | POST | 重试单个包的构建 |
| `/api/v1/crp/releases/<id>` | DELETE | 放弃单个包 |
| `/api/v1/crp/builds/<id>/jobs` | GET | 构建的 job 列表（按架构） |
| `/api/v1/crp/builds/<id>/logs/<job_id>` | GET | 单个 job 的构建日志 |
| `/api/v1/crp/builds/<id>/logs/<job_id>/analyze` | POST | AI 分析单个 job 日志 |
| `/api/v1/crp/builds/<id>/analyze` | POST | AI 分析所有失败 job |

### 工具组

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/projects` | GET | 可用项目列表 |
| `/api/v1/crp-topics` | GET | CRP 主题简要列表（仅 id/name） |
| `/api/v1/ai/analyze-commits` | POST | AI 分析提交信息 |

---

## 1. 监控组

### 系统概览

```bash
curl -s http://localhost:5000/api/v1/monitor/status | python3 -m json.tool
```

返回:
```json
{
  "success": true,
  "data": {
    "total_projects": 50,
    "ready_projects": 45,
    "projects_with_new_commits": 12,
    "details": [
      {"id": 1, "name": "dde-shell", "new_commits": 5}
    ]
  }
}
```

### 项目列表（含提交信息）

```bash
curl -s http://localhost:5000/api/v1/monitor/projects | python3 -m json.tool
```

返回字段: `id`, `name`, `github_url`, `github_branch`, `gerrit_branch`, `current_version`, `new_commits_count`, `new_commits` (列表，每项含 `hash`, `author`, `date`, `message`), `latest_commit`

### 刷新所有仓库

```bash
curl -s -X POST http://localhost:5000/api/v1/monitor/refresh | python3 -m json.tool
# → {"success": true, "message": "刷新任务已触发，正在后台执行"}
```

刷新后等待 10-30 秒再拉取 `/api/v1/monitor/projects` 获取最新数据。

---

## 2. 打包组

### 创建打包任务

```bash
# 基础打包（自动取最新 CRP 主题、自动生成版本号）
curl -s -X POST http://localhost:5000/api/v1/packages/create \
  -H "Content-Type: application/json" \
  -d '{"project_name": "dde-shell"}' | python3 -m json.tool

# 带参数
curl -s -X POST http://localhost:5000/api/v1/packages/create \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "deepin-music",
    "version": "6.0.30",
    "architectures": ["amd64", "arm64"],
    "mode": "normal"
  }' | python3 -m json.tool
```

参数:
- `project_name` (必填) - 项目名
- `version` - 版本号（**不指定则自动从 debian/changelog 读取当前版本并 patch+1**，无法自动生成时会报错提示用户手动指定）
- `architectures` - 架构列表（默认 `["amd64", "arm64", "loong64", "sw64", "mips64el"]`）
- `mode` - `normal`(默认) / `changelog_only` / `crp_only` / `github_action`
  - `normal`: 提交 changelog 并 CRP 打包（会修改源码 changelog）
  - `changelog_only`: 仅提交 changelog，不 CRP 打包
  - `crp_only`: 不更改 changelog，直接 CRP 打包。**可指定 `version` 以升版本打包**（CRP 以该版本号作为构建 Tag）；不指定则自动 patch+1
- `crp_topic_id` + `crp_topic_name` - 指定 CRP 主题（**不指定则自动选择最新的 CRP 主题**）

返回:
```json
{
  "success": true,
  "data": {
    "task_id": 123,
    "project_name": "dde-shell",
    "version": "20260527120000",
    "mode": "normal",
    "architectures": ["amd64", "arm64", "loong64", "sw64", "mips64el"],
    "crp_topic_name": "V26开发仓库",
    "status": "running"
  },
  "message": "打包任务已创建并启动: dde-shell v20260527120000"
}
```

**重要:** 创建打包任务后，需要做两件事：
1. **立即告知用户版本号**（自动生成的或用户指定的），让用户知道打包用的是哪个版本
2. **必须**轮询 `/api/v1/packages/<id>/status` 直到获取到 `github_pr_url`，然后将 PR 链接告知用户

**当轮询到 `github_pr_url` 后，按打包模式告知用户：**

- **`normal` / `changelog_only` 模式**: 必须提醒用户去审核 changelog PR 并手动合并：

  > 📦 打包版本: **<version>**
  > 🔗 Changelog PR: <github_pr_url>
  > ⚠️ 请审核 changelog PR 并**手动合并**，合并后我会自动完成后续的打包步骤。
  > 📊 随时可通过 `GET /api/v1/packages/<id>/status` 查询当前打包状态。

- **`crp_only` / `github_action` 模式**: 直接告知版本和 PR 链接即可，无需手动合并。

### 查询任务状态

```bash
curl -s http://localhost:5000/api/v1/packages/123/status | python3 -m json.tool
```

关键字段: `status` (pending/running/paused/success/failed/cancelled), `current_step`, `steps[]` (step_name, status, log_message, error_message), `github_pr_url`, `crp_build_url`, `error_message`

### 重试失败任务

```bash
# 从头重试
curl -s -X POST http://localhost:5000/api/v1/packages/123/retry \
  -H "Content-Type: application/json" -d '{}' | python3 -m json.tool

# 从指定步骤重试
curl -s -X POST http://localhost:5000/api/v1/packages/123/retry \
  -H "Content-Type: application/json" -d '{"from_step": 3}' | python3 -m json.tool
```

### 打包任务列表

```bash
curl -s "http://localhost:5000/api/v1/packages/list?status=failed&limit=10" | python3 -m json.tool
```

参数: `status` (可选筛选), `limit` (默认20)

---

## 3. CRP 主题组

### 主题列表

```bash
curl -s http://localhost:5000/api/v1/crp/topics | python3 -m json.tool
```

返回字段:
```json
{
  "success": true,
  "data": [
    {
      "id": 26037,
      "name": "V25 2500u1 Beta发布紧急推送主题",
      "description": "...",
      "create_time": "2026-05-20",
      "creator_name": "xxx"
    }
  ]
}
```

### 主题详情（含包构建列表）

```bash
curl -s http://localhost:5000/api/v1/crp/topics/26037 | python3 -m json.tool
```

返回:
```json
{
  "success": true,
  "data": {
    "topic": {
      "id": 26037,
      "name": "V25 2500u1 Beta发布紧急推送主题",
      "description": "...",
      "create_time": "...",
      "creator_name": "..."
    },
    "releases": [
      {
        "id": 12345,
        "project_id": 100,
        "project_name": "dde-shell",
        "source_pkg_name": "dde-shell",
        "branch": "master",
        "tag": "20260520",
        "commit": "abc123def456",
        "build_id": 5001,
        "build_state": "UPLOAD_OK",
        "state_label": "构建成功",
        "arches": "amd64;arm64;loongarch64"
      }
    ]
  }
}
```

**重要字段说明:**
- `build_state` - 原始状态值: `UPLOAD_OK`/`SUCCESS`=成功, `UPLOADING`=上传中, `APPLYING`=申请中, `UPLOAD_GIVEUP`=已放弃, `APPLY_FAILED`=申请失败, `UNKNOWN`=未知
- `state_label` - 中文状态标签（如"构建成功"、"上传中"）
- `tag` - 对应 autopack 打包时传入的 version
- `commit` - 构建所用的 commit hash

### 重试构建

```bash
curl -s -X POST http://localhost:5000/api/v1/crp/releases/12345/retry | python3 -m json.tool
# → {"success": true, "message": "已触发重新构建"}
```

### 放弃包

```bash
curl -s -X DELETE http://localhost:5000/api/v1/crp/releases/12345 | python3 -m json.tool
# → {"success": true, "message": "已放弃该包"}
```

---

### 构建日志 & AI 分析

CRP 每个 release 都有一个 `build_id`，对应 Shuttle 上的构建任务。一个构建任务包含多个 job（按架构拆分：amd64, arm64, loong64 等）。

**查看构建的 job 列表：**

```bash
curl -s http://localhost:5000/api/v1/crp/builds/586908/jobs | python3 -m json.tool
```

返回:
```json
{
  "success": true,
  "data": [
    {"job_id": 778933, "arch": "amd64", "status": "FAILED"},
    {"job_id": 778934, "arch": "arm64", "status": "FAILED"}
  ]
}
```

**获取单个 job 的构建日志：**

```bash
curl -s http://localhost:5000/api/v1/crp/builds/586908/logs/778933 | python3 -m json.tool
```

**AI 分析单个 job 日志：**

```bash
curl -s -X POST http://localhost:5000/api/v1/crp/builds/586908/logs/778933/analyze | python3 -m json.tool
```

**AI 分析所有失败的 job（一键分析）：**

```bash
curl -s -X POST http://localhost:5000/api/v1/crp/builds/586908/analyze | python3 -m json.tool
```

返回每个失败架构的分析结果：
```json
{
  "success": true,
  "data": {
    "build_id": 586908,
    "failed_count": 5,
    "total_jobs": 5,
    "analyses": [
      {
        "arch": "amd64",
        "job_id": 778933,
        "analysis": "平台/环境问题 — APT URL 路径过长导致 File name too long..."
      }
    ]
  }
}
```

如果没有失败的 job，返回 `"analysis": null` 和当前所有 job 的状态。

---

## 4. 工具组

### 可用项目列表

```bash
curl -s http://localhost:5000/api/v1/projects | python3 -m json.tool
```

### CRP 主题简要列表

```bash
curl -s http://localhost:5000/api/v1/crp-topics | python3 -m json.tool
# → [{"topic_id": 26037, "topic_name": "V25 Beta主题"}, ...]
```

### AI 分析提交

```bash
curl -s -X POST http://localhost:5000/api/v1/ai/analyze-commits \
  -H "Content-Type: application/json" \
  -d '{
    "projects": [
      {
        "name": "dde-shell",
        "commits": [
          {"hash": "abc123", "author": "dev", "date": "2026-01-01", "message": "fix: BUG-1234 修复崩溃"}
        ]
      }
    ],
    "force": false
  }' | python3 -m json.tool
```

- `force: false` 使用缓存，`force: true` 强制重新分析
- 返回 `{"success": true, "data": {"analysis": "...", "cached": true/false}}`

---

## 典型工作流

### 工作流 1: 排查 CRP 构建失败原因

```
1. GET /api/v1/crp/topics/<id>               → 获取 releases，筛选 build_state 非成功的
2. POST /api/v1/crp/builds/<build_id>/analyze → AI 一键分析所有失败的 job
3. 汇报根因：代码问题 → 建议检查源码；平台问题 → 建议重试
```

### 工作流 2: 查看 CRP 主题的包构建情况

```
用户: "看一下 V25 Beta 主题的包打得怎么样了"

1. GET /api/v1/crp/topics            → 找到目标主题的 id
2. GET /api/v1/crp/topics/<id>       → 获取主题详情 + releases 列表
3. 统计 releases 中各 build_state 的数量:
   - UPLOAD_OK/SUCCESS → 成功
   - UPLOADING/APPLYING → 进行中
   - UPLOAD_GIVEUP/APPLY_FAILED → 失败
4. 汇报: "主题共 N 个包，成功 X，进行中 Y，失败 Z"
```

### 工作流 2: 日常监控 → 打包

```
1. POST /api/v1/monitor/refresh                    → 刷新仓库
2. GET /api/v1/monitor/projects                    → 获取项目及新提交
3. POST /api/v1/ai/analyze-commits                 → AI 分析变更
4. POST /api/v1/packages/create {"project_name":"x"} → 打包
5. GET /api/v1/packages/<id>/status                → 跟踪进度
6. POST /api/v1/packages/<id>/retry                → 失败重试
```

### 工作流 3: 一键打包并跟踪

```
1. POST /api/v1/packages/create {"project_name": "dde-shell"}
2. 每 30 秒 GET /api/v1/packages/<id>/status 直到获取到 github_pr_url 或任务结束
3. 获取到 PR 链接后:
   - normal/changelog_only → 将版本号和 PR 链接发给用户，提醒审核并手动合并 changelog PR
     "📦 打包版本: 6.0.31
      🔗 Changelog PR: https://github.com/..."
     "请审核 changelog PR 并手动合并，合并后我会自动完成后续打包步骤。
      随时通过 GET /api/v1/packages/<id>/status 查询状态。"
   - crp_only/github_action → 直接告知版本号和 PR 链接即可
4. 任务失败 → 查看 error_message，尝试 retry 或报告给用户
```

---

## 常见用户请求映射

| 用户说 | 调用 API |
|--------|----------|
| "检查有没有需要打包的项目" | `GET /api/v1/monitor/status` |
| "有哪些项目有新增提交" | `GET /api/v1/monitor/projects` |
| "帮我分析下新增了什么" | `POST /api/v1/ai/analyze-commits` |
| "打包 dde-shell" | `POST /api/v1/packages/create` → 轮询 status 直到获取 PR 链接 → **normal/changelog_only 模式提醒用户审核并手动合并 PR** |
| "打包 deepin-music 版本 6.0.30" | `POST /api/v1/packages/create` → 轮询 status → **按模式提醒用户（normal 需手动合并 PR）** |
| "查询任务 123 的状态" | `GET /api/v1/packages/123/status` |
| "重试任务 123" | `POST /api/v1/packages/123/retry` |
| "有哪些项目可以打包" | `GET /api/v1/projects` |
| "有哪些 CRP 主题/仓库" | `GET /api/v1/crp/topics` |
| "看看 XXX 主题的包打得怎么样了" | `GET /api/v1/crp/topics/<id>` |
| "最近的打包任务" | `GET /api/v1/packages/list?limit=10` |
| "有哪些失败的任务" | `GET /api/v1/packages/list?status=failed` |
| "刷新所有仓库" | `POST /api/v1/monitor/refresh` |
| "重试这个包的构建" | `POST /api/v1/crp/releases/<id>/retry` |
| "放弃这个包" | `DELETE /api/v1/crp/releases/<id>` |
| "分析下这个构建为什么失败" | `POST /api/v1/crp/builds/<id>/analyze` |
| "看一下这个架构的日志" | `GET /api/v1/crp/builds/<id>/logs/<job_id>` |
| "看看有哪些架构失败了" | `GET /api/v1/crp/builds/<id>/jobs` |
| "这个 job 日志帮我分析下" | `POST /api/v1/crp/builds/<id>/logs/<job_id>/analyze` |

---

## 响应格式

所有 API 返回:
```json
{"success": true|false, "data": {...}, "message": "描述"}
```

- HTTP 200 + `success: true` = 成功
- HTTP 4xx/5xx + `success: false` = 失败，原因见 `message`
- 不要硬编码字段名，以实际 API 返回为准
