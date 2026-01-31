#!/bin/bash

set -e  # Exit on error

# Cleanup function for early exit
cleanup() {
    # Restore metadata if backup exists
    if [[ -f "metadata_.json" ]]; then
        mv metadata_.json metadata.json
    fi
    # Remove temp directory if it exists
    if [[ -n "$temp_dir" ]] && [[ -d "$temp_dir" ]]; then
        rm -rf "$temp_dir"
    fi
}
trap cleanup EXIT

# Check for required tools
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed"
    echo "  macOS:   brew install jq"
    echo "  Linux:   apt install jq"
    echo "  Windows: choco install jq (or download from https://jqlang.github.io/jq/)"
    exit 1
fi

if ! command -v zip &> /dev/null; then
    echo "Error: zip is required but not installed"
    echo "  macOS:   brew install zip"
    echo "  Linux:   apt install zip"
    echo "  Windows: Git Bash includes zip, or use: choco install zip"
    exit 1
fi

# Check and initialize/update submodules if needed
check_submodules() {
    local needs_init=false

    # Check if submodules are initialized (directories exist and are not empty)
    if [[ ! -d "plugins/kiutils/src/kiutils" ]] || [[ ! -d "plugins/easyeda2kicad/easyeda2kicad" ]]; then
        needs_init=true
    fi

    if $needs_init; then
        echo "Initializing submodules..."
        git submodule update --init
        if [[ $? -ne 0 ]]; then
            echo "  ⚠ Failed to initialize submodules"
            echo "  Please run: git submodule update --init"
            exit 1
        fi
        echo "  ✓ Submodules initialized"
    fi

    # Check for local changes in submodules before updating
    if [[ "$1" != "--no-update" ]]; then
        local has_local_changes=false

        # Check for uncommitted changes in kiutils
        if [[ -d "plugins/kiutils" ]]; then
            if ! git -C plugins/kiutils diff --quiet 2>/dev/null || \
               ! git -C plugins/kiutils diff --cached --quiet 2>/dev/null; then
                echo "  ℹ kiutils has local changes - skipping update"
                has_local_changes=true
            fi
        fi

        # Check for uncommitted changes in easyeda2kicad
        if [[ -d "plugins/easyeda2kicad" ]]; then
            if ! git -C plugins/easyeda2kicad diff --quiet 2>/dev/null || \
               ! git -C plugins/easyeda2kicad diff --cached --quiet 2>/dev/null; then
                echo "  ℹ easyeda2kicad has local changes - skipping update"
                has_local_changes=true
            fi
        fi

        # Only update if no local changes
        if ! $has_local_changes; then
            echo "Checking for submodule updates..."
            git submodule update --remote --merge 2>/dev/null
            if [[ $? -eq 0 ]]; then
                echo "  ✓ Submodules are up to date"
            fi
        else
            echo "  → Using local submodule versions (local changes detected)"
        fi
    fi
}

check_submodules "$1"

# Clean up old ZIP
rm -f Import-LIB-KiCad-Plugin.zip

# Update metadata version
mv metadata.json metadata_.json
jq --arg today "$(date +%Y.%m.%d)" '.versions[0].version |= $today' metadata_.json > metadata.json

# Create temporary directory for clean packaging
temp_dir=$(mktemp -d)
build_dir="$temp_dir/build"
mkdir -p "$build_dir"

echo "Preparing clean package structure..."

# Copy metadata and resources
cp metadata.json "$build_dir/"
cp -r resources "$build_dir/" 2>/dev/null || cp -r resources/ "$build_dir/resources/"

# Copy plugins directory structure but exclude submodule bloat
mkdir -p "$build_dir/plugins"

# Copy main plugin files
find plugins -maxdepth 1 -type f \( -name "*.py" -o -name "*.json" -o -name "*.txt" -o -name "*.ini" -o -name "*.png" \) \
    -exec cp {} "$build_dir/plugins/" \;

