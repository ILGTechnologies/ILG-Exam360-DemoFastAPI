from livekit import AccessToken, VideoGrant
from pydantic import BaseModel
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or use ["http://localhost:5173"] for tighter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory device registry
device_registry = {}  # identity -> {room, status, last_seen}

# Replace these with your actual LiveKit credentials
LIVEKIT_API_KEY = "APIJtTEpvwM9e3y"
LIVEKIT_API_SECRET = "KuhYBMLHvrgJelnFM9BRXoN5durqDDcqRYIISNe0mt6"

class TokenRequest(BaseModel):
    identity: str
    room: str

class RegisterRequest(BaseModel):
    identity: str
    room: str

class DisconnectRequest(BaseModel):
    identity: str

@app.post("/api/token")
def get_token(data: TokenRequest):
    grant = VideoGrant(room=data.room)
    grant.room_join = True  # 👈 optional but sometimes required
    at = AccessToken(
        LIVEKIT_API_KEY,
        LIVEKIT_API_SECRET,
        identity=data.identity,
        name=data.identity,
        grant=grant
    )
    token = at.to_jwt()
    return {"token": token}

@app.post("/api/register")
def register(data: RegisterRequest):
    device_registry[data.identity] = {
        "room": data.room,
        "status": "connected",
        "last_seen": datetime.utcnow()
    }
    return {"message": "heartbeat received"}

@app.get("/api/active-devices")
def get_active_devices():
    threshold = datetime.utcnow() - timedelta(minutes=5)
    active = {
        identity: info for identity, info in device_registry.items()
        if info['last_seen'] > threshold
    }
    return {"active_devices": active}

@app.get("/api/rooms")
def get_active_rooms():
    threshold = datetime.utcnow() - timedelta(minutes=5)
    room_counts = {}
    for identity, info in device_registry.items():
        if info['last_seen'] > threshold:
            room = info['room']
            room_counts[room] = room_counts.get(room, 0) + 1
    return {"rooms": room_counts}

@app.post("/api/disconnect")
def disconnect(data: DisconnectRequest):
    if data.identity in device_registry:
        device_registry[data.identity]["status"] = "disconnected"
        device_registry[data.identity]["last_seen"] = datetime.utcnow()
        return {"message": f"{data.identity} marked as disconnected"}
    else:
        return {"message": f"{data.identity} not found"}, 404

@app.get("/api/version")
def get_version():
    return {"version": "1.0.0"}
