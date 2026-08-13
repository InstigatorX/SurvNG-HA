# SurvNG Home Assistant integration architecture

Status: approved for phased implementation

## Verified SurvNG contracts

SurvNG currently exposes an HTTP API under its configured base path (normally
`/survng`). The custom integration must store the complete base URL, including
that path, and append the paths below.

| Purpose | Method and path | Verified behavior |
| --- | --- | --- |
| Camera inventory and runtime state | `GET /api/cameras` | Returns one runtime-status object per stable camera ID. Includes display name, running/connected/fresh-frame state, detection state, recording state, capture health, stream dimensions, ONVIF state, and motion/tracking diagnostics. |
| Server health | `GET /api/system/status` | Returns process instance ID, CPU and application memory, storage, detector, aggregate camera counts, MQTT, go2rtc, and camera-startup status. |
| Integration authentication | `Authorization: Bearer <token>` | Native scoped long-lived tokens. `read` covers inventory, status, snapshots, streams and events; `camera:control` covers power, recording and detection changes; `admin` includes every scope but is not needed by this integration. |
| State reconciliation | `GET /api/events/stream` | Server-sent event stream. Emits initial camera/system snapshots when replay is unavailable, then typed application events. Connections intentionally end after approximately six seconds and must reconnect with `Last-Event-ID`. |
| Clean current image | `GET /api/cameras/{camera_id}/snapshot.jpg?source=live|main` | Returns a clean JPEG with `Cache-Control: no-store`; `404` for an unknown camera and `503` for a powered-off camera or unavailable frame. |
| Stream metadata | `GET /api/cameras/{camera_id}/live-info?source=live|main` | Returns go2rtc availability, stream name, codec list, delivery and transcoding state. It currently also returns an internal go2rtc host. |
| Stable stream source | `GET /api/cameras/{camera_id}/stream-source?source=live|main` | Returns a versioned, credential-safe, FFmpeg-readable go2rtc RTSP descriptor. The integration consumes the returned URL but never exposes it as entity state or diagnostics. |
| Browser MJPEG fallback | `GET /api/cameras/{camera_id}/stream.mjpg?source=live|main&fps=...` | Relays JPEG frames at a bounded rate. This is a compatibility fallback, not the preferred HA stream source. |
| WebRTC/MSE browser relays | `WS /api/cameras/{camera_id}/webrtc` and `/mse` | SurvNG-specific go2rtc WebSocket relays. They do not directly satisfy Home Assistant's `stream_source()` contract. |
| Camera power | `POST /api/cameras/{camera_id}/camera/start|stop` | Returns `{"ok": true}` or `404`. |
| Recording state | `PUT /api/cameras/{camera_id}/recording` with `{"enabled": bool}` | Returns the resulting state or `404`. |
| Detection state | `PUT /api/cameras/{camera_id}/detection` with `{"enabled": bool}` | Returns the resulting state or `404`. |
| Incident snapshot | `GET /api/events/{event_id}/snapshot.jpg` | Returns the retained incident image using its actual MIME type. This is not the live camera image. |
| Incident push transport | MQTT `survng/events/incidents` | Emits schema-versioned `new`, `updated`, and `complete` incident payloads without embedding image bytes. |
| Camera and zone push state | MQTT under `survng/camera/...` and `survng/zone/...` | Provides power, recording, detection, motion, object and zone-object state. Commands use the corresponding `/set` topics. |

The camera ID is the stable identifier and must be used for device and entity
unique IDs. The display name is mutable presentation data.

## Authentication and current server-contract boundaries

SurvNG now supports native scoped long-lived bearer tokens. Tokens are created
in **Admin → General → API** or with `scripts/create-api-token.py`; only a
digest is retained and the raw secret is shown once. The integration requests a
token carrying `read` and `camera:control`. An `admin` token works but is
unnecessarily privileged. The integration always requires a token so enabling
SurvNG enforcement later cannot unexpectedly disconnect an entry created in a
temporary trusted-LAN mode.

Every HTTP, image and SSE request uses the same bearer header. The token is
stored only in the Home Assistant config entry and is never copied into URLs,
entity attributes, logs, issue details or diagnostics. A `401` or `403` starts
Home Assistant reauthentication.

SurvNG also now exposes the credential-safe stream descriptor at
`GET /api/cameras/{camera_id}/stream-source?source=live|main`. The integration
does not collect a separate go2rtc URL and never exposes the returned source as
entity state or diagnostics.

### Instance identity and version

`/api/system/status` exposes a process instance ID, which changes with the
process and is unsuitable as the persistent config-entry unique ID. SurvNG
should expose a persistent installation UUID and application/API version. The
first integration release can normalize the configured origin as its entry
identity, then migrate to a server UUID when available.

## Ownership decision

The custom integration should own all Home Assistant SurvNG entities. It should
use SurvNG MQTT as a push transport, not rely on SurvNG's existing MQTT
discovery payloads.

Running both ownership models creates duplicate devices, switches, binary
sensors and state histories. Setup should detect or clearly warn when SurvNG
Home Assistant Discovery remains enabled and direct the user to disable legacy
discovery after the custom integration is installed. Existing retained
discovery topics need a documented one-time cleanup path.

HTTP remains authoritative for inventory, snapshots, health reconciliation and
commands. MQTT provides low-latency state and incidents. Periodic HTTP refresh
repairs missed MQTT messages and startup ordering races.

## Proposed integration structure

```text
custom_components/survng/
  __init__.py
  api.py
  camera.py
  config_flow.py
  const.py
  coordinator.py
  diagnostics.py
  entity.py
  event.py
  manifest.json
  models.py
  repairs.py
  sensor.py
  binary_sensor.py
  switch.py
  strings.json
  translations/en.json
```

