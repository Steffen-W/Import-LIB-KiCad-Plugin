# KiCad Import Plugin - Code Structure

This document provides a detailed overview of the plugin's code architecture and component interactions.

## Overview

The KiCad Import Plugin supports importing library files from various sources (Octopart, Samacsys, UltraLibrarian, Snapeda, EasyEDA) and operates in two modes:

1. **IPC Mode**: Uses KiCad's IPC API for singleton behavior
2. **Fallback Mode**: Direct execution from PCBNew when IPC is unavailable

## Core Architecture

```
plugins/
├── __init__.py                  # PCBNew plugin entry point (fallback mode)
├── impart_action.py            # Main application logic
├── single_instance_manager.py  # IPC singleton management
├── impart_gui.py              # GUI framework (generated)
├── impart_easyeda.py          # EasyEDA-specific import logic
├── impart_migration.py        # Library migration utilities
└── [support modules]/
```

## Entry Points

### 1. Direct Execution (`__main__`)
- **File**: `impart_action.py` (lines 969-991)
- **Mode**: IPC-enabled singleton
- **Behavior**: 
  - Checks for existing instance via socket connection
  - Creates new instance only if none exists
  - Focuses existing window if found

### 2. PCBNew Plugin (`__init__.py`)
- **Class**: `ActionImpartPlugin`
- **Mode**: Fallback mode
- **Behavior**:
  - Always creates new instance
  - Sets up virtual environment if needed
  - Calls `ImpartFrontend(fallback_mode=True)`

## Instance Management

### SingleInstanceManager (`single_instance_manager.py`)

**Purpose**: Ensures only one IPC instance runs, provides window focus functionality

**Key Methods**:
- `is_already_running()`: Socket-based instance detection
- `start_server()`: IPC server for receiving focus commands
- `_bring_to_foreground()`: Window restoration and focus

**Port**: 59999 (configurable)

### Instance Check Logic (`impart_action.py` lines 22-32)

```python
def quick_instance_check(port: int = 59999) -> bool:
    """Quick check before logging setup"""
```

**Purpose**: Fast socket check before logging configuration to prevent log overwrites

## Logging System

### Dual Logging Strategy

**New Instance**:
- Full debug logging to `plugin.log`
- File mode: `"w"` (overwrite)
- Format: Timestamped with location info

**Follow-up Instance**:
- Minimal warning-level logging  
- File mode: `"a"` (append)
- Format: Simple message only

**Implementation** (`impart_action.py` lines 34-56):
```python
if __name__ == "__main__":
    is_new_instance = not quick_instance_check()
    # Configure logging based on instance status
```

## Backend Architecture

### ImpartBackend (`impart_action.py` lines 156-286)

**Purpose**: Core import logic and state management

**Key Components**:
- `KiCadApp`: KiCad integration and version checking
- `ConfigHandler`: Settings management
- `FileHandler`: File monitoring and processing
- `LibImporter`: Library conversion logic

**State Management**:
- Each frontend instance creates its own backend
- No persistent state between instances
- Clean separation between IPC and fallback modes

### Frontend Integration

**ImpartFrontend** (`impart_action.py` lines 345-948):
- Inherits from `impartGUI` (generated UI)
- Mode-aware initialization (`fallback_mode` parameter)
- Backend binding: `self.backend = create_backend_handler()`

## Import Process Flow

### 1. File Detection
- **FileHandler**: Monitors source directory
- **Supported**: ZIP files from various providers
- **Processing**: Automatic extraction and validation

### 2. Library Conversion
- **LibImporter**: Handles format conversion
- **KiCad CLI**: Used for legacy format conversion
- **Output**: Modern KiCad library formats

### 3. Installation
- **Global Mode**: Libraries stored in user-defined directory
- **Local Mode**: Project-specific library installation
- **Verification**: Automatic KiCad settings integration

## GUI Architecture

### Base Framework
- **Generated**: `impart_gui.py` (from wxFormBuilder)
- **Extended**: `ImpartFrontend` adds application logic
- **Threading**: `PluginThread` for status monitoring

### Event Handling
- **File Drop**: Drag & drop support for direct import
- **Path Changes**: Real-time configuration updates
- **Close Behavior**: Mode-specific cleanup logic

### Mode-Specific Behavior

**IPC Mode Close**:
- Auto-import active: Minimize window, keep running
- No auto-import: Complete shutdown
- Server cleanup on exit

**Fallback Mode Close**:
- Auto-import active: Option to run in background
- No auto-import: Direct shutdown
- No IPC server involvement

## Configuration Management

### ConfigHandler (`ConfigHandler.py`)
- **Storage**: INI-based configuration
- **Paths**: Source and destination directory management
- **Persistence**: Settings preserved between sessions

### KiCad Integration
- **Settings Detection**: Automatic KiCad version detection
- **Path Resolution**: Global vs. project-specific libraries
- **Library Registration**: Automatic symbol/footprint library addition

## Subprocess Management

### Console Window Prevention (Windows)
All subprocess calls include:
```python
creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
```

**Affected Components**:
- `kicad_cli`: KiCad CLI operations
- `PipManager`: Python package management
- `run_subprocess_safe`: General subprocess wrapper

## Error Handling

### Logging Strategy
- **Startup**: Comprehensive initialization logging
- **Runtime**: Operation-specific error tracking
- **Cleanup**: Graceful shutdown logging

### User Feedback
- **GUI Dialogs**: Critical error presentation
- **Status Buffer**: Real-time operation feedback
- **Log Integration**: Detailed troubleshooting information

## Dependencies

### Core Dependencies
- **wxPython**: GUI framework
- **pathlib**: Modern path handling
- **socket**: IPC communication
- **subprocess**: External tool integration

### Optional Dependencies
- **pydantic**: Configuration validation (EasyEDA)
- **requests**: Web API integration (EasyEDA)

### KiCad Integration
- **pcbnew**: PCBNew API access (fallback mode)
- **kicad-cli**: Command-line tool integration

## Development Notes

### Code Conventions
- **Type Hints**: Comprehensive type annotations
- **Docstrings**: Function and class documentation
- **Error Handling**: Explicit exception management

### Testing Approach
- **Mode Testing**: Both IPC and fallback scenarios
- **Platform Testing**: Windows subprocess behavior
- **Integration Testing**: KiCad version compatibility

### Performance Considerations
- **Lazy Loading**: Import modules only when needed
- **Background Processing**: Non-blocking file operations
- **Resource Cleanup**: Explicit resource management

## Future Enhancements

### Planned Improvements
- **Configuration UI**: Advanced settings interface
- **Batch Processing**: Multiple file import optimization  
- **Plugin Architecture**: Extensible import providers
- **Logging Rotation**: Automatic log file management

### Architecture Goals
- **Maintainability**: Clear separation of concerns
- **Extensibility**: Easy addition of new import sources
- **Reliability**: Robust error handling and recovery
- **User Experience**: Consistent behavior across modes