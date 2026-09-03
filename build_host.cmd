@echo off
set hereOrig=%~dp0
set here=%hereOrig%
if #%hereOrig:~-1%# == #\# set here=%hereOrig:~0,-1%
if "%PYTHON32%" == "" (
	for /f "usebackq delims=" %%P in (`py -3.13-32 -c "import sys; print(sys.executable)"`) do set PYTHON32=%%P
)
set UV_PROJECT_ENVIRONMENT=%here%\.venv32
call uv run --group host-build --python "%PYTHON32%" --directory "%here%" PyInstaller --onedir --noconsole --name eloquence_host32 host_eloquence32.py
if ERRORLEVEL 1 exit /b %ERRORLEVEL%
if exist addon\synthDrivers\eloquence_host32 rmdir /S /Q addon\synthDrivers\eloquence_host32
xcopy /E /I /Y dist\eloquence_host32 addon\synthDrivers\eloquence_host32 >nul
if ERRORLEVEL 1 exit /b %ERRORLEVEL%
if exist addon\synthDrivers\eloquence_host32.exe del /Q addon\synthDrivers\eloquence_host32.exe
