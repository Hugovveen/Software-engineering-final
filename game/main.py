"""Entry point for starting either the game server or a pygame client.

Usage examples:
- python main.py server
- python main.py client
- python main.py --server
- python main.py --client
"""

from __future__ import annotations

import argparse

from client.game_client import GameClient
from server.game_server import GameServer


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for mode selection."""
    parser = argparse.ArgumentParser(description="Multiplayer 2D horror scaffold")
    parser.add_argument("mode", nargs="?", choices=["server", "client"], help="Run as server or client")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--server", action="store_true", help="Run the multiplayer server")
    mode_group.add_argument("--client", action="store_true", help="Run the pygame client")
    parser.add_argument("--host", default=None, help="Server host override")
    parser.add_argument("--port", default=None, type=int, help="Server port override")
    args = parser.parse_args()

    if args.server:
        args.mode = "server"
    elif args.client:
        args.mode = "client"

    if args.mode is None:
        parser.error("Choose a mode: 'server' or 'client' (or use --server / --client).")

    return args


def main() -> None:
    """Run the selected mode."""
    args = parse_args()

    if args.mode == "server":
        server = GameServer(host=args.host, port=args.port)
        server.run()
        return

    client = GameClient(host=args.host, port=args.port)
    client.run()


if __name__ == "__main__":
    main()
