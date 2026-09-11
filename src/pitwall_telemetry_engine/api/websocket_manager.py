from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        #Tracks the list of drivers the user is watching
        self.selected_drivers: dict[WebSocket, list[int]] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    async def broadcast_telemetry(self, message:dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                await self.disconnect(connection)
    
    def update_client_selection(self, websocket: WebSocket, driver_numbers: list[int]):
        self.selected_drivers[websocket] = driver_numbers
    
    def get_active_driver_numbers(self) -> set[int]:
        all_drivers = set()
        for drivers in self.selected_drivers.values():
            all_drivers.update(drivers)
        
        return all_drivers or {4, 55}

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            
        self.selected_drivers.pop(websocket, None)

manager = ConnectionManager()