# Contributing  

## Coding 
- All changes must have a test that reflect the changes.
- If code not covered by test then add test for it. 
- For changes related to the API, prefer `py-surepetcare` and migrate logic there when possible. This keeps integration code clean and maintains separation of concerns.

## Testing changes with HACS
To fetch the latest version from the `main` branch for testing, use the HACS update service.  
See: [HACS docs](https://hacs.xyz/docs/use/entities/update/)

Example:

```yaml
action: update.install
data:
  version: main
target:
  entity_id: update.surepetcare_update
```

It is also possible to use same update from branch to verify functionality. 
