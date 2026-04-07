"""
Single Instance Manager with IPC communication for KiCad Plugin.
Handles ensuring only one instance runs and brings existing window to foreground.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import socket
import threading
from pathlib import Path
from typing import Any

try:
    import wx
except ImportError:
    wx = None


def _plugin_port(plugin_dir: Path) -> int:
    """Derive a stable, plugin-specific port from the install path.

    Uses a hash of the directory path so that different plugins installed in
    different locations always get different ports without any manual config.
    Port range 49152–65534 (IANA dynamic/private range).
    """
    h = int(hashlib.md5(str(plugin_dir).encode()).hexdigest(), 16)
    return 49152 + (h % 16383)


class SingleInstanceManager:
    """Manages single instance with IPC communication and window state.

    The TCP port is the single source of truth — no lock file needed.
    """

    def __init__(self) -> None:
        self.port = _plugin_port(Path(__file__).resolve().parent)
        self.socket: socket.socket | None = None
        self.server_thread: threading.Thread | None = None
        self.running = False
        self.frontend_instance: Any | None = None
        self._stopped = False

    def is_already_running(self) -> bool:
        """Try to claim the port. Returns True if another instance already holds it.

        On success (first instance): the socket is bound and ready for start_server().
        On failure (instance exists): sends a focus command to the existing window.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR allows re-binding quickly after a clean shutdown.
        # SO_REUSEPORT is intentionally NOT set: on Linux it allows multiple
        # processes to co-listen on the same port, which breaks single-instance
        # enforcement (the kernel would load-balance connections between them).
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", self.port))
            s.listen(5)
            s.settimeout(1.0)
            self.socket = s
            logging.info(f"Port {self.port} claimed — starting as new instance")
            return False
        except OSError as e:
            s.close()
            if e.errno != errno.EADDRINUSE:
                logging.error(f"Unexpected socket error on port {self.port}: {e}")
                return False
            logging.info(f"Port {self.port} in use — sending focus to existing instance")
            self._send_focus()
            return True

    def _send_focus(self) -> None:
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", self.port))
            s.sendall(b"focus\n")
            try:
                s.settimeout(1.0)
                logging.info(f"Focus acknowledged: {s.recv(4)!r}")
            except socket.timeout:
                logging.warning("Focus sent but no acknowledgment received")
        except OSError as e:
            logging.warning(f"Could not send focus command: {e}")
        finally:
            if s:
                s.close()

    def start_server(self, frontend_instance: Any) -> bool:
        """Start the IPC server using the socket claimed in is_already_running()."""
        if self.socket is None:
            logging.error("start_server() called without a claimed socket")
            return False

        self._stopped = False
        self.running = True
        if self.frontend_instance is None:
            self.frontend_instance = frontend_instance

        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

        logging.info(f"IPC server started on port {self.port}")
        return True

    def _server_loop(self) -> None:
        sock = self.socket
        if sock is None:
            return
        while self.running:
            client_socket = None
            try:
                client_socket, _ = sock.accept()
                client_socket.settimeout(5.0)
                data = client_socket.recv(64).strip()
                if data == b"focus" and self.frontend_instance and wx:
                    try:
                        wx.CallAfter(self._bring_to_foreground)
                    except RuntimeError as e:
                        logging.warning(f"wx.CallAfter failed: {e}")
                client_socket.sendall(b"ok\n")
            except socket.timeout:
                continue
            except OSError as e:
                if self.running:
                    logging.error(f"Server socket error: {e}")
                break
            finally:
                if client_socket:
                    try:
                        client_socket.close()
                    except OSError:
                        pass

    def _bring_to_foreground(self) -> None:
        """Bring the window to foreground (must be called from main thread)."""
        if not self.frontend_instance:
            return
        try:
            if self.frontend_instance.IsBeingDeleted():
                return
            if not self.frontend_instance.IsShown():
                self.frontend_instance.Show(True)
            # Iconize then restore: convinces the window manager to raise the
            # window even when another top-level window (e.g. board editor) has focus.
            self.frontend_instance.Iconize(True)
            self.frontend_instance.Iconize(False)
            self.frontend_instance.Raise()
            self.frontend_instance.SetFocus()
            self.frontend_instance.RequestUserAttention()
            logging.info("Window brought to foreground")
        except Exception as e:
            logging.error(f"Failed to bring window to foreground: {e}")
            # Only drop the reference if the window is confirmed destroyed.
            # Clearing on any exception would permanently disable focus on transient errors.
            try:
                if self.frontend_instance.IsBeingDeleted():
                    self.frontend_instance = None
            except Exception:
                self.frontend_instance = None

    def register_frontend(self, frontend_instance: Any) -> bool:
        """Register a frontend instance. Returns False if one is already registered."""
        if self.frontend_instance is not None:
            return False
        self.frontend_instance = frontend_instance
        return True

    def stop_server(self) -> None:
        """Stop the IPC server."""
        if self._stopped:
            return
        self._stopped = True
        self.running = False

        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.socket.close()
            except Exception as e:
                logging.debug(f"Error closing socket: {e}")
            finally:
                self.socket = None

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
            if self.server_thread.is_alive():
                logging.warning("Server thread did not stop within 5 seconds")
            self.server_thread = None

        self.frontend_instance = None
        logging.info("IPC server stopped")
