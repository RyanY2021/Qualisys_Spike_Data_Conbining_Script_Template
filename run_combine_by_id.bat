@echo off
setlocal

python combine_by_id.py %*

if errorlevel 1 (
  echo.
  echo combine_by_id failed with exit code %errorlevel%.
)

endlocal
