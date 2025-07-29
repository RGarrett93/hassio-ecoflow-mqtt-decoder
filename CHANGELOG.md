# Changelog

## v1.0.5
### Fix
- `deci_watts` preventing  0W from being sent, thanks @RudolfRendier.

### Notes
- No breaking changes.

## v1.0.4
### Added
- `control_logging` configuration option to enable or disable verbose logging of commands sent (disabled by default).

### Notes
- Minor update to include control_logging.

## v1.0.3
### Added
- `heartbeat_logging` configuration option to enable or disable verbose logging of decoded heartbeats (disabled by default).
- Improved compatibility with `paho-mqtt` by switching to the v2 API to remove the deprecation warning.

### Notes
- No breaking changes.
- Default behavior is unchanged; logs are quieter unless explicitly enabled via `heartbeat_logging`.
