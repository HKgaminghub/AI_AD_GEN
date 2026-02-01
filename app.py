from flask import Flask, request, jsonify, send_file, redirect, url_for, render_template, flash
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
import sys
import importlib.util
from moviepy.editor import VideoFileClip, concatenate_videoclips
import requests
import time
import json
import random
import datetime
import traceback

from services import scene_service, audio_service, caption_service

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
bcrypt = Bcrypt(app)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')

import certifi

# MongoDB Setup
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
try:
    # Set serverSelectionTimeoutMS to 5 seconds to avoid long hangs on startup
    # We use certifi to provide a reliable set of root CA certificates
    client = MongoClient(
        mongo_uri, 
        serverSelectionTimeoutMS=5000,
        tlsCAFile=certifi.where()
    )
    # The 'ping' command checks if we can actually reach the server
    client.admin.command('ping')
    print("SUCCESS: MongoDB connected successfully!")
except Exception as e:
    print(f"WARNING: MongoDB Connection Warning: {e}")
    if "SSL handshake failed" in str(e) or "TLSV1_ALERT_INTERNAL_ERROR" in str(e):
        print("TIP: This error usually means your IP is not whitelisted in MongoDB Atlas.")
        print("   Please ensure your current IP is added to 'Network Access' in the Atlas dashboard.")
    print("The app will start, but Login/Signup features will not work.")

db = client['video_gen_db']
users_collection = db['users']

# Flask-Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(str(user_data['_id']), user_data['username'])
    return None

