#!/bin/bash
# Install Go on macOS

set -e

echo "DeployBot Agent - Go Installation Script"
echo "========================================="
echo ""

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    GO_ARCH="arm64"
    echo "Detected: Apple Silicon (M1/M2/M3)"
elif [ "$ARCH" = "x86_64" ]; then
    GO_ARCH="amd64"
    echo "Detected: Intel Mac"
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi

# Get latest Go version
GO_VERSION="1.22.0"
echo "Installing Go $GO_VERSION for macOS $GO_ARCH..."
echo ""

# Download URL
GO_PKG="go${GO_VERSION}.darwin-${GO_ARCH}.pkg"
GO_URL="https://go.dev/dl/${GO_PKG}"

echo "Downloading from: $GO_URL"
echo ""

# Check if Go is already installed
if command -v go &> /dev/null; then
    CURRENT_VERSION=$(go version | awk '{print $3}')
    echo "Go is already installed: $CURRENT_VERSION"
    echo ""
    read -p "Do you want to reinstall? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

# Download the installer
echo "Downloading Go installer..."
curl -L -o "/tmp/${GO_PKG}" "$GO_URL"

echo ""
echo "Opening installer package..."
echo "Please follow the installation wizard."
echo ""
open "/tmp/${GO_PKG}"

echo ""
echo "After installation completes:"
echo "1. Open a new terminal window"
echo "2. Run: go version"
echo "3. Run: make build-agent"
echo ""
