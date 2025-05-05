from fastapi import FastAPI, UploadFile, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import json
import time
import threading
import subprocess
from typing import Dict, Optional
import utils

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store processing status
processing_status: Dict[str, Dict] = {}

@app.post("/watermark/image")
async def watermark_image_endpoint(
    file: UploadFile,
    watermark_text: str = Form(...)
):
    """Endpoint for image watermarking"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Save uploaded file
    input_path = await utils.save_upload_file(file)
    
    try:
        # Watermark the image
        output_path = utils.watermark_image(input_path, watermark_text)
        
        # Return the watermarked file
        return FileResponse(
            output_path,
            media_type=file.content_type,
            filename=f"watermarked_{file.filename}"
        )
    finally:
        # Clean up uploaded file
        if os.path.exists(input_path):
            os.remove(input_path)

@app.post("/watermark/video")
async def watermark_video_endpoint(
    file: UploadFile,
    watermark_text: str = Form(...),
    moving_watermark: Optional[bool] = Form(False),
    background_tasks: BackgroundTasks = None
):
    """Endpoint for video watermarking
    
    Parameters:
    - file: The video file to watermark
    - watermark_text: Text to use as watermark
    - moving_watermark: If True, the watermark will move across the video
    """
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    # Generate a unique task ID
    task_id = str(uuid.uuid4())
    
    # Save uploaded file
    input_path = await utils.save_upload_file(file)
    
    # Initialize processing status
    processing_status[task_id] = {
        "status": "processing",
        "progress": 0,
        "output_path": None,
        "original_filename": file.filename,
        "moving_watermark": moving_watermark
    }
    
    # Start background processing
    background_tasks.add_task(
        process_video,
        task_id,
        input_path,
        watermark_text,
        moving_watermark
    )
    
    # Return task ID for progress checking
    return JSONResponse({
        "task_id": task_id,
        "status_url": f"/status/{task_id}"
    })

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """Check processing status of a video"""
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = processing_status[task_id]
    
    if status["status"] == "completed":
        return JSONResponse({
            "status": "completed",
            "download_url": f"/download/{task_id}"
        })
    
    return JSONResponse({
        "status": status["status"],
        "progress": status["progress"]
    })

@app.get("/download/{task_id}")
async def download_file(task_id: str):
    """Download the processed file"""
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = processing_status[task_id]
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="File not ready")
    
    output_path = status["output_path"]
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    original_filename = status.get("original_filename", "video.mp4")
    watermark_type = "moving_" if status.get("moving_watermark", False) else ""
    
    return FileResponse(
        output_path,
        filename=f"{watermark_type}watermarked_{original_filename}"
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for Railway"""
    return {"status": "ok"}

async def process_video(task_id: str, input_path: str, watermark_text: str, moving_watermark: bool = False):
    """Process video in background"""
    try:
        # Get video duration for progress calculation
        duration = utils.get_file_duration(input_path)
        
        # Update initial progress
        processing_status[task_id]["progress"] = 5
        
        if duration:
            # Get FFmpeg command and output path with progress monitoring
            cmd, output_path = utils.watermark_video_with_progress(input_path, watermark_text, moving_watermark)
            
            # Start FFmpeg process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Thread to monitor progress
            def monitor_progress():
                current_time = 0
                
                # Read stdout line by line
                for line in process.stdout:
                    if line.startswith("out_time_ms="):
                        try:
                            # Convert microseconds to seconds
                            current_time = float(line.split("=")[1].strip()) / 1000000
                            # Calculate progress percentage (5-95%)
                            progress = 5 + min(90, int(90 * current_time / duration))
                            processing_status[task_id]["progress"] = progress
                        except (ValueError, ZeroDivisionError):
                            pass
            
            # Start monitoring in a separate thread
            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Wait for process to complete
            process.wait()
            
            # Check if process completed successfully
            if process.returncode == 0:
                processing_status[task_id].update({
                    "status": "completed",
                    "progress": 100,
                    "output_path": output_path
                })
            else:
                raise Exception(f"FFmpeg process failed with exit code {process.returncode}")
        else:
            # Fallback if duration can't be determined
            output_path = utils.watermark_video(input_path, watermark_text, moving_watermark)
            processing_status[task_id].update({
                "status": "completed",
                "progress": 100,
                "output_path": output_path
            })
    except Exception as e:
        processing_status[task_id].update({
            "status": "error",
            "error": str(e)
        })
    finally:
        # Clean up uploaded file
        if os.path.exists(input_path):
            os.remove(input_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 