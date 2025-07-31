"""
Single Instance Manager with IPC communication for KiCad Plugin.
Handles ensuring only one instance runs and brings existing window to foreground.
"""

import socket
import threading
import json
import logging
from typing import Optional, Any

try:
    import wx
except ImportError:
    wx = None


class SingleInstanceManager:
    """Manages single instance with IPC communication."""
    
    def __init__(self, port: int = 59999):
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.frontend_instance: Optional[Any] = None
        
    def is_already_running(self) -> bool:
        """Check if another instance is running and send focus command."""
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(1.0)
            client_socket.connect(('127.0.0.1', self.port))
            
            message = {"command": "focus"}
            client_socket.send(json.dumps(message).encode('utf-8'))
            client_socket.close()
            
            logging.info("Sent focus command to existing instance")
            return True
            
        except (socket.error, ConnectionRefusedError, OSError):
            return False
    
    def start_server(self, frontend_instance: Any) -> bool:
        """Start IPC server to listen for commands."""
        self.frontend_instance = frontend_instance
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('127.0.0.1', self.port))
            self.socket.listen(1)
            self.running = True
            
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            
            logging.info(f"IPC server started on port {self.port}")
            return True
            
        except socket.error as e:
            logging.error(f"Failed to start IPC server: {e}")
            return False
    
    def _server_loop(self) -> None:
        """Main server loop to handle incoming commands."""
        while self.running:
            try:
                client_socket, addr = self.socket.accept()
                client_socket.settimeout(5.0)
                
                data = client_socket.recv(1024).decode('utf-8')
                if data:
                    try:
                        message = json.loads(data)
                        self._handle_command(message)
                    except json.JSONDecodeError:
                        logging.warning("Received invalid JSON data")
                
                client_socket.close()
                
            except socket.timeout:
                continue
            except socket.error as e:
                if self.running:
                    logging.error(f"Server socket error: {e}")
                break
    
    def _handle_command(self, message: dict) -> None:
        """Handle incoming commands."""
        command = message.get("command")
        
        if command == "focus" and self.frontend_instance:
            if wx:
                wx.CallAfter(self._bring_to_foreground)
            else:
                logging.warning("wx not available - cannot bring window to foreground")
    
    def _bring_to_foreground(self) -> None:
        """Bring the window to foreground (must be called from main thread)."""
        if self.frontend_instance and hasattr(self.frontend_instance, 'IsShown'):
            try:
                if self.frontend_instance.IsShown():
                    self.frontend_instance.Raise()
                    self.frontend_instance.SetFocus()
                    self.frontend_instance.RequestUserAttention()
                    logging.info("Brought existing window to foreground")
                else:
                    logging.info("Window exists but is not shown")
            except Exception as e:
                logging.error(f"Failed to bring window to foreground: {e}")
    
    def stop_server(self) -> None:
        """Stop the IPC server."""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=1.0)