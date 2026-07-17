"""
BARQ Dynamic Chart Agent — Generative UI for the Dashboard.

Interprets natural language queries, fetches data from the database,
and returns a Recharts JSON schema that the React frontend can render
on-the-fly without any hardcoded if/else chains.

Supported chart types:
  - BarChart
  - LineChart
  - PieChart
  - AreaChart
  - RadialBarChart
"""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from utils.ollama_client import OllamaClient

# ─── Recharts Schema Types ────────────────────────────────────────────────

CHART_TYPES = ["BarChart", "LineChart", "PieChart", "AreaChart", "RadialBarChart"]


class RechartsSchema:
    """A serialisable schema describing a Recharts chart to render."""

    def __init__(
        self,
        chart_type: str,
        title: str,
        data: list[dict[str, Any]],
        config: dict[str, Any],
    ):
        assert chart_type in CHART_TYPES, f"Unsupported chart type: {chart_type}"
        self.type = chart_type
        self.title = title
        self.data = data
        self.config = config

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "data": self.data,
            "config": self.config,
        }


# ─── Intent Classifier ───────────────────────────────────────────────────

class ChartIntentClassifier:
    """Classifies a natural language query into a chart intent.

    Uses LLM if available; falls back to keyword matching.
    """

    def __init__(self):
        self.llm = OllamaClient()

    # ── Keyword-based intent mapping (fallback) ──────────────────────

    INTENT_KEYWORDS: dict[str, dict[str, Any]] = {
        "career_funnel": {
            "keywords": [
                "job", "career", "application", "funnel", "hire", "recruit",
                "interview", "offer", "scan", "match",
            ],
            "chart_type": "BarChart",
            "title": "Career Funnel Overview",
            "config": {
                "xKey": "stage",
                "yKey": "count",
                "xLabel": "Stage",
                "yLabel": "Count",
                "color": "#818cf8",
                "showLegend": False,
            },
        },
        "social_performance": {
            "keywords": [
                "social", "platform", "follower", "view", "engagement",
                "youtube", "twitter", "tiktok", "instagram", "linkedin",
            ],
            "chart_type": "BarChart",
            "title": "Social Media Performance",
            "config": {
                "xKey": "platform",
                "yKey": "value",
                "xLabel": "Platform",
                "yLabel": "Count",
                "color": "#34d399",
                "showLegend": False,
                "stacked": False,
            },
        },
        "revenue": {
            "keywords": [
                "revenue", "income", "earning", "money", "profit",
                "monthly", "financial", "source",
            ],
            "chart_type": "AreaChart",
            "title": "Revenue Over Time",
            "config": {
                "xKey": "month",
                "yKey": "total",
                "xLabel": "Month",
                "yLabel": "Revenue ($)",
                "color": "#fbbf24",
                "showLegend": False,
                "showGrid": True,
            },
        },
        "activity": {
            "keywords": [
                "activity", "recent", "event", "log", "timeline",
                "history",
            ],
            "chart_type": "LineChart",
            "title": "Recent Activity",
            "config": {
                "xKey": "date",
                "yKey": "count",
                "xLabel": "Date",
                "yLabel": "Activity Count",
                "color": "#a78bfa",
                "showLegend": False,
            },
        },
        "platform_breakdown": {
            "keywords": [
                "breakdown", "comparison", "compare", "across", "per",
                "distribution", "split",
            ],
            "chart_type": "PieChart",
            "title": "Platform Distribution",
            "config": {
                "nameKey": "name",
                "valueKey": "value",
                "showLegend": True,
            },
        },
    }

    def classify_keyword(self, query: str) -> Optional[str]:
        """Return intent key based on keyword matching, or None."""
        query_lower = query.lower()
        best_intent = None
        best_score = 0

        for intent_key, intent_data in self.INTENT_KEYWORDS.items():
            score = 0
            for kw in intent_data["keywords"]:
                if kw in query_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_intent = intent_key

        return best_intent if best_score > 0 else None

    # ── LLM-based classification ────────────────────────────────────

    LLM_INTENT_PROMPT = """You are BARQ's chart intent classifier. Given a user query, determine:
1. Which data domain they want (career, social, revenue, activity, or cross-platform)
2. What chart type is best (BarChart, LineChart, PieChart, AreaChart, RadialBarChart)
3. A short title for the chart
4. How data maps to axes

Return ONLY a JSON object with this exact shape (no markdown, no explanation):
{
  "intent": "career_funnel | social_performance | revenue | activity | platform_breakdown",
  "chart_type": "BarChart | LineChart | PieChart | AreaChart | RadialBarChart",
  "title": "string",
  "reasoning": "short explanation"
}"""

    async def classify_llm(self, query: str) -> Optional[dict[str, str]]:
        """Use the LLM to classify the query intent."""
        try:
            messages = [
                {"role": "system", "content": self.LLM_INTENT_PROMPT},
                {"role": "user", "content": f"Query: {query}"},
            ]
            response = await self.llm.chat(messages)
            # Strip markdown fences
            text = re.sub(r"```(?:json)?\s*", "", response).strip()
            data = json.loads(text)
            if data.get("intent") and data.get("chart_type"):
                return data
        except Exception:
            pass
        return None


