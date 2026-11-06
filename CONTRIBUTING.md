# Contributing  

## Coding 
- All changes must have a test that reflect the changes.
- If code not covered by test then add test for it. 
- For changes related to the API, prefer `py-surepetcare` and migrate logic there when possible. This keeps integration code clean and maintains separation of concerns.

## Development setup
- Install dependencies with `uv sync --group dev`.
- Run commands through `uv run`, for example `uv run pytest tests`.
- The dev container installs pre-commit hooks when it is created and started.
- Outside the dev container, install commit hooks with `uv run pre-commit install --install-hooks` after installing dependencies. Remove any `core.hooksPath` override first, since pre-commit requires Git's default hooks directory.
- Run `uv run pre-commit run --all-files` before opening a pull request. CI runs the same checks on every pull request, including Dependabot updates.

## Running Home Assistant locally

From the `hs` directory, run:

```bash
uv run --no-sync python scripts/dev_ha.py
```

Open <http://localhost:8123> (forward port 8123 in VS Code if needed), then add
**SurePetcare** under **Settings -> Devices & services**.
Run `uv sync --group dev` once when setting up or updating project dependencies.
Routine starts use `--no-sync`: this avoids repeatedly recompiling the entire
environment and removing component dependencies HA installed at runtime.
Wait for **Home Assistant ready** before opening the UI. The runner verifies
authenticated WebSocket access and HA's `RUNNING` state, and confirms pending
HTTP configuration so HA does not automatically revert it later.
The generated configuration uses HA's standard `default_config` bundle rather
than a minimal frontend. This includes history, activity, energy, media,
Companion app support, and discovery, with recorder loaded as a dependency.
Automations, scripts, and scenes are also enabled with empty initial
configuration. Existing development configurations are preserved: add
`default_config:` and, if absent, `automation: []`, `script: {}`, and `scene: []`
at the top level, then restart HA. Only changes recorded after enabling recorder
appear in entity history; SurePetcare's API history is not backfilled.
The HA version is pinned by the development dependencies; the local integration,
editable PS library, debug logging, and loopback login bypass remain intentional
development differences. This runs HA Core, not HA OS/Supervisor, so add-ons and
hardware/network discovery may differ from production. Bluetooth/USB and
multicast discovery require suitable host access and are not guaranteed inside
the dev container. Standard components may install dependencies on first start,
so allow extra startup time.
The runner links the working integration and uses the editable sibling `ps`
dependency. Home Assistant installs missing component dependencies on startup.
Development mode is enabled by default. It creates a **Developer** account
(`dev`) with a random password, completes
onboarding through HA's API, and enables trusted-network login **only from
loopback addresses**. Use the VS Code forwarded port, not the container's LAN
address. No SurePetcare account is configured automatically. Existing completed
onboarding is preserved, and interrupted onboarding resumes on the next run.
Passwordless login requires exactly one active user.

To opt out of automatic onboarding and passwordless access:

```bash
uv run --no-sync python scripts/dev_ha.py --no-skip-onboarding
```

This removes only the launcher's loopback trusted-network provider; other
authentication providers and existing accounts are preserved. Completed
onboarding is not reset. Before opting out of an already bootstrapped instance,
set a password for the development account in HA's user settings.
The authentication configuration persists after stopping the launcher, so use
the opt-out flag on subsequent starts to keep passwordless access disabled.
Do not use the default development mode in production or expose the forwarded
port publicly. `--skip-onboarding` remains accepted to explicitly enable it.

The parent workspace and standalone `hs` dev containers forward port 8123 and
install HA's runtime dependencies (`ffmpeg`, `libturbojpeg0`, `libpcap0.8`, and
go2rtc 1.9.14). After
updating a container definition, use **Dev Containers: Rebuild Container**,
then start the runner again. Use the forwarded address from VS Code's **Ports**
panel; its host port may differ if 8123 is already occupied on your computer.
Outside a dev container, install those system packages separately if media
features are needed.

Configuration, credentials and HA state persist in the git-ignored `.ha-config/`
directory. Existing configuration is preserved apart from adding or removing
the launcher's local authentication provider. To change the port,
edit `.ha-config/configuration.yaml`. You can reuse another development
configuration with `--config /absolute/path/to/config`.

Stop with **Ctrl+C** and rerun after Python changes. Starting the runner again
gracefully stops its previous instance, even if it used another `--config`.
A repository-local `.ha-runner.lock` tracks ownership; unrelated processes
using the same port are not stopped. This runner requires Linux (including
the dev container/WSL). VS Code also provides the **Run Local Home Assistant**
task when opening `hs` as the workspace.

## Testing changes with HACS
For testing follow the [guide](https://github.com/FredrikM97/hass-surepetcare/wiki/Dev). `update.install` is no longer valid since this repo uses zip releases. 

## How to release
1. Update the draft and set the tag to version to release.
2. After release the workflow will create a zip with the latest changes and update the version to match the tag.
