import os
import subprocess
import uuid
import shutil
from typing import Optional
import aiofiles
from fastapi import UploadFile

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("watermarked", exist_ok=True)
os.makedirs("temp", exist_ok=True)

# Get FFmpeg path - this ensures it works both locally and on Railway
def get_ffmpeg_path():
    # Try to find ffmpeg in PATH (works on Railway with nixpacks)
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    
    # Default paths as fallback
    if os.name == "nt":  # Windows
        return "ffmpeg.exe"
    return "ffmpeg"

def get_ffprobe_path():
    # Try to find ffprobe in PATH (works on Railway with nixpacks)
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        return ffprobe_path
    
    # Default paths as fallback
    if os.name == "nt":  # Windows
        return "ffprobe.exe"
    return "ffprobe"

async def save_upload_file(upload_file: UploadFile) -> str:
    """Save uploaded file and return its path"""
    file_extension = os.path.splitext(upload_file.filename)[1]
    file_name = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", file_name)
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    
    return file_path

def watermark_image(input_path: str, watermark_text: str) -> str:
    """Watermark an image using FFmpeg"""
    output_filename = f"watermarked_{os.path.basename(input_path)}"
    output_path = os.path.join("watermarked", output_filename)
    
    # FFmpeg command to add text watermark
    cmd = [
        get_ffmpeg_path(), "-i", input_path,
        "-vf", f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x=10:y=10",
        "-y", output_path
    ]
    
    subprocess.run(cmd, check=True)
    return output_path

def watermark_video(input_path: str, watermark_text: str, moving: bool = False) -> str:
    """Watermark a video using FFmpeg"""
    output_filename = f"watermarked_{os.path.basename(input_path)}"
    output_path = os.path.join("watermarked", output_filename)
    
    # Set up watermark filter based on whether it should be moving or static
    if moving:
        # Moving watermark: text scrolls across the bottom of the video
        vf_text = f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x='if(gte(t,0),w-50*t,NAN)':y=h-30"
    else:
        # Static watermark in the corner
        vf_text = f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x=10:y=10"
    
    # FFmpeg command to add text watermark
    cmd = [
        get_ffmpeg_path(), "-i", input_path,
        "-vf", vf_text,
        "-codec:a", "copy",
        "-y", output_path
    ]
    
    subprocess.run(cmd, check=True)
    return output_path

def watermark_video_with_progress(input_path: str, watermark_text: str, moving: bool = False) -> list:
    """Create FFmpeg command for video watermarking with progress monitoring"""
    output_filename = f"watermarked_{os.path.basename(input_path)}"
    output_path = os.path.join("watermarked", output_filename)
    
    # Set up watermark filter based on whether it should be moving or static
    if moving:
        # Moving watermark: text scrolls across the bottom of the video
        vf_text = f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x='if(gte(t,0),w-50*t,NAN)':y=h-30"
    else:
        # Static watermark in the corner
        vf_text = f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x=10:y=10"
    
    # FFmpeg command with progress monitoring
    cmd = [
        get_ffmpeg_path(),
        "-i", input_path,
        "-vf", vf_text,
        "-codec:a", "copy",
        "-progress", "pipe:1",
        "-y", output_path
    ]
    
    return cmd, output_path

def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    return os.path.getsize(file_path)

def get_file_duration(file_path: str) -> Optional[float]:
    """Get video duration in seconds"""
    try:
        cmd = [
            get_ffprobe_path(), "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return None 