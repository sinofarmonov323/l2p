from argparse import ArgumentParser
import asyncio
import httpx
import websockets
import json

SERVER_URL = "ws://localhost:8000/tunnel"

def parse_args():
    parser = ArgumentParser(description="ltp - local to public")
    parser.add_argument("-p", "--port", type=int, required=True, help="Local port to expose")
    parser.add_argument("-n", "--name", type=str, required=True, help="Public tunnel name")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args()

async def tunnel(local_port: int, name: str, verbose: bool):
    async with websockets.connect(SERVER_URL) as ws:
        await ws.send(json.dumps({"type": "register", "port": local_port, "name": name}))

        response = json.loads(await ws.recv())
        if "error" in response:
            print(f"Error: {response['error']}")
            return

        print(f"Tunnel open: http://localhost:8000/join/{name}/")
        print("Ctrl+C to stop")

        async with httpx.AsyncClient() as client:
            while True:
                message = json.loads(await ws.recv())

                if verbose:
                    print(f"→ {message['method']} {message['path']}")

                try:
                    resp = await client.request(
                        method=message["method"],
                        url=f"http://localhost:{local_port}{message['path']}",
                        headers=message.get("headers", {}),
                        content=message.get("body", b""),
                    )
                    await ws.send(json.dumps({
                        "type": "response",
                        "request_id": message["request_id"],
                        "status": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp.text,
                    }))
                except Exception as e:
                    await ws.send(json.dumps({
                        "type": "response",
                        "request_id": message["request_id"],
                        "status": 502,
                        "body": str(e),
                    }))

def main():
    args = parse_args()
    try:
        asyncio.run(tunnel(args.port, args.name, args.verbose))
    except KeyboardInterrupt:
        print("\nTunnel closed")

if __name__ == "__main__":
    main()
