"""
BARQ Agentic Workflows — named, scheduled, skill-backed workflow modules.

- morning_briefing   (W4)  Prompt-Chaining: weather + calendar + jobs + memory → briefing
- conversation_memory (W5) Orchestrator-Workers: extract action items/entities from chat
- research_to_brain  (W6) Orchestrator-Workers: research report → knowledge graph triplets
- content_critic     (W7) Evaluator-Optimizer: draft → critique → rewrite until quality gate
- weekly_review      (W11) Analytics + skill success rates + memory → weekly summary report

Each module exposes an async ``run(...)`` that returns a result dict/string and a
``*_skill`` handler suitable for registration in the SkillRegistry.
"""
