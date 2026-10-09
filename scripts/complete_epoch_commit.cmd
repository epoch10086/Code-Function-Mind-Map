@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0.." || exit /b 1
for /f "delims=" %%B in ('git branch --show-current') do set "CODE_MAP_BRANCH=%%B"
for /f "delims=" %%H in ('git rev-parse HEAD') do set "CODE_MAP_HEAD=%%H"
if not "%CODE_MAP_BRANCH%"=="Epoch" goto blocked
if not "%CODE_MAP_HEAD%"=="15db67b4554234511abf7228e0c4de9963062eb2" goto blocked
git diff --cached --quiet
if errorlevel 1 goto blocked
if not exist ".artifacts\epoch-implementation.patch" goto blocked
git apply --cached --check ".artifacts\epoch-implementation.patch"
if errorlevel 1 goto failed
git apply --cached ".artifacts\epoch-implementation.patch"
if errorlevel 1 goto failed
git commit -m "feat: add portable multilingual code function mind map skill"
if errorlevel 1 goto failed
echo [DONE] Reviewed implementation committed locally on Epoch.
popd
pause
exit /b 0
:blocked
echo [BLOCKED] Requires Epoch at the agreed baseline, an empty index and the delivery patch.
echo No changes were staged.
popd
pause
exit /b 1
:failed
echo [FAILED] Read the Git error above. No push was performed.
echo If commit failed after staging, the reviewed patch remains staged for inspection.
popd
pause
exit /b 1
