// Paste into a Node-RED Function node. Configure Events: all to put its
// "event data" output in msg.payload. An explicit msg.incident is also accepted.
const event = msg.incident || msg.payload?.event || msg.payload;
const incident = event?.data || event;
if (!incident?.incident_id || incident.reconciled) return null;

// "exclude": objects/people only; "only": motion-only; "include": all incidents.
const motionFilter = String("exclude");
// Empty means all object types. Example: ["person", "car", "dog"].
const objectTypes = [];
const normalize = value => String(value || "").trim().toLowerCase();
const classes = [
    ...(Array.isArray(incident.classes) ? incident.classes : []),
    ...(Array.isArray(incident.objects) ? incident.objects.map(object => object?.label) : [])
].map(normalize).filter(Boolean);
const allowedTypes = new Set(objectTypes.map(normalize).filter(Boolean));
const hasObjects = incident.has_objects === true || classes.length > 0;
if (motionFilter === "exclude" && !hasObjects) return null;
if (motionFilter === "only" && hasObjects) return null;
if (hasObjects && allowedTypes.size && !classes.some(type => allowedTypes.has(type))) return null;

// Put optional camera/recognized-person/zone filters here, before notification mapping.
const initial = incident.state === "new" && incident.delivery === "lifecycle";
const data = {
    tag: incident.notification_tag,
    alert_once: true,
    url: incident.event_url,
    clickAction: incident.event_url,
    push: { sound: initial ? "default" : "none" },
    actions: [{ action: "URI", title: "View incident", uri: incident.event_url }]
};
if (incident.image_url) data.image = incident.image_url;
msg.incident = incident;
msg.notification = {
    title: incident.title,
    message: incident.summary + (incident.state === "complete" ? " Incident complete." : ""),
    data
};
return msg;
