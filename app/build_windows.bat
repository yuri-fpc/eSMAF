@echo off
title eSMAF build
cd /d "%~dp0"

echo.
echo   eSMAF build
echo   --------------------------------------------------------------
echo.
echo   Working folder: %~dp0
echo.

where py >nul 2>&1 && goto runpy
where python >nul 2>&1 && goto runpython
where python3 >nul 2>&1 && goto runpython3
goto nopython

:runpy
py -3 "%~dp0build.py" %*
if errorlevel 100 goto runpython
goto done

:runpython
python "%~dp0build.py" %*
if errorlevel 9009 goto nopython
goto done

:runpython3
python3 "%~dp0build.py" %*
goto done

:nopython
echo   Python was not found on this computer.
echo.
echo   Install Python 3.10 or newer from
echo     https://www.python.org/downloads/windows/
echo.
echo   During setup, tick the box that says
echo     "Add python.exe to PATH"
echo.
echo   Then run this file again.
echo.

:done
echo.
echo   Press any key to close this window.
pause >nul
