@echo off
chcp 65001 >nul
echo ========================================
echo   校园数据导航Agent - 启动脚本
echo ========================================
echo.

REM 自动查找 Python
set PYTHON=python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 设置 API Key（替换为你的真实 Key）
if "%OPENAI_API_KEY%"=="" (
    echo [提示] 请设置 OPENAI_API_KEY 环境变量
    echo   或复制 .env.example 为 .env 并填入真实 Key
)

echo [1/2] 检查数据文件...
if not exist "data\courses.csv" (
    echo   生成模拟数据...
    %PYTHON% backend\data_generator.py
) else (
    echo   数据文件已存在
)

echo [2/2] 启动Agent服务...
echo   后端地址: http://localhost:8000
echo   前端地址: http://localhost:8000/static/index.html
echo   接口文档: http://localhost:8000/docs
echo.
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

%PYTHON% backend\main.py
