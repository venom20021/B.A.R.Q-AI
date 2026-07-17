"""
BARQ Knowledge Module — Graph Brain auto-extraction + Obsidian vault dumping.

Provides:
1. ObsidianDumper — writes YAML-frontmatter .md files into an Obsidian vault
2. AutoExtractor — scheduled extraction of knowledge triplets from jobs/social
"""

from .obsidian_dumper import ObsidianDumper
from .auto_extractor import AutoExtractor

__all__ = ["ObsidianDumper", "AutoExtractor"]
