from argparse import ArgumentParser
import asyncio
import httpx

SERVER_URL = "https://l2p-beige.vercel.app"  # change to your deployed server

def parse_args():
    parser = ArgumentParser(description="ltp - local to public")
    parser.add_argument("-p", "--port", type=int, required=True)
    parser.add_argument("-n", "--name", type=str, required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()

async def tunnel(local_port: int, name: str, verbose: bool):
    print(f"Tunnel open: {SERVER_URL}/join/{name}/")
    print("Ctrl+C to stop")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                # poll for pending requests
                resp = await client.get(f"{SERVER_URL}/poll/{name}", timeout=5)
                requests = resp.json()

                for request_id, req in requests.items():
                    if verbose:
                        print(f"→ {req['method']} {req['path']}")

                    try:
                        # forward to local server
                        local_resp = await client.request(
                            method=req["method"],
                            url=f"http://localhost:{local_port}{req['path']}",
                            content=req["body"],
                            timeout=10,
                        )
                        # send response back to server
                        await client.post(f"{SERVER_URL}/respond/{request_id}", json={
                            "status": local_resp.status_code,
                            "body": local_resp.text,
                        })
                    except Exception as e:
                        await client.post(f"{SERVER_URL}/respond/{request_id}", json={
                            "status": 502,
                            "body": str(e),
                        })

            except Exception as e:
                print(f"Poll error: {e}")

            await asyncio.sleep(0.5)

def main():
    args = parse_args()
    try:
        asyncio.run(tunnel(args.port, args.name, args.verbose))
    except KeyboardInterrupt:
        print("\nTunnel closed")

if __name__ == "__main__":
    main()