# Copy plugin subdirectories (excluding submodules)
for dir in plugins/*/; do
    dirname=$(basename "$dir")
    
    # Skip submodules - we'll handle them specially
    if [[ "$dirname" == "easyeda2kicad" || "$dirname" == "kiutils" ]]; then
        continue
    fi
    
    # Copy regular plugin directories
    if [[ -d "$dir" ]]; then
        # Remove trailing slash to ensure directory is copied, not just contents (macOS compatibility)
        cp -r "${dir%/}" "$build_dir/plugins/"
    fi
done

# Copy only needed parts from submodules
echo "Copying essential parts from submodules..."

# Keep kiutils in its original structure for easier development
if [[ -d "plugins/kiutils/src/kiutils" ]]; then
    mkdir -p "$build_dir/plugins/kiutils/src"
    cp -r plugins/kiutils/src/kiutils "$build_dir/plugins/kiutils/src/"
    echo "  ✓ Copied kiutils (keeping src/kiutils structure)"
else
    echo "  ⚠ kiutils/src/kiutils not found - run: git submodule update --init"
    exit 1
fi

# Keep easyeda2kicad in its original structure for easier development
if [[ -d "plugins/easyeda2kicad/easyeda2kicad" ]]; then
    mkdir -p "$build_dir/plugins/easyeda2kicad"
    cp -r plugins/easyeda2kicad/easyeda2kicad "$build_dir/plugins/easyeda2kicad/"
    echo "  ✓ Copied easyeda2kicad (keeping easyeda2kicad structure)"
else
    echo "  ⚠ easyeda2kicad/easyeda2kicad not found - run: git submodule update --init"
    exit 1
fi

# Copy kicad_advanced if it's a file/script
if [[ -f "plugins/kicad_advanced" ]]; then
    cp plugins/kicad_advanced "$build_dir/plugins/"
fi

# Clean up unwanted files from the build
echo "Cleaning up unwanted files..."
find "$build_dir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find "$build_dir" -name "*.pyc" -delete 2>/dev/null
find "$build_dir" -name "*.log" -delete 2>/dev/null
find "$build_dir" -name "*.fbp" -delete 2>/dev/null
find "$build_dir" -name "*.svg" -delete 2>/dev/null

# Create ZIP from clean build directory
echo "Creating ZIP file..."
zip_target="$(pwd)/Import-LIB-KiCad-Plugin.zip"
cd "$build_dir"
zip -rq "$zip_target" . -x "*.pyc" "*/__pycache__/*"
cd - > /dev/null

# Cleanup is handled by trap


# Show what's included
echo ""
echo "Package contents:"
if [[ -f "Import-LIB-KiCad-Plugin.zip" ]]; then
    unzip -l Import-LIB-KiCad-Plugin.zip
    echo "..."
    total_files=$(unzip -l Import-LIB-KiCad-Plugin.zip | tail -1 | awk '{print $2}')
    echo "Total files: $total_files"
    
    # Show ZIP size (portable across systems)
    if command -v stat &> /dev/null; then
        # Try GNU stat first, then BSD stat (macOS)
        zip_bytes=$(stat -c%s Import-LIB-KiCad-Plugin.zip 2>/dev/null || stat -f%z Import-LIB-KiCad-Plugin.zip 2>/dev/null)
        if [[ -n "$zip_bytes" ]]; then
            zip_size=$((zip_bytes / 1024))K
        else
            zip_size=$(ls -lh Import-LIB-KiCad-Plugin.zip | awk '{print $5}')
        fi
    else
        zip_size=$(ls -lh Import-LIB-KiCad-Plugin.zip | awk '{print $5}')
    fi
    echo "ZIP size: $zip_size"
else
    echo "Error: ZIP file not found after creation"
    echo "Debug: Looking for files in current directory:"
    ls -la *.zip 2>/dev/null || echo "No ZIP files found"
fi

# Use realpath if available, otherwise pwd
if command -v realpath &> /dev/null; then
    echo "ZIP file created: $(realpath Import-LIB-KiCad-Plugin.zip)"
else
    echo "ZIP file created: $(pwd)/Import-LIB-KiCad-Plugin.zip"
fi