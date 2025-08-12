#!/bin/bash

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
cp -r resources "$build_dir/"

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
        cp -r "$dir" "$build_dir/plugins/"
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
    echo "  ⚠ kiutils/src/kiutils not found"
fi

# Keep easyeda2kicad in its original structure for easier development
if [[ -d "plugins/easyeda2kicad/easyeda2kicad" ]]; then
    mkdir -p "$build_dir/plugins/easyeda2kicad"
    cp -r plugins/easyeda2kicad/easyeda2kicad "$build_dir/plugins/easyeda2kicad/"
    echo "  ✓ Copied easyeda2kicad (keeping easyeda2kicad structure)"
else
    echo "  ⚠ easyeda2kicad/easyeda2kicad not found"
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
zip -r "$zip_target" . -x "*.pyc" "*/__pycache__/*"
cd - > /dev/null

# Restore original metadata
mv metadata_.json metadata.json

# Cleanup temp directory
rm -rf "$temp_dir"


# Show what's included
echo ""
echo "Package contents:"
if [[ -f "Import-LIB-KiCad-Plugin.zip" ]]; then
    unzip -l Import-LIB-KiCad-Plugin.zip
    echo "..."
    total_files=$(unzip -l Import-LIB-KiCad-Plugin.zip | tail -1 | awk '{print $2}')
    echo "Total files: $total_files"
    
    # Show ZIP size
    zip_size=$(ls -lh Import-LIB-KiCad-Plugin.zip | awk '{print $5}')
    echo "ZIP size: $zip_size"
else
    echo "Error: ZIP file not found after creation"
    echo "Debug: Looking for files in current directory:"
    ls -la *.zip 2>/dev/null || echo "No ZIP files found"
fi

echo "ZIP file created: $(realpath Import-LIB-KiCad-Plugin.zip)"