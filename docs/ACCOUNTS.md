# 账号体系（Accounts & Auth）

本项目自 v2.1 起引入登录鉴权，覆盖后端全部业务 API 与前端所有页面。定位是 **家人朋友邀请制小圈子（2~10 人）**，不做自助注册。

## 关键决策

- 邀请方式：**admin 手动在管理页创建账号**，把凭证告诉家人朋友。
- 密码存储：`passlib[bcrypt]`。
- Token：JWT（`python-jose[cryptography]`, HS256），有效期 `JWT_EXPIRE_DAYS` 天，前端存 `localStorage`。
- 首个 admin：`.env` 里 `INITIAL_ADMIN_USERNAME` + `INITIAL_ADMIN_PASSWORD`，**首次启动 users 表为空时自动播种**，播种后不再读取。
- 部署无需改 Nginx，认证全部在 FastAPI 层；HTTPS 请自行在网关配好。

## 环境变量

在 `.env` 追加（`.env.example` 已列出）：

```dotenv
JWT_SECRET=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<强密码>
```

## 角色分层

| 角色 | 能做 |
|------|------|
| **admin** | 全部功能，包括富途看板、周报/存储行业/选股器等所有 **触发生成/写配置** 类操作，以及用户管理 |
| **user**  | 读取市场级共享数据；管理自己的 watchlist、AI 对话、回测；不能触发全站扫描/报告生成，不能看富途 |
| **未登录** | 所有业务 API 403/401；仅 `/api/health`、`/api/feishu/webhook` 保持公开 |

## 数据隔离

- 私有（按 `user_id` 隔离）：`user_preferences`（含关注列表）、`chat_conversations` + `chat_messages`、以及带 `user_id` 字段的历史扩展表。
- 市场级共享（登录后所有用户可读）：scoring / screener runs / vcp scan / weekly report / storage report / x_tweets 等。
- 只有 admin 能触发写：`/api/screener/run`、`/api/vcp-monitor/scan`、`/api/*-report*/generate`、`/api/screener/presets` 增删改、`/api/x-monitor/config`、`/api/futu/*` 全部。

## 首次部署

1. 部署完最新代码，`.env` 补齐上面的变量。
2. 启动服务，观察日志出现类似 `Initial admin seeded: admin` 即成功。
3. 用 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 登录，随后修改密码。
4. 备份 SQLite 后跑一次 **存量数据归属迁移脚本**：

   ```bash
   # 先 dry-run
   python scripts/migrate_ownership.py --dry-run
   # 无异常再真跑
   python scripts/migrate_ownership.py
   ```

   会把历史 `monitor_rules / backtest_records / user_preferences` 里 `user_id IS NULL` 的行归到首个 admin。

## 前端行为

- `/login`：账号密码登录，成功后跳回被拦截的原路径（`?from=`）。
- 401 自动登出：任一请求返回 401 会清空 token 并跳 `/login?from=...`。
- Sidebar 会按角色隐藏管理员菜单（用户管理、报告管理、系统设置、富途看板）。
- `/profile`：所有登录用户都可以修改自己的密码。
- `/admin/users`：仅 admin。可新建用户、切换角色、启用/禁用、重置密码、删除。首个 admin 与当前登录者受保护，不能被降级/禁用/删除。

## 关闭 / 重开账号体系

本次改动是硬开关，不再支持匿名访问业务 API。若临时需要“无鉴权模式”，请自行在 `app/auth/dependencies.py` 里放开 `get_current_user`；不推荐这样做。
