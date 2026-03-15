"""Low-level TCP server networking utilities.

This module handles connection acceptance and JSON message I/O so game state
logic in `game_server.py` remains focused and readable.
"""

from __future__ import annotations

import json
import socket
from typing import Any


class ServerNetwork:
    """TCP server wrapper with newline-delimited JSON messaging."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen()
        self.sock.setblocking(False)

    def accept_client(self) -> tuple[socket.socket, tuple[str, int]] | None:
        """Accept one client connection if available."""
        try:
            conn, addr = self.sock.accept()
            conn.setblocking(False)
            return conn, addr
        except BlockingIOError:
            return None

    @staticmethod
    def receive_many(conn: socket.socket, buffer: str) -> tuple[list[dict[str, Any]], str]:
        """Read zero or more JSON messages from one client connection."""
        messages: list[dict[str, Any]] = []
        try:
            data = conn.recv(8192)
            if not data:
                raise ConnectionResetError("Client disconnected")
            buffer += data.decode("utf-8")
        except BlockingIOError:
            return messages, buffer

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return messages, buffer

    @staticmethod
    def send(conn: socket.socket, message: dict[str, Any]) -> None:
        """Send one JSON message to a client connection."""
        payload = (json.dumps(message) + "\n").encode("utf-8")
        conn.sendall(payload)
