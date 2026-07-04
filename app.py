from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import uuid
from fastapi import WebSocket, WebSocketDisconnect


app = FastAPI(
    title="Local To Public",
    docs_url='/',
    redoc_url='/docs',
)

# stores active tunnels: name -> websocket
tunnels: dict[str, WebSocket] = {}

# stores pending requests: request_id -> Future
pending: dict[str, asyncio.Future] = {}

@app.websocket("/tunnel")
async def tunnel_endpoint(websocket: WebSocket):
    await websocket.accept()

    data = await websocket.receive_json()
    port = data["port"]
    name = data["name"]

    if name in tunnels:
        await websocket.send_json({"error": "name already taken"})
        await websocket.close()
        return

    tunnels[name] = websocket
    await websocket.send_json({"name": name})
    print(f"Tunnel open: {name} -> localhost:{port}")

    try:
        while True:
            response = await websocket.receive_json()
            request_id = response["request_id"]
            if request_id in pending:
                pending[request_id].set_result(response)
    except WebSocketDisconnect:
        tunnels.pop(name, None)
        print(f"Tunnel closed: {name}")

@app.api_route("/join/{name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(name: str, path: str, request: Request):
    if name not in tunnels:
        return JSONResponse({"error": "tunnel not found"}, status_code=404)

    ws = tunnels[name]
    request_id = str(uuid.uuid4())

    # read request body
    body = (await request.body()).decode("utf-8", errors="ignore")

    # forward request to CLI client
    await ws.send_json({
        "request_id": request_id,
        "method": request.method,
        "path": f"/{path}",
        "headers": dict(request.headers),
        "body": body,
    })

    # wait for CLI client to respond
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    pending[request_id] = future

    try:
        response = await asyncio.wait_for(future, timeout=30)
        pending.pop(request_id, None)
        return HTMLResponse(
            content=response.get("body"),
            status_code=response.get("status", 200),
        )
    except asyncio.TimeoutError:
        pending.pop(request_id, None)
        return JSONResponse({"error": "tunnel timeout"}, status_code=504)
