@echo off
setlocal EnableExtensions

rem Always build relative to this script, even when launched from another folder.
pushd "%~dp0"

set "APP_NAME=HELINK"
set "VENV_DIR=%CD%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "ENTRY_POINT=%CD%\main.py"
set "ASSETS_DIR=%CD%\helink\assets"
set "BUILD_DIR=%CD%\build"
set "DIST_DIR=%CD%\dist"

if not exist "%ENTRY_POINT%" (
    echo [ERROR] main.py was not found in:
    echo         %CD%
    goto :fail
)

if not exist "%ASSETS_DIR%\portugal_z12.pmtiles" (
    echo [ERROR] The offline map was not found in:
    echo         %ASSETS_DIR%
    goto :fail
)

if not exist "%PYTHON_EXE%" (
    echo [1/4] Creating the Python virtual environment...
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] The Python launcher ^(py.exe^) is not installed or is not in PATH.
        echo         Install Python 3.12 or newer from https://www.python.org/
        goto :fail
    )
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 goto :fail
) else (
    echo [1/4] Reusing the existing virtual environment.
)

echo [2/4] Installing application and build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PYTHON_EXE%" -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto :fail
"%PYTHON_EXE%" -m pip install "pyinstaller>=6.10"
if errorlevel 1 goto :fail

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if errorlevel 1 goto :fail

echo [3/4] Building the Windows application...
"%PYTHON_EXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --icon "%ASSETS_DIR%\helink_icon.ico" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%\pyinstaller" ^
    --specpath "%BUILD_DIR%" ^
    --add-data "%ASSETS_DIR%;helink\assets" ^
    "%ENTRY_POINT%"
if errorlevel 1 goto :fail

if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo [ERROR] PyInstaller finished without producing the expected executable.
    goto :fail
)

echo [4/4] Build completed successfully.
echo.
echo Executable:
echo   %DIST_DIR%\%APP_NAME%.exe
echo.
echo You can distribute this EXE file by itself.
echo No additional folder is required.
popd
pause
exit /b 0

:fail
echo.
echo [ERROR] HELINK could not be built. Review the messages above.
popd
pause
exit /b 1