# ─── Data Fetcher ───────────────────────────────────────────────────────

class ChartDataFetcher:
    """Fetches data from DAOs based on intent key."""

    def __init__(self, analytics_dao, social_dao=None):
        self.analytics = analytics_dao
        self.social = social_dao

    async def fetch(self, intent: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch data for a given intent.

        Returns:
            Tuple of (data_rows, default_config_overrides)
        """
        if intent == "career_funnel":
            return await self._fetch_career_funnel()
        elif intent == "social_performance":
            return await self._fetch_social_performance()
        elif intent == "revenue":
            return await self._fetch_revenue()
        elif intent == "activity":
            return await self._fetch_activity()
        elif intent == "platform_breakdown":
            return await self._fetch_platform_breakdown()
        return [], {}

    async def _fetch_career_funnel(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        funnel = await self.analytics.compute_funnel_summary()
        stages = [
            ("Jobs Scanned", funnel.get("jobs_scanned", 0)),
            ("Matches Found", funnel.get("matches_found", 0)),
            ("Applications Sent", funnel.get("applications_sent", 0)),
            ("Interviews", funnel.get("interviews_scheduled", 0)),
            ("Offers", funnel.get("offers_received", 0)),
        ]
        data = [{"stage": stage, "count": count} for stage, count in stages]
        # Color per stage: indigo gradation
        colors = ["#6366f1", "#818cf8", "#a5b4fc", "#c7d2fe", "#e0e7ff"]
        return data, {"colors": colors}

    async def _fetch_social_performance(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        snapshots = await self.analytics.get_latest_social_snapshots()
        if not snapshots:
            # Return demo data so the chart always has something to render
            return self._demo_social(), {}

        rows = []
        for s in snapshots:
            rows.append({
                "platform": s.get("platform", "unknown"),
                "followers": s.get("followers", 0),
                "views": s.get("total_views", 0),
                "engagement": s.get("total_engagement", 0),
                "revenue": s.get("revenue", 0),
            })
        return rows, {}

    def _demo_social(self) -> list[dict[str, Any]]:
        return [
            {"platform": "YouTube", "followers": 12400, "views": 452000, "engagement": 8900, "revenue": 3200},
            {"platform": "Twitter", "followers": 5600, "views": 189000, "engagement": 4200, "revenue": 1200},
            {"platform": "TikTok", "followers": 28300, "views": 892000, "engagement": 21500, "revenue": 5800},
            {"platform": "LinkedIn", "followers": 3200, "views": 45000, "engagement": 1100, "revenue": 800},
        ]

    async def _fetch_revenue(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        by_month = await self.analytics.get_revenue_by_month(months=12)
        if by_month:
            rows = []
            for r in reversed(by_month):
                rows.append({
                    "month": r.get("month", ""),
                    "total": r.get("total", 0),
                    "sources": r.get("sources", ""),
                })
            return rows, {}
        # Demo data
        return self._demo_revenue(), {}

    def _demo_revenue(self) -> list[dict[str, Any]]:
        return [
            {"month": "Jan", "total": 4200, "sources": "youtube,blog"},
            {"month": "Feb", "total": 5100, "sources": "youtube,blog"},
            {"month": "Mar", "total": 4800, "sources": "youtube,twitter"},
            {"month": "Apr", "total": 6200, "sources": "youtube,twitter,blog"},
            {"month": "May", "total": 5900, "sources": "youtube,twitter"},
            {"month": "Jun", "total": 7400, "sources": "youtube,tiktok,twitter"},
        ]

    async def _fetch_activity(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        activities = await self.analytics.get_recent_activity(limit=50)
        # Group by date
        date_counts: Counter = Counter()
        for a in activities:
            created = a.get("created_at", "")
            date = created[:10] if created else datetime.now(timezone.utc).date().isoformat()
            date_counts[date] += 1
        rows = sorted(
            [{"date": d, "count": c} for d, c in date_counts.items()],
            key=lambda x: x["date"],
        )
        return rows[-14:], {}  # last 14 days

    async def _fetch_platform_breakdown(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        snapshots = await self.analytics.get_latest_social_snapshots()
        if snapshots:
            total = sum(s.get("followers", 0) for s in snapshots)
            if total > 0:
                rows = [
                    {"name": s.get("platform", "unknown"), "value": s.get("followers", 0)}
                    for s in snapshots
                ]
                return rows, {}
        # Demo pie data
        return [
            {"name": "YouTube", "value": 12400},
            {"name": "TikTok", "value": 28300},
            {"name": "Twitter", "value": 5600},
            {"name": "LinkedIn", "value": 3200},
        ], {}


# ─── DynamicChartAgent ─────────────────────────────────────────────────

class DynamicChartAgent:
    """Orchestrates intent classification, data fetching, and schema construction."""

    def __init__(self, analytics_dao, social_dao=None):
        self.classifier = ChartIntentClassifier()
        self.fetcher = ChartDataFetcher(analytics_dao, social_dao)

    async def build_schema(self, query: str) -> dict[str, Any]:
        """Process a natural language query and return a Recharts schema.

        Args:
            query: Natural language query from the user.

        Returns:
            Dict with keys: query, interpretation, schema (RechartsSchema as dict)
        """
        # 1. Try LLM classification first
        llm_result = await self.classifier.classify_llm(query)

        if llm_result:
            intent = llm_result.get("intent", "")
            chart_type = llm_result.get("chart_type", "BarChart")
            title = llm_result.get("title", "Chart")
            interpretation = llm_result.get("reasoning", "LLM interpreted query")
        else:
            # Fallback to keyword classification
            intent_key = self.classifier.classify_keyword(query)
            if intent_key is None:
                # Default: show career funnel
                intent_key = "career_funnel"
                chart_type = "BarChart"
                title = "Career Funnel Overview"
                interpretation = "Showing career funnel (default)"
            else:
                intent_data = self.classifier.INTENT_KEYWORDS.get(intent_key, {})
                chart_type = intent_data.get("chart_type", "BarChart")
                title = intent_data.get("title", "Analytics")
                interpretation = f"Keyword match: {intent_key}"

        # 2. Fetch data
        data_rows, extra_config = await self.fetcher.fetch(intent_key)

        # 3. Build config
        intent_data = self.classifier.INTENT_KEYWORDS.get(intent_key, {})
        base_config = dict(intent_data.get("config", {}))
        base_config.update(extra_config)

        schema = RechartsSchema(
            chart_type=chart_type,
            title=title,
            data=data_rows,
            config=base_config,
        )

        return {
            "query": query,
            "interpretation": interpretation,
            "schema": schema.to_dict(),
        }
