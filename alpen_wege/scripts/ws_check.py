#!/usr/bin/env python
"""Open the job WebSocket like a client and print every message.

Usage (inside the api container; TOKEN is a login access token):
    python scripts/ws_check.py --token "$TOKEN"                       # general socket
    python scripts/ws_check.py --token "$TOKEN" --job <job_id>        # dedicated socket
    python scripts/ws_check.py --ticket <ticket>                      # reuse a ticket (it works once)
Options: --host http://localhost:8000   --seconds 60
"""
import argparse
import asyncio
import json
import time
import urllib.request

import websockets


def get_ticket(host: str, token: str) -> str:
    request = urllib.request.Request(
        f"{host}/api/v1/management/ws/ticket", method="POST", headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["response_data"]["ticket"]


def close_info(exc) -> str:
    rcvd = getattr(exc, "rcvd", None)
    code, reason = (rcvd.code, rcvd.reason) if rcvd else (getattr(exc, "code", None), getattr(exc, "reason", None))
    return f"CLOSED code={code} reason={reason!r}"


async def run(args) -> None:
    ticket = args.ticket or get_ticket(args.host, args.token)
    ws_host = args.host.replace("https://", "wss://").replace("http://", "ws://")
    path = f"/api/v1/management/ws/jobs/{args.job}" if args.job else "/api/v1/management/ws"
    end = time.time() + args.seconds
    try:
        async with websockets.connect(f"{ws_host}{path}?ticket={ticket}") as ws:
            while True:
                remaining = end - time.time()
                if remaining <= 0:
                    print("STOPPED (time is up)")
                    return
                try:
                    print(await asyncio.wait_for(ws.recv(), remaining), flush=True)
                except asyncio.TimeoutError:
                    print("STOPPED (time is up)")
                    return
    except websockets.ConnectionClosed as exc:
        print(close_info(exc))
    except Exception as exc:  # rejected handshake (missing ticket) and similar
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) or getattr(response, "status", None)
        if status:
            print(f"REJECTED http status {status}")
        else:
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print job WebSocket messages")
    parser.add_argument("--token")
    parser.add_argument("--ticket")
    parser.add_argument("--job")
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--seconds", type=int, default=60)
    asyncio.run(run(parser.parse_args()))
