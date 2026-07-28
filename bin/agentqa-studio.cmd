@echo off
rem agentqa-studio — launch the AgentQA Studio dashboard against the current app repo.
rem
rem Install on PATH: copy or link this file into a folder already on your PATH,
rem e.g. a personal %USERPROFILE%\bin you've added to PATH yourself.
rem
rem Env: AGENTQA_STUDIO_PORT overrides the default port (7332).
rem
rem All real logic (repo/port/memory-scripts resolution, spawning the daemon)
rem lives in studio-launch.py --foreground — this file only locates Python and
rem forwards to it, so nothing is duplicated in batch script.
python "%~dp0..\skills\agentqa-studio\scripts\studio-launch.py" --foreground "%CD%"
