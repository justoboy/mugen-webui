git pull
git submodule update --remote
echo Update Complete!
choice /C:YN /M:"Start Webui?"
if errorlevel 2 (
    break
) else if errorlevel 1 (
    call start.bat
)