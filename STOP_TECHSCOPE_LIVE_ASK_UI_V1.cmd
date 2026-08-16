@echo off
docker.exe --context desktop-linux rm -f techscope-live-ui-proxy >nul 2>&1
echo LIVE_UI_PROXY=STOPPED
