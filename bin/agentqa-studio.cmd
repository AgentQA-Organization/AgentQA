@echo off
rem agentqa-studio — launch the AgentQA Studio dashboard against the current app repo.
rem
rem Install on PATH: add this repo's bin\ folder itself to your PATH (System
rem Properties > Environment Variables, or `setx PATH "%PATH%;<repo>\bin"` in a
rem terminal you then restart). Do not copy or symlink this file elsewhere — it
rem locates studio-launch.py relative to its own folder, so it only works from
rem inside this repo's bin\.
rem
rem Env: AGENTQA_STUDIO_PORT overrides the default port (7332).
rem
rem All real logic (repo/port/memory-scripts resolution, spawning the daemon)
rem lives in studio-launch.py --foreground — this file only locates Python and
rem forwards to it, so nothing is duplicated in batch script.
python "%~dp0..\skills\agentqa-studio\scripts\studio-launch.py" --foreground "%CD%\."
