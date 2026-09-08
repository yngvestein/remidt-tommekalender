/*
 * Remidt Tømmekalender – Lovelace-kort
 *
 * Viser neste tømming per fraksjon med syklusprogress, basert på attributtene
 * til sensor.neste_tomming (`<fraksjon>_dager_igjen`, `_neste`, `_progress`).
 */

const CARD_TAG = "remidt-tommekalender-card";
const CARD_VERSION = "0.4.0";
const DOCS_URL = "https://github.com/yngvestein/remidt-tommekalender";
const DEFAULT_ENTITY = "sensor.neste_tomming";

const LABELS = {
  restavfall: "Restavfall",
  papir: "Papir",
  glass_og_metallemballasje: "Glass og metall",
  plastemballasje: "Plastemballasje",
  matavfall: "Matavfall",
};

const ICONS = {
  restavfall: "mdi:trash-can",
  papir: "mdi:newspaper-variant",
  glass_og_metallemballasje: "mdi:bottle-wine-outline",
  plastemballasje: "mdi:recycle",
  matavfall: "mdi:food-apple-outline",
};

const WEEKDAYS = ["søndag", "mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag"];

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 14px; }
  .header {
    display: flex; align-items: center; gap: 7px; margin-bottom: 10px;
  }
  .header ha-icon { --mdc-icon-size: 16px; color: var(--secondary-text-color); }
  .header-label {
    font-size: .78em; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--secondary-text-color);
  }
  .row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
  .row ha-icon { --mdc-icon-size: 17px; color: var(--primary-text-color); }
  .name { flex: 1; font-size: .9em; font-weight: 500; color: var(--primary-text-color); }
  .days {
    font-size: .82em; font-weight: 500; color: var(--secondary-text-color);
    white-space: nowrap; min-width: 58px; text-align: right;
  }
  .days.today  { color: var(--success-color, #4caf50); font-weight: 700; }
  .days.urgent { color: var(--error-color, #f44336); font-weight: 700; }
  .track {
    height: 5px; border-radius: 3px; overflow: hidden; margin-bottom: 8px;
    background: var(--aurora-fill-strong, var(--divider-color));
  }
  .track:last-child { margin-bottom: 0; }
  .fill { height: 100%; border-radius: 3px; transition: width .5s cubic-bezier(.2,.8,.2,1); }
  .fill.today  { background: var(--success-color, #4caf50); }
  .fill.urgent { background: var(--error-color, #f44336); }
  .fill.calm   { background: var(--info-color, #2196f3); }
  .message { padding: 8px 0; color: var(--secondary-text-color); font-size: .9em; }
`;

/** Sant hvis entiteten kommer fra denne integrasjonen og har fraksjonsattributter. */
function isRemidtSensor(hass, entityId) {
  if (!entityId?.startsWith("sensor.")) return false;
  const stateObj = hass.states[entityId];
  if (!stateObj) return false;
  const attrs = stateObj.attributes || {};
  const hasFractions = Object.keys(attrs).some((k) => k.endsWith("_dager_igjen"));
  const platform = hass.entities?.[entityId]?.platform;
  return platform === "remidt_tommekalender" || hasFractions;
}

class RemidtTommekalenderCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = undefined;
    this._hass = undefined;
    this._lastRendered = undefined;
  }

  // ---- Lovelace-kontrakt ------------------------------------------------

  setConfig(config) {
    if (config.entity !== undefined && typeof config.entity !== "string") {
      throw new Error("«entity» må være en entitets-ID (tekst)");
    }
    this._config = { entity: DEFAULT_ENTITY, title: "Tømmeplaner", ...config };
    this._lastRendered = undefined;
    this._build();
    if (this._hass) this._render();
  }

  set hass(hass) {
    if (!hass) return;
    this._hass = hass;
    if (!this._config) return;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { columns: 6, rows: 3, min_columns: 4, min_rows: 2 };
  }

  static getStubConfig(hass) {
    const entity =
      Object.keys(hass?.states ?? {}).find((id) => isRemidtSensor(hass, id)) ??
      DEFAULT_ENTITY;
    return { entity };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: {
            entity: { filter: { domain: "sensor", integration: "remidt_tommekalender" } },
          },
        },
        { name: "title", selector: { text: {} } },
      ],
      computeLabel: (schema) =>
        ({ entity: "Sensor (neste tømming)", title: "Overskrift" })[schema.name] ?? schema.name,
      assertConfig: (config) => {
        if (config.entity !== undefined && typeof config.entity !== "string") {
          throw new Error("«entity» må være en entitets-ID");
        }
      },
    };
  }

  // ---- Rendering ----------------------------------------------------------

  _build() {
    if (this._card) return;
    const style = document.createElement("style");
    style.textContent = STYLE;
    this._card = document.createElement("ha-card");
    this._content = document.createElement("div");
    this._card.appendChild(this._content);
    this.shadowRoot.append(style, this._card);
  }

  _render() {
    const entityId = this._config.entity;
    const stateObj = this._hass.states[entityId];

    if (!stateObj) {
      this._setContent(`loading:${entityId}`, () =>
        this._message(`Finner ikke ${entityId}`)
      );
      return;
    }
    if (stateObj.state === "unavailable") {
      this._setContent("unavailable", () => this._message("Tømmekalenderen er utilgjengelig"));
      return;
    }

    // Tegn bare på nytt når attributtene faktisk har endret seg.
    const key = JSON.stringify(stateObj.attributes) + this._config.title;
    this._setContent(key, () => this._fractionsHtml(stateObj.attributes));
  }

  _setContent(key, htmlFn) {
    if (this._lastRendered === key) return;
    this._lastRendered = key;
    this._content.innerHTML = htmlFn();
  }

  _message(text) {
    return `<div class="message">${text}</div>`;
  }

  _fractionsHtml(attrs) {
    const fractions = Object.keys(attrs)
      .filter((k) => k.endsWith("_dager_igjen"))
      .map((k) => k.replace("_dager_igjen", ""))
      .sort((a, b) => (attrs[`${a}_dager_igjen`] ?? 999) - (attrs[`${b}_dager_igjen`] ?? 999));

    if (!fractions.length) return this._message("Ingen kommende tømminger");

    const header = this._config.title
      ? `<div class="header">
           <ha-icon icon="mdi:recycle-variant"></ha-icon>
           <span class="header-label">${this._escape(this._config.title)}</span>
         </div>`
      : "";

    const rows = fractions
      .map((f) => {
        const days = Number(attrs[`${f}_dager_igjen`] ?? 0);
        const next = attrs[`${f}_neste`] ?? null;
        const progress = Math.min(100, Math.max(0, Number(attrs[`${f}_progress`] ?? 0)));
        const urgency = days === 0 ? "today" : days <= 3 ? "urgent" : "calm";
        return `
          <div class="row">
            <ha-icon icon="${ICONS[f] ?? "mdi:delete"}"></ha-icon>
            <span class="name">${this._escape(this._label(f))}</span>
            <span class="days ${urgency}">${this._daysLabel(days, next)}</span>
          </div>
          <div class="track"><div class="fill ${urgency}" style="width:${progress}%"></div></div>`;
      })
      .join("");

    return header + rows;
  }

  _label(fraction) {
    return LABELS[fraction] ?? fraction.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  _weekday(dateStr) {
    if (typeof dateStr !== "string") return "";
    const [y, m, d] = dateStr.split("-").map(Number);
    if (!y || !m || !d) return "";
    return WEEKDAYS[new Date(y, m - 1, d).getDay()];
  }

  _daysLabel(days, nextDate) {
    if (days === 0) return "I dag";
    const weekday = this._weekday(nextDate);
    if (days === 1) return weekday ? `I morgen (${weekday})` : "I morgen";
    if (days <= 5 && weekday) return `Om ${days} dager på ${weekday}`;
    return `Om ${days} dager`;
  }

  _escape(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }
}

// ---- Registrering -----------------------------------------------------------
//
// HA-frontenden bytter ut `window.customElements` med en polyfill tidlig i
// app.js. Registrerer vi elementet før det byttet, ser ikke HA det. Vi venter
// derfor til HA sitt eget rot-element er definert – da er polyfillen garantert
// på plass, uansett om denne fila ble lastet som dashbord-ressurs eller som
// ekstra modul fra index.html.
const defineCard = () => {
  if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, RemidtTommekalenderCard);
};
customElements.whenDefined("home-assistant").then(defineCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: CARD_TAG,
  name: "Tømmekalender (Remidt)",
  description: "Viser tømmeplaner fra Remidt med syklusprogress per fraksjon",
  preview: true,
  documentationURL: DOCS_URL,
  // HA 2026.6+: foreslå kortet i kortvelgeren når brukeren velger sensoren vår.
  getEntitySuggestion: (hass, entityId) =>
    isRemidtSensor(hass, entityId) ? { config: { type: `custom:${CARD_TAG}`, entity: entityId } } : null,
});

console.info(
  `%c REMIDT-TOMMEKALENDER-CARD %c v${CARD_VERSION} `,
  "color:#4caf50;font-weight:bold;background:#111",
  "color:#fff;font-weight:bold;background:#555"
);
