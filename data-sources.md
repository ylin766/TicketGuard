# TicketGuard 数据来源清单

> 本文档列出 TicketGuard 项目所需的全部数据方向、具体来源和接入方式。

---

## 类别 1：赛事数据（场次、场馆、赛程）

Agent 需要知道"这张票对应的是哪场比赛、哪个阶段、在哪个城市"，用于比价基准调整和法规匹配。

| 来源 | 链接 | 接入方式 | 说明 |
|---|---|---|---|
| **wc26-mcp**（推荐） | https://github.com/jordanlyall/wc26-mcp | MCP 直接调用，零配置 | 18 个工具，覆盖 104 场比赛、16 个场馆、48 支球队，数据随包附带，无需 API key |
| **WC2026 API** | https://www.wc2026api.com/ | REST API，需注册获取 Bearer token | 提供全部 104 场比赛的场次、场馆、赛事阶段、实时比分 |
| **worldcupwiki.com 票价指南** | https://worldcupwiki.com/tickets/ | 手动整理 → CSV | 官方票价分级（Cat 1/2/3/VIP/Supporter Entry）的公开参考数据 |
| **FIFA 官方票价公告** | https://inside.fifa.com/organisation/news/world-cup-2026-new-ticket-pricing-tier-fans-qualified-teams | 手动整理 → CSV | FIFA 官方 Supporter Entry Tier $60 定价及各类别价格区间 |

---

## 类别 2：二手市场价格数据（实时挂牌价）

Agent 需要同场次同区域的市场价格分布（P25/P50/P75），用于判断卖家报价是否合理。

| 来源 | 链接 | 接入方式 | 说明 |
|---|---|---|---|
| **SeatGeek API**（推荐） | https://seatgeek.github.io/ | REST API，注册即用，免费 client_id | 提供 events、listings、venues 端点；FIFA 2026 世界杯票已在平台上架；`GET /2/listings?event_id=xxx` 返回实时挂牌价 |
| **SeatGeek 开发者平台** | https://seatgeek.com/build | 注册入口 | 获取 client_id，无需审核 |
| **Ticketmaster Discovery API** | https://developer.ticketmaster.com/products-and-docs/apis/getting-started/ | REST API，注册即用 | 一级市场票价数据，可作为面值参考；`GET /discovery/v2/events` 支持按场馆和日期筛选 |
| **TickPick 世界杯票价指南** | https://www.tickpick.com/blog/2026-world-cup-seating-guide-all-16-venues-best-and-worst-seats/ | 手动参考 | 各场馆各区域的价格区间参考，可用于验证 API 数据合理性 |

> **注意**：StubHub API 目前需要邮件申请合作伙伴资质（affiliates@stubhub.com），审核周期不确定，不适合 Hackathon 节奏，已排除。

---

## 类别 3：座位视线数据（遮挡情况）

Agent 需要判断目标座位是否存在视线遮挡（承重柱、转播摄像机、护栏等）。

| 来源 | 链接 | 接入方式 | 说明 |
|---|---|---|---|
| **A View From My Seat**（核心） | https://aviewfrommyseat.com/ | Browser-Use 实时抓取 + Gemini Vision 分析 | 众包座位视角照片库，按场馆/section 聚合；有 `has an obstructed view` 等 seat tag 标注 |
| MetLife Stadium 视角照片 | https://aviewfrommyseat.com/venue/MetLife+Stadium/seating/soccer/ | Browser-Use 抓取 | FIFA 2026 决赛场馆，soccer 分类下有大量真实视角照片 |
| SoFi Stadium 视角照片 | https://aviewfrommyseat.com/venue/SoFi+Stadium/ | Browser-Use 抓取 | FIFA 2026 场馆之一 |
| AT&T Stadium 视角照片 | https://aviewfrommyseat.com/venue/AT-and-T+Stadium/ | Browser-Use 抓取 | FIFA 2026 场馆之一，容量最大（~94,000） |
| **wc26-mcp `get_venues`** | https://github.com/jordanlyall/wc26-mcp | MCP 调用 | 提供 16 个场馆的结构化信息（容量、位置、天气），可用于场馆识别和匹配 |

> **使用方式**：Agent 拿到座位信息（如 Section 114A）后，Browser-Use 访问对应场馆页面，抓取该 section 的用户照片，Gemini Vision 分析照片中的遮挡物，输出视线评分。视线评分为 section 级别，非精确座位级别，报告中需注明。

---

## 类别 4：欺诈域名情报（钓鱼网站检测）

