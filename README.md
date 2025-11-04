# SurePetCare for Home Assistant

[![Home Assistant][ha-versions-shield]][homeassistant]
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE.md)
[![Downloads][downloads-shield]][downloads]
[![Build Status][build-shield]][build]
[![Code Coverage][codecov-shield]][codecov]
[![Documentation Status][wiki-shield]][wiki]
[![Open in Dev Containers][devcontainer-shield]][devcontainer]


## About
Built upon py-surepetcare to integrate with home assistant. Allow fine control to Pet and devices from SurePetCare. Provides services for fine control of SurePetCare data such as access to device, curfew and more.

## Documentation
The full documentation can be found at [Wiki][wiki].

# Installation
This integration requires the HACS add-on.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FredrikM97&repository=hass-surepetcare&category=integration)


## What does this integration do?
- Adds sensors and binary sensors for each supported device (e.g., door status, battery, feeding events, water level, connectivity)
- Custom name for position indoor/outdoor.
- Keep track of number of devices connected to a pet
- Allow Service updates for tags, device control and pet indoor/outdoor per pet

## Issues

If you encounter problems with the integration:

1. **Enable debug logging**: Go to Settings → Devices & Services → SurePetCare → Enable debug logging
2. **Reproduce the issue**: Perform the action that causes the problem
3. **Download diagnostics**: Go to Settings → Devices & Services → SurePetCare → Download diagnostics
4. **Create an issue**: [Open a GitHub issue](https://github.com/FredrikM97/hass-surepetcare/issues/new) and attach the diagnostics file

For urgent issues, check the Home Assistant logs at Settings → System → Logs.






[build-shield]: https://github.com/FredrikM97/hass-surepetcare/actions/workflows/test-and-coverage.yml/badge.svg
[build]: https://github.com/FredrikM97/hass-surepetcare/actions
[codecov-shield]: https://codecov.io/gh/FredrikM97/hass-surepetcare/branch/main/graph/badge.svg
[codecov]: https://codecov.io/gh/FredrikM97/hass-surepetcare
[license-shield]: https://img.shields.io/github/license/FredrikM97/hass-surepetcare.svg
[devcontainer-shield]: https://img.shields.io/static/v1?label=Dev%20Containers&message=Open&color=blue&logo=visualstudiocode
[devcontainer]: https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/FredrikM97/hass-surepetcare
[ha-versions-shield]: https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/FredrikM97/hass-surepetcare/main/hacs.json&label=homeassistant&query=$.homeassistant&color=blue&logo=homeassistant
[releases-shield]: https://img.shields.io/github/release/FredrikM97/hass-surepetcare.svg
[releases]: https://github.com/FredrikM97/hass-surepetcare/releases
[wiki-shield]: https://img.shields.io/badge/docs-wiki-blue.svg
[wiki]: https://github.com/FredrikM97/hass-surepetcare/wiki
[homeassistant]: https://my.home-assistant.io/redirect/hacs_repository/?owner=FredrikM97&repository=hass-surepetcare&category=integration
[downloads-shield]: https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=downloads&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.surepcha.total
[downloads]: https://analytics.home-assistant.io/custom_integrations.json