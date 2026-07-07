import asyncio
import os
import uuid
from fastapi import WebSocket, WebSocketDisconnect, Request, FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
template = Jinja2Templates(directory="templates")
BASE_DOMAIN = os.getenv("LTP_BASE_DOMAIN", "localhost").strip().lower().rstrip(".")

# stores active tunnels: name -> websocket
tunnels: dict[str, WebSocket] = {}

# stores pending requests: request_id -> Future
pending: dict[str, asyncio.Future] = {}


def tunnel_name_from_host(host: str | None) -> str | None:
    if not host or not BASE_DOMAIN:
        return None

    hostname = host.split(":", 1)[0].lower().rstrip(".")
    suffix = f".{BASE_DOMAIN}"
    if hostname == BASE_DOMAIN or not hostname.endswith(suffix):
        return None

    name = hostname[:-len(suffix)]
    if not name or "." in name:
        return None
    return name


async def proxy_to_tunnel(name: str, path: str, request: Request):
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


@app.get("/")
async def homepage(request: Request):
    name = tunnel_name_from_host(request.headers.get("host"))
    if name:
        return await proxy_to_tunnel(name, "", request)

    return template.TemplateResponse(request, "index.html")

@app.websocket("/tunnel")
async def tunnel_endpoint(websocket: WebSocket):
    await websocket.accept()

    # wait for register message
    data = await websocket.receive_json()
    port = data["port"]

    # assign a unique name
    name = data['name']
    tunnels[name] = websocket
    print(f"Client registered: {name} -> localhost:{port}")

    await websocket.send_json({"name": name})
    if BASE_DOMAIN:
        print(f"Tunnel open at https://{name}.{BASE_DOMAIN}/")
    else:
        print(f"Tunnel open at /join/{name}")

    try:
        while True:
            # receive response from CLI client
            response = await websocket.receive_json()
            request_id = response["request_id"]

            # resolve the pending request
            if request_id in pending:
                pending[request_id].set_result(response)

    except WebSocketDisconnect:
        tunnels.pop(name, None)
        print(f"Tunnel closed: {name}")


@app.api_route("/join/{name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(name: str, path: str, request: Request):
    return await proxy_to_tunnel(name, path, request)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def subdomain_proxy(path: str, request: Request):
    name = tunnel_name_from_host(request.headers.get("host"))
    if not name:
        return JSONResponse({"error": "tunnel not found"}, status_code=404)

    return await proxy_to_tunnel(name, path, request)
