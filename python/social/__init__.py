"""
BARQ Social Media Automation Module

End-to-end pipeline for trend research, AI scripting,
video assembly, and multi-platform posting.
"""

from .calendar import ContentCalendar
from .poster import ContentPoster
from .script import ScriptGenerator
from .trends import TrendResearch
from .video import VideoAssembler

__all__ = [
    "TrendResearch",
    "ScriptGenerator",
    "VideoAssembler",
    "ContentPoster",
    "ContentCalendar",
]
