import asyncio
import base64
import os
import re
import uuid
from fastapi import WebSocket, WebSocketDisconnect, Request, FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

ENABLE_DOCS = os.getenv("LTP_ENABLE_DOCS", "").lower() in {"1", "true", "yes"}
BASE_DOMAIN = os.getenv("LTP_BASE_DOMAIN", "localhost").strip().lower().rstrip(".")
REQUEST_TIMEOUT = float(os.getenv("LTP_REQUEST_TIMEOUT", "30"))
MAX_BODY_BYTES = int(os.getenv("LTP_MAX_BODY_BYTES", str(10 * 1024 * 1024)))
NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

app = FastAPI(
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
template = Jinja2Templates(directory="templates")

# stores active tunnels: name -> websocket
tunnels: dict[str, WebSocket] = {}

# stores pending requests: request_id -> Future
pending: dict[str, asyncio.Future] = {}


def is_valid_tunnel_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name))


def filtered_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def tunnel_name_from_host(host: str | None) -> str | None:
    if not host or not BASE_DOMAIN:
        return None

    hostname = host.split(":", 1)[0].lower().rstrip(".")
    suffix = f".{BASE_DOMAIN}"
    if hostname == BASE_DOMAIN or not hostname.endswith(suffix):
        return None

    name = hostname[:-len(suffix)]
    if "." in name or not is_valid_tunnel_name(name):
        return None
    return name


async def proxy_to_tunnel(name: str, path: str, request: Request):
    if not is_valid_tunnel_name(name):
        return JSONResponse({"error": "invalid tunnel name"}, status_code=400)

    if name not in tunnels:
        return JSONResponse({"error": "tunnel not found"}, status_code=404)

    ws = tunnels[name]
    request_id = str(uuid.uuid4())

    # read request body
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse({"error": "request body too large"}, status_code=413)

    # forward request to CLI client
    await ws.send_json({
        "request_id": request_id,
        "method": request.method,
        "path": f"/{path}",
        "query_string": request.url.query,
        "headers": filtered_headers(dict(request.headers)),
        "body": base64.b64encode(body).decode("ascii"),
        "body_encoding": "base64",
    })

    # wait for CLI client to respond
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    pending[request_id] = future

    try:
        response = await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        pending.pop(request_id, None)
        response_body = response.get("body", "")
        if response.get("body_encoding") == "base64":
            content = base64.b64decode(response_body)
        else:
            content = response_body.encode("utf-8")

        return Response(
            content=content,
            status_code=response.get("status", 200),
            headers=filtered_headers(response.get("headers", {})),
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


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.websocket("/tunnel")
async def tunnel_endpoint(websocket: WebSocket):
    await websocket.accept()

    # wait for register message
    data = await websocket.receive_json()
    port = data["port"]

    # assign a unique name
    name = data["name"].strip().lower()
    if not is_valid_tunnel_name(name):
        await websocket.send_json({"error": "invalid tunnel name"})
        await websocket.close(code=1008)
        return

    if name in tunnels:
        await websocket.send_json({"error": "tunnel name already in use"})
        await websocket.close(code=1008)
        return

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
