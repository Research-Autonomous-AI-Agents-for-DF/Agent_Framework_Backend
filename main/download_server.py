import os
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Create a separate FastAPI instance for file downloads
download_app = FastAPI()

# Enable CORS for requests from the Chainlit app (running on localhost:8000)
download_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],  # adjust if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the base directory for session logs
# Assuming your project root is E:\research\Agent_Framework_Backend
BASE_DIR = Path(__file__).resolve().parent.parent / "session_logs"


@download_app.get("/download_logs")
async def download_logs(thread_id: str):
    # Build the file name. Log files are like: thread_<thread_id>.log
    file_name = f"thread_{thread_id}.log"
    file_path = BASE_DIR / file_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        str(file_path),
        media_type="text/plain",
        filename=file_name
    )


def run_download_server():
    # Run the download server on port 8001
    uvicorn.run(download_app, host="127.0.0.1", port=8001)
