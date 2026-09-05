"""Fixed MVP topic taxonomy and deterministic safety routing."""

from enum import StrEnum


class PrimaryTopic(StrEnum):
    MODELS_AND_AGENTS = "大模型与智能体"
    PRODUCTS_AND_INDUSTRY = "AI 产品形态与行业应用"
    PRODUCT_PRACTICE = "AI 产品实战"
    ENGINEERING_SAFETY = "AI 工程安全与可靠性"


SAFETY_MARKERS = (
    "hallucination",
    "幻觉",
    "prompt injection",
    "提示词注入",
    "privilege escalation",
    "unauthorized tool",
    "越权",
    "poisoning",
    "supply-chain poison",
    "投毒",
    "data contamination",
    "knowledge base contamination",
    "数据污染",
    "知识库污染",
    "data leakage",
    "sensitive data leak",
    "数据泄露",
    "敏感数据泄露",
)

EXCLUDED_MVP_MARKERS = (
    "arxiv.org",
    "academic paper",
    "research paper",
    "学术论文",
    "监管文件",
    "regulatory filing",
    "law database",
    "法规数据库",
    "compliance obligation",
    "合规义务",
)


def enforce_safety_topic(proposed: PrimaryTopic, untrusted_text: str) -> PrimaryTopic:
    """Safety terms have a product-owned route that model output cannot override."""

    folded = untrusted_text.casefold()
    if any(marker in folded for marker in SAFETY_MARKERS):
        return PrimaryTopic.ENGINEERING_SAFETY
    return proposed


def is_mvp_excluded(title: str, content: str, url: str = "") -> bool:
    folded = f"{title}\n{content}\n{url}".casefold()
    return any(marker in folded for marker in EXCLUDED_MVP_MARKERS)
