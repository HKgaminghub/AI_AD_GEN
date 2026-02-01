"""Audio service for generating and attaching voiceover audio to videos.

This module handles:
- Voiceover script generation using Gemini
- TTS audio generation using ElevenLabs
- Audio duration adjustment
- Audio attachment to video
"""

from __future__ import annotations

from typing import Dict, Any
import os


def generate_voiceover_script(main_module: Any, video_path: str) -> Dict[str, Any]:
    """Generate a voiceover script for a video using Gemini.

    Args:
        main_module: The main module containing generate_script and get_video_duration
        video_path: Path to the video file

    Returns:
        Dictionary containing:
        - script: The generated script text
        - script_file: Path to the saved script file
        - duration: Video duration in seconds
    """
    duration = main_module.get_video_duration(video_path)
    script: str = main_module.generate_script(video_path, duration)

    # Save script to file for inspection / reuse
    # Create script path based on video path directory
    dir_name = os.path.dirname(video_path)
    filename = os.path.splitext(os.path.basename(video_path))[0]
    script_file = os.path.join(dir_name, f"{filename}_script.txt")
    
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(script)
    print(f"INFO: Script saved to: {script_file}")

    return {
        "script": script,
        "script_file": script_file,
        "duration": duration,
    }


def generate_and_attach_audio(
    main_module: Any,
    video_path: str,
    script: str,
    duration: float,
    output_audio_path: str,
    safe_audio_path: str,
    output_video_path: str,
) -> str:
    """Generate TTS audio from script and attach to video.

    Args:
        main_module: The main module containing audio generation functions
        video_path: Path to the input video file
        script: The voiceover script text
        duration: Target audio duration in seconds
        output_audio_path: Path to save the raw generated audio
        safe_audio_path: Path to save the duration-safe audio
        output_video_path: Path for the output video with audio

    Returns:
        Path to the output video with attached audio
    """
    # Generate TTS audio using ElevenLabs
    main_module.generate_voice(script, output_audio_path)

    # Make audio safe (adjust duration to match video)
    # Note: make_audio_safe exports to SAFE_AUDIO global in 9x16_srt.py usually.
    # We need to ensure we call a version that accepts output path. 
    main_module.make_audio_safe(output_audio_path, duration, safe_audio_path)

    # Attach audio to video
    main_module.attach_audio_to_video(
        video_path,
        safe_audio_path,
        output_video_path,
    )

    print(f"SUCCESS: Audio attached to video: {output_video_path}")
    return output_video_path
