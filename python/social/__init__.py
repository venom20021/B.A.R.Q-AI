"""
BARQ Social Media Automation Module

End-to-end pipeline for trend research, AI scripting,
video assembly, and multi-platform posting.
"""

from .trends import TrendResearch
from .script import ScriptGenerator
from .video import VideoAssembler
from .poster import ContentPoster

__all__ = ["TrendResearch", "ScriptGenerator", "VideoAssembler", "ContentPoster"]
