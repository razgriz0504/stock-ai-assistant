# 富途 OpenD 集成（只读数据源）

本模块把 Futu OpenD 作为项目的第四路数据源接入，**只读**：不含下单、撤单、改单入口。

## 一、模块边界与硬约束

| 层级 | 文件 | 责任 | 硬约束 |
|---|---|---|---|
| Provider | [app/data/futu_provider.py](../app/data/futu_provider.py) | SDK 单例、连接管理、TTL 缓存 | 只封装查询方法；禁止新增 `place_order/modify_order/cancel_order/unlock_trade` |
| API | [app/api/futu_api.py](../app/api/futu_api.py) | FastAPI 路由，`/api/futu/*` | 12 个端点全部为 GET；`FUTU_ENABLED=false` 时 503 |
| 前端 | [frontend/src/pages/FutuPage.tsx](../frontend/src/pages/FutuPage.tsx) | 只读三 Tab | 无任何 form / 下单按钮 |
| 部署 | [scripts/setup_futu_opend.sh](../scripts/setup_futu_opend.sh) | 一键装 OpenD systemd | OpenD 绑定 `127.0.0.1:11111`，不暴露公网 |

## 二、部署流程（服务器一次性）

```bash
# 1) 部署 OpenD
ssh root@your-server
cd /opt/stock-ai-assistant
sudo bash scripts/setup_futu_opend.sh

# 2) 首次登录（获取二维码/短信码）
journalctl -u futu-opend -f
# 用手机 Futu App 扫码或按提示输入验证码

# 3) 打开开关
vi .env
# 修改：FUTU_ENABLED=true
sudo systemctl restart stock-ai-assistant
```

## 三、环境变量

参见 [.env.example](../.env.example)：

| 变量 | 默认 | 说明 |
|---|---|---|
| `FUTU_ENABLED` | `false` | 总开关；false 时 API 返回 503、前端页面显示"未启用" |
| `FUTU_OPEND_HOST` | `127.0.0.1` | OpenD 主机，**必须** loopback |
| `FUTU_OPEND_PORT` | `11111` | OpenD TCP 端口 |
| `FUTU_TRD_ENV` | `SIMULATE` | 交易账户环境。`SIMULATE` / `REAL`（仅查询） |
| `FUTU_TRD_MARKET` | `US` | 主账户市场。`US` / `HK` / `CN` |

## 四、API 端点一览

前缀 `/api/futu`：

| 方法 | 路径 | 用途 | 缓存 |
|---|---|---|---|
| GET | `/status` | 连接与登录状态探测 | - |
| GET | `/snapshot?codes=US.AAPL,HK.00700` | 批量快照 | 5s |
| GET | `/orderbook?code=&num=` | 买卖盘 | 3s |
| GET | `/ticker?code=&num=` | 逐笔成交 | 3s |
| GET | `/kline?code=&ktype=&start=&end=&max_count=` | K 线 | 60s |
| GET | `/timeshare?code=` | 分时 | 5s |
| GET | `/plate/list?market=&plate_class=` | 板块列表 | 300s |
| GET | `/plate/stocks?plate_code=` | 板块成分股 | 300s |
| GET | `/capital/flow?code=` | 资金流向 | 30s |
| GET | `/capital/distribution?code=` | 大中小单分布 | 30s |
| GET | `/positions` | 持仓（只读） | 15s |
| GET | `/account` | 账户资金（只读） | 15s |

## 五、故障排查

| 现象 | 排查步骤 |
|---|---|
| `/api/futu/status` 返回 `connected=false, reason="futu-api SDK 未安装"` | 服务器 `pip install -r requirements.txt`，重启后端 |
| `connected=false, reason="OpenD 未连接"` | `systemctl status futu-opend` 检查进程；`journalctl -u futu-opend -f` 看错误 |
| `qot_logined=false` 或 `trd_logined=false` | Session 已过期；重跑首次登录流程扫码 |
| 云 IP 触发风控（登录后立刻断开） | 手机 Futu App 手动解锁账户，然后重登；频繁触发时联系富途客服 |
| 请求超时 / 限频错误 | 提高 Provider TTL 缓存；`/orderbook` 单只股票别高于 1 次/秒 |

## 六、非目标（明确不做）

- **不做下单/撤单/改单**：涉及资金安全，需要网页多因素认证+熔断+审计等基础设施，超出本项目定位。
- **不做实时推送订阅**：订阅额度紧张（100~2000 只），先用 REST 轮询即可。
- **不整合到 WatchlistPage 快照**：避免与 yfinance/finnhub 混合导致口径不一致，独立成"富途看板"。
- **不做 A 股接入**：Futu API 主要覆盖港美股，A 股用现有 akshare 数据源。
