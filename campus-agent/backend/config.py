"""配置文件"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（若存在，按优先级：backend/.env → 项目根/.env）
_env1 = Path(__file__).resolve().parent / ".env"
_env2 = Path(__file__).resolve().parent.parent / ".env"
if _env1.exists():
    load_dotenv(dotenv_path=_env1)
if _env2.exists():
    load_dotenv(dotenv_path=_env2, override=False)

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VECTOR_DB_DIR = BASE_DIR / "data" / "vector_db"

# 确保目录存在
for d in [DATA_DIR, VECTOR_DB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# OpenAI 兼容 API 配置（支持任何兼容接口）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "未找到 OPENAI_API_KEY 环境变量！\n"
        "请创建 .env 文件或在环境变量中设置 OPENAI_API_KEY。\n"
        "参考：复制 .env.example 为 .env 并填入你的 API Key。"
    )

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# 学校信息
SCHOOL_NAME = "衡水学院"
SCHOOL_SHORT = "衡院"
SCHOOL_FULL_NAME = "衡水学院（Hengshui University）"

# 本地 Embedding 模型（无需API）
LOCAL_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 服务配置
HOST = os.getenv("HOST", "0.0.0.0")
try:
    PORT = int(os.getenv("PORT", "8000"))
except ValueError:
    PORT = 8000

# ChromaDB 集合名称
CHROMA_COLLECTIONS = {
    "notices": "campus_notices",
    "faq": "campus_faq",
    "policies": "campus_policies",
}

# 数据文件
DATA_FILES = {
    "courses": DATA_DIR / "courses.csv",
    "consumption": DATA_DIR / "consumption.csv",
    "library": DATA_DIR / "library.csv",
    "notices": DATA_DIR / "notices.json",
    "classrooms": DATA_DIR / "classrooms.csv",
    "competitions": DATA_DIR / "competitions.json",
}
