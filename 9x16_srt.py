import google.generativeai as genai
from PIL import Image, ImageFilter
import json
import re
import os
from dotenv import load_dotenv
import time
import random
import requests
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from pydub import AudioSegment
import whisper

# =====================================
# CONFIG
# =====================================

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
DEAPI_KEY = os.getenv("DEAPI_KEY") # Note: app.py handles rotation but this script uses it directly too
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

SCENE_IMAGES = {
    "scene1": os.getenv("SCENE1_IMAGE_PATH", "scene1.png"),
    "scene2": os.getenv("SCENE2_IMAGE_PATH", "scene2.png"),
    "scene3": os.getenv("SCENE3_IMAGE_PATH", "scene3.png"),
    "scene4": os.getenv("SCENE4_IMAGE_PATH", "scene4.png"),
}

SCENE_FILES = {
    "scene1": os.getenv("SCENE1_FILE", "scene1.mp4"),
    "scene2": os.getenv("SCENE2_FILE", "scene2.mp4"),
    "scene3": os.getenv("SCENE3_FILE", "scene3.mp4"),
    "scene4": os.getenv("SCENE4_FILE", "scene4.mp4"),
}

FINAL_VIDEO = os.getenv("FINAL_VIDEO", "final_reel_ad_9x16.mp4")
FINAL_VIDEO_WITH_VOICE = os.getenv("FINAL_VIDEO_WITH_VOICE", "final_video_with_voice.mp4")

TARGET_W = int(os.getenv("TARGET_WIDTH", 432))
TARGET_H = int(os.getenv("TARGET_HEIGHT", 768))

VOICE_ID = os.getenv("VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
OUTPUT_AUDIO = os.getenv("OUTPUT_AUDIO", "final_voice.mp3")
SAFE_AUDIO = os.getenv("SAFE_AUDIO", "final_voice_safe.mp3")

model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

# =====================================
# WHISPER CAPTION CONFIG
# =====================================

SRT_OUTPUT = "ainsta_caption.srt"
MAX_WORDS = 3
WHISPER_MODEL_SIZE = "small"

# =====================================
# UTIL
# =====================================

def show_progress_bar(progress):
    bar_length = 30
    filled = int(bar_length * progress / 100)
    bar = "#" * filled + "-" * (bar_length - filled)
    print(f"\r[{bar}] {progress:.1f}%", end="", flush=True)

def clean_json(text: str):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

# =====================================
# IMAGE -> BLUR BACKGROUND 9:16
# =====================================

def convert_to_vertical_safe(image_path, output_path):
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    bg = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(30))

    scale = min(TARGET_W / w, TARGET_H / h)
    fg = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    x = (TARGET_W - fg.width) // 2
    y = (TARGET_H - fg.height) // 2

    bg.paste(fg, (x, y))
    bg.save(output_path)

    return output_path

# =====================================
# STEP 1 - GEMINI SCENE PROMPTS
# =====================================

def generate_scene_prompts_from_gemini():

    images = [Image.open(SCENE_IMAGES[k]) for k in SCENE_IMAGES]

    prompt = """
You are an elite cinematic advertisement director and AI video engineer.

You are given 4 images of the SAME product from different angles.
Infer product category, material, surface behavior, scale.

Rules:
- Same dark premium studio
- Soft volumetric fog
- Controlled rim lighting
- Glossy floor reflections
- Vertical 9:16 framing
- No distortion

Scene logic:
1. Hero reveal
2. Side geometry
3. 3D orbit / depth
4. Important detail close-up

Return STRICT JSON ONLY:

{
  "scene1": "",
  "scene2": "",
  "scene3": "",
  "scene4": ""
}
"""

    print("AI: Asking Gemini to design scenes...")
    resp = model.generate_content([prompt] + images)
    return clean_json(resp.text)

# =====================================
# STEP 2 - DEAPI VIDEO GENERATION
# =====================================

def generate_scene(prompt: str, image_path: str, out_file: str):

    print(f"\nSCENE: Generating {out_file}...")

    url = "https://api.deapi.ai/api/v1/client/img2video"
    headers = {"Authorization": f"Bearer {DEAPI_KEY}"}
    files = {"first_frame_image": open(image_path, "rb")}

    data = {
        "prompt": prompt,
        "width": TARGET_W,
        "height": TARGET_H,
        "fps": 30,
        "frames": 120,
        "steps": 1,
        "guidance": 8,
        "seed": random.randint(1, 99999999),
        "model": "Ltxv_13B_0_9_8_Distilled_FP8",
        "motion": "cinematic",
    }

    r = requests.post(url, data=data, files=files, headers=headers)
    j = r.json()

    if "data" not in j or "request_id" not in j.get("data", {}):
        print(f"ERROR: DEAPI Error: {json.dumps(j, indent=2)}")
        if "message" in j:
            raise Exception(f"DEAPI Error: {j['message']}")
        raise KeyError(f"Missing 'data' or 'request_id' in response: {j}")

    request_id = j["data"]["request_id"]
    status_url = f"https://api.deapi.ai/api/v1/client/request-status/{request_id}"

    while True:
        res = requests.get(status_url, headers=headers).json()
        progress = res["data"].get("progress", 0)
        show_progress_bar(progress)

        if progress >= 100:
            video_url = res["data"]["result_url"]
            with open(out_file, "wb") as f:
                f.write(requests.get(video_url).content)
            print("\nSUCCESS: Saved:", out_file)
            return

        time.sleep(2)

