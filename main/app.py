from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import asyncio
from mainflow import start_forensic_analysis

app = FastAPI()
log_messages = []  # Global list to store conversation history
websocket_connections = []  # List to store active WebSocket connections
log_lock = asyncio.Lock()  # Lock for thread-safe access to log_messages

# HTML page for testing WebSocket testing only
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Forensic Analysis Logs</title>
    </head>
    <body>
        <h1>Forensic Analysis Logs</h1>
        <p>WebSocket Connection Status: <span id="status">Not Connected</span></p>
        <ul id="logs"></ul>
        <script>
            const ws = new WebSocket("ws://localhost:8000/ws");
            const status = document.getElementById("status");
            const logs = document.getElementById("logs");

            ws.onopen = function() {
                status.textContent = "Connected";
            };

            ws.onmessage = function(event) {
                const logItem = document.createElement("li");
                logItem.textContent = event.data;
                logs.appendChild(logItem);
            };

            ws.onclose = function() {
                status.textContent = "Disconnected";
            };

            ws.onerror = function(error) {
                status.textContent = "Error: " + error.message;
            };
        </script>
    </body>
</html>
"""

@app.get("/")
def read_root():
    return HTMLResponse(html)

async def run_forensic_analysis():
    print("Forensic analysis started...")
    global log_messages
    logs = await asyncio.to_thread(start_forensic_analysis)  # Run in a separate thread and capture logs
    async with log_lock:  # Ensure thread-safe access
        log_messages = logs
    print("Forensic analysis completed!")
    await broadcast_logs()  # Broadcast logs to all WebSocket clients

@app.post("/start_analysis")
async def start_analysis():
    await asyncio.create_task(run_forensic_analysis())  # Run in background
    return {"status": "success", "message": "Analysis initiated"}

@app.get("/get_logs")
async def get_logs():
    async with log_lock:  # Ensure thread-safe access
        return {"logs": log_messages}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)

# Broadcast logs to all WebSocket clients
async def broadcast_logs():
    async with log_lock:  # thread-safe access
        logs = log_messages
    for connection in websocket_connections:
        await connection.send_text(str(logs))

# Test WebSocket
@app.get("/test_websocket")
async def test_websocket():
    return HTMLResponse(html)