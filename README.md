# SurvNG for Home Assistant

Local Home Assistant integration for SurvNG cameras, clean snapshots, live
streams, controls, activity state and incident automations.

## Prerequisites

- Home Assistant 2025.12 or newer.
- SurvNG from the current `v1.2` or `v1.3-gstreamer` branch.
- A reachable SurvNG URL including its base path. Use the HTTPS endpoint when
  TLS is enabled, for example `https://survng.example.com/survng` (or
  `https://SERVER:8088/survng` for direct access).
- A SurvNG API token with `read` and `camera:control` scopes. Create it in
  **SurvNG → Admin → General → API** and copy the secret when shown.
- SurvNG with native incident notification schema 2 support (update both server
  and integration together). MQTT is optional for motion/object activity overlays;
  incident notifications do not require MQTT.
- A configured Home Assistant local media directory for notification attachments.

Disable SurvNG's legacy Home Assistant MQTT discovery before enabling this
integration, otherwise Home Assistant will show duplicate devices.

## Install

Copy `custom_components/survng` into Home Assistant's `config/custom_components`
directory and restart Home Assistant. Then open **Settings → Devices & services
→ Add integration**, search for **SurvNG**, and enter the server URL and API
token. HACS custom-repository installation can use this repository's root.

## Behavior

HTTP polling every 30 seconds reconciles authoritative server and camera state.
An authenticated native event stream supplies incident lifecycle notifications.
Optional MQTT supplies motion/object activity overlays. Clean camera images are
fetched on demand; live streams use SurvNG's credential-safe go2rtc descriptor.

Each incident updates its camera's event entity and fires `survng_incident` with:

- Stable `incident_id`, `camera_id`, `server_id`, `notification_tag`, and `revision`.
- `state`: `new`, `updated`, or `complete`; readable `title` and factual `summary`.
- `objects` (class, confidence, zones, observation count), `people`, and `identities`
  (recognition confidence/status). Observation counts are not unique person counts.
- `started_at`, `last_activity_at`, `completed_at`, and `duration_seconds`.
- `image_url`, `initial_image_url`, `final_image_url`, `image_pending`, and
  `image_available`. These are authenticated HA media URLs, not SurvNG credentials.
- `event_url`, `changed_fields`, and `delivery` (`lifecycle` or `image`).

Text is delivered immediately. Image download completion fires another event
with the same incident revision and notification tag, with `delivery: image`.
`initial_image_url` preserves the first image fetched during live delivery;
`final_image_url` is supplied once a completed revision's image is fetched.
A cover is fetched from the representative event at download time; a delayed
fetch can therefore see a refinement that already replaced the original cover.
Cached attachment files themselves are immutable per revision. Images are limited
to 10 MiB each; the per-entry cache retains at most 512 files / 128 MiB / seven
days, with cleanup when new images arrive. Older attachment links may expire.
Images unavailable during a storage/network outage do not prevent text delivery.

Reconnect uses the last processed stream cursor. SurvNG journals recent lifecycle
state in its local database directory, allowing a recovery snapshot after server
restart or replay-history expiry. Revisions suppress duplicate delivery. The
first connection after HA setup/reload populates event entities without sending
historical notifications; later reconnects deliver changed/missed incidents.
Recovery history retains active incidents and the latest 256 completed groups.
Incidents outside that retained window cannot be recovered by this stream.

The event entity's “What happened” value identifies the lifecycle stage; its
`summary` attribute describes the detections. For notification automations, use
`survng_incident` rather than entity state changes, which also reflect baseline
reconciliation.

## Node-RED notifications

Use the Home Assistant WebSocket nodes in Node-RED; no MQTT node is required:

1. Add **Events: all**, select your HA server, and set **Event Type** to
   `survng_incident`. Set its **event data** output to `msg.payload`.
2. Add a **Function** node with [the notification mapper](examples/node-red-notification.js).
   Add camera/class/person/zone filters before the notification mapping as desired.
3. Add a Home Assistant **Action** node, select your `notify.mobile_app_*` action,
   and set **Data** to the JSONata expression `notification`. This reads the
   object prepared in `msg.notification`; no JSON string interpolation is needed.
4. Use a Debug node on `msg.incident` to inspect the full detection information.

Both lifecycle and image deliveries matter: an image delivery can share the same
`revision` as its preceding text delivery. Do not discard it merely because the
revision matches. Use `notification_tag` for replacement, and if your flow adds
its own deduplication, include `delivery` and `image_url` alongside the revision.

The HA integration repairs its connection to SurvNG. A separate Node-RED-to-HA
WebSocket outage can still miss event-bus messages; those messages are not a
persistent notification queue. Node-RED can inspect the latest incident entity
attributes on reconnect if your flow needs additional reconciliation.

The [Events: all](https://zachowj.github.io/node-red-contrib-home-assistant-websocket/node/events-all.html)
and [Action](https://zachowj.github.io/node-red-contrib-home-assistant-websocket/node/action.html)
node documentation describes these settings. The flow remains yours to route
notifications, select devices, and apply presence or time-of-day rules.

## Device notifications

Copy `blueprints/automation/survng/incident_notifications.yaml` into the matching
Home Assistant blueprints directory, reload automations, and create an automation
from **SurvNG incident notifications**. Select your `notify.mobile_app_*` action;
optionally filter cameras, classes, and stages. The blueprint replaces one
notification per incident and requests quiet image/lifecycle updates.

HA must be reachable by the Companion app for attachments to load away from home.
The default click target is the configured SurvNG incident URL; use the blueprint's
URL override for a HA dashboard or externally reachable destination if needed.

The attachment and replacement behavior follows the Companion app's
[attachment](https://companion.home-assistant.io/docs/notifications/notification-attachments/)
and [notification](https://companion.home-assistant.io/docs/notifications/notifications-basic/)
contracts. Actual phone delivery still needs acceptance testing on your devices.

## Troubleshooting

- **Invalid authentication:** create a replacement token with both `read` and
  `camera:control`, then use Home Assistant's reauthentication prompt.
- **TLS certificate error:** Home Assistant verifies HTTPS certificates by
  default. Install the CA that issued a private/self-signed SurvNG certificate
  in the Home Assistant host/container, then keep **Verify TLS certificate**
  enabled. Disable it only on a trusted private network when installing the CA
  is not practical; this weakens protection against man-in-the-middle attacks.
- **Still image works but video does not:** verify Home Assistant can reach the
  RTSP address returned by SurvNG's go2rtc stream-source endpoint.
- **Duplicate devices:** disable legacy MQTT discovery in SurvNG and remove its
  old retained discovery entities.
- **Camera unavailable:** camera power and current-frame availability are
  independent of the SurvNG server's overall availability.

Removing the config entry stops the native stream and image tasks, unsubscribes
optional MQTT listeners, and unloads every entity platform. Removing files alone is not sufficient; remove the entry first.