`api.py` is a Home-Assistant-independent asynchronous client using the shared
Home Assistant `aiohttp` session. It owns bounded HTTP timeouts, response schema
validation and exception translation, but no entity state.

`models.py` contains frozen typed records for server status, camera status and
incident messages. HTTP and MQTT payloads are treated as untrusted and parsed
at this boundary.

`coordinator.py` owns slow reconciliation only: camera inventory, server health
and removal/addition discovery. Snapshot requests bypass the coordinator and
call the shared API client directly. MQTT events update the coordinator's
in-memory records and request listener refreshes without causing an immediate
HTTP poll for every event.

The typed config-entry `runtime_data` owns exactly one API client, coordinator,
MQTT unsubscribe collection and dynamically managed entity registry. Entry
unload cancels refreshes, unsubscribes MQTT listeners and unloads every
platform. The shared Home Assistant HTTP and MQTT clients are not closed by the
integration.

## Home Assistant device and entity model

One hub device represents the SurvNG server. Each camera is a child device with
`via_device` pointing to the server and an identifier derived from the stable
SurvNG camera ID.

The server device initially provides health, lifecycle, uptime when available,
CPU, application memory, free storage, detector state/latency, cameras available
and recorders active. Diagnostic details remain attributes only when bounded
and useful; high-cardinality telemetry does not become entities.

Each camera device provides:

- one camera entity using the clean snapshot endpoint;
- a power switch;
- recording and detection switches;
- motion and object binary sensors;
- last-object sensor;
- recording and capture-health sensors where the API has an authoritative
  value; and
- dynamically reconciled zone binary sensors.

The camera entity's properties use coordinator memory only. Its
`async_camera_image()` performs an independent bounded image request. Streaming
uses the live/substream by default and main only when selected in options.
Snapshot failure does not make an otherwise healthy camera device disappear,
and stream failure does not prevent still images.

## Events and incidents

Subscribe through Home Assistant's MQTT integration to the configured SurvNG
incident topic. Emit both:

- a Home Assistant event entity representing the latest incident transition;
  and
- a namespaced `survng_incident` event-bus event for automation compatibility.

The bounded event payload contains incident and camera IDs, lifecycle state,
timestamps, labels, confidence summaries, zones, trigger source when supplied,
the representative event ID, and URLs relative to the configured SurvNG base
URL. It never contains image bytes, video, credentials or original stream URLs.

The HTTP incident feed is used at setup/reconnect to reconcile the latest state;
it is not polled continuously.

## Configuration flow

The first flow collects:

- complete SurvNG base URL;
- API token carrying `read` and `camera:control` scopes;
- SSL verification;
- MQTT topic prefix when MQTT is enabled.

Validation calls `/api/system/status`, `/api/cameras`, and a read-only stream
descriptor, verifies JSON schemas, and distinguishes rejected credentials from
connection failures. SurvNG does not expose a non-mutating scope-introspection
endpoint, so `camera:control` is verified on the first control operation. A
camera being offline must not invalidate an otherwise valid server entry.

The options flow controls reconciliation interval, preferred stream and
optional entity families. `401` and `403` initiate reauthentication. Reconfigure
handles URL, TLS and MQTT changes independently of token replacement.

## Security model

- Reject base URLs containing embedded credentials.
- Permit only HTTP and HTTPS schemes.
- Use Home Assistant's SSRF-safe URL validation facilities where applicable.
- Default to TLS verification and require an explicit choice to disable it.
- Never log authorization headers, tokens, credentials or stream URLs.
- Redact the API token, base URL user information and stream descriptors from
  diagnostics.
- Do not expose stream sources as entity attributes.
- Bound JSON, image and error-body reads and enforce connect/read timeouts.
- Treat `404`, `409`, `429`, `503`, timeouts and malformed payloads as distinct
  recoverable conditions.

## Phased implementation

### Phase 1 — foundation and server device

Create the HACS-compatible repository structure, typed bearer-auth API client,
UI config flow, options/reconfigure/reauth handling, coordinator, server
device/sensors, diagnostics redaction and foundational tests.

### Phase 2 — cameras and still images

Add dynamic camera discovery, stable device/entity IDs, availability and clean
JPEG snapshot retrieval. Test rename, add/remove, disable, server restart,
temporary snapshot failure and entry unload.

### Phase 3 — live streaming

Implement `stream_source()` using SurvNG's credential-safe descriptor and the
preferred live/main stream. Test authentication, go2rtc restart and independent
snapshot/stream availability.

### Phase 4 — controls, state and zones

Add switch, binary-sensor and sensor platforms. Subscribe to existing SurvNG
MQTT state topics through Home Assistant's MQTT client, reconcile from HTTP and
document migration away from legacy discovery-owned entities.

### Phase 5 — incidents and automations

Add the event entity, incident MQTT subscription, event-bus automation contract,
reconnect reconciliation and direct SurvNG links. Test all incident lifecycle
states, duplicate delivery and malformed payloads.

### Phase 6 — hardening and release

Add repairs, translations, HACS metadata, complete user documentation,
troubleshooting, config-entry migrations, full lifecycle/failure tests and a
Home Assistant version compatibility matrix.

## Acceptance gates

Each phase is committed separately only after its focused test suite passes.
Before release, tests must prove that config-entry unload leaves no listeners or
tasks, camera renaming preserves entity IDs, server/go2rtc restarts recover,
credentials are absent from logs and diagnostics, and no image bytes traverse
MQTT.
