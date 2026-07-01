# 校园数据融合服务智能体

> 2026年数据要素素质大赛 · 智能体开发赛道

基于 **FastAPI + Vue3 + DeepSeek LLM + ChromaDB RAG** 构建的一站式校园数据导航智能体，为学生提供课表查询、消费分析、图书馆座位、空教室、校园通知等综合服务。

## 功能概览

| 模块 | 说明 |
|------|------|
| 智能对话 | 自然语言查询校园信息，支持多轮对话 + RAG 知识增强 |
| 数据总览 | 个人课表、消费、图书馆座位一站式 Dashboard |
| 完整课表 | 全校课表检索，支持学号/课程/教师/教室多维度查询 |
| 图书馆 | 各楼层座位实时状态、预约引导 |
| 消费分析 | 一卡通消费流水可视化，按食堂/餐类/日期多维度分析 |
| 知识库检索 | ChromaDB 向量检索校园 FAQ、通知、政策 |
| 选课推荐 | 基于课程关联和空教室的智能排课推荐 |

## 技术架构

```
frontend/index.html  ←→  FastAPI (main.py)
                              ├── agent_engine.py   (LLM 对话 + 关键字路由)
                              ├── rag_engine.py     (ChromaDB 向量检索)
                              ├── scheduler.py      (智能排课推荐)
                              ├── etl.py            (数据治理 ETL 管线)
                              └── data_generator.py (模拟数据生成器)
```

## 快速开始

### 1. 环境配置

```bash
pip install -r backend/requirements.txt
```

复制环境变量模板并填入你的 API Key：

```bash
cp backend/.env.example .env
# 编辑 .env 填入 OPENAI_API_KEY
```

### 2. 生成数据

```bash
python backend/data_generator.py
```

### 3. 启动服务

```bash
python backend/main.py
```

或者双击 `启动.bat`（Windows）。

访问 http://localhost:8000 进入前端。

## 数据说明

- `data/courses.csv` — 课表数据（已匿名化，学号使用哈希脱敏）
- `data/consumption.csv` — 消费样例数据
- `data/library.csv` — 图书馆座位数据
- `data/classrooms.csv` — 教室信息
- `data/notices.json` — 校园通知
- `data/competitions.json` — 竞赛信息

> 所有数据均为模拟数据或已脱敏处理的样例，不包含真实个人信息。

## 许可证

MIT License
