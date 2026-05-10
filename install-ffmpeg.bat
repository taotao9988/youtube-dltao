@echo off
chcp 65001 > nul
echo ================================================
echo       自动安装 ffmpeg（YouTube 高清下载必需）
echo ================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "ZIP_FILE=%SCRIPT_DIR%ffmpeg.zip"
set "TEMP_DIR=%SCRIPT_DIR%ffmpeg_temp"
set "TARGET_DIR=%SCRIPT_DIR%ffmpeg"

:: 检查是否已安装
if exist "%TARGET_DIR%\bin\ffmpeg.exe" (
    echo [OK] ffmpeg 已安装，无需重复操作。
    echo 路径: %TARGET_DIR%\bin\ffmpeg.exe
    pause
    exit /b 0
)

:: 用 PowerShell 下载
echo [1/5] 正在下载 ffmpeg（约 80MB，请稍候）...
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%ZIP_FILE%' -ErrorAction Stop}"
if not exist "%ZIP_FILE%" (
    echo [错误] 下载失败，请检查网络连接后重试。
    pause
    exit /b 1
)
echo [OK] 下载完成。

:: 解压
echo.
echo [2/5] 正在解压...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
powershell -Command "& {Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%TEMP_DIR%' -Force}"
del "%ZIP_FILE%"
if not exist "%TEMP_DIR%" (
    echo [错误] 解压失败。
    pause
    exit /b 1
)
echo [OK] 解压完成。

:: 查找 ffmpeg.exe
echo.
echo [3/5] 查找 ffmpeg.exe...
set "FFMPEG_SRC="
for /r "%TEMP_DIR%" %%i in (ffmpeg.exe) do (
    set "FFMPEG_SRC=%%i"
    goto :found_ffmpeg
)
:found_ffmpeg
if "%FFMPEG_SRC%"=="" (
    echo [错误] 未找到 ffmpeg.exe
    pause
    exit /b 1
)
echo [OK] 找到: %FFMPEG_SRC%

:: 复制到目标目录
echo.
echo [4/5] 安装到项目目录...
if not exist "%TARGET_DIR%\bin" mkdir "%TARGET_DIR%\bin"
copy /y "%FFMPEG_SRC%" "%TARGET_DIR%\bin\ffmpeg.exe" >nul
if not exist "%TARGET_DIR%\bin\ffmpeg.exe" (
    echo [错误] 复制失败。
    pause
    exit /b 1
)
echo [OK] 已安装到: %TARGET_DIR%\bin\ffmpeg.exe

:: 清理临时文件
rmdir /s /q "%TEMP_DIR%"

:: 添加到 PATH（当前用户）
echo.
echo [5/5] 添加到 PATH...
setx PATH "%PATH%;%TARGET_DIR%\bin" >nul 2>&1
echo [OK] 已添加到 PATH（重启后生效）。

echo.
echo ================================================
echo    ffmpeg 安装完成！
echo ================================================
echo.
echo  ffmpeg 路径: %TARGET_DIR%\bin\ffmpeg.exe
echo.
echo  请重新打开「启动YouTube下载器.bat」
echo  即可下载 1080P / 4K 高清视频！
echo.
pause
