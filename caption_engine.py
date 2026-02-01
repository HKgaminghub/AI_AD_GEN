import os
import pysrt
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.config import change_settings as moviepy_change_settings

def change_settings(settings):
    """
    Configure MoviePy settings, specifically the ImageMagick binary path.
    """
    if "IMAGEMAGICK_BINARY" in settings:
        moviepy_change_settings({"IMAGEMAGICK_BINARY": settings["IMAGEMAGICK_BINARY"]})
    print(f"SUCCESS: MoviePy settings updated: {settings}")

def burn_captions(
    video_path, 
    srt_path, 
    output_path, 
    font_name=None, 
    font_size=40, 
    font_color='white', 
    stroke_color='black', 
    stroke_width=2, 
    position=('center', 'bottom')
):
    """
    Burn SRT captions into a video file using MoviePy and ImageMagick.
    """
    print(f"BURN: Burning captions into {video_path}...")
    
    # Load the video
    video = VideoFileClip(video_path)
    
    # Load the subtitles
    subs = pysrt.open(srt_path)
    
    # Function to create a TextClip for each subtitle segment
    def create_caption_clip(sub):
        # MoviePy expects duration/timings in seconds
        start_time = sub.start.to_time()
        end_time = sub.end.to_time()
        
        # Convert time objects to total seconds
        start_seconds = (sub.start.hours * 3600 + sub.start.minutes * 60 + 
                        sub.start.seconds + sub.start.milliseconds / 1000.0)
        end_seconds = (sub.end.hours * 3600 + sub.end.minutes * 60 + 
                      sub.end.seconds + sub.end.milliseconds / 1000.0)
        duration = end_seconds - start_seconds
        
        if duration <= 0:
            return None

        # Create the text clip
        # Note: 'center' position in MoviePy can be (pos_x, pos_y)
        # Handle the specialized position format from app.py
        actual_pos = position
        if isinstance(position, tuple) and position[0] == "axis":
            actual_pos = (position[1], position[2])

        txt_clip = TextClip(
            sub.text,
            fontsize=font_size,
            color=font_color,
            font=font_name or 'Arial-Bold',
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method='caption',
            size=(video.w * 0.8, None) # Wrap text at 80% width
        ).set_start(start_seconds).set_duration(duration).set_position(actual_pos)
        
        return txt_clip

    # Generate all caption clips
    caption_clips = []
    for sub in subs:
        clip = create_caption_clip(sub)
        if clip:
            caption_clips.append(clip)
    
    # Composite the video with all captions
    result = CompositeVideoClip([video] + caption_clips)
    
    # Write the output file
    # We use libx264 and aac for broad compatibility
    result.write_videofile(output_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
    
    # Close clips to free resources
    video.close()
    result.close()
    
    return output_path

if __name__ == "__main__":
    # Test script (if needed)
    pass