# Auth Routes
@app.route('/api/signup', methods=['POST'])
def signup():
    # Support both JSON (Ajax) and Form (Traditional)
    if request.is_json:
        data = request.json
    else:
        # Standard form data
        data = request.form

    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        if not request.is_json:
            flash("Username and password required", "error")
            return redirect(url_for('signup_page'))
        return jsonify({"error": "Username and password required"}), 400
    
    if users_collection.find_one({"username": username}):
        if not request.is_json:
            flash("Username already exists", "error")
            return redirect(url_for('signup_page'))
        return jsonify({"error": "Username already exists"}), 400
    
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    result = users_collection.insert_one({
        "username": username,
        "password": hashed_password,
        "video_count": 0
    })
    
    if not request.is_json:
        flash("Account created! You can now sign in.", "success")
        return redirect(url_for('login_page'))
    return jsonify({"success": True, "message": "User created"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.json
    else:
        data = request.form

    username = data.get('username')
    password = data.get('password')
    
    user_data = users_collection.find_one({"username": username})
    if user_data and bcrypt.check_password_hash(user_data['password'], password):
        user = User(str(user_data['_id']), user_data['username'])
        login_user(user)
        if not request.is_json:
            return redirect(url_for('home'))
        return jsonify({"success": True, "message": "Logged in"})
    
    if not request.is_json:
        flash("Invalid username or password", "error")
        return redirect(url_for('login_page'))
    return jsonify({"success": False, "error": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    if not request.is_json:
        return redirect(url_for('home'))
    return jsonify({"success": True, "message": "Logged out"})

@app.route('/api/me', methods=['GET'])
def get_me():
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "username": current_user.username})
    return jsonify({"authenticated": False})

# Import the existing modules without modifying them
# We'll dynamically configure them using environment variables

# Import 9x16_srt module
spec1 = importlib.util.spec_from_file_location("main_module", "9x16_srt.py")
main_module = importlib.util.module_from_spec(spec1)
sys.modules['main_module'] = main_module
spec1.loader.exec_module(main_module)

# Import caption engine module
spec2 = importlib.util.spec_from_file_location("caption_module", "caption_engine.py")
caption_module = importlib.util.module_from_spec(spec2)
sys.modules['caption_module'] = caption_module
spec2.loader.exec_module(caption_module)

# Handle multiple DEAPI keys
deapi_keys_str = os.getenv('DEAPI_KEYS', os.getenv('DEAPI_KEY', ''))
DEAPI_KEYS_LIST = [k.strip() for k in deapi_keys_str.split(',') if k.strip()]
current_key_index = 0

def rotate_api_key():
    global current_key_index
    if len(DEAPI_KEYS_LIST) > 1:
        current_key_index = (current_key_index + 1) % len(DEAPI_KEYS_LIST)
        new_key = DEAPI_KEYS_LIST[current_key_index]
        main_module.DEAPI_KEY = new_key
        print(f"ROTATE: Switched to DEAPI Key #{current_key_index + 1}: {new_key[:10]}...")
        return True
    return False

# Configure modules with environment variables
main_module.genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
if DEAPI_KEYS_LIST:
    main_module.DEAPI_KEY = DEAPI_KEYS_LIST[0]
if os.getenv('ELEVEN_API_KEY'):
    main_module.ELEVEN_API_KEY = os.getenv('ELEVEN_API_KEY')

main_module.SCENE_IMAGES = {
    "scene1": os.getenv('SCENE1_IMAGE_PATH', 'd:/gemini/front.png'),
    "scene2": os.getenv('SCENE2_IMAGE_PATH', 'd:/gemini/left.png'),
    "scene3": os.getenv('SCENE3_IMAGE_PATH', 'd:/gemini/right.png'),
    "scene4": os.getenv('SCENE4_IMAGE_PATH', 'd:/gemini/back.png'),
}

main_module.SCENE_FILES = {
    "scene1": os.getenv('SCENE1_FILE', 'scene1.mp4'),
    "scene2": os.getenv('SCENE2_FILE', 'scene2.mp4'),
    "scene3": os.getenv('SCENE3_FILE', 'scene3.mp4'),
    "scene4": os.getenv('SCENE4_FILE', 'scene4.mp4'),
}

main_module.FINAL_VIDEO = os.getenv('FINAL_VIDEO', 'final_reel_ad_9x16.mp4')
main_module.FINAL_VIDEO_WITH_VOICE = os.getenv('FINAL_VIDEO_WITH_VOICE', 'final_video_with_voice.mp4')
main_module.TARGET_W = int(os.getenv('TARGET_WIDTH', 432))
main_module.TARGET_H = int(os.getenv('TARGET_HEIGHT', 768))
main_module.VOICE_ID = os.getenv('VOICE_ID', '21m00Tcm4TlvDq8ikWAM')
main_module.OUTPUT_AUDIO = os.getenv('OUTPUT_AUDIO', 'final_voice.mp3')
main_module.SAFE_AUDIO = os.getenv('SAFE_AUDIO', 'final_voice_safe.mp3')
main_module.SRT_OUTPUT = os.getenv('SRT_OUTPUT', 'ainsta_caption.srt')
main_module.MAX_WORDS = int(os.getenv('MAX_WORDS_PER_CAPTION', 3))
main_module.WHISPER_MODEL_SIZE = os.getenv('WHISPER_MODEL_SIZE', 'small')

main_module.model = main_module.genai.GenerativeModel(os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'))

# Configure ImageMagick path based on OS
if os.name == 'posix': # Linux / Render / Docker
    default_im_path = '/usr/bin/magick'
else: # Windows (Local Dev)
    default_im_path = r'C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe'

imagemagick_path = os.getenv('IMAGEMAGICK_BINARY', default_im_path)
caption_module.change_settings({
    "IMAGEMAGICK_BINARY": imagemagick_path
})

def log_step(msg, label="INFO"):
    """Helper to print timestamped logs with labels"""
    now = datetime.datetime.now().strftime("%I:%M:%S %p")
    print(f"[{now}] {label} {msg}")

# =====================================
# HELPER: Enhanced generate_scene with better error handling
# =====================================

def generate_scene_with_retry(prompt, image_path, out_file, max_retries=3, retry_delay=20):
    """
    Wrapper around generate_scene with retry logic and API key rotation
    """
    log_step(f"Initializing generation for: {out_file}", "START")
    for attempt in range(max_retries):
        try:
            log_step(f"Attempt {attempt + 1}/{max_retries}: Requesting DEAPI...", "REQUEST")
            # Try to generate the scene using the robust main_module logic
            main_module.generate_scene(prompt, image_path, out_file)
            log_step(f"Success: Scene created at {out_file}", "SUCCESS")
            return True, None
        except Exception as e:
            error_msg = str(e)
            log_step(f"Error (Attempt {attempt + 1}): {error_msg}", "ERROR")
            
            # Handle rate limiting specifically
            if "Too Many Attempts" in error_msg or "429" in error_msg:
                wait_time = retry_delay * (attempt + 1)
                log_step(f"Rate limited (429). Waiting {wait_time}s...", "WAIT")
                time.sleep(wait_time)
                if rotate_api_key():
                    log_step("API Key rotated. Retrying...", "ROTATE")
                continue
            
            # Handle other errors with rotation or wait
            if attempt < max_retries - 1:
                if rotate_api_key():
                    log_step("Error encountered. Rotating API Key for retry...", "ROTATE")
                else:
                    wait_time = retry_delay * (attempt + 1)
                    log_step(f"Waiting {wait_time}s before retry...", "WAIT")
                    time.sleep(wait_time)
                continue
            else:
                log_step(f"Final Failure: All {max_retries} attempts exhausted.", "FAILURE")
                return False, error_msg
    
    return False, f"Failed after {max_retries} attempts"

# =====================================
# API ENDPOINTS
# =====================================

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/leaderboard')
@login_required
def leaderboard_page():
    # Fetch leaderboard data from MongoDB
    users_data = list(users_collection.find({}, {"username": 1, "video_count": 1, "_id": 0}))
    for user in users_data:
        if 'video_count' not in user:
            user['video_count'] = 0
            
    # Use the requested DSA Merge Sort for college project requirement
    leaderboard_sorted = merge_sort_leaderboard(users_data)
    return render_template('leaderboard.html', leaderboard=leaderboard_sorted)


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "API is running"})

@app.route('/api/generate-scene-prompts', methods=['POST'])
@login_required
def generate_scene_prompts():
    """Generate scene prompts from Gemini using uploaded images"""
    print("\n" + "="*50)
    log_step("STEP 1: ANALYZING IMAGES & GENERATING PROMPTS", "PROMPTS")
    print("="*50)
    try:
        # Check if images are provided in request
        if 'scene1' not in request.files or 'scene2' not in request.files or \
           'scene3' not in request.files or 'scene4' not in request.files:
            log_step("Input Error: Missing one or more scene images.", "ERROR")
            return jsonify({"error": "Please upload 4 images (scene1, scene2, scene3, scene4)"}), 400
        
        # Save uploaded images temporarily
        temp_images = {}
        for scene in ['scene1', 'scene2', 'scene3', 'scene4']:
            file = request.files[scene]
            temp_path = f"temp_{scene}.png"
            file.save(temp_path)
            temp_images[scene] = temp_path
            log_step(f"Saved temporary image for {scene}: {temp_path}", "IMAGE")
        
        # Generate prompts using scene_service
        log_step("Sending images to Gemini for prompt generation...", "AI")
        scenes = scene_service.generate_scene_prompts(main_module, temp_images)
        log_step(f"Prompts generated successfully: {list(scenes.keys())}", "SUCCESS")
        
        # Clean up temp files
        for path in temp_images.values():
            if os.path.exists(path):
                os.remove(path)
        
        return jsonify({"success": True, "scenes": scenes})
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in generate_scene_prompts")
        print(f"{'='*50}")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        print(f"\nFull Traceback:")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-scene', methods=['POST'])
@login_required
def generate_scene():
    """Generate a single scene video"""
    try:
        # Handle both JSON and form data
        if request.is_json and request.json:
            data = request.json
        else:
            data = request.form.to_dict()
        
        scene_key = data.get('scene_key')
        prompt = data.get('prompt')
        
        if not scene_key or not prompt:
            log_step(f"Input Error: Missing key ({scene_key}) or prompt ({prompt[:20]})", "ERROR")
            return jsonify({"error": "scene_key and prompt are required"}), 400
        
        print("\n" + "-"*40)
        log_step(f"STEP 2-5: GENERATING SCENE: {scene_key.upper()}", "SCENE")
        log_step(f"Prompt: {prompt[:100]}...", "PROMPT")
        print("-"*40)
        
        # Handle image upload
        image_path = None
        if scene_key in request.files:
            file = request.files[scene_key]
            image_path = f"temp_{scene_key}_input.png"
            file.save(image_path)
            log_step(f"Using uploaded image for {scene_key}", "UPLOAD")
        elif scene_key in main_module.SCENE_IMAGES:
            image_path = main_module.SCENE_IMAGES[scene_key]
            log_step(f"Using default image path for {scene_key}: {image_path}", "IMAGE")
        else:
            log_step(f"Image for {scene_key} not found", "ERROR")
            return jsonify({"error": f"Image for {scene_key} not found"}), 400
        
        # Convert to vertical safe
        safe_img = f"safe_{scene_key}.png"
        log_step(f"Converting {scene_key} image to 9:16 safe format...", "CONVERT")
        main_module.convert_to_vertical_safe(image_path, safe_img)
        
        # Define output file path
        output_file = main_module.SCENE_FILES.get(scene_key, f"{scene_key}.mp4")
        
        # Generate scene using retry/rotation logic
        log_step(f"Sending request to DEAPI for {scene_key}...", "API")
        success, error_msg = generate_scene_with_retry(
            prompt, 
            safe_img, 
            output_file, 
            max_retries=len(DEAPI_KEYS_LIST) + 1
        )
        
        if not success:
            log_step(f"Scene {scene_key} generation failed: {error_msg}", "ERROR")
            if image_path and "temp_" in image_path and os.path.exists(image_path):
                os.remove(image_path)
            return jsonify({"error": f"Error generating scene: {error_msg}"}), 500
        
        log_step(f"Scene {scene_key} generated successfully: {output_file}", "SUCCESS")
        
        # Cleanup temp image/safe image after success if they were temporary
        if image_path and "temp_" in image_path and os.path.exists(image_path):
            os.remove(image_path)
        if safe_img and os.path.exists(safe_img):
            os.remove(safe_img)
            
        return jsonify({"success": True, "output_file": output_file})
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in generate_scene")
        print(f"{'='*50}")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-all-scenes', methods=['POST'])
@login_required
def generate_all_scenes():
    """Generate all 4 scenes"""
    try:
        # Get scene prompts (either from request or generate from images)
        scenes = None
        temp_images = {}
        
        if request.is_json and request.json and 'scenes' in request.json:
            scenes = request.json['scenes']
        elif 'scenes' in request.form:
            import json
            scenes = json.loads(request.form['scenes'])
        
        if not scenes:
            # Generate prompts from uploaded images
            if 'scene1' not in request.files:
                return jsonify({"error": "Please provide scenes JSON or upload 4 images"}), 400
            
            for scene in ['scene1', 'scene2', 'scene3', 'scene4']:
                file = request.files[scene]
                temp_path = f"temp_{scene}.png"
                file.save(temp_path)
                temp_images[scene] = temp_path
            
            scenes = scene_service.generate_scene_prompts(main_module, temp_images)
        else:
            # If scenes provided but need images from upload
            for scene in ['scene1', 'scene2', 'scene3', 'scene4']:
                if scene in request.files:
                    file = request.files[scene]
                    temp_path = f"temp_{scene}.png"
                    file.save(temp_path)
                    temp_images[scene] = temp_path
                else:
                    # Use default image path
                    temp_images[scene] = main_module.SCENE_IMAGES.get(scene)
        
        # Generate all scenes using scene_service
        results = scene_service.generate_all_scenes(
            main_module,
            scenes,
            temp_images,
            generate_scene_with_retry,
            required_scenes=['scene1', 'scene2', 'scene3', 'scene4']
        )
        
        # Check if at least one scene succeeded
        successful_scenes = [r for r in results if r.get("status") == "success"]
        
        # Cleanup temp images
        for path in temp_images.values():
            if path and os.path.exists(path):
                os.remove(path)
        
        return jsonify({
            "success": len(successful_scenes) > 0,
            "results": results,
            "successful_count": len(successful_scenes),
            "total_count": len(results)
        })
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in generate_all_scenes")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/merge-scenes', methods=['POST'])
@login_required
def merge_scenes():
    """Merge all scene videos into final video"""
    print("\n" + "="*50)
    log_step("STEP 6: MERGING ALL SCENES INTO REEL", "MERGE")
    print("="*50)
    try:
        # Build scene_results format expected by scene_service
        scene_results = []
        for key in ['scene1', 'scene2', 'scene3', 'scene4']:
            scene_file = main_module.SCENE_FILES.get(key, f"{key}.mp4")
            if os.path.exists(scene_file):
                log_step(f"Found scene video: {scene_file}", "VIDEO")
                scene_results.append({
                    "scene": key,
                    "status": "success",
                    "output_file": scene_file
                })
        
        if not scene_results:
            log_step("No scene files found to merge", "ERROR")
            return jsonify({
                "error": "No scene files found to merge. Please generate scenes first.",
                "checked_files": list(main_module.SCENE_FILES.values())
            }), 400
        
        # Use scene_service to merge
        log_step(f"Merging {len(scene_results)} scenes into {main_module.FINAL_VIDEO}...", "MERGE")
        final_video = scene_service.merge_scenes(main_module, scene_results)
        log_step(f"Scenes merged successfully: {final_video}", "SUCCESS")
        
        return jsonify({
            "success": True,
            "output_file": final_video,
            "merged_scenes": [r["output_file"] for r in scene_results],
            "scene_count": len(scene_results)
        })
    except ValueError as e:
        print(f"\n{'='*50}")
        print(f"ERROR: ValueError in merge_scenes")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in merge_scenes")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-voiceover', methods=['POST'])
@login_required
def generate_voiceover():
    """Generate voiceover script and audio"""
    print("\n" + "="*50)
    log_step("STEP 7: CREATING AI VOICEOVER SCRIPT", "VOICE")
    print("="*50)
    try:
        data = request.json if request.is_json and request.json else {}
        video_path = data.get('video_path', main_module.FINAL_VIDEO)
        
        if not os.path.exists(video_path):
            log_step(f"Video file not found: {video_path}", "ERROR")
            return jsonify({"error": f"Video file not found: {video_path}"}), 400
        
        # Use audio_service to generate voiceover script
        log_step(f"Analyzing {video_path} for script generation...", "VOICE")
        script_result = audio_service.generate_voiceover_script(main_module, video_path)
        log_step(f"Voiceover script generated ({script_result['duration']}s)", "SUCCESS")
        log_step(f"Script Preview: {script_result['script'][:100]}...", "SCRIPT")
        
        return jsonify({
            "success": True,
            "script": script_result["script"],
            "script_file": script_result["script_file"],
            "duration": script_result["duration"],
            "audio_file": main_module.OUTPUT_AUDIO
        })
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in generate_voiceover")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/attach-audio', methods=['POST'])
@login_required
def attach_audio():
    """Attach audio to video"""
    print("\n" + "="*50)
    log_step("STEP 8: SYNCHRONIZING AUDIO & VIDEO", "SYNC")
    print("="*50)
    try:
        data = request.json if request.is_json and request.json else {}
        video_path = data.get('video_path', main_module.FINAL_VIDEO)
        script = data.get('script', '')
        output_path = data.get('output_path', main_module.FINAL_VIDEO_WITH_VOICE)
        
        if not os.path.exists(video_path):
            log_step(f"Video file not found: {video_path}", "ERROR")
            return jsonify({"error": f"Video file not found: {video_path}"}), 400
        
        # Get duration and use audio_service
        duration = main_module.get_video_duration(video_path)
        
        # If script provided, generate new audio; otherwise use existing
        if script:
            log_step("Generating and attaching new audio using ElevenLabs...", "VOICE")
            output_file = audio_service.generate_and_attach_audio(
                main_module,
                video_path,
                script,
                duration,
                output_path
            )
        else:
            # Just attach existing audio
            audio_path = data.get('audio_path', main_module.SAFE_AUDIO)
            if not os.path.exists(audio_path):
                log_step(f"Audio file not found: {audio_path}", "ERROR")
                return jsonify({"error": f"Audio file not found: {audio_path}"}), 400
            log_step(f"Attaching existing audio file: {audio_path}", "ATTACH")
            main_module.attach_audio_to_video(video_path, audio_path, output_path)
            output_file = output_path
        
        log_step(f"Audio attached successfully: {output_file}", "SUCCESS")
        return jsonify({
            "success": True,
            "output_file": output_file
        })
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in attach_audio")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-captions', methods=['POST'])
@login_required
def generate_captions():
    """Generate Instagram-style SRT captions using Whisper"""
    print("\n" + "="*50)
    log_step("STEP 9: TRANSCRIBING AUDIO (AI CAPTIONS)", "WHISPER")
    print("="*50)
    try:
        data = request.json if request.is_json and request.json else {}
        video_path = data.get('video_path', main_module.FINAL_VIDEO_WITH_VOICE)
        output_srt = data.get('output_srt', main_module.SRT_OUTPUT)
        max_words = int(data.get('max_words', main_module.MAX_WORDS))
        
        if not os.path.exists(video_path):
            log_step(f"Video file not found: {video_path}", "ERROR")
            return jsonify({"error": f"Video file not found: {video_path}"}), 400
        
        # Use caption_service to generate SRT
        log_step(f"Transcribing audio from {video_path} using Whisper...", "WHISPER")
        srt_file = caption_service.generate_srt(
            main_module,
            video_path,
            output_srt,
            max_words
        )
        log_step(f"SRT generated: {srt_file}", "SUCCESS")
        
        return jsonify({
            "success": True,
            "srt_file": srt_file
        })
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in generate_captions")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/burn-captions', methods=['POST'])
@login_required
def burn_captions():
    """Burn SRT captions into video"""
    print("\n" + "="*50)
    log_step("STEP 10: FINAL RENDER (BURNING CAPTIONS)", "BURN")
    print("="*50)
    try:
        data = request.json if request.is_json and request.json else {}
        video_path = data.get('video_path')
        srt_path = data.get('srt_path')
        output_path = data.get('output_path', 'final_video_with_voice_captions.mp4')
        
        if not video_path or not srt_path:
            log_step("video_path and srt_path are required", "ERROR")
            return jsonify({"error": "video_path and srt_path are required"}), 400
        
        if not os.path.exists(video_path):
            log_step(f"Video file not found: {video_path}", "ERROR")
            return jsonify({"error": f"Video file not found: {video_path}"}), 400
        if not os.path.exists(srt_path):
            log_step(f"SRT file not found: {srt_path}", "ERROR")
            return jsonify({"error": f"SRT file not found: {srt_path}"}), 400
        
        # Get optional parameters
        font_name = data.get('font_name', os.getenv('CAPTION_FONT_NAME'))
        font_size = data.get('font_size', int(os.getenv('CAPTION_FONT_SIZE', 40)))
        font_color = data.get('font_color', os.getenv('CAPTION_FONT_COLOR', 'white'))
        stroke_color = data.get('stroke_color', os.getenv('CAPTION_STROKE_COLOR', 'black'))
        stroke_width = data.get('stroke_width', int(os.getenv('CAPTION_STROKE_WIDTH', 2)))
        
        # Handle position
        pos_x = data.get('position_x', os.getenv('CAPTION_POSITION_X', 'center'))
        pos_y = data.get('position_y', os.getenv('CAPTION_POSITION_Y', 'bottom'))
        
        if pos_x == 'center' and pos_y in ['top', 'bottom']:
            position = (pos_x, pos_y)
        elif pos_x.isdigit() and pos_y.isdigit():
            position = ("axis", int(pos_x), int(pos_y))
        else:
            position = ("center", "bottom")
        
        # Use caption_service to burn captions
        log_step("Burning captions using MoviePy and ImageMagick...", "BURN")
        log_step(f"Styling: Font={font_name or 'Default'}, Size={font_size}, Color={font_color}, Stroke={stroke_color}", "STYLE")
        result = caption_service.burn_captions(
            caption_module,
            video_path,
            srt_path,
            output_path,
            font_name=font_name,
            font_size=font_size,
            font_color=font_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            position=position
        )
        
        if result:
            log_step(f"Final video with captions created: {result}", "SUCCESS")
            return jsonify({
                "success": True,
                "output_file": result
            })
        else:
            log_step("Failed to burn captions", "ERROR")
            return jsonify({
                "success": False,
                "error": "Failed to burn captions"
            }), 500
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Exception in burn_captions")
        traceback.print_exc()
        print(f"{'='*50}\n")
        return jsonify({"error": str(e)}), 500

# =====================================
# HELPER: File Cleanup
# =====================================

def cleanup_pipeline_files(files_to_remove):
    """Safely remove a list of files."""
    removed = []
    for path in files_to_remove:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                removed.append(path)
        except Exception as exc:
            print(f"Warning: Could not remove {path}: {exc}")
    if removed:
        print(f"CLEANUP: Cleaned up {len(removed)} temporary files")
    return removed


@app.route('/api/debug-deapi', methods=['POST'])
def debug_deapi():
    """Debug endpoint to test DEAPI connection and see response"""
    try:
        import requests
        url = "https://api.deapi.ai/api/v1/client/img2video"
        headers = {"Authorization": f"Bearer {main_module.DEAPI_KEY}"}
        
        # Create a dummy test
        test_data = {
            "prompt": "test",
            "width": 432,
            "height": 768,
            "fps": 30,
            "frames": 120,
            "steps": 1,
            "guidance": 8,
            "seed": 12345,
            "model": "Ltxv_13B_0_9_8_Distilled_FP8",
            "motion": "cinematic",
        }
        
        # Try without file first to see error response
        r = requests.post(url, data=test_data, headers=headers)
        response_data = {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "response": r.text[:1000] if len(r.text) < 1000 else r.text[:1000] + "... (truncated)",
            "json_response": r.json() if r.headers.get('content-type', '').startswith('application/json') else None
        }
        
        return jsonify({
            "success": True,
            "api_key_set": bool(main_module.DEAPI_KEY),
            "api_key_preview": main_module.DEAPI_KEY[:10] + "..." if main_module.DEAPI_KEY else "Not set",
            "response": response_data
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": str(__import__('traceback').format_exc())}), 500

@app.route('/api/download/<filename>', methods=['GET'])
@login_required
def download_file(filename):
    """Download generated files"""
    try:
        if not os.path.exists(filename):
            return jsonify({"error": "File not found"}), 404
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/list-files', methods=['GET'])
@login_required
def list_files():
    """List all generated files"""
    try:
        files = []
        for file in [main_module.FINAL_VIDEO, main_module.FINAL_VIDEO_WITH_VOICE, 
                     main_module.OUTPUT_AUDIO, main_module.SAFE_AUDIO, main_module.SRT_OUTPUT] + \
                    list(main_module.SCENE_FILES.values()):
            if os.path.exists(file):
                files.append({
                    "name": file,
                    "size": os.path.getsize(file),
                    "exists": True
                })
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================
# LEADERBOARD & DSA SORTING
# =====================================

def merge_sort_leaderboard(arr):
    """
    Merge Sort algorithm to sort leaderboard by video_count in descending order.
    """
    if len(arr) <= 1:
        return arr
    
    mid = len(arr) // 2
    left = merge_sort_leaderboard(arr[:mid])
    right = merge_sort_leaderboard(arr[mid:])
    
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        # Sort in descending order (highest video_count first)
        if left[i]['video_count'] >= right[j]['video_count']:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
            
    result.extend(left[i:])
    result.extend(right[j:])
    return result

@app.route('/api/leaderboard', methods=['GET'])
@login_required
def get_leaderboard():
    """Fetch and return sorted leaderboard data"""
    try:
        users_data = list(users_collection.find({}, {"username": 1, "video_count": 1, "_id": 0}))
        
        # Ensure every user has a video_count field (migration/safety)
        for user in users_data:
            if 'video_count' not in user:
                user['video_count'] = 0
                
        # Use DSA Merge Sort
        sorted_leaderboard = merge_sort_leaderboard(users_data)
        
        return jsonify({"success": True, "leaderboard": sorted_leaderboard})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/increment-video-count', methods=['POST'])
@login_required
def increment_video_count():
    """Increment the video count for the current user"""
    try:
        users_collection.update_one(
            {"username": current_user.username},
            {"$inc": {"video_count": 1}}
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Disable reloader to avoid conflicts with numba/Whisper file watching
    # When Whisper uses numba, it can trigger file change events that cause
    # Flask's debug reloader to restart the server. Setting use_reloader=False
    # prevents this issue while keeping debug mode enabled for error messages.
    # 
    # Note: With use_reloader=False, you'll need to manually restart the server
    # if you make code changes. For production, set debug=False.
    # Use PORT environment variable if available (Render)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
