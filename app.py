from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import uuid
from fastapi import WebSocket, WebSocketDisconnect


app = FastAPI(
    title="Local To Public",
    docs_url='/',
    redoc_url='/docs',
)

import asyncio
import uuid

pending_requests = {}  # request_id -> {"request": ..., "future": ...}
    
@app.get("/poll/{name}")
async def poll(name: str):
    requests = {
        rid: {"method": r["method"], "path": r["path"], "body": r["body"]}
        for rid, r in pending_requests.items()
    }
    return JSONResponse(requests)

@app.post("/respond/{request_id}")
async def respond(request_id: str, request: Request):
    data = await request.json()
    if request_id in pending_requests:
        pending_requests[request_id]["future"].set_result(data)
    return JSONResponse({"ok": True})

@app.api_route("/{name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(name: str, path: str, request: Request):
    request_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    pending_requests[request_id] = {
        "method": request.method,
        "path": f"/{path}",
        "body": (await request.body()).decode(),
        "future": future,
    }

    # wait for CLI to respond
    try:
        response = await asyncio.wait_for(future, timeout=30)
        return Response(content=response["body"], status_code=response["status"])
    except asyncio.TimeoutError:
        return JSONResponse({"error": "timeout"}, status_code=504)
    finally:
        pending_requests.pop(request_id, None)
