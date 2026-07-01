# 校园数据融合服务智能体 — 项目上下文

## 一、项目定位

**2026年大学生数据要素素质大赛** · 智能体开发赛道作品

一句话：**学生输入学号即可获取全部校园数据（课表/消费/图书馆/通知/竞赛），无需自己提供任何数据。**

底层对接教务系统、一卡通系统、图书馆座位管理系统三大数据源，管理员完成一次性配置后全校学生零门槛使用。

## 二、技术栈

| 层级 | 技术 | 备注 |
|------|------|------|
| 后端框架 | FastAPI (Python 3.11+) | OpenAI 兼容 API |
| 前端 | Vue 3 CDN + ECharts 5 | 单 HTML 文件，无外部 CSS/JS 依赖 |
| LLM | DeepSeek-chat (可替换) | 通过 `/v1` 兼容接口 |
| RAG | ChromaDB + sentence-transformers | 本地向量检索，无需联网 |
| 数据 | CSV/JSON 静态文件 | data_generator.py 生成模拟数据 |
| 爬虫 | requests + curl | crawl_schedule.py 爬取教务系统（已脱敏） |

## 三、项目结构

```
campus-agent/
├── frontend/index.html      # Vue 3 SPA 前端（Stripe风格校园蓝）
├── backend/
│   ├── main.py              # FastAPI 主服务（8个API端点）
│   ├── agent_engine.py      # 核心引擎（关键字路由 + 多轮对话 + RAG增强 + LLM）
│   ├── rag_engine.py        # ChromaDB 向量检索引擎
│   ├── etl.py               # 数据管线（加载/查询/统计）
│   ├── config.py            # 配置（环境变量 + 路径）
│   ├── data_generator.py    # 模拟数据生成器（DEMO_USER为主账号）
│   ├── crawl_schedule.py    # 教务系统爬虫（已脱敏，config示例化）
│   └── requirements.txt     # Python依赖
├── data/
│   ├── courses.csv          # 课表（416条模拟数据，18门/DEMO_USER）
│   ├── consumption.csv      # 消费流水（8,938条）
│   ├── library.csv          # 图书馆座位（730条）
│   ├── classrooms.csv       # 教室信息（142间）
│   ├── notices.json         # 校园通知（40条）
│   └── competitions.json    # 竞赛信息（10条）
├── .gitignore               # 已配置：排除.env/logs/__pycache__/chroma_db/备份
├── README.md                # 项目README
└── CONTEXT.md               # 本文件
```

## 四、API端点一览

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/debug` | 调试（数据加载状态） |
| POST | `/api/chat` | 对话（含Dashboard数据） |
| POST | `/api/chat/stream` | SSE流式对话 |
| POST | `/api/rag/search` | RAG语义检索 |
| POST | `/api/rag/ask` | RAG增强问答 |
| GET | `/api/dashboard/{student_id}` | 仪表盘聚合（不走LLM） |
| GET | `/api/courses/{student_id}` | 课表查询 |
| GET | `/api/consumption/{student_id}` | 消费统计 |
| GET | `/api/library` | 图书馆状态 |
| GET | `/api/classrooms/empty` | 空教室查询 |
| GET | `/api/notices` | 校园通知 |
| GET | `/api/competitions` | 竞赛信息 |
| DELETE | `/api/session/{user_id}` | 清除会话 |

## 五、已完成的模块

- [x] 智能对话：关键字路由 + LLM 多轮对话 + 参数提取
- [x] RAG知识增强：每轮对话自动检索 ChromaDB，注入 LLM context
- [x] 课表查询：按学号/星期几/周数多维度检索
- [x] 空教室查询：按星期+节次查找空闲教室
- [x] 图书馆座位概览：11个区域使用率展示
- [x] 消费分析：月/日统计、食堂分布、趋势图
- [x] 通知/竞赛浏览：最近通知和竞赛报名信息
- [x] 仪表盘：`/api/dashboard/{学号}` 一次返回所有概要数据
- [x] 前端重写：清爽白色校园风格，顶部标签导航
- [x] 数据脱敏：真实课表学号已哈希，模拟数据用 DEMO_USER
- [x] 教务系统爬虫：覆盖3校区30栋教学楼22万+条课表
- [x] 3个硬编码融合场景（课后去图书馆/消费-课程关联/竞赛-课程推荐）

## 六、待完成/可改进

- [ ] **图书馆预约功能**：目前只有座位状态展示，无实际预约操作
- [ ] **消费深度分析**：增加环比/同比、异常检测、预算预警
- [ ] **通知个性化推荐**：根据用户院系/年级过滤通知
- [ ] **选课推荐引擎**：`schedule_recommend` 路由已预留，需完善3阶段求解器
- [ ] **前端移动端适配**：目前桌面端优先
- [ ] **ChromaDB 数据初始化脚本**：rag_engine.py 需要在首次运行时填充知识库
- [ ] **真实数据对接**：消费记录、图书馆实时座位需要对接学校API
- [ ] **性能优化**：courses.csv 22万行可用 SQLite 替代内存 pandas

## 七、快速开始

```bash
# 1. 进入 backend 目录
cd campus-agent/backend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key（复制 .env.example → .env，填入 DeepSeek Key）
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY

# 4. 生成模拟数据（首次或数据损坏时运行）
python data_generator.py

# 5. 启动后端
python main.py
# 服务运行在 http://localhost:8000

# 6. 浏览器打开
# http://localhost:8000（FastAPI 会自动 serve frontend/index.html）
# 或用 Live Server 直接打开 frontend/index.html
```

## 八、演示账号

- **学号**：`DEMO_USER`
- **课表**：18门课（数学与计算机学院大二下学期）
- **消费**：8938条记录，近3个月
- 前端登录框输入 `DEMO_USER` 即可体验全部功能

## 九、脱敏说明

以下内容已脱敏处理，可安全上传 GitHub：
- 学号：已 SHA256 哈希（真实数据）或替换为 DEMO_USER（模拟数据）
- API Key：通过 `.env` 管理，已加入 `.gitignore`
- 教务系统 Cookie/URL：`crawl_schedule.py` 中改为占位符 `YOUR_COOKIE_HERE`
- 图书馆预约密码规则：已移除
- 校内电话：替换为 `XXXX-XXXXXXX`
- 校内服务URL：替换为 `example.edu.cn`
