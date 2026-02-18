#!/bin/bash
# Ubuntu installation script for web-traffic-bot dependencies

set -e

echo "Updating apt cache..."
sudo apt update

echo "Installing Python 3, pip, and required system libraries..."
sudo apt install -y python3 python3-pip python3-venv wget unzip curl

echo "Installing Chromium for Selenium usage..."
sudo apt install -y chromium-browser

echo "System setup complete!"