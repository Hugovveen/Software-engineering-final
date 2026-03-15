"""Entry point for starting either the game server or a pygame client.

Usage examples:
- python main.py server
- python main.py client
- python main.py preview
- python main.py --server
- python main.py --client
- python main.py --preview
"""

from __future__ import annotations

import argparse

from client.game_client import GameClient
from enemy_preview import run_preview
from server.game_server import GameServer


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for mode selection."""
    parser = argparse.ArgumentParser(description="Multiplayer 2D horror scaffold")
    parser.add_argument("mode", nargs="?", choices=["server", "client", "preview"], help="Run as server, client, or local preview")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--server", action="store_true", help="Run the multiplayer server")
    mode_group.add_argument("--client", action="store_true", help="Run the pygame client")
    mode_group.add_argument("--preview", action="store_true", help="Run a local pygame enemy preview")
    parser.add_argument("--host", default=None, help="Server host override")
    parser.add_argument("--port", default=None, type=int, help="Server port override")
    args = parser.parse_args()

    if args.server:
        args.mode = "server"
    elif args.client:
        args.mode = "client"
    elif args.preview:
        args.mode = "preview"

    if args.mode is None:
        parser.error("Choose a mode: 'server', 'client', or 'preview' (or use --server / --client / --preview).")

    return args


def main() -> None:
    """Run the selected mode."""
    args = parse_args()

    if args.mode == "server":
        server = GameServer(host=args.host, port=args.port)
        server.run()
        return

    if args.mode == "preview":
        run_preview()
        return

    client = GameClient(host=args.host, port=args.port)
    client.run()


if __name__ == "__main__":
    main()
