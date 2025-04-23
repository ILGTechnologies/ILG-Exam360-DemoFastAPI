from asyncio import Lock
assign_lock = Lock()

from livekit import AccessToken, VideoGrant, RoomServiceClient
from pydantic import BaseModel
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or use ["http://localhost:5173"] for tighter security
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory device registry
device_registry = {}  # identity -> {room, status, last_seen}
room_assignments = {}  # identity -> room
room_index = 0
MAX_TOTAL_PARTICIPANTS = 900
MAX_PER_ROOM = 18
ROOM_BUFFER = 2  # Reserved slots for suspicious users

class AssignRoomRequest(BaseModel):
    identity: str

@app.post("/api/assign-room")
async def assign_room(data: AssignRoomRequest):
    global room_index
    async with assign_lock:
        current_total = len(room_assignments)
        print("Current Total", current_total)
        if current_total >= MAX_TOTAL_PARTICIPANTS:
            return {"room": None, "retry": 30}

        if data.identity in room_assignments:
            room = room_assignments[data.identity]
        else:
            for i in range(room_index + 1):
                room_id = f"proctor-room-{i+1}"
                count = list(room_assignments.values()).count(room_id)
                print("Current room count: for - ", f"proctor-room-{i+1} is ", count)
                if count < MAX_PER_ROOM:
                    room = room_id
                    break
            else:
                room_index += 1
                print("Creating a new room for: ", data.identity, "room index: ", room_index)
                room = f"proctor-room-{room_index+1}"

            print("New Total: ", len(room_assignments))
            room_assignments[data.identity] = room

        return {"room": room}


# Replace these with your actual LiveKit credentials
#LIVEKIT_API_KEY = "APIJtTEpvwM9e3y"
#LIVEKIT_API_SECRET = "KuhYBMLHvrgJelnFM9BRXoN5durqDDcqRYIISNe0mt6"

LIVEKIT_API_KEY = "APIXCY4TPk3aHQn"
LIVEKIT_API_SECRET = "xVPJcVahISSgtQwuBI9EidyRojZB2EjDO4KTjG9NzDN"
LIVEKIT_HOST = "https://demoapp-g27k0q6r.livekit.cloud"
room_service = RoomServiceClient(LIVEKIT_HOST, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

class TokenRequest(BaseModel):
    identity: str
    room: str

class RegisterRequest(BaseModel):
    identity: str
    room: str

class DisconnectRequest(BaseModel):
    identity: str

@app.post("/api/token")
async def get_token(data: TokenRequest):
    async with assign_lock: 
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
async def register(data: RegisterRequest):
    async with assign_lock:
        device_registry[data.identity] = {
            "room": data.room,
            "status": "connected",
            "last_seen": datetime.utcnow()
        }
        return {"message": "heartbeat received"}

@app.get("/api/active-devices")
def get_active_devices():
    active = {
        identity: info for identity, info in device_registry.items()
    }
    return {"active_devices": active}

@app.get("/api/rooms")
def get_active_rooms():
    room_counts = {}
    for identity, info in device_registry.items():
        room = info['room']
        room_counts[room] = room_counts.get(room, 0) + 1

    return {"rooms": room_counts}

@app.post("/api/disconnect")
async def disconnect(data: DisconnectRequest):
    async with assign_lock:
        if data.identity in device_registry:
            device_registry[data.identity]["status"] = "disconnected"
            device_registry[data.identity]["last_seen"] = datetime.utcnow()
            # Remove from room_assignments and update total count
            if data.identity in room_assignments:
                del room_assignments[data.identity]
            return {"message": f"{data.identity} marked as disconnected"}
        else:
            return {"message": f"{data.identity} not found"}, 404

@app.get("/api/version")
def get_version():
    return {"version": "1.0.1"}

@app.get("/api/room-members")
def get_room_members():
    room_members = {}
    for identity, info in device_registry.items():
        room = info['room']
        room_members.setdefault(room, []).append(identity)
        
    return {"room_members": room_members}

@app.get("/api/room-members/{room}")
def get_members_for_room(room: str):
    members = [
        identity for identity, info in device_registry.items()
        if info.get("room") == room
    ]
    return {"room": room, "members": members}

@app.get("/api/debug-registry")
def debug_registry():
    return device_registry

@app.get("/api/clear-database")
def clear_database():
    global device_registry, room_assignments, room_index
    device_registry.clear()
    room_assignments.clear()
    room_index = 0
    return {"message": "In-memory database has been cleared."}

@app.get("/api/livekit-participants/{room}")
def get_livekit_participants(room: str):
    try:
        participants = room_service.list_participants(room)
        print(f"🔍 Raw participants for room '{room}':", participants)
        return {"room": room, "participants": [vars(p) for p in participants]}
    except Exception as e:
        print(f"❌ Error listing participants for room '{room}': {e}")
        return {"error": str(e)}, 500
    
@app.post("/api/register_suspicious")
def register_suspicious(data: DisconnectRequest):
    if data.identity in device_registry:
        device_registry[data.identity]["suspicious"] = True
        # Try to reassign to a room with available suspicious buffer
        suspicious_counts = {}
        for room_id in set(room_assignments.values()):
            suspicious_counts[room_id] = sum(
                1 for i in device_registry
                if device_registry[i].get("room") == room_id and device_registry[i].get("suspicious", False)
            )
        for i in range(room_index + 1):
            room_id = f"proctor-room-{i+1}"
            if suspicious_counts.get(room_id, 0) < ROOM_BUFFER:
                device_registry[data.identity]["room"] = room_id
                room_assignments[data.identity] = room_id
                return {"message": f"{data.identity} marked as suspicious and added to {room_id}"}
        return {"message": f"{data.identity} marked as suspicious but no buffer slot available"}, 429
    else:
        return {"message": f"{data.identity} not found"}, 404
    
@app.get("/api/metrics")
def get_metrics():
    connected = sum(1 for info in device_registry.values() if info.get("status") == "connected")
    suspicious_connected = sum(
        1 for info in device_registry.values()
        if info.get("status") == "connected" and info.get("suspicious", False)
    )
    return {
        "registered_devices": len(device_registry),
        "connected_devices": connected,
        "suspicious_connected": suspicious_connected
    }