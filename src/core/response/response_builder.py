"""Build MCP tool responses from retrieval results."""

from __future__ import annotations

from core import RetrievalResult

from .citation_generator import CitationGenerator
from .multimodal_assembler import MultimodalAssembler


MCPToolResult = dict


class ResponseBuilder:
    """Build Markdown and structured citations for MCP tool responses."""

    def __init__(
        self,
        citation_generator: CitationGenerator | None = None,
        multimodal_assembler: MultimodalAssembler | None = None,
    ) -> None:
        self.citation_generator = citation_generator or CitationGenerator()
        self.multimodal_assembler = multimodal_assembler or MultimodalAssembler()

    def build(
        self,
        retrieval_results: list[RetrievalResult],
        query: str,
    ) -> MCPToolResult:
        """Return an MCP-compatible tool result."""
        citations = self.citation_generator.generate(retrieval_results)
        markdown = _build_markdown(query, retrieval_results, citations)
        text_content = [{"type": "text", "text": markdown}]
        return {
            "content": self.multimodal_assembler.assemble(text_content, retrieval_results),
            "structuredContent": {
                "query": query,
                "citations": citations,
            },
            "isError": False,
        }


def _build_markdown(
    query: str,
    retrieval_results: list[RetrievalResult],
    citations: list[dict],
) -> str:
    if not retrieval_results:
        return (
            f"未找到与 `{query}` 相关的文档。"
            "请先运行 ingestion 流程摄取数据，或尝试更换查询关键词。"
        )

    lines = [f"找到 {len(retrieval_results)} 条与 `{query}` 相关的结果："]
    for result, citation in zip(retrieval_results, citations, strict=True):
        index = citation["index"]
        source = citation["source"] or "-"
        page = citation["page"]
        page_text = f", page={page}" if page is not None else ""
        lines.extend(
            [
                "",
                f"### [{index}] {result.chunk_id}",
                _preview(result.text),
                "",
                f"引用：[{index}] source={source}{page_text}, score={result.score:.6f}",
            ]
        )
    return "\n".join(lines)


def _preview(text: str, limit: int = 800) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
