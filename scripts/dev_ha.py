"""Run Home Assistant against the local integration."""

import argparse
import asyncio
import fcntl
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

import aiohttp
import yaml

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / ".ha-runner.lock"
CONFIGURATION = """\
homeassistant:
  name: SurePetcare Development

default_config:
automation: []
script: {}
scene: []
http:
  server_host: 0.0.0.0
  server_port: 8123
logger:
  default: warning
  logs:
    custom_components.surepcha: debug
    surepcio: debug
"""
LOCAL_AUTH = {
    "type": "trusted_networks",
    "trusted_networks": ["127.0.0.1/32", "::1/128"],
    "allow_bypass_login": True,
}


def interrupt(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


@contextmanager
def running_instance(lock_path: Path) -> Iterator[None]:
    """Keep ownership until HA stops, and signal only a verified lock owner."""
    previous_handler = signal.signal(signal.SIGTERM, interrupt)
    try:
        with lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.seek(0)
                owner = lock.read().split()
                if len(owner) != 2 or not owner[0].isdigit():
                    raise ValueError("Previous runner has no valid process identity")
                pid = int(owner[0])
                # A pidfd prevents PID reuse from redirecting the shutdown signal.
                try:
                    descriptor = os.pidfd_open(pid)
                except ProcessLookupError:
                    descriptor = None
                if descriptor is not None:
                    try:
                        identity = (
                            Path(f"/proc/{pid}/stat")
                            .read_text()
                            .rsplit(")", 1)[1]
                            .split()[19]
                        )
                        if identity != owner[1]:
                            raise ValueError(
                                "Previous runner process identity has changed"
                            )
                        print(
                            f"Stopping previous local HA runner (PID {pid})...",
                            flush=True,
                        )
                        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                    finally:
                        os.close(descriptor)
                deadline = time.monotonic() + 30
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Previous runner did not stop within 30 seconds"
                            )
                        time.sleep(0.1)

            identity = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
            lock.seek(0)
            lock.truncate()
            lock.write(f"{os.getpid()} {identity}\n")
            lock.flush()
            yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


def prepare_config(config: Path) -> None:
    config.mkdir(parents=True, exist_ok=True, mode=0o700)
    installed = config / "custom_components"
    source = ROOT / "custom_components"
    if installed.is_symlink():
        if installed.resolve() != source:
            raise ValueError(f"{installed} points to another integration directory")
    elif installed.exists():
        raise ValueError(f"{installed} already exists; refusing to replace it")
    else:
        installed.symlink_to(source, target_is_directory=True)

    configuration = config / "configuration.yaml"
    if not configuration.exists():
        configuration.write_text(CONFIGURATION, encoding="utf-8")


def enable_local_login(config: Path, *, enabled: bool = True) -> str | None:
    configuration = config / "configuration.yaml"
    settings = yaml.safe_load(configuration.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise TypeError("Development configuration must be a YAML mapping")
    homeassistant = settings.setdefault("homeassistant", {})
    if not isinstance(homeassistant, dict):
        raise TypeError("homeassistant configuration must be a mapping")
    providers = homeassistant.get("auth_providers", [{"type": "homeassistant"}])
    if not isinstance(providers, list) or not all(
        isinstance(provider, dict) for provider in providers
    ):
        raise ValueError("auth_providers must be a list of mappings")
    trusted = [
        provider for provider in providers if provider.get("type") == "trusted_networks"
    ]
    if not enabled:
        if LOCAL_AUTH in providers:
            homeassistant["auth_providers"] = [
                provider for provider in providers if provider != LOCAL_AUTH
            ] or [{"type": "homeassistant"}]
            configuration.write_text(
                yaml.safe_dump(settings, sort_keys=False), encoding="utf-8"
            )
        return None
    if trusted and trusted != [LOCAL_AUTH]:
        raise ValueError("Refusing to replace an existing trusted_networks provider")
    http = settings.get("http")
    if http is None:
        http = {}
    if not isinstance(http, dict):
        raise TypeError("http configuration must be a mapping")
    if http.get("ssl_certificate") or http.get("server_host") not in (
        None,
        "0.0.0.0",
        "127.0.0.1",
    ):
        raise ValueError("Automatic onboarding requires HTTP reachable on 127.0.0.1")
    port = http.get("server_port", 8123)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("http.server_port must be an integer between 1 and 65535")
    if not trusted:
        homeassistant["auth_providers"] = [LOCAL_AUTH, *providers]
        configuration.write_text(
            yaml.safe_dump(settings, sort_keys=False), encoding="utf-8"
        )
    return f"http://127.0.0.1:{port}"


async def skip_onboarding(base: str, process: subprocess.Popen[bytes]) -> None:
    client_id = f"{base}/"
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15), raise_for_status=True
    ) as session:
        deadline = time.monotonic() + 120
        print("Waiting for HA to complete development onboarding...", flush=True)
        while True:
            if process.poll() is not None:
                raise RuntimeError("Home Assistant exited before onboarding was ready")
            try:
                async with session.get(
                    f"{base}/api/onboarding", raise_for_status=False
                ) as response:
                    if response.status == 404:
                        steps = []
                    else:
                        response.raise_for_status()
                        steps = await response.json()
                break
            except aiohttp.ClientConnectionError, TimeoutError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Home Assistant did not start within 120 seconds"
                    )
                await asyncio.sleep(0.5)

        steps = [step for step in steps if not step["done"]]
        if any(step["step"] == "user" for step in steps):
            async with session.post(
                f"{base}/api/onboarding/users",
                json={
                    "name": "Developer",
                    "username": "dev",
                    "password": secrets.token_urlsafe(32),
                    "client_id": client_id,
                    "language": "en",
                },
            ) as response:
                code = (await response.json())["auth_code"]
        else:
            async with session.post(
                f"{base}/auth/login_flow",
                json={
                    "client_id": client_id,
                    "redirect_uri": client_id,
                    "handler": ["trusted_networks", None],
                },
            ) as response:
                flow = await response.json()
            if flow["type"] != "create_entry":
                raise RuntimeError(
                    "Passwordless development login requires exactly one active user"
                )
            code = flow["result"]

        async with session.post(
            f"{base}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
            },
        ) as response:
            access = (await response.json())["access_token"]
        if steps:
            for step in steps:
                if step["done"] or step["step"] == "user":
                    continue
                name = step["step"]
                if name not in ("core_config", "analytics", "integration"):
                    raise RuntimeError(f"Unsupported onboarding step: {name}")
                body = (
                    {"client_id": client_id, "redirect_uri": client_id}
                    if name == "integration"
                    else {}
                )
                async with session.post(
                    f"{base}/api/onboarding/{name}",
                    json=body,
                    headers={"Authorization": f"Bearer {access}"},
                ) as response:
                    await response.read()
            async with session.get(
                f"{base}/api/onboarding", raise_for_status=False
            ) as response:
                if response.status != 404:
                    response.raise_for_status()
                    if any(not step["done"] for step in await response.json()):
                        raise RuntimeError("Home Assistant onboarding is incomplete")
        await wait_for_ready(base, session, access, process)
    print(f"Home Assistant ready: {base}/ (use VS Code's forwarded port).", flush=True)


