@echo off
cd /d "%~dp0"
py -m pip install --upgrade edge-tts pydub
py tts_server.py
pause
