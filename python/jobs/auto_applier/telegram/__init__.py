"""Two-way interactive Telegram bot — aiogram with inline Apply/Skip buttons."""

from .bot import AutoApplyBot
from .handlers import Router as HandlersRouter

__all__ = ["AutoApplyBot", "HandlersRouter"]
