@echo off
chcp 65001 > nul
echo ================================
echo  衡水学院校园数据导航智能Agent
echo ================================
echo.

REM 查找 Python（优先用虚拟环境）
set PYTHON_EXE=
if exist "%~dp0backend\venv\Scripts\python.exe" (
    set PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe
) else if exist "%~dp0backend\env\Scripts\python.exe" (
    set PYTHON_EXE=%~dp0backend\env\Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

echo [+] 使用 Python：%PYTHON_EXE%
echo.

REM 检查8000端口是否被占用
netstat -ano | findstr ":8000" > nul 2>&1
if %errorlevel% == 0 (
    echo [✓] 后端已在运行，直接打开前端...
    goto :open
)

echo [+] 启动后端服务...
cd /d "%~dp0backend"
start /min "" "%PYTHON_EXE%" main.py

echo [+] 等待服务启动...
timeout /t 6 > nul

:open
echo [+] 打开浏览器...
start http://localhost:8000/

echo.
echo [✓] 完成！浏览器已打开
echo     如页面显示"拒绝连接"，请等待几秒后刷新页面
echo.
pause
