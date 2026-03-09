#!/bin/bash
# SampleForge — Installation script (macOS / Linux)
set -e

echo "=== SampleForge Installer ==="

# Check Python
python_cmd=""
for cmd in python3.11 python3.12 python3; do
    if command -v $cmd &>/dev/null; then
        version=$($cmd --version 2>&1 | awk '{print $2}')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            python_cmd=$cmd
            break
        fi
    fi
done

if [ -z "$python_cmd" ]; then
    echo "ERROR: Python 3.11+ required. Install from https://python.org"
    exit 1
fi
echo "Using: $python_cmd ($version)"

# Create virtual environment
VENV_DIR="$(dirname "$0")/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $python_cmd -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip -q

# Install PyTorch first (CPU or MPS for Apple Silicon)
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    echo "Apple Silicon detected — installing PyTorch with MPS support..."
    pip install torch torchvision torchaudio -q
else
    echo "Installing PyTorch (CPU)..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu -q
fi

# Install requirements
echo "Installing dependencies..."
pip install -r "$(dirname "$0")/requirements.txt" -q

echo ""
echo "=== Installation complete! ==="
echo ""
echo "To run SampleForge:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "NOTE: First launch will download the CLAP model (~1.5GB)."
echo "      Subsequent launches are instant."
