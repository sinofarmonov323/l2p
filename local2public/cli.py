from argparse import ArgumentParser
import asyncio
import base64
import json
import os
import re
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

SERVER_URL = os.getenv("LTP_SERVER_URL", "ws://localhost:8000/tunnel")
PUBLIC_BASE_URL = os.getenv("LTP_PUBLIC_BASE_URL")
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


def parse_args():
    parser = ArgumentParser(description="ltp - local to public")
    parser.add_argument("-p", "--port", type=int, required=True, help="Local port to expose")
    parser.add_argument("-n", "--name", type=str, required=True, help="Public tunnel name")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args()


def normalize_tunnel_name(name: str) -> str:
    normalized = name.strip().lower()
    if not NAME_RE.fullmatch(normalized):
        raise ValueError(
            "name must be a valid DNS label: lowercase letters, numbers, and hyphens only"
        )
    return normalized


def filtered_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def public_url_for_name(name: str) -> str:
    base_url = PUBLIC_BASE_URL
    if not base_url:
        parsed_server = urlparse(SERVER_URL)
        scheme = "https" if parsed_server.scheme == "wss" else "http"
        base_url = urlunparse((scheme, parsed_server.netloc, "", "", "", ""))

    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    netloc = f"{name}.{parsed.netloc}"
    return urlunparse((parsed.scheme, netloc, "/", "", "", ""))


async def tunnel(local_port: int, name: str, verbose: bool):
    name = normalize_tunnel_name(name)

    async with websockets.connect(SERVER_URL) as ws:
        await ws.send(json.dumps({"type": "register", "port": local_port, "name": name}))

        response = json.loads(await ws.recv())
        if "error" in response:
            print(f"Error: {response['error']}")
            return

        print(f"Tunnel open: {public_url_for_name(name)}")
        print("Ctrl+C to stop")

        async with httpx.AsyncClient() as client:
            while True:
                message = json.loads(await ws.recv())

                if verbose:
                    print(f"-> {message['method']} {message['path']}")

                try:
                    path = message["path"]
                    if message.get("query_string"):
                        path = f"{path}?{message['query_string']}"

                    body = message.get("body", "")
                    if message.get("body_encoding") == "base64":
                        content = base64.b64decode(body)
                    else:
                        content = body.encode("utf-8")

                    resp = await client.request(
                        method=message["method"],
                        url=f"http://localhost:{local_port}{path}",
                        headers=filtered_headers(message.get("headers", {})),
                        content=content,
                    )
                    await ws.send(json.dumps({
                        "type": "response",
                        "request_id": message["request_id"],
                        "status": resp.status_code,
                        "headers": filtered_headers(dict(resp.headers)),
                        "body": base64.b64encode(resp.content).decode("ascii"),
                        "body_encoding": "base64",
                    }))
                except Exception as e:
                    await ws.send(json.dumps({
                        "type": "response",
                        "request_id": message["request_id"],
                        "status": 502,
                        "headers": {"content-type": "text/plain; charset=utf-8"},
                        "body": base64.b64encode(str(e).encode("utf-8")).decode("ascii"),
                        "body_encoding": "base64",
                    }))


def main():
    args = parse_args()
    try:
        asyncio.run(tunnel(args.port, args.name, args.verbose))
    except ValueError as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nTunnel closed")


if __name__ == "__main__":
    main()
