# 职析：AI 求职面试助手

职析是一个面向 AI 应用工程岗位的全栈作品。用户注册登录后，可以输入简历和职位描述，调用 DeepSeek 生成岗位匹配分析、简历建议和 8 道个性化面试题；还可以逐题作答，获得 AI 评分并对比多次练习结果。

## 项目亮点

- 使用 FastAPI 和 Pydantic 同时校验用户输入与大模型结构化输出。
- 大模型返回非法 JSON 或字段不合格时，自动携带纠错提示重试一次。
- 使用 SQLAlchemy 保存分析记录、模型、耗时、token 和多次答题成绩。
- 使用邮箱密码、Argon2 密码哈希和 JWT 实现真实登录，并隔离不同用户的数据。
- 使用 Alembic 管理数据库版本，同时支持 SQLite 和 PostgreSQL。
- 提供 SQLite 到 PostgreSQL 的数据迁移脚本，保留用户、分析和答题关系。
- 同一道题支持重复练习，平均分只采用每道题的最新成绩。
- 支持粘贴简历文本或提取带文本层的 PDF，不依赖 OCR。
- 提供完整加载、空状态、错误重试、删除确认和移动端适配。
- 提供不调用 DeepSeek 的演示数据，现场网络异常时仍能展示完整产品。
- 通过用户级和全站级每日限额控制公开部署后的模型调用成本。
- 支持 Vercel、Render 和 Neon 的免费作品集部署方案。

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python、FastAPI、Pydantic |
| AI | DeepSeek API、OpenAI 兼容客户端 |
| 数据库 | SQLAlchemy、SQLite、PostgreSQL、Alembic |
| 鉴权 | JWT、Argon2、Bearer Token |
| 前端 | Next.js 15、React 19、TypeScript |
| 测试 | Pytest、Vitest、Testing Library |
| 部署 | GitHub Actions、Vercel、Render、Neon |

## 目录结构

```text
AIwork/
├─ .vscode/tasks.json       # VS Code 一键启动任务
├─ backend/
│  ├─ app/
│  │  ├─ api/              # FastAPI 路由与登录依赖
│  │  ├─ services/         # 鉴权、PDF 解析与模型调用
│  │  ├─ demo_seed.py      # 幂等演示数据脚本
│  │  ├─ models.py         # SQLAlchemy 数据表
│  │  └─ schemas.py        # 请求、响应与 AI 输出结构
│  ├─ alembic/             # 数据库迁移脚本
│  └─ tests/               # Pytest 测试
└─ frontend/
   ├─ app/                 # Next.js 页面
   ├─ components/          # 分析结果与面试练习组件
   └─ lib/                 # API 请求与 TypeScript 类型
```

## 快速运行

### 1. 配置环境变量

项目同时保留 `.env.example` 和 `.env`：

- `.env.example` 是可以提交的配置模板，不包含真实密钥。
- `.env` 是本机配置，已被 `.gitignore` 排除。

在根目录创建或修改 `.env`：

```env
DEEPSEEK_API_KEY=你的真实Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
DATABASE_URL=sqlite:///./data/job_assistant.db
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_RECYCLE_SECONDS=1800
DATABASE_CONNECT_TIMEOUT_SECONDS=10
FRONTEND_ORIGIN=http://localhost:3000
JWT_SECRET_KEY=请替换为足够长的随机字符串
ACCESS_TOKEN_EXPIRE_MINUTES=1440
USER_DAILY_ANALYSIS_LIMIT=3
USER_DAILY_INTERVIEW_LIMIT=10
GLOBAL_DAILY_ANALYSIS_LIMIT=30
GLOBAL_DAILY_INTERVIEW_LIMIT=100
```

默认 SQLite 可以直接运行。准备 PostgreSQL 后，将 `DATABASE_URL` 改为：

```env
DATABASE_URL=postgresql+psycopg://postgres:你的密码@localhost:5432/zhixi
```

常见平台提供的 `postgres://` 或 `postgresql://` 地址也能自动转换为 psycopg 3
连接。密码包含 `@`、`:` 等特殊字符时，需要先进行 URL 编码。

### 2. 使用 VS Code 一键启动

1. 用 VS Code 打开 `E:\AIwork` 文件夹。
2. 按 `Ctrl+Shift+P`。
3. 输入并选择 `Tasks: Run Task`。
4. 选择 `启动完整项目`。

VS Code 会先执行 `alembic upgrade head`，再分别打开前后端任务：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

也可以使用两个终端手动启动：

```powershell
cd E:\AIwork\backend
E:\AIwork\.venv\Scripts\python.exe -m alembic upgrade head
E:\AIwork\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
cd E:\AIwork\frontend
npm run dev
```

## 导入演示数据

