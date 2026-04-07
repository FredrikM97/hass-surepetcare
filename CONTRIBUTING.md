# Contributing  

## Coding 
- All changes must have a test that reflect the changes.
- If code not covered by test then add test for it. 
- For changes related to the API, prefer `py-surepetcare` and migrate logic there when possible. This keeps integration code clean and maintains separation of concerns.

## Development setup
- Install dependencies with `uv sync --group dev`.
- Run commands through `uv run`, for example `uv run pytest tests`.

## Testing changes with HACS
For testing follow the [guide](https://github.com/FredrikM97/hass-surepetcare/wiki/Dev). `update.install` is no longer valid since this repo uses zip releases. 

## How to release
1. Update the draft and set the tag to version to release.
2. After release the workflow will create a zip with the latest changes and update the version to match the tag.
