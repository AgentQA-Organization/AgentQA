import socket
import sys
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


launch = _load("studio-launch.py")


def _listening_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s


def test_port_open_true_when_listening():
    s = _listening_socket()
    try:
        port = s.getsockname()[1]
        assert launch.port_open(port) is True
    finally:
        s.close()


def test_port_open_false_when_nothing_listening():
    s = _listening_socket()
    port = s.getsockname()[1]
    s.close()   # port now free
    assert launch.port_open(port) is False


def test_find_memory_scripts_matches_first_candidate_with_marker(tmp_path):
    studio_root = tmp_path / "studio_root"
    write_test_scripts = studio_root / "skills" / "agentqa-write-test" / "scripts"
    write_test_scripts.mkdir(parents=True)
    (write_test_scripts / "memory-index.py").write_text("# marker\n")
    found = launch.find_memory_scripts(tmp_path / "some-repo", studio_root=studio_root)
    assert found == write_test_scripts


def test_find_memory_scripts_none_when_no_candidate_has_marker(tmp_path):
    found = launch.find_memory_scripts(tmp_path / "some-repo", studio_root=tmp_path / "nowhere")
    assert found is None


def test_server_argv_without_memory_scripts():
    argv = launch.server_argv("/repo", 7332, None)
    assert argv == [sys.executable, "-m", "studio.server",
                     "--repo", "/repo", "--port", "7332", "--open"]


def test_server_argv_with_memory_scripts():
    argv = launch.server_argv("/repo", 7332, Path("/mem/scripts"))
    assert argv[-2:] == ["--memory-scripts", "/mem/scripts"]


def test_env_prepends_studio_root_to_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/existing")
    env = launch._env()
    assert env["PYTHONPATH"] == str(launch.STUDIO_ROOT) + launch.os.pathsep + "/existing"


def test_env_sets_pythonpath_when_unset(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = launch._env()
    assert env["PYTHONPATH"] == str(launch.STUDIO_ROOT)


def test_popen_kwargs_windows(monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "win32")
    kwargs = launch._popen_kwargs("LOGFILE")
    assert kwargs["creationflags"] == launch._CREATE_NEW_PROCESS_GROUP | launch._DETACHED_PROCESS
    assert "start_new_session" not in kwargs
    assert kwargs["stdout"] == "LOGFILE" and kwargs["stderr"] == "LOGFILE"


def test_popen_kwargs_posix(monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "darwin")
    kwargs = launch._popen_kwargs("LOGFILE")
    assert kwargs["start_new_session"] is True
    assert "creationflags" not in kwargs


def test_launch_detached_reports_started_once_port_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    calls = []
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    seq = iter([False, False, True])
    monkeypatch.setattr(launch, "port_open", lambda port, host="127.0.0.1": next(seq))
    monkeypatch.setattr(launch, "POLL_INTERVAL", 0.01)
    result = launch.launch_detached("/repo", 7332, None)
    assert result == "started"
    assert len(calls) == 1
    call_args, call_kwargs = calls[0]
    assert call_args[0] == launch.server_argv("/repo", 7332, None)


def test_launch_detached_reports_timeout_when_port_never_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(launch, "port_open", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(launch, "POLL_TIMEOUT", 0.05)
    monkeypatch.setattr(launch, "POLL_INTERVAL", 0.01)
    result = launch.launch_detached("/repo", 7332, None)
    assert result.startswith("started (port not open after")


def test_main_already_running_does_not_spawn(monkeypatch, tmp_path, capsys):
    s = _listening_socket()
    try:
        port = s.getsockname()[1]

        def _boom(*a, **k):
            raise AssertionError("Popen must not be called when the port is already open")
        monkeypatch.setattr(launch.subprocess, "Popen", _boom)

        rc = launch.main([str(tmp_path), "--port", str(port)])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "already-running"
    finally:
        s.close()


def test_main_foreground_runs_server_in_foreground(monkeypatch, tmp_path):
    # find_memory_scripts would otherwise pick up this real repo's actual
    # skills/agentqa-write-test/scripts (it exists on disk) regardless of the
    # tmp_path "repo" argument, since that candidate is checked first and
    # doesn't depend on `repo` at all -- stub it so this test's expected argv
    # doesn't depend on incidental repo state.
    monkeypatch.setattr(launch, "find_memory_scripts", lambda repo, studio_root=launch.STUDIO_ROOT: None)
    captured = {}

    class FakeCompleted:
        returncode = 42

    def fake_run(argv, env=None):
        captured["argv"] = argv
        return FakeCompleted()

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    rc = launch.main([str(tmp_path), "--port", "7332", "--foreground"])
    assert rc == 42
    assert captured["argv"] == [sys.executable, "-m", "studio.server",
                                 "--repo", str(tmp_path), "--port", "7332", "--open"]


def test_main_port_defaults_to_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(launch, "find_memory_scripts", lambda repo, studio_root=launch.STUDIO_ROOT: None)
    monkeypatch.setenv("AGENTQA_STUDIO_PORT", "9999")
    captured = {}

    def fake_run(argv, env=None):
        captured["argv"] = argv

        class FakeCompleted:
            returncode = 0
        return FakeCompleted()

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    launch.main([str(tmp_path), "--foreground"])
    assert "9999" in captured["argv"]


def test_windows_cmd_shim_delegates_to_studio_launch_foreground():
    cmd_path = SCRIPTS.parent.parent.parent / "bin" / "agentqa-studio.cmd"
    text = cmd_path.read_text()
    assert "studio-launch.py" in text
    assert "--foreground" in text
