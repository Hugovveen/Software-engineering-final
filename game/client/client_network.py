"""TCP client networking helper for sending and receiving JSON messages.

This module keeps socket details away from gameplay code to make networking
logic easy for teammates to read and modify.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from config import SERVER_HOST, SERVER_PORT


class ClientNetwork:
    """Small wrapper around a TCP socket with newline-delimited JSON messages."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT
        self.sock: socket.socket | None = None
        self._buffer = ""

    def connect(self) -> None:
        """Connect to the game server."""
        self.sock = socket.create_connection((self.host, self.port))
        self.sock.setblocking(False)

    def send(self, message: dict[str, Any]) -> None:
        """Send one JSON message to the server."""
        if self.sock is None:
            return
        payload = json.dumps(message) + "\n"
        try:
            self.sock.sendall(payload.encode("utf-8"))
        except (BlockingIOError, OSError):
            return

    def receive_many(self) -> list[dict[str, Any]]:
        """Receive zero or more complete JSON messages from the socket buffer."""
        if self.sock is None:
            return []

        messages: list[dict[str, Any]] = []
        while True:
            try:
                chunk = self.sock.recv(8192)
                if not chunk:
                    break
                self._buffer += chunk.decode("utf-8")
            except BlockingIOError:
                break
            except OSError:
                break

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                # Ignore malformed lines to keep the demo resilient.
                continue

        return messages

    def close(self) -> None:
        """Close the network connection."""
        if self.sock:
            self.sock.close()
            self.sock = None
