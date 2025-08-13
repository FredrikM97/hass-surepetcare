# SurePetCare for Home Assistant

Built upon py-surepetcare to integrate with home assistant 

Sensors for Feeders, flaps, hub and fountain.

## Installation via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FredrikM97&repository=hass-surepetcare&category=integration)

**To install:**
1. Go to HACS in your Home Assistant sidebar.
2. Click the three dots (⋮) in the top right and select “Custom repositories”.
3. Add this repository’s URL and select “Integration” as the category.
4. Search for “SurePetCare” in HACS, click “Install”, and restart Home Assistant.

**After installation:**
- Go to **Settings → Devices & Services → Add Integration** and search for “SurePetCare”.
- Follow the prompts to log in and set up your devices.


## Supported Devices

This integration supports the following Sure Petcare devices:
- Pet Door Connect
- Flap Connect
- Feeder Connect
- SureFlap Hub
- Felaqua Connect 
- DualScan Pet Door
- Connect-enabled accessories


## What does this integration do?
- Adds sensors and binary sensors for each supported device (e.g., door status, battery, feeding events, water level, connectivity)
- Shows device information in Home Assistant’s Device Info panel
- Lets you automate based on pet location, feeder usage, battery status, and more
- Supports configuration and setup via the Home Assistant UI
- Works seamlessly with HACS for easy updates

## Issues
In case of issue enable debug for the integration or download diagnostics and create a issue.
