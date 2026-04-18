@echo off
REM setup_env.bat - Creates conda environment from environment.yml
REM Usage: Double-click or run from anywhere to launch project environment

REM Get the directory where this .bat file lives
set PROJECT_DIR=%~dp0
REM Remove trailing backslash
set PROJECT_DIR=%PROJECT_DIR:~0,-1%

REM Get the name of the folder where this .bat file lives
for %%I in ("%PROJECT_DIR%") do set ENV_NAME=%%~nI

REM Initialize conda in this shell session
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" "%USERPROFILE%\miniconda3"

REM Check if the environment already exists in conda's list
conda env list | findstr /C:"%ENV_NAME%" >nul 2>&1
if %errorlevel%==0 (
    echo Environment "%ENV_NAME%" already exists. Skipping creation...
) else (
    echo Environment "%ENV_NAME%" not found. Creating from environment.yml...
    conda env create --name %ENV_NAME% --file "%PROJECT_DIR%\environment.yml"
)

REM Change to the project directory
cd /d "%PROJECT_DIR%"

REM Activate the project environment and keep the prompt open
cmd /k "call conda activate %ENV_NAME% && echo. && echo Environment "%ENV_NAME%" is active. && echo Working directory: %CD%"
