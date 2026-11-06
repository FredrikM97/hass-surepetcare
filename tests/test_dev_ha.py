import select
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
import yaml
from aiohttp import web

from scripts import dev_ha


def test_prepare_config(tmp_path: Path) -> None:
    config = tmp_path / "ha"

    dev_ha.prepare_config(config)

    assert (config / "custom_components").is_symlink()
    assert (config / "custom_components").resolve() == dev_ha.ROOT / "custom_components"
    assert (config / "configuration.yaml").read_text() == dev_ha.CONFIGURATION
    settings = yaml.safe_load(dev_ha.CONFIGURATION)
    assert "default_config" in settings
    assert settings["automation"] == []
    assert settings["script"] == {}
    assert settings["scene"] == []


def test_prepare_config_preserves_existing_configuration(tmp_path: Path) -> None:
    dev_ha.prepare_config(tmp_path)
    configuration = tmp_path / "configuration.yaml"
    configuration.write_text("http:\n  server_port: 8124\n")

    dev_ha.prepare_config(tmp_path)

    assert configuration.read_text() == "http:\n  server_port: 8124\n"


def test_enable_local_login_preserves_settings(tmp_path: Path) -> None:
    dev_ha.prepare_config(tmp_path)
    configuration = tmp_path / "configuration.yaml"
    configuration.write_text(
        "homeassistant:\n  name: Custom\nhttp:\n  server_port: 8124\n"
    )

    assert dev_ha.enable_local_login(tmp_path) == "http://127.0.0.1:8124"
    settings = yaml.safe_load(configuration.read_text())
    assert settings["homeassistant"]["name"] == "Custom"
    assert settings["http"]["server_port"] == 8124
    assert settings["homeassistant"]["auth_providers"] == [
        dev_ha.LOCAL_AUTH,
        {"type": "homeassistant"},
    ]
    previous = configuration.read_text()
    dev_ha.enable_local_login(tmp_path)
    assert configuration.read_text() == previous


def test_disable_local_login_removes_only_development_provider(tmp_path: Path) -> None:
    dev_ha.prepare_config(tmp_path)
    dev_ha.enable_local_login(tmp_path)
    configuration = tmp_path / "configuration.yaml"
    settings = yaml.safe_load(configuration.read_text())
    other = {"type": "command_line", "command": "/usr/local/bin/authenticate"}
    settings["homeassistant"]["auth_providers"].append(other)
    configuration.write_text(yaml.safe_dump(settings))

    assert dev_ha.enable_local_login(tmp_path, enabled=False) is None
    updated = yaml.safe_load(configuration.read_text())
    assert updated["homeassistant"]["auth_providers"] == [
        {"type": "homeassistant"},
        other,
    ]
    assert updated["homeassistant"]["name"] == settings["homeassistant"]["name"]
    previous = configuration.read_text()
    dev_ha.enable_local_login(tmp_path, enabled=False)
    assert configuration.read_text() == previous


def test_disable_local_login_preserves_custom_auth(tmp_path: Path) -> None:
    dev_ha.prepare_config(tmp_path)
    path = tmp_path / "configuration.yaml"
    configuration = "homeassistant:\n  auth_providers:\n    - type: trusted_networks\n"
    path.write_text(configuration)

    assert dev_ha.enable_local_login(tmp_path, enabled=False) is None
    assert path.read_text() == configuration


@pytest.mark.parametrize(
    "configuration",
    [
        "homeassistant:\n  auth_providers:\n    - type: trusted_networks\n",
        "http:\n  server_port: 0\n",
        "http:\n  server_port: true\n",
        "http:\n  ssl_certificate: certificate.pem\n",
        "homeassistant: invalid\n",
    ],
)
def test_enable_local_login_rejects_conflicting_settings(
    tmp_path: Path, configuration: str
) -> None:
    dev_ha.prepare_config(tmp_path)
    path = tmp_path / "configuration.yaml"
    path.write_text(configuration)

    with pytest.raises((TypeError, ValueError)):
        dev_ha.enable_local_login(tmp_path)

    assert path.read_text() == configuration


