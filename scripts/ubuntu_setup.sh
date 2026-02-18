#!/bin/bash
# Ubuntu / Debian installation script for web-traffic-bot dependencies
# Tested on Ubuntu 20.04, 22.04, 24.04

set -e

echo "=== Updating apt cache ==="
sudo apt update

echo ""
echo "=== Installing Python 3, pip, venv, and utilities ==="
sudo apt install -y python3 python3-pip python3-venv wget unzip curl

echo ""
echo "=== Installing Chromium and ChromeDriver ==="

# Ubuntu 22.04+ ships Chromium as a snap; the apt package is a stub.
# We install both the browser and the matching chromedriver via apt.
# On 20.04 the package is 'chromium-browser'; on 22.04+ it is 'chromium'.
if apt-cache show chromium &>/dev/null; then
    sudo apt install -y chromium chromium-driver
elif apt-cache show chromium-browser &>/dev/null; then
    sudo apt install -y chromium-browser chromium-chromedriver
else
    echo "WARNING: Could not find a Chromium package via apt."
    echo "You may need to install Chrome manually or set 'chromium_path' in the config."
fi

echo ""
echo "=== Verifying installations ==="

# Print browser version
for bin in chromium chromium-browser google-chrome; do
    if command -v "$bin" &>/dev/null; then
        echo "Browser : $($bin --version 2>/dev/null || echo 'version check failed')"
        break
    fi
done

# Print chromedriver version
for bin in chromedriver chromium-chromedriver; do
    if command -v "$bin" &>/dev/null; then
        echo "Driver  : $($bin --version 2>/dev/null || echo 'version check failed')"
        break
    fi
done

echo ""
echo "=== System setup complete! ==="
echo ""
echo "Next steps:"
echo "  python3 -m venv venv"
echo "  source venv/bin/activate"
echo "  pip install -e ."
echo "  web-traffic-bot --dashboard"