演示数据不会调用 DeepSeek，也不会覆盖已有记录。重复执行只会保留同一条演示分析。已有用户时数据归属最早注册的用户；尚未注册时数据暂不归属任何人，并由首个注册用户自动接管。

在 VS Code 的 `Tasks: Run Task` 中选择 `导入演示数据`，或执行：

```powershell
cd E:\AIwork\backend
E:\AIwork\.venv\Scripts\python.exe -m app.demo_seed
```

然后打开历史记录，可以看到：

- 一条 AI 应用全栈岗位分析；
- 8 道个性化面试题；
- 第 1 题的两次练习成绩；
- 第 2、4 题的评分反馈；
- 基于每道题最新成绩计算的平均分。

## 从 SQLite 迁移到 PostgreSQL

迁移前先备份 `backend/data/job_assistant.db`，并创建一个空的 PostgreSQL
数据库，例如 `zhixi`。项目不会自动创建数据库本身，只会创建其中的数据表。

1. 在 `.env` 中把 `DATABASE_URL` 改为 PostgreSQL 地址。
2. 在 `backend` 目录创建表结构：

```powershell
E:\AIwork\.venv\Scripts\python.exe -m alembic upgrade head
```

3. 复制原 SQLite 数据：

```powershell
E:\AIwork\.venv\Scripts\python.exe -m app.migrate_sqlite_to_postgres --source sqlite:///./data/job_assistant.db
```

也可以在 VS Code 中运行任务 `迁移 SQLite 数据到 PostgreSQL`。脚本按
`users → analyses → interview_attempts` 顺序复制，并保留原 ID 和关联关系。
为了防止覆盖数据，只要目标业务表非空，脚本就会停止。

4. 正常运行 `启动完整项目`，再检查注册、历史记录和答题功能。

## 完整数据流

### 岗位分析

```text
React 从 localStorage 读取 JWT
→ 请求携带 Authorization: Bearer <token>
→ FastAPI 验证 JWT 并恢复当前用户
→ React 提交简历和 JD
→ POST /api/analyses
→ Pydantic 校验输入
→ DeepSeek 生成 JSON
→ Pydantic 校验 AI 输出，失败重试一次
→ SQLAlchemy 保存 analyses，并写入当前 user_id
→ FastAPI 返回 AnalysisResponse
→ React 显示结果
```

### 模拟面试评分

```text
用户选择题目并输入回答
→ POST /api/analyses/{id}/questions/{number}/attempts
→ Pydantic 校验回答
→ 后端读取简历、JD 和题目
→ DeepSeek 生成结构化评分
→ Pydantic 校验，失败重试一次
→ SQLAlchemy 保存 interview_attempts
→ React 更新最新分数和历次成绩
```

## 主要 API

| 方法 | 地址 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 检查 API 和数据库 |
| `POST` | `/api/auth/register` | 邮箱密码注册并返回 JWT |
| `POST` | `/api/auth/login` | 登录并返回 JWT |
| `GET` | `/api/auth/me` | 读取当前登录用户 |
| `GET` | `/api/usage` | 查询今日个人 AI 剩余额度 |
| `POST` | `/api/resumes/parse` | 提取 PDF 文本 |
| `POST` | `/api/analyses` | 创建岗位分析 |
| `GET` | `/api/analyses` | 查询历史记录 |
| `GET` | `/api/analyses/{id}` | 查询分析详情 |
| `DELETE` | `/api/analyses/{id}` | 删除分析及关联练习 |
| `POST` | `/api/analyses/{id}/questions/{number}/attempts` | 提交回答并评分 |
| `GET` | `/api/analyses/{id}/interview-attempts` | 查询练习记录 |

除健康检查、注册和登录外，其他接口都需要：

```http
Authorization: Bearer <access_token>
```

访问其他用户的分析记录统一返回 `404`，避免泄露记录是否存在。

## 免费部署上线

线上架构：

```text
GitHub
├─ Vercel：Next.js 前端
├─ Render：FastAPI 后端
└─ Neon：PostgreSQL
```

### 1. GitHub

创建公开仓库 `zhixi-ai-job-assistant` 并推送项目。仓库中的 GitHub Actions
会运行后端测试、前端测试、类型检查、生产构建和密钥扫描。

### 2. Neon

1. 创建 Free 项目，区域选择 `AWS Asia Pacific (Singapore)`。
2. 复制 pooled connection string，并确认地址包含 `sslmode=require`。
3. 不导入本地数据库，线上只由部署脚本创建专用演示数据。

### 3. Render

使用仓库根目录的 `render.yaml` 创建 Blueprint。除自动生成的 JWT Secret
外，需要在 Render 控制台填写：

