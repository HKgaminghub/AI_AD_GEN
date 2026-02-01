"""Scene service for generating and merging video scenes.

This module handles:
- Scene prompt generation from images using Gemini
- Single/multiple scene video generation with retry logic
- Scene merging into final video
"""

from __future__ import annotations

from typing import Dict, Any, List
import os
import time

from moviepy.editor import VideoFileClip, concatenate_videoclips


def generate_scene_prompts(main_module: Any, temp_images: Dict[str, str]) -> Dict[str, str]:
    """Generate scene prompts from images using Gemini.

    Args:
        main_module: The main module containing SCENE_IMAGES and generate_scene_prompts_from_gemini
        temp_images: Dictionary mapping scene keys to temporary image paths

    Returns:
        Dictionary mapping scene keys to generated prompts
    """
    # Use temporary images to infer prompts without touching originals
    original_images = main_module.SCENE_IMAGES.copy()
    main_module.SCENE_IMAGES = temp_images
    try:
        scenes = main_module.generate_scene_prompts_from_gemini()
        return scenes
    finally:
        # Always restore original config
        main_module.SCENE_IMAGES = original_images


def generate_single_scene(
    main_module: Any,
    scene_key: str,
    prompt: str,
    temp_image_path: str,
    generate_scene_with_retry,
) -> Dict[str, Any]:
    """Generate a single scene video with retry logic.

    Args:
        main_module: The main module containing scene configuration
        scene_key: Key identifying the scene (e.g., "scene1")
        prompt: The prompt for scene generation
        temp_image_path: Path to the temporary image for this scene
        generate_scene_with_retry: Retry function for scene generation

    Returns:
        Dictionary with scene generation result containing:
        - scene: The scene key
        - status: "success", "error", or "skipped"
        - output_file: Path to generated video (if successful)
        - error: Error message (if failed)
    """
    try:
        safe_img = f"safe_{scene_key}.png"
        main_module.convert_to_vertical_safe(temp_image_path, safe_img)
        output_file = main_module.SCENE_FILES.get(scene_key, f"{scene_key}.mp4")

        print(f"Generating {scene_key}...")
        success, error_msg = generate_scene_with_retry(
            prompt,
            safe_img,
            output_file,
            max_retries=3,
            retry_delay=20,
        )

        if success:
            return {
                "scene": scene_key,
                "status": "success",
                "output_file": output_file,
            }
        else:
            print(f"Error generating {scene_key}: {error_msg}")
            return {
                "scene": scene_key,
                "status": "error",
                "error": error_msg,
            }
    except Exception as exc:  # noqa: BLE001
        print(f"Error generating {scene_key}: {exc}")
        return {
            "scene": scene_key,
            "status": "error",
            "error": str(exc),
        }


def generate_all_scenes(
    main_module: Any,
    scenes: Dict[str, str],
    temp_images: Dict[str, str],
    generate_scene_with_retry,
    required_scenes: List[str] = None,
) -> List[Dict[str, Any]]:
    """Generate all scenes with retry logic and 20-second spacing.

    Args:
        main_module: The main module containing scene configuration
        scenes: Dictionary mapping scene keys to prompts
        temp_images: Dictionary mapping scene keys to temporary image paths
        generate_scene_with_retry: Retry function for scene generation
        required_scenes: List of required scene keys (defaults to ["scene1", "scene2", "scene3", "scene4"])

    Returns:
        List of scene result dictionaries
    """
    if required_scenes is None:
        required_scenes = ["scene1", "scene2", "scene3", "scene4"]

    scene_results: List[Dict[str, Any]] = []

    for key in required_scenes:
        if key not in scenes:
            scene_results.append(
                {
                    "scene": key,
                    "status": "skipped",
                    "reason": "No prompt generated",
                }
            )
            continue

        result = generate_single_scene(
            main_module,
            key,
            scenes[key],
            temp_images[key],
            generate_scene_with_retry,
        )
        scene_results.append(result)

        # Add 20-second delay between scenes (except after the last one)
        if key != required_scenes[-1]:
            print("Waiting 20 seconds before next scene...")
            time.sleep(20)

    return scene_results


def merge_scenes(
    main_module: Any,
    scene_results: List[Dict[str, Any]],
) -> str:
    """Merge successful scenes into a single video.

    Args:
        main_module: The main module containing TARGET_W, TARGET_H, and FINAL_VIDEO
        scene_results: List of scene result dictionaries

    Returns:
        Path to the merged final video

    Raises:
        ValueError: If no successful scenes are found to merge
    """
    successful_scenes = [r for r in scene_results if r.get("status") == "success"]
    if not successful_scenes:
        raise ValueError("No successful scenes found to merge")

    successful_scene_files: List[str] = []
    for r in successful_scenes:
        path = r.get("output_file")
        if path and os.path.exists(path):
            successful_scene_files.append(path)

    if not successful_scene_files:
        raise ValueError("No scene files found to merge after generation")

    clips = [VideoFileClip(p) for p in successful_scene_files]
    try:
        final = concatenate_videoclips(clips, method="compose")
        final = final.resize((main_module.TARGET_W, main_module.TARGET_H))
        final.write_videofile(main_module.FINAL_VIDEO, fps=30)
    finally:
        for c in clips:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass

    print(
        f"\nSUCCESS: FINAL VIDEO READY: {main_module.FINAL_VIDEO} "
        f"(merged {len(successful_scene_files)} scenes)"
    )

    return main_module.FINAL_VIDEO