Agent 需要判断用户提交的 URL 是否为已知钓鱼/仿冒域名，或与官方域名高度相似的新注册域名。

| 来源 | 链接 | 接入方式 | 说明 |
|---|---|---|---|
| **PhishHunt**（推荐） | https://phishunt.io/feed/ | REST API，无需认证，每小时更新 | 提供 JSON/CSV/TXT 格式的可疑钓鱼域名实时 feed；完全免费开放 |
| **PhishHunt API 文档** | https://phishunt.io/api/ | REST API | 支持按域名查询是否在钓鱼列表中 |
| **Phishing-Database（GitHub）** | https://github.com/Phishing-Database/Phishing.Database | 直接下载 CSV/TXT | 持续维护的钓鱼域名数据库，使用 PyFunceble 验证域名活跃状态，可通过 Fivetran Connector SDK 定期同步 |
| **FIFA 2026 仿冒域名报告** | https://www.techradar.com/pro/this-enormous-demand-has-made-the-football-tournament-a-magnet-for-fraud-experts-warn-scammers-are-ramping-up-their-work-ahead-of-the-fifa-world-cup-2026-heres-how-to-avoid-being-hit | 手动参考 | 安全研究人员已识别 4,300+ 个仿冒 FIFA 官方网站的欺诈域名，可作为白名单构建参考 |
| **官方售票平台域名白名单** | 手动整理 | 静态 CSV | 包括：fifa.com、stubhub.com、ticketmaster.com、seatgeek.com、viagogo.com、axs.com 等官方域名 |

---

## 类别 5：法规数据（反黄牛法溢价上限）

Agent 需要根据场馆所在州/省，判断当前报价是否违反当地票务法规。

| 来源 | 链接 | 接入方式 | 说明 |
|---|---|---|---|
| **美国各州票务转售法律汇总** | https://the-ticket-collective.crisp.help/en/article/us-ticket-resale-laws-by-state-1msl4l2/ | 手动整理 → CSV | 按州列出溢价上限、是否需要转售许可证等信息 |
| **LegalClarity 票务法规指南** | https://legalclarity.org/secondary-ticket-market-resale-laws-and-your-rights/ | 手动参考 | 覆盖联邦 BOTS Act、FTC 全价显示规则及各州差异 |
| **LegalMatch 反黄牛法概览** | https://www.legalmatch.com/law-library/article/ticket-scalping-lawyers.html | 手动参考 | 各州法规差异的法律解读 |
| **加拿大各省票务法规** | 各省消费者保护局官网（手动整理） | 静态 CSV | 安大略省、不列颠哥伦比亚省等有世界杯场馆的省份 |
| **墨西哥联邦消费者保护法** | https://www.profeco.gob.mx/ | 手动参考 | PROFECO（墨西哥联邦消费者保护局）官网 |

> **接入方式**：法规数据为静态数据，手动整理成 CSV 后通过 Fivetran Google Sheets Connector 同步至 BigQuery，后续按需更新。

---

## 数据接入架构总览

```
数据来源                    接入方式                    存储
─────────────────────────────────────────────────────────────
wc26-mcp                →  MCP 直接调用           →  Agent 内存（无需持久化）
SeatGeek API            →  Fivetran Connector SDK →  BigQuery: market_listings
Phishing-Database       →  Fivetran Connector SDK →  BigQuery: known_phishing_domains
官方票价 + 法规 CSV      →  Fivetran Google Sheets →  BigQuery: regulation_reference
aviewfrommyseat.com     →  Browser-Use 实时抓取   →  Agent 内存（按需分析）
```

---

## 立即行动项

| 优先级 | 任务 | 预计时间 |
|---|---|---|
| 🔴 P0 | 注册 SeatGeek developer account，获取 client_id | 10 分钟 |
| 🔴 P0 | 测试 SeatGeek API 能否查到 FIFA 2026 场次数据 | 30 分钟 |
| 🟡 P1 | 注册 Fivetran 14 天免费试用 | 10 分钟 |
| 🟡 P1 | 手动整理法规 CSV（16 个场馆所在州/省的溢价上限） | 2 小时 |
| 🟡 P1 | 手动整理官方票价 CSV（Cat 1/2/3/VIP 各场次面值） | 1 小时 |
| 🟢 P2 | 测试 wc26-mcp 的 `get_venues` 和 `get_matches` 工具 | 30 分钟 |
| 🟢 P2 | 验证 aviewfrommyseat.com 的 MetLife Stadium soccer 页面可正常抓取 | 30 分钟 |
