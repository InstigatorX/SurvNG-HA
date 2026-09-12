// Paste into a Node-RED Function node. Configure Events: all to put its
// "event data" output in msg.payload. An explicit msg.incident is also accepted.
const event = msg.incident || msg.payload?.event || msg.payload;
const incident = event?.data || event;
if (!incident?.incident_id || incident.reconciled) return null;

// Put optional camera/class/person/zone filters here, before notification mapping.
// Example: if (!incident.classes?.includes("person")) return null;
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
