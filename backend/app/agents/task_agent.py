from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import CognitiveVector, TaskInput, TaskProfile


@dataclass(frozen=True)
class CategoryRule:
    keywords: tuple[str, ...]
    requirements: CognitiveVector
    rationale: str


CATEGORY_RULES: dict[str, CategoryRule] = {
    "strategic": CategoryRule(
        keywords=(
            "strategy", "strategic", "roadmap", "pitch", "investor", "fundraising",
            "规划", "战略", "融资", "路演", "商业计划", "决策",
        ),
        requirements=CognitiveVector(executive=0.92, attention=0.78, creative=0.76, social=0.28),
        rationale="Strategic work combines executive reasoning with sustained attention and synthesis.",
    ),
    "analytical": CategoryRule(
        keywords=(
            "analysis", "analyze", "financial", "report", "review", "debug", "research",
            "分析", "财务", "报告", "审查", "调试", "研究", "论文",
        ),
        requirements=CognitiveVector(executive=0.84, attention=0.92, creative=0.34, social=0.18),
        rationale="Analytical work relies most on focused attention and structured reasoning.",
    ),
    "creative": CategoryRule(
        keywords=(
            "design", "brainstorm", "write", "concept", "prototype", "ideate",
            "设计", "创作", "头脑风暴", "写作", "构思", "原型",
        ),
        requirements=CognitiveVector(executive=0.56, attention=0.66, creative=0.95, social=0.22),
        rationale="Generative work benefits from creative fluency with enough attention to develop ideas.",
    ),
    "social": CategoryRule(
        keywords=(
            "meeting", "interview", "negotiation", "coach", "one-on-one", "presentation",
            "会议", "面试", "谈判", "沟通", "汇报", "一对一",
        ),
        requirements=CognitiveVector(executive=0.62, attention=0.58, creative=0.38, social=0.92),
        rationale="Interactive work is dominated by social processing and real-time attention.",
    ),
    "administrative": CategoryRule(
        keywords=(
            "email", "inbox", "expense", "organize", "admin", "update",
            "邮件", "报销", "整理", "行政", "更新", "归档",
        ),
        requirements=CognitiveVector(executive=0.24, attention=0.42, creative=0.16, social=0.38),
        rationale="Routine administration is comparatively tolerant of lower cognitive capacity.",
    ),
}

DEFAULT_RULE = CategoryRule(
    keywords=(),
    requirements=CognitiveVector(executive=0.58, attention=0.64, creative=0.42, social=0.30),
    rationale="General knowledge work requires a balanced mix of reasoning and attention.",
)


class TaskAnalyst:
    """Offline baseline task agent with an LLM-compatible output contract."""

    def analyze(self, tasks: list[TaskInput]) -> list[TaskProfile]:
        return [self._analyze_task(task) for task in tasks]

    def _analyze_task(self, task: TaskInput) -> TaskProfile:
        text = f"{task.title} {task.description}".lower()
        scored_categories = {
            category: sum(1 for keyword in rule.keywords if keyword in text)
            for category, rule in CATEGORY_RULES.items()
        }
        category, match_count = max(scored_categories.items(), key=lambda item: item[1])
        rule = CATEGORY_RULES[category] if match_count else DEFAULT_RULE
        if not match_count:
            category = "knowledge_work"

        requirements = rule.requirements.model_copy(deep=True)
        duration_factor = min(max((task.duration_minutes - 45) / 240, 0), 0.18)
        requirements.attention = min(1.0, round(requirements.attention + duration_factor, 3))
        intensity = round(
            0.32 * requirements.executive
            + 0.32 * requirements.attention
            + 0.22 * requirements.creative
            + 0.14 * requirements.social,
            3,
        )
        matched = [
            keyword
            for keyword in CATEGORY_RULES.get(category, DEFAULT_RULE).keywords
            if keyword in text
        ][:3]
        evidence = f"Matched task signals: {', '.join(matched)}." if matched else "No specialist keyword matched; balanced baseline applied."
        return TaskProfile(
            task_id=task.id,
            title=task.title,
            category=category,
            requirements=requirements,
            intensity=min(1.0, intensity),
            rationale=[rule.rationale, evidence],
        )

