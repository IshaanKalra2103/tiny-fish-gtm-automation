"""vidgen: short-form video generation (ElevenLabs voice, Bing images, gameplay, ffmpeg)."""

from .cli import main
from .render import FORMATS, render

__all__ = ["main", "render", "FORMATS"]
