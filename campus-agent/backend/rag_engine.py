"""RAG 知识库引擎 - 基于 ChromaDB + SentenceTransformer 本地向量化
语义检索学校通知、政策文件、FAQ等知识库内容
"""

import os
import json
from pathlib import Path
from typing import Optional

# ⚠️ 必须在导入 huggingface/sentence-transformers 之前设置
# 国内网络通过镜像下载模型，已缓存后自动使用本地文件
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

import config as cfg


class RAGEngine:
    """本地 RAG 检索引擎（全离线运行，模型已预下载）"""

    COLLECTION_NAME = "campus_knowledge"
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self):
        # ChromaDB 持久化目录
        chroma_dir = str(cfg.BASE_DIR / "data" / "chroma_db")
        os.makedirs(chroma_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=chroma_dir)

        # 嵌入函数（模型已通过 hf-mirror 预下载到本地缓存）
        self.embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=self.MODEL_NAME,
            device="cpu",
        )

        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[RAG] ChromaDB 初始化完成，集合: {self.collection.count()} 条文档")

    # ─────────────────────────────────────────
    # 数据注入（由 etl 提供文档）
    # ─────────────────────────────────────────

    def build_index(self, documents: list[dict], force_rebuild: bool = False):
        """
        构建/更新向量索引
        documents: [{"text": str, "metadata": dict, "id": str}, ...]
        """
        if self.collection.count() > 0 and not force_rebuild:
            print(f"[RAG] 跳过构建（已有 {self.collection.count()} 条），force_rebuild=False")
            return

        print(f"[RAG] 开始构建索引，文档数: {len(documents)}")

        # 分批注入（避免一次性太多）
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch = documents[i: i + batch_size]
            self.collection.upsert(
                ids=[d["id"] for d in batch],
                documents=[d["text"] for d in batch],
                metadatas=[d.get("metadata", {}) for d in batch],
            )

        print(f"[RAG] 索引构建完成，共 {self.collection.count()} 条")

    # ─────────────────────────────────────────
    # 语义检索
    # ─────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
    ) -> list[dict]:
        """
        语义检索
        返回: [{"text": str, "metadata": dict, "score": float}, ...]
        """
        if self.collection.count() == 0:
            return []

        where = {"type": doc_type} if doc_type else None

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, self.collection.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            print(f"[RAG] 检索失败: {e}")
            return []

        docs = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # 余弦距离转相似度（距离越小越相似）
            score = round(1 - dist, 4)
            if score > 0.3:  # 相似度阈值，过滤不相关结果
                docs.append({"text": text, "metadata": meta, "score": score})

        return docs

    def format_context(self, docs: list[dict]) -> str:
        """将检索结果格式化为 LLM 上下文"""
        if not docs:
            return ""
        lines = ["以下是从学校知识库中检索到的相关内容：\n"]
        for i, d in enumerate(docs, 1):
            src = d["metadata"].get("source", d["metadata"].get("type", "知识库"))
            lines.append(f"[{i}] 来源：{src}")
            lines.append(d["text"])
            lines.append("")
        return "\n".join(lines)


# ─────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────

_rag: RAGEngine = None


def get_rag() -> RAGEngine:
    global _rag
    if _rag is None:
        _rag = RAGEngine()
    return _rag
