from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from pitwall_telemetry_engine.ingestion.timeline_replayer import TimelineReplayer

class ClientSession:
    def __init__(self, websocket: WebSocket, session_key: str | int = 9472):
        self.websocket = websocket
        self.session_key = session_key
        self.selected_drivers: list[int] = [1, 55]
        self.replayer = TimelineReplayer(session_key, fps = 30)
        self.stream_task: asyncio.Task | None = None

class ConnectionManager:
    def __init__(self):
        self.sessions: dict[WebSocket, ClientSession] = {}
    
    async def connect(self, websocket: WebSocket, session_key:str | int = 9472):
        await websocket.accept()
        
        session = ClientSession(websocket, session_key)
        self.sessions[websocket] = session

        session.stream_task = asyncio.create_task(self._stream_to_client(session))

    async def disconnect(self, websocket: WebSocket):
        session = self.sessions.pop(websocket, None)
            
        if session and session.stream_task:
            session.stream_task.cancel()
    
    async def _stream_to_client(self, session: ClientSession):
        try:
            async for frame in session.replayer.stream_frames(
                get_selected_drivers_cb=lambda: session.selected_drivers
            ):
                await session.websocket.send_json(frame)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            print(f"Stream Error: {e}")
    
    async def handle_client_message(self, websocket: WebSocket, data:dict):
        session = self.sessions.get(websocket)
        if not session:
            return
        
        #User makes an action on the front end
        action = data.get("action")

        if action == "play":
            session.replayer.play()

        elif action == "pause":
            session.replayer.pause()

        elif action == "toggle_play":
            session.replayer.toggle_play()

        elif action == "seek":
            # Target timestamp in seconds
            if "time" in data:
                session.replayer.seek(float(data["time"]))
        
        elif action == "seek_percent":
            # Target percentage (0.0 to 1.0)
            if "percent" in data:
                session.replayer.seek_percent(float(data["percent"]))
        
        elif action == "set_speed":
            # Playback multiplier (e.g. 1.0, 2.0, 5.0)
            if "speed" in data:
                session.replayer.set_speed(float(data["speed"]))
        
        elif action == "select_drivers":
            # Drivers to show in cockpit drawer (e.g. [1, 55])
            if "drivers" in data and isinstance(data["drivers"], list):
                session.selected_drivers = [int(d) for d in data["drivers"]]
        

manager = ConnectionManager()