```text
DATABASE_URL              Neon pooled connection string
DEEPSEEK_API_KEY           DeepSeek Key
FRONTEND_ORIGIN            Vercel 正式域名，首次可先填占位地址
PORTFOLIO_USER_EMAIL       仅你本人使用的演示登录邮箱
PORTFOLIO_USER_PASSWORD    演示账号私有密码
```

发布命令会自动执行：

```text
alembic upgrade head
→ 创建或确认私有演示账号
→ 幂等写入演示分析与练习
→ 启动 Uvicorn
```

### 4. Vercel

1. 导入同一个 GitHub 仓库。
2. Root Directory 选择 `frontend`。
3. 添加 `NEXT_PUBLIC_API_BASE_URL=https://你的后端.onrender.com`。
4. 发布后将正式 `https://xxx.vercel.app` 地址填回 Render 的
   `FRONTEND_ORIGIN`，再重新部署后端。

### 5. 线上验收

- 打开 Render `/api/health`，确认数据库为 `ok`。
- 注册普通账号，验证分析、评分、历史记录和退出登录。
- 使用私有演示账号验证演示数据存在。
- 超过每日限额时接口返回 `429`，前端保留输入并提示次日重试。

Render 免费后端闲置约 15 分钟会休眠，首次访问可能等待约一分钟；Neon
免费计算闲置时也会缩容到零。正式把链接用于集中投递前，可升级 Render
实例以避免冷启动。

## 测试

后端测试不会请求真实 DeepSeek：

```powershell
cd E:\AIwork\backend
E:\AIwork\.venv\Scripts\python.exe -m pytest
```

前端测试、类型检查和生产构建：

```powershell
cd E:\AIwork\frontend
npm test
npx tsc --noEmit
npm run build
```

## 3–5 分钟面试讲解

1. **项目目标**：解决简历与 JD 难以快速对照、面试准备缺少针对性的问题。
2. **核心流程**：前端提交材料，FastAPI 校验后调用 DeepSeek，再校验模型 JSON 并保存。
3. **主要难点**：大模型输出不稳定，因此使用 Pydantic 固定结构，并在失败时纠错重试。
4. **数据设计**：一个分析对应多条答题记录，同题多次回答保存为独立记录，便于对比。
5. **鉴权隔离**：密码使用 Argon2 哈希，JWT 恢复当前用户，所有查询都带 `user_id` 条件。
6. **数据库演进**：本地使用 SQLite 快速开发，生产型环境切换 PostgreSQL；
   Alembic 管理表结构，迁移脚本保留旧数据及外键关系。
7. **工程质量**：模型超时、令牌失效、越权访问、非法 PDF 和关联删除都有测试。
8. **成本控制**：模型调用前写入用量事件，失败调用也计数，并用 PostgreSQL
   事务锁避免并发绕过全站限额。

## 演示顺序

1. 注册一个账号，说明密码哈希、JWT 和首用户旧数据接管。
2. 首页填入示例，展示真实分析流程。
3. 进入结果页，说明匹配分析和 8 道题来自固定结构的 AI 输出。
4. 提交一道回答，展示评分、改进建议和 token/耗时记录。
5. 打开历史记录，展示数据隔离、多次练习对比及关联删除。
6. 退出并重新登录，说明前端令牌恢复流程。
7. 打开 `/docs`，展示 FastAPI 自动生成的接口文档。

## 常见问题

### 后端提示端口被占用

关闭之前启动的 Uvicorn 终端，或在任务管理器结束残留的 Python 进程后重试。

### 前端请求后端失败

确认后端运行在 `http://localhost:8000`，并检查 `frontend/.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL`。

### 提示数据库缺少 users 或 user_id

说明数据库还没有升级。在 `backend` 目录执行：

```powershell
E:\AIwork\.venv\Scripts\python.exe -m alembic upgrade head
```

### PostgreSQL 连接失败

检查 PostgreSQL 服务是否启动、数据库 `zhixi` 是否已创建，以及用户名、密码和
端口是否正确。应用使用短连接超时和连接存活检查，失效连接不会直接交给请求。

### 登录状态突然失效

JWT 默认 24 小时过期。前端收到 `401` 后会清除本地令牌并返回登录页，重新登录即可。

### PDF 无法解析

首版只支持带文本层的 PDF。扫描件或图片 PDF 需要 OCR，不在当前范围内。

### DeepSeek 超时或余额不足

输入内容不会被清空，可以直接重试。面试演示时也可以导入演示数据展示完整结果。

## 当前边界

- 当前支持 SQLite 与 PostgreSQL，但 PostgreSQL 服务和数据库需要自行准备。
- 尚未加入邮箱验证、找回密码、刷新令牌和第三方登录。
- JWT 为方便作品集讲解保存在 `localStorage`；生产环境可升级为 HttpOnly Cookie。
- 不支持扫描版 PDF、OCR、录音和语音识别。
- 暂不加入 RAG、Docker 和公开部署。