# =====================================
# STEP 3 - MERGE SCENES
# =====================================

def merge_scenes():
    clips = [VideoFileClip(SCENE_FILES[k]) for k in SCENE_FILES]
    final = concatenate_videoclips(clips, method="compose")
    final = final.resize((TARGET_W, TARGET_H))
    final.write_videofile(FINAL_VIDEO, fps=30)
    print("\nSUCCESS: FINAL VIDEO READY:", FINAL_VIDEO)

# =====================================
# VOICEOVER PIPELINE
# =====================================

def get_video_duration(video_path):
    clip = VideoFileClip(video_path)
    d = clip.duration
    clip.close()
    return round(d, 2)

def generate_script(video_path, duration):
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    # Calculate estimated words needed (approx 2.5 words per second for normal speaking pace)
    target_words = int(duration * 2.5)
    
    prompt = f"""
You are a professional cinematic advertisement voiceover writer.

STRICT RULES:
- Script MUST be approximately {duration} seconds long to match the video flow.
- Target word count: ~{target_words} words.
- The script should NOT be too short. Fill the {duration} seconds.
- Use <emphasis> and <break> tags to control pacing.
- Natural sentences only.
- Return only formatted text.
"""

    r = model.generate_content([prompt, {"mime_type": "video/mp4", "data": video_bytes}])
    return r.text.strip()

def generate_voice(script_text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_API_KEY
    }
    data = {
        "text": script_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.7}
    }
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code != 200:
        print(f"ERROR: ElevenLabs Error ({resp.status_code}): {resp.text}")
        raise Exception(f"ElevenLabs TTS failed: {resp.text}")
    
    audio = resp.content
    with open(OUTPUT_AUDIO, "wb") as f:
        f.write(audio)

def make_audio_safe(audio_path, video_duration):
    audio = AudioSegment.from_mp3(audio_path)
    if len(audio) / 1000 < video_duration:
        audio += AudioSegment.silent(duration=int((video_duration * 1000) - len(audio)))
    audio.export(SAFE_AUDIO, format="mp3")

def attach_audio_to_video(video_path, audio_path, output_path):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    final = video.set_audio(audio)
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    video.close()
    audio.close()
    final.close()

# =====================================
# WHISPER -> INSTAGRAM STYLE SRT
# =====================================

def generate_instagram_srt_from_video(video_path, output_srt, max_words=3):

    print("\nINFO: Generating Instagram-style captions using Whisper...")

    model = whisper.load_model(WHISPER_MODEL_SIZE)

    result = model.transcribe(
        video_path,
        word_timestamps=True,
        verbose=False
    )

    def format_time(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    index = 1
    srt_lines = []

    for segment in result["segments"]:
        words = segment.get("words", [])
        i = 0

        while i < len(words):
            chunk = words[i:i + max_words]

            start = chunk[0]["start"]
            end = chunk[-1]["end"]
            text = " ".join(w["word"].strip() for w in chunk)

            srt_lines.append(
                f"{index}\n"
                f"{format_time(start)} --> {format_time(end)}\n"
                f"{text}\n"
            )

            index += 1
            i += max_words

    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    print("SUCCESS: PERFECTLY SYNCED Instagram SRT created:", output_srt)

# =====================================
# MAIN
# =====================================

def main():

    scenes = generate_scene_prompts_from_gemini()

    for key in scenes:
        safe_img = f"safe_{key}.png"
        convert_to_vertical_safe(SCENE_IMAGES[key], safe_img)
        generate_scene(scenes[key], safe_img, SCENE_FILES[key])
        time.sleep(20)

    merge_scenes()

    while True:
        print("\n1 -> Change a scene")
        print("2 -> Finalize video")

        choice = input("Choose: ").strip()

        if choice == "2":
            print("\nVOICEOVER: Generating voiceover...")
            dur = get_video_duration(FINAL_VIDEO)
            script = generate_script(FINAL_VIDEO, dur)
            print("\nSCRIPT:\n", script)

            generate_voice(script)
            make_audio_safe(OUTPUT_AUDIO, dur)
            attach_audio_to_video(FINAL_VIDEO, SAFE_AUDIO, FINAL_VIDEO_WITH_VOICE)

            print("\nSUCCESS: FINAL VIDEO WITH VOICE READY:", FINAL_VIDEO_WITH_VOICE)

            # CAPTIONS
            generate_instagram_srt_from_video(
                FINAL_VIDEO_WITH_VOICE,
                SRT_OUTPUT,
                MAX_WORDS
            )

            return

if __name__ == "__main__":
    main()