@pytest.mark.parametrize(
    "completed", [[], ["user"], ["user", "core_config", "analytics", "integration"]]
)
async def test_skip_onboarding(completed: list[str]) -> None:
    done = set(completed)
    requests = []

    async def handle(request: web.Request) -> web.Response:
        requests.append(request.path)
        if request.path == "/api/onboarding":
            if len(done) == 4:
                raise web.HTTPNotFound
            return web.json_response(
                [
                    {"step": step, "done": step in done}
                    for step in ("user", "core_config", "analytics", "integration")
                ]
            )
        if request.path == "/api/onboarding/users":
            body = await request.json()
            assert body["username"] == "dev"
            assert len(body["password"]) >= 32
            done.add("user")
            return web.json_response({"auth_code": "code"})
        if request.path == "/auth/login_flow":
            assert (await request.json())["handler"] == ["trusted_networks", None]
            return web.json_response({"type": "create_entry", "result": "code"})
        if request.path == "/auth/token":
            assert (await request.post())["code"] == "code"
            return web.json_response({"access_token": "test-token"})
        if request.path == "/api/websocket":
            websocket = web.WebSocketResponse()
            await websocket.prepare(request)
            await websocket.send_json({"type": "auth_required"})
            assert (await websocket.receive_json())["access_token"] == "test-token"
            await websocket.send_json({"type": "auth_ok"})
            async for message in websocket:
                body = message.json()
                result = (
                    {"pending": None}
                    if body["type"] == "http/config"
                    else {"state": "RUNNING", "components": ["default_config"]}
                )
                await websocket.send_json(
                    {"id": body["id"], "success": True, "result": result}
                )
            return websocket
        if request.path == "/":
            return web.Response(text="frontend")
        assert request.headers["Authorization"] == "Bearer test-token"
        name = request.path.rsplit("/", 1)[1]
        assert name not in done
        done.add(name)
        return web.json_response({})

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        host, port = runner.addresses[0]
        await dev_ha.skip_onboarding(
            f"http://{host}:{port}", Mock(poll=Mock(return_value=None))
        )
        assert done == {"user", "core_config", "analytics", "integration"}
        assert ("/api/onboarding/users" in requests) == ("user" not in completed)
    finally:
        await runner.cleanup()


async def test_skip_onboarding_detects_exited_process() -> None:
    with pytest.raises(RuntimeError, match="exited"):
        await dev_ha.skip_onboarding(
            "http://127.0.0.1:8123", Mock(poll=Mock(return_value=1))
        )


async def test_skip_onboarding_startup_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.get = Mock(side_effect=aiohttp.ClientConnectionError("Not ready"))
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(dev_ha.aiohttp, "ClientSession", Mock(return_value=context))
    monkeypatch.setattr(dev_ha, "time", Mock(monotonic=Mock(side_effect=[0, 120])))

    with pytest.raises(TimeoutError, match="120 seconds"):
        await dev_ha.skip_onboarding(
            "http://127.0.0.1:8123", Mock(poll=Mock(return_value=None))
        )


