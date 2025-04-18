from livekit import AccessToken, VideoGrant
from pydantic import BaseModel
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or use ["http://localhost:5173"] for tighter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Replace these with your actual LiveKit credentials
LIVEKIT_API_KEY = "APIJtTEpvwM9e3y"
LIVEKIT_API_SECRET = "KuhYBMLHvrgJelnFM9BRXoN5durqDDcqRYIISNe0mt6"

class TokenRequest(BaseModel):
    identity: str
    room: str

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
