import os
import logging
from pathlib import Path
from typing import List
from typing import Optional

class FileHandler:
    """Monitors a directory for new ZIP files within a specific size range."""
    
    def __init__(self, path: str, 
                 min_size: int = 1_000,        # 1 KB
                 max_size: int = 50_000_000,   # 50 MB
                 file_extension: str = ".zip"):
        """
        Initializes the FileHandler.
        
        Args:
            path: Path to the directory to monitor
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            file_extension: File extension to monitor
        """
        self.min_size = min_size
        self.max_size = max_size
        self.file_extension = file_extension
        self.path = ""
        self.known_files = set()  # Set is more efficient for membership checks
        self.logger = logging.getLogger(__name__)
        
        self.change_path(path)
    
    def change_path(self, new_path: str) -> None:
        """
        Changes the directory to monitor.
        
        Args:
            new_path: New directory path
        """
        path_obj = Path(new_path)
        
        if not path_obj.is_dir():
            self.logger.warning(f"Path '{new_path}' is not a directory. Using current directory.")
            new_path = "."
            path_obj = Path(new_path)
        
        if new_path != self.path:
            self.path = new_path
            self.known_files = set()  # Reset known files
            self.logger.info(f"Changed directory to '{new_path}'")
    
    def get_new_files(self, path: Optional[str] = None) -> List[str]:
        """
        Finds new files in the specified directory.
        
        Args:
            path: Optional - directory to monitor, 
                  if different from the current one
        
        Returns:
            List of full paths to new files
        """
        if path is not None and path != self.path:
            self.change_path(path)
        
        try:
            # Use pathlib for better path handling
            directory = Path(self.path)
            files = [f for f in directory.iterdir() if f.is_file()]
            
            new_files = []
            
            for file_path in sorted(files):
                # Check if it's a new file with the correct extension
                if (file_path.name not in self.known_files and 
                        file_path.name.endswith(self.file_extension)):
                    
                    # Check if the file size is within the allowed range
                    file_size = file_path.stat().st_size
                    if self.min_size <= file_size <= self.max_size:
                        new_files.append(str(file_path.absolute()))
                        self.known_files.add(file_path.name)
                    else:
                        self.logger.debug(
                            f"File '{file_path.name}' is outside the size range "
                            f"({file_size} bytes)"
                        )
            
            return new_files
            
        except (PermissionError, FileNotFoundError) as e:
            self.logger.error(f"Error reading directory: {e}")
            return []