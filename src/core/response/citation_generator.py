"""Citation generation for retrieval responses."""

from __future__ import annotations

from typing import Any

from core import RetrievalResult


Citation = dict[str, Any]


class CitationGenerator:
    """Create structured citation payloads from retrieval results."""

    def generate(self, retrieval_results: list[RetrievalResult]) -> list[Citation]:
        """Return citation dictionaries in display order."""
        return [
            {
                "index": index,
                "source": result.metadata.get("source_path", ""),
                "page": result.metadata.get("page"),
                "chunk_id": result.chunk_id,
                "score": float(result.score),
            }
            for index, result in enumerate(retrieval_results, start=1)
        ]


# 1. 文件定位
# 项目作用：在 RAG（检索增强生成）系统中，负责将底层检索到的文本片段信息转化为结构化的“参考文献/引用”数据。
# 所处层级：位于项目的核心层（core）下的响应处理模块（response）。
# 核心职责：对检索结果进行格式化和关键信息提取，生成前端或用户界面可以直接渲染的引用列表，确保最终生成的 AI 回答“有据可查”，提升回答的可信度。
# 2. 函数拆解
# 该文件主要包含一个类 CitationGenerator 和一个核心方法 generate：

# generate 方法：
# 作用目的：将原始的检索结果列表转换成标准化的引用信息字典列表。
# 输入参数：retrieval_results（类型为 list[RetrievalResult]），即检索模块返回的包含文本块内容、元数据和得分的原始结果列表。
# 输出结果：list[Citation]（即 list[dict]），包含序号、来源、页码、文本块 ID 和相似度得分的字典列表。
# 核心功能：通过列表推导式遍历输入结果，利用 enumerate 生成从 1 开始的展示序号，并从每个结果的 metadata（元数据）和属性中提取来源路径（source_path）、页码（page）、文本块 ID（chunk_id）和得分（score），最后组装成字典返回。
# 3. 执行流程
# 获取检索结果：上游模块（如问答编排器）调用检索模块，获取到与用户问题相关的文本块列表（RetrievalResult 对象列表）。
# 调用生成器：上游模块实例化 CitationGenerator 类，并调用其 generate 方法，将检索结果列表作为参数传入。
# 数据遍历与提取：generate 方法内部开始遍历列表，为每个结果分配展示序号（从 1 开始递增）。
# 信息组装：提取每个结果的关键元数据（如文件路径、页码）和核心指标（如文本块 ID、相关性得分），将其封装成标准字典。
# 返回结果：将组装好的字典列表返回给上游模块。
# 响应拼接：上游模块将这些引用数据与 LLM 生成的最终文本回答一起打包，返回给前端进行展示。
# 4. 场景示例
# 假设用户在系统中提问：“公司的差旅报销流程是什么？”

# 检索阶段：系统的检索模块在知识库中找到了两段最相关的文本，返回了两个 RetrievalResult 对象：
# 结果 1：来自 财务制度手册.pdf 的第 10 页，相似度得分 0.92。
# 结果 2：来自 日常办公指南.docx 的第 3 页，相似度得分 0.85。
# 生成引用阶段：系统调用 CitationGenerator().generate([结果1, 结果2])。
# 数据处理：
# 处理结果 1 时，提取出 source="财务制度手册.pdf", page=10, score=0.92，并分配 index=1。
# 处理结果 2 时，提取出 source="日常办公指南.docx", page=3, score=0.85，并分配 index=2。
# 最终输出：generate 方法返回如下结构化的列表：
# python
# [
#     {"index": 1, "source": "财务制度手册.pdf", "page": 10, "chunk_id": "chunk_001", "score": 0.92},
#     {"index": 2, "source": "日常办公指南.docx", "page": 3, "chunk_id": "chunk_042", "score": 0.85}
# ]
# 前端展示：前端拿到这个列表后，就可以在 AI 回答的末尾自动渲染出引用标记，例如展示：“参考来源：[1] 财务制度手册.pdf (第10页)；[2] 日常办公指南.docx (第3页)”，让用户清楚知道答案的具体出处。