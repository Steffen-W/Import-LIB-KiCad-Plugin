$outputName = "KiCad-Footprint-Importer.zip"

# Clean up old ZIP
Remove-Item -Path $outputName -ErrorAction SilentlyContinue

# Update metadata version
Move-Item -Path "metadata.json" -Destination "metadata_.json" -Force
$today = Get-Date -Format "yyyy.MM.dd"
$metadata = Get-Content "metadata_.json" | ConvertFrom-Json
$metadata.versions[0].version = $today
$metadata | ConvertTo-Json -Depth 10 | Set-Content "metadata.json"

# Create temporary directory for clean packaging
$tempDir = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName()))
$buildDir = New-Item -ItemType Directory -Path (Join-Path $tempDir "build")

Write-Host "Preparing clean package structure..."

# Copy metadata and resources
Copy-Item -Path "metadata.json" -Destination "$buildDir\" -Force
Copy-Item -Path "resources" -Destination "$buildDir\" -Recurse -Force

# Copy plugins directory structure but exclude submodule bloat
New-Item -ItemType Directory -Path "$buildDir\plugins" -Force | Out-Null

# Copy main plugin files
Get-ChildItem -Path "plugins" -File -Depth 0 | Where-Object {
    $_.Extension -in @('.py', '.json', '.txt', '.ini', '.png')
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$buildDir\plugins\" -Force
}

# Copy plugin subdirectories (excluding submodules)
Get-ChildItem -Path "plugins" -Directory | Where-Object {
    $_.Name -notin @('easyeda2kicad', 'kiutils')
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$buildDir\plugins\" -Recurse -Force
}

# Copy only needed parts from submodules
Write-Host "Copying essential parts from submodules..."

# Keep kiutils in its original structure for easier development
if (Test-Path "plugins\kiutils\src\kiutils") {
    New-Item -ItemType Directory -Path "$buildDir\plugins\kiutils\src" -Force | Out-Null
    Copy-Item -Path "plugins\kiutils\src\kiutils" -Destination "$buildDir\plugins\kiutils\src\" -Recurse -Force
    Write-Host "  ✓ Copied kiutils (keeping src/kiutils structure)"
} else {
    Write-Host "  ⚠ kiutils/src/kiutils not found"
}

# Keep easyeda2kicad in its original structure for easier development
if (Test-Path "plugins\easyeda2kicad\easyeda2kicad") {
    New-Item -ItemType Directory -Path "$buildDir\plugins\easyeda2kicad" -Force | Out-Null
    Copy-Item -Path "plugins\easyeda2kicad\easyeda2kicad" -Destination "$buildDir\plugins\easyeda2kicad\" -Recurse -Force
    Write-Host "  ✓ Copied easyeda2kicad (keeping easyeda2kicad structure)"
} else {
    Write-Host "  ⚠ easyeda2kicad/easyeda2kicad not found"
}

# Copy kicad_advanced if it's a file/script
if (Test-Path "plugins\kicad_advanced" -PathType Leaf) {
    Copy-Item -Path "plugins\kicad_advanced" -Destination "$buildDir\plugins\" -Force
}

# Clean up unwanted files from the build
Write-Host "Cleaning up unwanted files..."
Get-ChildItem -Path $buildDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $buildDir -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $buildDir -Recurse -Filter "*.log" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $buildDir -Recurse -Filter "*.fbp" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $buildDir -Recurse -Filter "*.svg" | Remove-Item -Force -ErrorAction SilentlyContinue

# Create ZIP from clean build directory
Write-Host "Creating ZIP file..."
$zipTarget = Join-Path (Get-Location) $outputName
Compress-Archive -Path "$buildDir\*" -DestinationPath $zipTarget -Force

# Restore original metadata
Move-Item -Path "metadata_.json" -Destination "metadata.json" -Force

# Cleanup temp directory
Remove-Item -Path $tempDir -Recurse -Force

# Show what's included
Write-Host ""
Write-Host "Package contents:"
if (Test-Path $outputName) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipTarget)
    
    # Show first 20 entries
    $entries = $zip.Entries | Select-Object -First 20
    foreach ($entry in $entries) {
        Write-Host "  $($entry.FullName)"
    }
    
    Write-Host "..."
    $totalFiles = $zip.Entries.Count
    Write-Host "Total files: $totalFiles"
    
    $zip.Dispose()
    
    # Show ZIP size
    $zipSize = (Get-Item $outputName).Length
    $zipSizeFormatted = if ($zipSize -gt 1MB) {
        "{0:N2} MB" -f ($zipSize / 1MB)
    } elseif ($zipSize -gt 1KB) {
        "{0:N2} KB" -f ($zipSize / 1KB)
    } else {
        "$zipSize bytes"
    }
    Write-Host "ZIP size: $zipSizeFormatted"
    
    Write-Host ""
    Write-Host "ZIP file created: $(Resolve-Path $outputName)"
} else {
    Write-Host "Error: ZIP file not found after creation"
    Write-Host "Debug: Looking for files in current directory:"
    Get-ChildItem -Filter "*.zip" -ErrorAction SilentlyContinue
}
