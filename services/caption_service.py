"""Caption service for generating and burning captions into videos.

This module handles:
- SRT caption generation from video audio using Whisper
- Caption burning into video with customizable styling
"""

from __future__ import annotations

from typing import Any, Optional, Tuple
import os


def generate_srt(
    main_module: Any,
    video_path: str,
    srt_output_path: str,
    max_words: int = 3,
) -> str:
    """Generate Instagram-style SRT captions from video using Whisper.

    Args:
        main_module: The main module containing generate_instagram_srt_from_video
        video_path: Path to the video file with audio
        srt_output_path: Path where the SRT file should be saved
        max_words: Maximum words per caption segment (default: 3)

    Returns:
        Path to the generated SRT file
    """
    main_module.generate_instagram_srt_from_video(
        video_path,
        srt_output_path,
        max_words,
    )
    print(f"SUCCESS: SRT captions generated: {srt_output_path}")
    return srt_output_path


def burn_captions(
    caption_module: Any,
    video_path: str,
    srt_path: str,
    output_path: str,
    font_name: Optional[str] = None,
    font_size: int = 40,
    font_color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2,
    position: Tuple[str, str] = ("center", "bottom"),
) -> Optional[str]:
    """Burn captions into video with customizable styling using ImageMagick/MoviePy.

    Args:
        caption_module: The caption module (e.g., try2) containing burn_captions
        video_path: Path to the input video file
        srt_path: Path to the SRT caption file
        output_path: Path for the output video with burned captions
        font_name: Font name to use (None for default)
        font_size: Font size in pixels (default: 40)
        font_color: Font color (default: "white")
        stroke_color: Text stroke/outline color (default: "black")
        stroke_width: Stroke width in pixels (default: 2)
        position: Tuple of (horizontal, vertical) position (default: ("center", "bottom"))

    Returns:
        Path to the output video with burned captions, or None if failed
    """
    try:
        caption_module.burn_captions(
            video_path=video_path,
            srt_path=srt_path,
            output_path=output_path,
            font_name=font_name,
            font_size=font_size,
            font_color=font_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            position=position,
        )
        print(f"SUCCESS: Final video with burned captions created: {output_path}")
        return output_path
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: Failed to burn captions with ImageMagick: {exc}")
        return None


def burn_captions_with_env_config(
    caption_module: Any,
    video_path: str,
    srt_path: str,
    output_path: str,
) -> Optional[str]:
    """Burn captions using configuration from environment variables.

    Reads caption styling from environment variables:
    - CAPTION_FONT_NAME: Font name (optional)
    - CAPTION_FONT_SIZE: Font size in pixels (default: 40)
    - CAPTION_FONT_COLOR: Font color (default: "white")
    - CAPTION_STROKE_COLOR: Stroke color (default: "black")
    - CAPTION_STROKE_WIDTH: Stroke width (default: 2)

    Args:
        caption_module: The caption module containing burn_captions
        video_path: Path to the input video file
        srt_path: Path to the SRT caption file
        output_path: Path for the output video with burned captions

    Returns:
        Path to the output video with burned captions, or None if failed
    """
    font_name = os.getenv("CAPTION_FONT_NAME") or None
    font_size = int(os.getenv("CAPTION_FONT_SIZE", 40))
    font_color = os.getenv("CAPTION_FONT_COLOR", "white")
    stroke_color = os.getenv("CAPTION_STROKE_COLOR", "black")
    stroke_width = int(os.getenv("CAPTION_STROKE_WIDTH", 2))

    return burn_captions(
        caption_module=caption_module,
        video_path=video_path,
        srt_path=srt_path,
        output_path=output_path,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        position=("center", "bottom"),
    )
