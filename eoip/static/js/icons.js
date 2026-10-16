// Small inline stroke icon set (24x24). Kept local so the dashboard works offline.
const P = {
  flame: '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.3-4.8.2 1.6 1 2.6 2 3 0-3 .2-5.6.7-8.2z"/>',
  medical: '<path d="M3 12h4l2-4 4 8 2-4h6"/><path d="M12 21s-8-4.5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 1-.2 2-.5 2.9"/>',
  crowd: '<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2.5 20c.6-3.4 2.8-5.5 5.5-5.5s4.9 2.1 5.5 5.5"/><path d="M14.5 15.2c.8-.5 1.6-.7 2.5-.7 2.2 0 4 1.8 4.5 5"/>',
  facility: '<path d="M14.7 6.3a4 4 0 0 0 5 5l-8.8 8.8a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3 17 4"/>',
  it: '<path d="M2 9a15 15 0 0 1 20 0"/><path d="M5 12.5a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r=".8"/>',
  radio: '<rect x="6" y="7" width="12" height="14" rx="2"/><path d="M9 7 15 3"/><path d="M9 12h6M9 15.5h6"/>',
  camera: '<path d="M3 8h3l2-3h8l2 3h3v11H3z"/><circle cx="12" cy="13" r="3.5"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  headset: '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
  server: '<rect x="4" y="4" width="16" height="7" rx="1.5"/><rect x="4" y="13" width="16" height="7" rx="1.5"/><path d="M8 7.5h.01M8 16.5h.01"/>',
  system: '<circle cx="12" cy="12" r="2"/><path d="M8 8a5.6 5.6 0 0 0 0 8M16 8a5.6 5.6 0 0 1 0 8M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
  service: '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
  sensor: '<circle cx="12" cy="12" r="2"/><path d="M8 8a5.6 5.6 0 0 0 0 8M16 8a5.6 5.6 0 0 1 0 8M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
  roster: '<rect x="4" y="4" width="16" height="17" rx="2"/><path d="M8 2.5v3M16 2.5v3M8 11h8M8 15h5"/>',
  door: '<path d="M5 21V4h11v17"/><path d="M16 4l3 1.5V21"/><circle cx="13" cy="13" r=".8"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevron: '<path d="M9 5l7 7-7 7"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  skip: '<path d="M5 5v14l9-7zM18 5v14"/>',
  reset: '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4h4"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9S14.5 18.4 12 21c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3z"/>',
  person: '<circle cx="12" cy="7" r="3.5"/><path d="M5 21c.8-4 3.5-6.5 7-6.5s6.2 2.5 7 6.5"/>',
  eye: '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
  eyeOff: '<path d="m3 3 18 18M10.6 6.2A11.2 11.2 0 0 1 12 6c6.4 0 10 6 10 6a16 16 0 0 1-3 3.6M6.2 6.3C3.5 8.1 2 12 2 12s3.6 6 10 6a11 11 0 0 0 3-.4"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  logout: '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  send: '<path d="M4 12 20 4l-6 16-3-7z"/>',
  overview: '<path d="M3 13h4l2-6 4 12 3-8 2 2h3"/>',
  map: '<path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4z"/><path d="M9 4v13M15 6.5v13"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  incident: '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  decide: '<path d="M12 3v18M5 7h14"/><path d="M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z"/>',
  log: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11M9 8h6"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
  team: '<circle cx="9" cy="8" r="3"/><path d="M3 20c.7-3.5 3-5.5 6-5.5s5.3 2 6 5.5"/><path d="M16 4.5a3 3 0 0 1 0 6M18 14.5c1.7.8 2.7 2.6 3 5.5"/>',
  tools: '<path d="M4 7h16M4 12h10M4 17h7"/><circle cx="18" cy="15" r="3"/>',
  food: '<path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10"/><path d="M17 21V3c-2 1.5-3 4-3 7v3h3"/>',
  event: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M9 14.5l2 2 4-4"/>',
  aid: '<rect x="3.5" y="6" width="17" height="14" rx="2"/><path d="M9 6V4h6v2M12 10v6M9 13h6"/>',
  route: '<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/>',
  gate: '<path d="M3 21V9l9-5 9 5v12"/><path d="M7 21v-8h10v8M12 13v8"/>',
  pin: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  home: '<path d="M3.5 11 12 4l8.5 7"/><path d="M6 9.5V20h12V9.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  layers: '<path d="M12 3 2.5 8 12 13l9.5-5z"/><path d="M2.5 12.5 12 17.5l9.5-5M2.5 16.5 12 21.5l9.5-5"/>',
  pulse: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  chevronDown: '<path d="M6 9l6 6 6-6"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 .6-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 18z"/>',
  wind: '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7"/>',
  drop: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  sun: '<circle cx="12" cy="12" r="2.4"/><path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4M5.3 5.3l2.8 2.8M15.9 15.9l2.8 2.8M5.3 18.7l2.8-2.8M15.9 8.1l2.8-2.8"/>',
  eoip: '<circle cx="12" cy="12" r="2.2"/><circle cx="4.5" cy="6" r="1.6"/><circle cx="19.5" cy="6" r="1.6"/><circle cx="4.5" cy="18" r="1.6"/><circle cx="19.5" cy="18" r="1.6"/><path d="M6 7l4.3 3.7M18 7l-4.3 3.7M6 17l4.3-3.7M18 17l-4.3-3.7"/>',
};

// EOIP brand mark: a stylised sunburst (rays + core), drawn filled.
// EOIP logo (the team's new logo icon, transparent background). Same slot as before: only the mark changes.
export function brandMark(cls = "") {
  return `<img class="brand-logo ${cls}" src="/static/img/eoip-logo.png" alt="" aria-hidden="true" draggable="false">`;
}

export function icon(name, cls = "") {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || P.bell}</svg>`;
}

export const TYPE_ICON = { fire: "flame", medical: "medical", crowd_pressure: "crowd", facility: "facility", it_system: "it", visitor_conduct: "person" };
export const SOURCE_ICON = {
  fire_system: "flame", cctv_ai: "camera", crowd_sensors: "sensor", queue_sensors: "sensor", radio: "radio",
  service_desk: "headset", staff_roster: "roster", bms: "server", it_monitoring: "it", access_control: "door",
};
export const SIGNAL_ICON = { alert: "bell", radio_message: "radio", service_request: "headset", system_notification: "server" };
