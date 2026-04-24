@echo off

echo Building upsampler DLLs...

REM --- 64-bit build ---
set PATH=C:\msys64\mingw64\bin;%PATH%
if not exist C:\msys64\mingw64\bin\gcc.exe (
    echo MinGW64 not found!
    exit /b 1
)

echo Building 64-bit...
gcc -shared -static-libgcc -o upsampler64.dll upsampler.c
if %errorlevel% neq 0 exit /b %errorlevel%

REM --- 32-bit build ---
set PATH=C:\msys64\mingw32\bin;%PATH%
if not exist C:\msys64\mingw32\bin\gcc.exe (
    echo MinGW32 not found!
    exit /b 1
)

echo Building 32-bit...
gcc -shared -static-libgcc -o upsampler32.dll upsampler.c
if %errorlevel% neq 0 exit /b %errorlevel%

echo Copying DLLs...

copy /Y upsampler64.dll addon\synthDrivers\
copy /Y upsampler32.dll addon\synthDrivers\

echo Done!
