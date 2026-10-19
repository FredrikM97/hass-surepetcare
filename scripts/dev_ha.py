"""Run a throwaway local Home Assistant instance with SurePetCare loaded."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".ha-config"
INTEGRATION = ROOT / "custom_components" / "surepcha"
ONBOARDING_MARKER = CONFIG / ".dev-onboarded"
LOCK_FILE = Path(tempfile.gettempdir()) / (
    f"surepcha-dev-{hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]}.lock"
)

CONFIGURATION = """\
frontend:
config:
automation: !include automations.yaml
script:
history:
logbook:
system_log:

homeassistant:
  name: SurePetCare Dev
  auth_providers:
    - type: trusted_networks
      trusted_networks:
        - "127.0.0.1/32"
        - "::1/128"
        - "10.0.0.0/8"
        - "172.16.0.0/12"
        - "192.168.0.0/16"
      allow_bypass_login: true
    - type: homeassistant

http:
  server_port: {port}

logger:
  default: warning
  logs:
    custom_components.surepcha: debug
"""

DEV_AUTOMATION_ID = "surepcha_track_events"
DEV_AUTOMATION = (ROOT / "scripts" / "dev_ha_automations.yaml").read_text(
    encoding="utf-8"
)


def with_http_port(configuration: str, port: int) -> str:
    lines = configuration.splitlines()
    http_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.partition("#")[0].strip() == "http:"
        ),
        None,
    )
    if http_index is None:
        lines.extend(["", "http:", f"  server_port: {port}"])
    else:
        for index in range(http_index + 1, len(lines)):
            line = lines[index]
            if line and not line[0].isspace():
                lines.insert(index, f"  server_port: {port}")
                break
            if line.strip().startswith("server_port:"):
                indentation = line[: len(line) - len(line.lstrip())]
                lines[index] = f"{indentation}server_port: {port}"
                break
        else:
            lines.append(f"  server_port: {port}")
    return "\n".join(lines) + "\n"


def with_automation_include(configuration: str) -> str:
    lines = configuration.splitlines()
    for index, line in enumerate(lines):
        key, separator, value = line.partition(":")
        if line[:1].isspace() or not separator or key.strip() != "automation":
            continue
        value, comment_separator, comment = value.partition("#")
        if value.strip():
            return configuration
        for child in lines[index + 1 :]:
            if child and not child[0].isspace() and not child.lstrip().startswith("#"):
                break
            if child.strip() and not child.lstrip().startswith("#"):
                return configuration
        updated = "automation: !include automations.yaml"
        if comment_separator:
            updated += f"  #{comment}"
        lines[index] = updated
        break
    else:
        lines.extend(["", "automation: !include automations.yaml"])
    return "\n".join(lines) + "\n"


def prepare_automations() -> None:
    """Add the event-tracking automation without replacing local automations."""
    automations = CONFIG / "automations.yaml"
    existing = automations.read_text(encoding="utf-8") if automations.exists() else ""
    if DEV_AUTOMATION_ID in existing:
        return

    with automations.open("a", encoding="utf-8") as file:
        if existing and not existing.endswith("\n"):
            file.write("\n")
        file.write(DEV_AUTOMATION)


def prepare_config(port: int, reset: bool) -> None:
    if reset and CONFIG.exists():
        shutil.rmtree(CONFIG)

    components = CONFIG / "custom_components"
    components.mkdir(parents=True, exist_ok=True)
    (components / "__init__.py").touch()

    installed = components / "surepcha"
    if installed.exists():
        shutil.rmtree(installed)
    shutil.copytree(
        INTEGRATION,
        installed,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    configuration = CONFIG / "configuration.yaml"
    if not configuration.exists():
        configuration.write_text(CONFIGURATION.format(port=port), encoding="utf-8")
    else:
        existing = configuration.read_text(encoding="utf-8")
        updated = with_http_port(existing, port)
        updated = with_automation_include(updated)
        if updated != existing:
            configuration.write_text(updated, encoding="utf-8")
    prepare_automations()


async def wait_for_http(base: str, session: aiohttp.ClientSession) -> None:
    for _ in range(240):
        try:
            async with session.get(f"{base}/api/onboarding") as response:
                if response.status < 500:
                    return
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(0.5)
    raise TimeoutError("Home Assistant did not start within 2 minutes.")


async def complete_onboarding(port: int) -> None:
    base = f"http://127.0.0.1:{port}"
    client_id = f"http://localhost:{port}/"
    async with aiohttp.ClientSession() as session:
        await wait_for_http(base, session)
        if ONBOARDING_MARKER.exists():
            return

        async with session.post(
            f"{base}/api/onboarding/users",
            json={
                "name": "Developer",
                "username": "dev",
                "password": "dev",
                "client_id": client_id,
                "language": "en",
            },
        ) as response:
            response.raise_for_status()
            auth_code = (await response.json())["auth_code"]

        async with session.post(
            f"{base}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": client_id,
            },
        ) as response:
            response.raise_for_status()
            access_token = (await response.json())["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}
        for step, body in (
            ("core_config", None),
            ("analytics", None),
            (
                "integration",
                {
                    "client_id": client_id,
                    "redirect_uri": f"{client_id}?auth_callback=1",
                },
            ),
        ):
            async with session.post(
                f"{base}/api/onboarding/{step}", json=body, headers=headers
            ) as response:
                response.raise_for_status()

        async with session.ws_connect(
            f"{base.replace('http', 'ws', 1)}/api/websocket"
        ) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": access_token})
            if (await ws.receive_json())["type"] != "auth_ok":
                raise RuntimeError("Home Assistant websocket authentication failed.")
            await ws.send_json({"id": 1, "type": "http/config/promote"})
            while (reply := await ws.receive_json()).get("id") != 1:
                pass
            if not reply.get("success", True):
                raise RuntimeError(f"Home Assistant setup failed: {reply.get('error')}")

    ONBOARDING_MARKER.touch()


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=30)
    except ProcessLookupError, subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


@contextmanager
def dev_instance():
    with LOCK_FILE.open("a+") as lock:
        deadline = time.monotonic() + 45
        stopped: set[int] = set()
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                lock.seek(0)
                owner = lock.read().strip()
                if owner.isdecimal() and int(owner) not in stopped:
                    process_id = int(owner)
                    print(
                        f"[dev] Stopping previous instance ({process_id})...",
                        flush=True,
                    )
                    try:
                        os.kill(process_id, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    stopped.add(process_id)
                if time.monotonic() >= deadline:
                    raise TimeoutError("Previous dev instance did not stop in time.")
                time.sleep(0.1)

        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        try:
            yield
        finally:
            lock.seek(0)
            lock.truncate()
            lock.flush()
            fcntl.flock(lock, fcntl.LOCK_UN)


def run_dev(port: int, reset: bool) -> int:
    def exit_on_signal(signum: int, frame: object) -> None:
        raise SystemExit(0)

    handled_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous_handlers = {
        signum: signal.signal(signum, exit_on_signal) for signum in handled_signals
    }
    try:
        with dev_instance():
            prepare_config(port, reset)
            url = f"http://localhost:{port}"
            print(f"[dev] Starting Home Assistant at {url}", flush=True)
            print(
                "[dev] Onboarding is automatic; trusted local networks bypass login.",
                flush=True,
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "homeassistant", "-c", str(CONFIG)],
                cwd=CONFIG,
                start_new_session=True,
            )
            try:
                asyncio.run(complete_onboarding(port))
                print(
                    f"\n[dev] API available: {url} "
                    "(no login needed on trusted networks)\n",
                    flush=True,
                )
                return process.wait()
            finally:
                stop_process(process)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--reset", action="store_true", help="recreate .ha-config")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    raise SystemExit(run_dev(args.port, args.reset))


if __name__ == "__main__":
    main()
