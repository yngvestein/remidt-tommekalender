# Remidt Tømmekalender

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant-integrasjon for tømmekalender fra [Remidt](https://www.remidt.no) – renovasjonsselskapet for Indre Østfold kommune og omegn.

Integrasjonen henter tømmedatoer direkte fra Remidts API og oppretter sensorer og binære sensorer per avfallsfraksjon.

---

## Funksjoner

- **Sensor** – viser neste tømming og antall dager igjen
- **Binære sensorer** – én per fraksjon, slår seg på kvelden før og hele tømmedagen
- **Progress-attributter** – syklusfremdrift (0–100 %) og intervall per fraksjon
- **Historikk** – husker forrige tømmingsdato mellom oppdateringer
- **Oppdateringsintervall** – kan konfigureres fra 1 til 7 dager

---

## Krav

- Home Assistant 2023.1 eller nyere
- Adresse innenfor Remidts dekningsområde (primært Indre Østfold)

---

## Installasjon via HACS

1. Åpne **HACS** i Home Assistant
2. Gå til **Integrasjoner** → meny øverst til høyre → **Egendefinerte repositorier**
3. Lim inn URL-en til dette repoet og velg kategori **Integrasjon**
4. Søk etter **Remidt Tømmekalender** og installer
5. Start Home Assistant på nytt
6. Gå til **Innstillinger → Enheter og tjenester → Legg til integrasjon** og søk etter *Remidt*

---

## Manuell installasjon

1. Last ned eller klon dette repositoriet
2. Kopier mappen `custom_components/remidt_tommekalender/` til `<config>/custom_components/`
3. Start Home Assistant på nytt
4. Legg til integrasjonen via **Innstillinger → Enheter og tjenester**

---

## Konfigurasjon

Integrasjonen konfigureres via brukergrensesnittet:

1. Skriv inn gateadressen din (f.eks. `Storgata 1`)
2. Velg riktig adresse fra forslagslisten
3. Integrasjonen oppretter automatisk sensorer basert på fraksjonene registrert på adressen

### Innstillinger (Options)

| Innstilling | Standard | Beskrivelse |
|---|---|---|
| Oppdateringsintervall | 2 dager | Hvor ofte nye tømmedatoer hentes fra Remidt |

---

## Entiteter

### Sensor – `sensor.neste_tomming`

Viser hvilken fraksjon som tømmes neste, og antall dager til tømmingen.

**Eksempel på tilstand:** `Restavfall om 3 dager`

#### Attributter

| Attributt | Eksempel | Beskrivelse |
|---|---|---|
| `{fraksjon}_neste` | `2025-03-12` | Neste tømmedato |
| `{fraksjon}_dager_igjen` | `14` | Dager til neste tømming |
| `{fraksjon}_datoer` | `2025-03-12, 2025-03-26` | Alle kommende datoer |
| `{fraksjon}_forrige` | `2025-02-26` | Forrige tømmedato |
| `{fraksjon}_intervall` | `14` | Dager mellom tømminger |
| `{fraksjon}_progress` | `50` | Prosent gjennom syklusen (0–100) |
| `kommende_tømminger` | `Restavfall om 3 dager; Papir om 10 dager` | Oppsummering av de 3 neste |

Fraksjonsnavnene er lowercase med understrek, f.eks. `restavfall`, `papir`, `glass_og_metall`.

### Binære sensorer – én per fraksjon

Slår seg **på** kvelden før tømming (kl. 13:00) og **av** tømmingsdagen kl. 14:00. Nyttig for automations og varsler.

**Eksempel:** `binary_sensor.restavfall_tomming`

---

## Dashboard-eksempler

### Mushroom Cards

#### Enkel progress-visning

```yaml
type: custom:mushroom-template-card
entity: sensor.neste_tomming
primary: Restavfall
secondary: >-
  {{ state_attr('sensor.neste_tomming', 'restavfall_progress') }}% ·
  {{ state_attr('sensor.neste_tomming', 'restavfall_dager_igjen') }} dager igjen
icon: mdi:trash-can
icon_color: |-
  {% set p = state_attr('sensor.neste_tomming', 'restavfall_progress') | int(0) %}
  {% if p > 80 %}red
  {% elif p > 50 %}orange
  {% else %}green
  {% endif %}
```

#### Med progress-bakgrunn (krever card-mod)

```yaml
type: custom:mushroom-template-card
entity: sensor.neste_tomming
primary: Restavfall
secondary: >-
  {{ state_attr('sensor.neste_tomming', 'restavfall_neste') }}
icon: mdi:trash-can
icon_color: |-
  {% set p = state_attr('sensor.neste_tomming', 'restavfall_progress') | int(0) %}
  {% if p > 80 %}red{% elif p > 50 %}orange{% else %}green{% endif %}
card_mod:
  style:
    mushroom-shape-icon$: |
      .shape {
        --shape-color: none !important;
        background: linear-gradient(
          to right,
          {% set p = state_attr('sensor.neste_tomming', 'restavfall_progress') | int(0) %}
          {% if p > 80 %}rgba(var(--rgb-red), 0.3)
          {% elif p > 50 %}rgba(var(--rgb-orange), 0.3)
          {% else %}rgba(var(--rgb-green), 0.3)
          {% endif %} {{ p }}%,
          rgba(var(--rgb-disabled), 0.2) {{ p }}%
        ) !important;
      }
```

#### Alle fraksjoner i en stack

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-title-card
    title: Tømmekalender
    subtitle: "{{ states('sensor.neste_tomming') }}"

  - type: custom:mushroom-template-card
    entity: sensor.neste_tomming
    primary: Restavfall
    secondary: "{{ state_attr('sensor.neste_tomming', 'restavfall_dager_igjen') }} dager"
    icon: mdi:trash-can
    icon_color: |-
      {% set p = state_attr('sensor.neste_tomming', 'restavfall_progress') | int(0) %}
      {% if p > 80 %}red{% elif p > 50 %}orange{% else %}green{% endif %}

  - type: custom:mushroom-template-card
    entity: sensor.neste_tomming
    primary: Papir
    secondary: "{{ state_attr('sensor.neste_tomming', 'papir_dager_igjen') }} dager"
    icon: mdi:newspaper-variant-outline
    icon_color: |-
      {% set p = state_attr('sensor.neste_tomming', 'papir_progress') | int(0) %}
      {% if p > 80 %}blue{% elif p > 50 %}light-blue{% else %}cyan{% endif %}

  - type: custom:mushroom-template-card
    entity: sensor.neste_tomming
    primary: Plastemballasje
    secondary: "{{ state_attr('sensor.neste_tomming', 'plastemballasje_dager_igjen') }} dager"
    icon: mdi:bottle-soda-outline
    icon_color: |-
      {% set p = state_attr('sensor.neste_tomming', 'plastemballasje_progress') | int(0) %}
      {% if p > 80 %}purple{% elif p > 50 %}deep-purple{% else %}indigo{% endif %}
```

---

### ApexCharts Card

#### Radial gauge – alle fraksjoner

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Tømmesyklus
chart_type: radialBar
series:
  - entity: sensor.neste_tomming
    attribute: restavfall_progress
    name: Restavfall
    color: "#4CAF50"
  - entity: sensor.neste_tomming
    attribute: papir_progress
    name: Papir
    color: "#2196F3"
  - entity: sensor.neste_tomming
    attribute: plastemballasje_progress
    name: Plast
    color: "#9C27B0"
apex_config:
  plotOptions:
    radialBar:
      hollow:
        size: "40%"
      dataLabels:
        name:
          fontSize: "14px"
        value:
          fontSize: "20px"
          formatter: |
            EVAL:function(val) { return val + "%"; }
```

---

### Bar Card

```yaml
type: custom:bar-card
entities:
  - entity: sensor.neste_tomming
    attribute: restavfall_progress
    name: Restavfall
    icon: mdi:trash-can
    severity:
      - color: green
        from: 0
        to: 50
      - color: orange
        from: 51
        to: 80
      - color: red
        from: 81
        to: 100
  - entity: sensor.neste_tomming
    attribute: papir_progress
    name: Papir
    icon: mdi:newspaper-variant-outline
    color: "#2196F3"
  - entity: sensor.neste_tomming
    attribute: plastemballasje_progress
    name: Plast
    icon: mdi:bottle-soda-outline
    color: "#9C27B0"
max: 100
positions:
  icon: inside
  indicator: "off"
  name: inside
```

---

### Gauge Card (innebygd)

Viser antall dager igjen til neste tømming. Fargen reflekterer hvor mye tid det er igjen – rød når tømmingen er nær.

```yaml
type: gauge
entity: sensor.neste_tomming
attribute: restavfall_dager_igjen
name: Restavfall
unit: "dager"
min: 0
max: 14
needle: true
severity:
  red: 0
  yellow: 3
  green: 7
```

> **Tips:** Juster `max` etter hentehyppigheten for fraksjonen (f.eks. `7` for ukentlig, `14` for annenhver uke). `needle: true` gjør at viseren peker på verdien og fargene vises korrekt.

---

### Template-sensor (valgfritt)

Hvis du ønsker separate sensorer per fraksjon i stedet for attributter:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "Restavfall Progress"
        unique_id: restavfall_progress
        unit_of_measurement: "%"
        state: "{{ state_attr('sensor.neste_tomming', 'restavfall_progress') | int(0) }}"
        icon: mdi:trash-can
        attributes:
          forrige: "{{ state_attr('sensor.neste_tomming', 'restavfall_forrige') }}"
          neste: "{{ state_attr('sensor.neste_tomming', 'restavfall_neste') }}"
          intervall: "{{ state_attr('sensor.neste_tomming', 'restavfall_intervall') }}"
```

---

## Anbefalte ikoner per fraksjon

| Fraksjon | Anbefalt ikon |
|---|---|
| Restavfall | `mdi:trash-can` |
| Papir | `mdi:newspaper-variant-outline` |
| Plastemballasje | `mdi:bottle-soda-outline` |
| Glass og metall | `mdi:bottle-wine-outline` |
| Matavfall | `mdi:food-apple-outline` |
| Farlig avfall | `mdi:biohazard` |

---

## Feilsøking

### Attributt viser «unknown»
- Sjekk at fraksjonsnavnet er korrekt (lowercase, understrek i stedet for mellomrom)
- Bruk **Developer Tools → States** og søk etter `sensor.neste_tomming` for å se alle tilgjengelige attributter

### Progress viser 0 %
- Ved første installasjon estimeres forrige dato fra intervallet mellom de to neste datoene
- Hvis det bare finnes én fremtidig dato, kan ikke progress beregnes
- Vent til en tømming har passert for nøyaktig historikk

### Integrasjonen laster ikke data
- Sjekk at adressen er innenfor Remidts dekningsområde
- Se Home Assistant-loggen (**Innstillinger → System → Logger**) for feilmeldinger

---

## Lisens

MIT
