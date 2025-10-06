# Contributing  

## Coding 
- All changes must have a test that reflect the changes.
- If code not covered by test then add test for it. 
- For changes related to the API, prefer `py-surepetcare` and migrate logic there when possible. This keeps integration code clean and maintains separation of concerns.

## Testing changes with HACS
To fetch the latest version from the `main` branch for testing, use the HACS update service.  
See: [HACS docs](https://hacs.xyz/docs/use/entities/update/)

Example for latest dev:

```yaml
action: update.install
data:
  version: dev
target:
  entity_id: update.surepetcare_update
```

It is also possible to use same update from branch to verify functionality. 

## How to release
1. Run `python scripts/release.py` determine which version to bump to etc.
2. Create the pull request and merge it into main after all tests pass
3. Create a tag in releases and find the commit of latest release.