async def wait_for_ready(
    base: str,
    session: aiohttp.ClientSession,
    access: str,
    process: subprocess.Popen[bytes],
) -> None:
    print("Waiting for authenticated frontend and HA startup...", flush=True)
    deadline = time.monotonic() + 300
    async with session.ws_connect(
        f"{base}/api/websocket",
        timeout=aiohttp.ClientWSTimeout(ws_receive=15),
    ) as websocket:
        if (await websocket.receive_json()).get("type") != "auth_required":
            raise RuntimeError("Unexpected Home Assistant WebSocket greeting")
        await websocket.send_json({"type": "auth", "access_token": access})
        if (await websocket.receive_json()).get("type") != "auth_ok":
            raise RuntimeError("Home Assistant WebSocket authentication failed")

        async def request(request_id: int, command: str) -> dict:
            await websocket.send_json({"id": request_id, "type": command})
            reply = await websocket.receive_json()
            if reply.get("id") != request_id or not reply.get("success"):
                raise RuntimeError(
                    f"Home Assistant {command} failed: {reply.get('error')}"
                )
            return reply.get("result") or {}

        http = await request(1, "http/config")
        if http.get("pending") is not None and not http["pending"].get("error"):
            await request(2, "http/config/promote")
        elif http.get("pending") is not None:
            print(
                "Warning: HA retained a failed HTTP trial and is using its stable "
                "configuration. Review Settings -> System -> Repairs.",
                file=sys.stderr,
            )
        request_id = 2
        while True:
            if process.poll() is not None:
                raise RuntimeError("Home Assistant exited during startup")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Home Assistant did not reach RUNNING within 300 seconds"
                )
            request_id += 1
            config = await request(request_id, "get_config")
            if config["state"] == "RUNNING":
                if "default_config" not in config["components"]:
                    print(
                        "Warning: default_config is not loaded. If enabled in your YAML, "
                        "check home-assistant.log for failed dependencies.",
                        file=sys.stderr,
                    )
                async with session.get(f"{base}/") as response:
                    await response.read()
                return
            await asyncio.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-onboarding",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Complete onboarding and enable loopback-only passwordless login (default); "
            "--no-skip-onboarding disables automatic onboarding and the local login bypass"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / ".ha-config",
        help="Persistent development configuration (default: hs/.ha-config)",
    )
    args = parser.parse_args()
    config = args.config.resolve()
    try:
        prepare_config(config)
        base = enable_local_login(config, enabled=args.skip_onboarding)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Cannot prepare Home Assistant: {error}\n")

    print(f"Home Assistant configuration: {config}", flush=True)
    print(
        "Starting HA; wait for the readiness message before opening the UI.", flush=True
    )
    command = [
        sys.executable,
        "-m",
        "homeassistant",
        "--config",
        str(config),
        "--log-no-color",
    ]
    try:
        with running_instance(LOCK):
            while True:
                process = subprocess.Popen(command)
                try:
                    if base is not None:
                        asyncio.run(skip_onboarding(base, process))
                    result = process.wait()
                except (
                    KeyboardInterrupt,
                    OSError,
                    ValueError,
                    RuntimeError,
                    aiohttp.ClientError,
                ):
                    process.terminate()
                    try:
                        process.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        print(
                            "HA did not stop within 25 seconds; killing its child process.",
                            file=sys.stderr,
                        )
                        process.kill()
                        process.wait()
                    raise
                if result != 100:
                    return result
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, aiohttp.ClientError) as error:
        parser.exit(1, f"Cannot run Home Assistant: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