@pytest.mark.parametrize("pending", [None, {"error": None}, {"error": "not_promoted"}])
async def test_readiness_waits_for_running_and_confirms_pending_http(
    pending: dict | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    websocket = AsyncMock()
    promoted = pending is not None and not pending.get("error")
    replies = [
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {"id": 1, "success": True, "result": {"pending": pending}},
    ]
    if promoted:
        replies.append({"id": 2, "success": True})
    replies.extend(
        [
            {"id": 3, "success": True, "result": {"state": "STARTING"}},
            {
                "id": 4,
                "success": True,
                "result": {"state": "RUNNING", "components": ["default_config"]},
            },
        ]
    )
    websocket.receive_json.side_effect = replies
    context = AsyncMock()
    context.__aenter__.return_value = websocket
    session = Mock()
    session.ws_connect.return_value = context
    session.get.return_value = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr(dev_ha.asyncio, "sleep", sleep)

    await dev_ha.wait_for_ready(
        "http://127.0.0.1:8123",
        session,
        "test-token",
        Mock(poll=Mock(return_value=None)),
    )

    sleep.assert_awaited_once_with(0.5)
    commands = [
        call.args[0].get("type") for call in websocket.send_json.await_args_list
    ]
    assert ("http/config/promote" in commands) == promoted
    assert commands.count("get_config") == 2
    session.get.assert_called_once_with("http://127.0.0.1:8123/")


async def test_readiness_rejects_failed_authentication() -> None:
    websocket = AsyncMock()
    websocket.receive_json.side_effect = [
        {"type": "auth_required"},
        {"type": "auth_invalid"},
    ]
    context = AsyncMock()
    context.__aenter__.return_value = websocket
    session = Mock()
    session.ws_connect.return_value = context
    with pytest.raises(RuntimeError, match="authentication failed"):
        await dev_ha.wait_for_ready(
            "http://127.0.0.1:8123", session, "test-token", Mock()
        )


def test_main_cleans_up_after_onboarding_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = Mock()
    bootstrap = AsyncMock(side_effect=aiohttp.ClientConnectionError("Connection lost"))
    monkeypatch.setattr(
        sys, "argv", ["dev_ha.py", "--config", str(tmp_path), "--skip-onboarding"]
    )
    monkeypatch.setattr(dev_ha.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(dev_ha, "skip_onboarding", bootstrap)
    monkeypatch.setattr(dev_ha, "LOCK", tmp_path / "runner.lock")

    with pytest.raises(SystemExit) as error:
        dev_ha.main()

    assert error.value.code == 1
    bootstrap.assert_awaited_once_with("http://127.0.0.1:8123", process)
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=25)


@pytest.mark.parametrize("symlink", [False, True])
def test_prepare_config_rejects_conflicting_components(
    tmp_path: Path, symlink: bool
) -> None:
    installed = tmp_path / "custom_components"
    if symlink:
        installed.symlink_to(tmp_path / "other", target_is_directory=True)
    else:
        installed.mkdir()

    with pytest.raises(ValueError, match="another integration|refusing to replace"):
        dev_ha.prepare_config(tmp_path)


@pytest.mark.parametrize("results", [[0], [100, 0], [1]])
@pytest.mark.parametrize("automatic", [True, False])
def test_main_launches_homeassistant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results: list[int], automatic: bool
) -> None:
    processes = [Mock() for _ in results]
    for process, result in zip(processes, results, strict=True):
        process.wait.return_value = result
    launch = Mock(side_effect=processes)
    arguments = ["dev_ha.py", "--config", str(tmp_path)]
    if not automatic:
        arguments.append("--no-skip-onboarding")
        dev_ha.prepare_config(tmp_path)
        dev_ha.enable_local_login(tmp_path)
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setattr(dev_ha.subprocess, "Popen", launch)
    monkeypatch.setattr(dev_ha, "LOCK", tmp_path / "runner.lock")
    bootstrap = AsyncMock()
    monkeypatch.setattr(dev_ha, "skip_onboarding", bootstrap)

    assert dev_ha.main() == results[-1]

    assert launch.call_count == len(results)
    assert bootstrap.await_count == (len(results) if automatic else 0)
    if automatic:
        bootstrap.assert_awaited_with("http://127.0.0.1:8123", processes[-1])
    providers = yaml.safe_load((tmp_path / "configuration.yaml").read_text())[
        "homeassistant"
    ]["auth_providers"]
    assert (dev_ha.LOCAL_AUTH in providers) == automatic
    launch.assert_called_with(
        [
            sys.executable,
            "-m",
            "homeassistant",
            "--config",
            str(tmp_path),
            "--log-no-color",
        ],
    )


def test_main_stops_child_before_releasing_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = Mock()
    process.wait.side_effect = [KeyboardInterrupt, 0]
    monkeypatch.setattr(sys, "argv", ["dev_ha.py", "--config", str(tmp_path)])
    monkeypatch.setattr(dev_ha.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(dev_ha, "LOCK", tmp_path / "runner.lock")
    monkeypatch.setattr(dev_ha, "skip_onboarding", AsyncMock())

    assert dev_ha.main() == 130

    process.terminate.assert_called_once()
    process.wait.assert_called_with(timeout=25)


def test_main_kills_only_its_unresponsive_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = Mock()
    process.wait.side_effect = [
        KeyboardInterrupt,
        subprocess.TimeoutExpired("homeassistant", 25),
        0,
    ]
    monkeypatch.setattr(sys, "argv", ["dev_ha.py", "--config", str(tmp_path)])
    monkeypatch.setattr(dev_ha.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(dev_ha, "LOCK", tmp_path / "runner.lock")
    monkeypatch.setattr(dev_ha, "skip_onboarding", AsyncMock())

    assert dev_ha.main() == 130

    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 3


@pytest.mark.parametrize("stale_identity", [False, True])
def test_running_instance_replaces_only_verified_owner(
    tmp_path: Path, stale_identity: bool
) -> None:
    lock = tmp_path / "runner.lock"
    code = """\
import sys
import time
from pathlib import Path
from scripts.dev_ha import running_instance

try:
    with running_instance(Path(sys.argv[1])):
        print("ready", flush=True)
        time.sleep(60)
except KeyboardInterrupt:
    sys.exit(130)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(lock)],
        cwd=dev_ha.ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert select.select([process.stdout], [], [], 5)[0]
        assert process.stdout.readline().strip() == "ready"
        if stale_identity:
            lock.write_text(f"{process.pid} invalid-start-time\n")
            with (
                pytest.raises(ValueError, match="identity has changed"),
                dev_ha.running_instance(lock),
            ):
                pytest.fail("Should not replace an unverified owner")
            assert process.poll() is None
        else:
            with dev_ha.running_instance(lock):
                assert process.wait(timeout=5) == 130
            # The lock can be reused even though its previous PID record remains.
            with dev_ha.running_instance(lock):
                pass
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
