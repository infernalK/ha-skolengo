/**
 * Cartes Lovelace bundlées avec l'intégration Home Assistant "Skolengo".
 *
 * Fichier JavaScript unique, sans dépendance externe ni étape de build,
 * chargé automatiquement par l'intégration (voir custom_components/skolengo/__init__.py).
 *
 * S'inspire des cartes de https://github.com/delphiki/lovelace-pronote,
 * adaptées au modèle de données de Skolengo (voir README.md).
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Utilitaires partagés
  // ---------------------------------------------------------------------

  const FR_DATE_FMT = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const FR_DATE_SHORT_FMT = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
  });
  const FR_TIME_FMT = new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Ne fait jamais confiance au HTML renvoyé par l'API : on le convertit en
  // texte brut (via un élément détaché, sans l'insérer dans le DOM visible)
  // avant de le ré-échapper pour l'affichage, afin d'éviter tout risque de
  // XSS si la réponse de l'API était compromise ou malformée.
  function htmlToPlainText(html) {
    if (!html) return "";
    const tmp = document.createElement("div");
    tmp.innerHTML = String(html)
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n")
      .replace(/<[^>]*>/g, " ");
    const text = tmp.textContent || tmp.innerText || "";
    return text.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trim();
  }

  function parseDate(value) {
    if (!value) return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }

  function formatDayHeader(dayIso) {
    const d = parseDate(dayIso);
    if (!d) return "";
    const label = FR_DATE_FMT.format(d);
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  function formatDateShort(iso) {
    const d = parseDate(iso);
    return d ? FR_DATE_SHORT_FMT.format(d) : "";
  }

  function formatTime(iso) {
    const d = parseDate(iso);
    return d ? FR_TIME_FMT.format(d) : "";
  }

  function isSameDay(a, b) {
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function relativeDayLabel(iso) {
    const d = parseDate(iso);
    if (!d) return null;
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(now.getDate() + 1);
    if (isSameDay(d, now)) return "Pour aujourd'hui";
    if (isSameDay(d, tomorrow)) return "Pour demain";
    return null;
  }

  function isValidColor(color) {
    if (!color || typeof color !== "string") return false;
    return /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(color.trim()) || /^[a-z]+$/i.test(color.trim());
  }

  function subjectColor(color) {
    return isValidColor(color) ? color : "var(--primary-color)";
  }

  const BASE_STYLE = `
    :host {
      display: block;
    }
    .skolengo-card {
      background: var(--ha-card-background, var(--card-background-color, white));
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, none);
      border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
      color: var(--primary-text-color);
      padding: 16px;
      font-family: var(--paper-font-body1_-_font-family, inherit);
      box-sizing: border-box;
    }
    .skolengo-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .skolengo-title {
      font-size: 1.2em;
      font-weight: 500;
      color: var(--primary-text-color);
      text-transform: capitalize;
    }
    .skolengo-subtitle {
      font-size: 0.95em;
      color: var(--secondary-text-color);
    }
    .skolengo-empty {
      color: var(--secondary-text-color);
      font-style: italic;
      padding: 8px 0;
    }
    .skolengo-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .skolengo-item {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      padding: 8px 10px;
      border-left: 4px solid var(--item-color, var(--primary-color));
      border-radius: 4px;
      background: var(--secondary-background-color, rgba(0,0,0,0.03));
    }
    .skolengo-item.is-dimmed {
      opacity: 0.55;
    }
    .skolengo-item-main {
      flex: 1;
      min-width: 0;
    }
    .skolengo-item-top {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
      flex-wrap: wrap;
    }
    .skolengo-subject {
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .skolengo-meta {
      color: var(--secondary-text-color);
      font-size: 0.9em;
    }
    .skolengo-line {
      color: var(--secondary-text-color);
      font-size: 0.9em;
      margin-top: 2px;
    }
    .skolengo-badge {
      display: inline-block;
      font-size: 0.78em;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 10px;
      white-space: nowrap;
    }
    .skolengo-badge.error {
      background: color-mix(in srgb, var(--error-color) 18%, transparent);
      color: var(--error-color);
    }
    .skolengo-badge.warning {
      background: color-mix(in srgb, var(--warning-color, orange) 18%, transparent);
      color: var(--warning-color, orange);
    }
    .skolengo-badge.success {
      background: color-mix(in srgb, var(--success-color, green) 18%, transparent);
      color: var(--success-color, green);
    }
    .skolengo-badge.neutral {
      background: color-mix(in srgb, var(--primary-color) 15%, transparent);
      color: var(--primary-color);
    }
    .skolengo-strike {
      text-decoration: line-through;
    }
    .skolengo-mark {
      font-weight: 600;
      font-size: 1.05em;
    }
    .skolengo-skills {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 4px;
    }
    .skolengo-skill-chip {
      font-size: 0.78em;
      padding: 2px 8px;
      border-radius: 10px;
      background: color-mix(in srgb, var(--item-color, var(--primary-color)) 18%, transparent);
      color: var(--primary-text-color);
    }
    .skolengo-done-section {
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px solid var(--divider-color);
    }
    .skolengo-done-section .skolengo-item {
      opacity: 0.6;
      font-size: 0.92em;
    }
    .skolengo-check {
      color: var(--success-color, green);
      margin-right: 4px;
    }
  `;

  function cardWrapper(bodyHtml) {
    return `<style>${BASE_STYLE}</style><div class="skolengo-card">${bodyHtml}</div>`;
  }

  // Entity ids are generated by Home Assistant from each sensor's
  // (French) display name, not from any stable internal key -- so
  // guessing them by suffix is unreliable. Instead, a sensor is
  // considered "compatible" with a given card when its state attributes
  // contain (at least one of) the specific list key(s) that card reads,
  // e.g. "lessons" for the timetable card. This is also used to build
  // the entity picker's `include_entities`, so users only ever see
  // Skolengo entities that actually work with the card they're editing.
  function findCompatibleEntities(hass, attrKeys) {
    if (!hass || !hass.states) return [];
    const keys = Array.isArray(attrKeys) ? attrKeys : [attrKeys];
    return Object.keys(hass.states).filter((id) => {
      if (!id.startsWith("sensor.")) return false;
      const attrs = hass.states[id].attributes || {};
      return keys.some((k) => Array.isArray(attrs[k]));
    });
  }

  function findFirstCompatibleEntity(hass, attrKeys) {
    return findCompatibleEntities(hass, attrKeys)[0] || "";
  }

  // ---------------------------------------------------------------------
  // Éditeur visuel de configuration (partagé par les 4 cartes)
  //
  // Utilise le composant HA `ha-form`, déjà chargé par le frontend HA
  // (pas besoin de l'importer), pour éviter de coder un éditeur "à la
  // main" pour chaque option. `getConfigElement`/`getStubConfig` sur
  // chaque carte sont le contrat standard attendu par Lovelace pour
  // proposer l'édition visuelle plutôt que forcer l'édition YAML.
  // ---------------------------------------------------------------------

  const FIELD_LABELS = {
    entity: "Entité",
    title: "Titre (optionnel)",
    display_header: "Afficher l'en-tête",
    display_teacher: "Afficher le(s) professeur(s)",
    display_classroom: "Afficher la salle",
    dim_ended_lessons: "Estomper les cours terminés",
    display_day_hours: "Afficher les horaires",
    display_done_homework: "Afficher les devoirs déjà faits",
    reduce_done_homework: "Réduire l'affichage des devoirs faits",
    max_items: "Nombre maximum d'éléments",
    display_date: "Afficher la date",
    display_coefficient: "Afficher le coefficient",
    display_class_average: "Afficher la moyenne de classe",
    display_comment: "Afficher le commentaire",
  };

  function computeFieldLabel(schema) {
    return FIELD_LABELS[schema.name] || schema.name;
  }

  function createConfigEditor(extraFields, attrKeys) {
    return class extends HTMLElement {
      setConfig(config) {
        this._config = config || {};
        this._render();
      }

      set hass(hass) {
        this._hass = hass;
        this._render();
      }

      connectedCallback() {
        this._render();
      }

      _render() {
        if (!this._hass || !this._config) return;
        const compatibleEntities = findCompatibleEntities(this._hass, attrKeys);
        // Always keep the currently-configured entity selectable even if
        // it doesn't (yet) match -- e.g. right after adding the card,
        // before the coordinator's first data fetch has populated the
        // attribute this filter looks for.
        if (this._config.entity && !compatibleEntities.includes(this._config.entity)) {
          compatibleEntities.push(this._config.entity);
        }
        const schema = [
          { name: "entity", required: true, selector: { entity: { include_entities: compatibleEntities } } },
          ...extraFields,
        ];
        if (!this._form) {
          this._form = document.createElement("ha-form");
          this._form.addEventListener("value-changed", (ev) => {
            ev.stopPropagation();
            this._config = ev.detail.value;
            this.dispatchEvent(
              new CustomEvent("config-changed", {
                detail: { config: this._config },
                bubbles: true,
                composed: true,
              })
            );
          });
          this.appendChild(this._form);
        }
        this._form.hass = this._hass;
        this._form.schema = schema;
        this._form.data = this._config;
        this._form.computeLabel = computeFieldLabel;
      }
    };
  }

  const TITLE_FIELD = { name: "title", selector: { text: {} } };
  const MAX_ITEMS_FIELD = { name: "max_items", selector: { number: { mode: "box", min: 1, max: 100 } } };
  const boolField = (name) => ({ name, selector: { boolean: {} } });

  // ---------------------------------------------------------------------
  // skolengo-timetable-card
  // ---------------------------------------------------------------------

  class SkolengoTimetableCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error('"entity" est obligatoire dans la configuration de la carte');
      }
      this._config = {
        display_header: true,
        display_teacher: true,
        display_classroom: true,
        dim_ended_lessons: true,
        display_day_hours: true,
        ...config,
      };
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      const stateObj = this._hass && this._hass.states[this._config.entity];
      const lessons = (stateObj && stateObj.attributes.lessons) || [];
      return 1 + Math.max(1, lessons.length);
    }

    connectedCallback() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._render();
    }

    _render() {
      if (!this.shadowRoot) return;
      if (!this._hass || !this._config) return;
      const stateObj = this._hass.states[this._config.entity];
      if (!stateObj) {
        this.shadowRoot.innerHTML = cardWrapper(
          `<div class="skolengo-empty">Entité "${escapeHtml(this._config.entity)}" introuvable.</div>`
        );
        return;
      }

      const attrs = stateObj.attributes || {};
      const lessons = Array.isArray(attrs.lessons) ? attrs.lessons.slice() : [];
      lessons.sort((a, b) => (a.start || "").localeCompare(b.start || ""));

      let html = "";
      if (this._config.display_header) {
        const title = this._config.title || "Emploi du temps";
        const dayLabel = formatDayHeader(attrs.day);
        html += `<div class="skolengo-header">
          <span class="skolengo-title">${escapeHtml(title)}</span>
          <span class="skolengo-subtitle">${escapeHtml(dayLabel)}</span>
        </div>`;
      }

      if (!lessons.length) {
        html += `<div class="skolengo-empty">Aucun cours prévu</div>`;
      } else {
        const now = new Date();
        html += '<div class="skolengo-list">';
        for (const lesson of lessons) {
          const color = subjectColor(lesson.subject_color);
          const end = parseDate(lesson.end);
          const ended = this._config.dim_ended_lessons && end && end < now;
          const canceled = !!lesson.canceled;
          const teachers = Array.isArray(lesson.teachers)
            ? lesson.teachers.filter(Boolean).join(", ")
            : "";

          let timeLine = "";
          if (this._config.display_day_hours) {
            timeLine = `${formatTime(lesson.start)} - ${formatTime(lesson.end)}`;
          }
          const metaBits = [];
          if (this._config.display_classroom && lesson.location) {
            metaBits.push(escapeHtml(lesson.location));
          }
          if (this._config.display_teacher && teachers) {
            metaBits.push(escapeHtml(teachers));
          }

          html += `<div class="skolengo-item${ended && !canceled ? " is-dimmed" : ""}" style="--item-color:${color}">
            <div class="skolengo-item-main">
              <div class="skolengo-item-top">
                <span class="skolengo-subject${canceled ? " skolengo-strike" : ""}">${escapeHtml(
            lesson.subject || "Cours"
          )}</span>
                ${
                  canceled
                    ? '<span class="skolengo-badge error">Annulé</span>'
                    : `<span class="skolengo-meta">${escapeHtml(timeLine)}</span>`
                }
              </div>
              ${canceled && timeLine ? `<div class="skolengo-line">${escapeHtml(timeLine)}</div>` : ""}
              ${metaBits.length ? `<div class="skolengo-line">${metaBits.join(" · ")}</div>` : ""}
            </div>
          </div>`;
        }
        html += "</div>";
      }

      this.shadowRoot.innerHTML = cardWrapper(html);
    }

    static getConfigElement() {
      return document.createElement("skolengo-timetable-card-editor");
    }

    static getStubConfig(hass) {
      return { entity: findFirstCompatibleEntity(hass, "lessons") };
    }
  }
  customElements.define("skolengo-timetable-card", SkolengoTimetableCard);
  customElements.define(
    "skolengo-timetable-card-editor",
    createConfigEditor(
      [
        TITLE_FIELD,
        boolField("display_header"),
        boolField("display_teacher"),
        boolField("display_classroom"),
        boolField("dim_ended_lessons"),
        boolField("display_day_hours"),
      ],
      "lessons"
    )
  );

  // ---------------------------------------------------------------------
  // skolengo-homework-card
  // ---------------------------------------------------------------------

  class SkolengoHomeworkCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error('"entity" est obligatoire dans la configuration de la carte');
      }
      this._config = {
        display_header: true,
        display_done_homework: false,
        reduce_done_homework: true,
        max_items: 20,
        ...config,
      };
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      const stateObj = this._hass && this._hass.states[this._config.entity];
      const assignments = (stateObj && stateObj.attributes.assignments) || [];
      return 1 + Math.max(1, assignments.length);
    }

    connectedCallback() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._render();
    }

    _renderItem(hw, dimmed) {
      const color = subjectColor(hw.subject_color);
      const relLabel = !hw.done ? relativeDayLabel(hw.due_date) : null;
      const dateLabel = formatDateShort(hw.due_date);
      const text = htmlToPlainText(hw.html);
      return `<div class="skolengo-item${dimmed ? " is-dimmed" : ""}" style="--item-color:${color}">
        <div class="skolengo-item-main">
          <div class="skolengo-item-top">
            <span class="skolengo-subject">${hw.done ? '<span class="skolengo-check">✔</span>' : ""}${escapeHtml(
        hw.subject || "Devoir"
      )}</span>
            <span class="skolengo-meta">${
              relLabel ? `<span class="skolengo-badge neutral">${escapeHtml(relLabel)}</span> ` : ""
            }${escapeHtml(dateLabel)}</span>
          </div>
          ${hw.title ? `<div class="skolengo-line">${escapeHtml(hw.title)}</div>` : ""}
          ${text ? `<div class="skolengo-line">${escapeHtml(text)}</div>` : ""}
          ${hw.teacher ? `<div class="skolengo-line">${escapeHtml(hw.teacher)}</div>` : ""}
        </div>
      </div>`;
    }

    _render() {
      if (!this.shadowRoot) return;
      if (!this._hass || !this._config) return;
      const stateObj = this._hass.states[this._config.entity];
      if (!stateObj) {
        this.shadowRoot.innerHTML = cardWrapper(
          `<div class="skolengo-empty">Entité "${escapeHtml(this._config.entity)}" introuvable.</div>`
        );
        return;
      }

      const attrs = stateObj.attributes || {};
      const assignments = (Array.isArray(attrs.assignments) ? attrs.assignments.slice() : []).sort(
        (a, b) => (a.due_date || "").localeCompare(b.due_date || "")
      );
      const doneAssignments = Array.isArray(attrs.done_assignments) ? attrs.done_assignments : [];
      const maxItems = this._config.max_items;

      let html = "";
      if (this._config.display_header) {
        const title = this._config.title || "Devoirs";
        html += `<div class="skolengo-header">
          <span class="skolengo-title">${escapeHtml(title)}</span>
          <span class="skolengo-subtitle">${assignments.length} à faire</span>
        </div>`;
      }

      if (!assignments.length) {
        html += `<div class="skolengo-empty">Aucun devoir à faire</div>`;
      } else {
        html += '<div class="skolengo-list">';
        for (const hw of assignments.slice(0, maxItems)) {
          html += this._renderItem(hw, false);
        }
        html += "</div>";
      }

      if (this._config.display_done_homework && doneAssignments.length) {
        html += '<div class="skolengo-done-section"><div class="skolengo-list">';
        for (const hw of doneAssignments.slice(0, maxItems)) {
          html += this._renderItem(hw, this._config.reduce_done_homework);
        }
        html += "</div></div>";
      }

      this.shadowRoot.innerHTML = cardWrapper(html);
    }

    static getConfigElement() {
      return document.createElement("skolengo-homework-card-editor");
    }

    static getStubConfig(hass) {
      return { entity: findFirstCompatibleEntity(hass, "assignments") };
    }
  }
  customElements.define("skolengo-homework-card", SkolengoHomeworkCard);
  customElements.define(
    "skolengo-homework-card-editor",
    createConfigEditor(
      [
        TITLE_FIELD,
        boolField("display_header"),
        boolField("display_done_homework"),
        boolField("reduce_done_homework"),
        MAX_ITEMS_FIELD,
      ],
      "assignments"
    )
  );

  // ---------------------------------------------------------------------
  // skolengo-evaluations-card ("Notes")
  // ---------------------------------------------------------------------

  class SkolengoEvaluationsCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error('"entity" est obligatoire dans la configuration de la carte');
      }
      this._config = {
        title: "Notes",
        display_header: true,
        display_date: true,
        display_coefficient: true,
        display_class_average: true,
        max_items: 15,
        ...config,
      };
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      const stateObj = this._hass && this._hass.states[this._config.entity];
      const evaluations = (stateObj && stateObj.attributes.evaluations) || [];
      return 1 + Math.max(1, evaluations.length);
    }

    connectedCallback() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._render();
    }

    _render() {
      if (!this.shadowRoot) return;
      if (!this._hass || !this._config) return;
      const stateObj = this._hass.states[this._config.entity];
      if (!stateObj) {
        this.shadowRoot.innerHTML = cardWrapper(
          `<div class="skolengo-empty">Entité "${escapeHtml(this._config.entity)}" introuvable.</div>`
        );
        return;
      }

      const attrs = stateObj.attributes || {};
      const evaluations = Array.isArray(attrs.evaluations) ? attrs.evaluations : [];

      let html = "";
      if (this._config.display_header) {
        // Computed client-side from the numeric marks in `evaluations`
        // (not read from the entity's state, since this card can be
        // pointed at either the "Notes" sensor, whose state is a count,
        // or the separate "Moyenne générale" sensor).
        const numericMarks = evaluations
          .map((ev) => ev.mark)
          .filter((m) => typeof m === "number" && !isNaN(m));
        const avgLabel = numericMarks.length
          ? `${(numericMarks.reduce((a, b) => a + b, 0) / numericMarks.length).toFixed(2)}/20`
          : "Moyenne indisponible";
        html += `<div class="skolengo-header">
          <span class="skolengo-title">${escapeHtml(this._config.title)}</span>
          <span class="skolengo-subtitle">${escapeHtml(avgLabel)}</span>
        </div>`;
      }

      if (!evaluations.length) {
        html += `<div class="skolengo-empty">Aucune note disponible</div>`;
      } else {
        html += '<div class="skolengo-list">';
        for (const ev of evaluations.slice(0, this._config.max_items)) {
          const color = subjectColor(ev.subject_color);
          const metaBits = [];
          if (this._config.display_date && ev.date) {
            metaBits.push(escapeHtml(formatDateShort(ev.date)));
          }
          if (this._config.display_coefficient && ev.coefficient) {
            metaBits.push(`Coef. ${escapeHtml(ev.coefficient)}`);
          }
          if (this._config.display_class_average && ev.class_average !== null && ev.class_average !== undefined) {
            metaBits.push(`Moy. classe : ${escapeHtml(ev.class_average)}`);
          }

          let markHtml;
          if (ev.mark !== null && ev.mark !== undefined) {
            const scale = ev.scale || 20;
            markHtml = `<span class="skolengo-mark">${escapeHtml(ev.mark)}/${escapeHtml(scale)}</span>`;
          } else if (Array.isArray(ev.skills) && ev.skills.length) {
            markHtml = `<div class="skolengo-skills">${ev.skills
              .map(
                (s) =>
                  `<span class="skolengo-skill-chip">${escapeHtml(s.skill || "Compétence")}${
                    s.level ? " : " + escapeHtml(s.level) : ""
                  }</span>`
              )
              .join("")}</div>`;
          } else {
            markHtml = `<span class="skolengo-meta">Non noté</span>`;
          }

          html += `<div class="skolengo-item" style="--item-color:${color}">
            <div class="skolengo-item-main">
              <div class="skolengo-item-top">
                <span class="skolengo-subject">${escapeHtml(ev.subject || "Matière")}</span>
                ${Array.isArray(ev.skills) && ev.skills.length && (ev.mark === null || ev.mark === undefined) ? "" : markHtml}
              </div>
              ${ev.title ? `<div class="skolengo-line">${escapeHtml(ev.title)}</div>` : ""}
              ${metaBits.length ? `<div class="skolengo-line">${metaBits.join(" · ")}</div>` : ""}
              ${Array.isArray(ev.skills) && ev.skills.length && (ev.mark === null || ev.mark === undefined) ? markHtml : ""}
            </div>
          </div>`;
        }
        html += "</div>";
      }

      this.shadowRoot.innerHTML = cardWrapper(html);
    }

    static getConfigElement() {
      return document.createElement("skolengo-evaluations-card-editor");
    }

    static getStubConfig(hass) {
      return { entity: findFirstCompatibleEntity(hass, "evaluations"), title: "Notes" };
    }
  }
  customElements.define("skolengo-evaluations-card", SkolengoEvaluationsCard);
  customElements.define(
    "skolengo-evaluations-card-editor",
    createConfigEditor(
      [
        TITLE_FIELD,
        boolField("display_header"),
        boolField("display_date"),
        boolField("display_coefficient"),
        boolField("display_class_average"),
        MAX_ITEMS_FIELD,
      ],
      "evaluations"
    )
  );

  // ---------------------------------------------------------------------
  // skolengo-absences-card
  //
  // Generic: works for any of the three "vie scolaire" sensors, which all
  // share the same item shape but expose it under a different attribute
  // key -- absences ("absences"), retards ("delays") or dispenses
  // ("exemptions"). The card looks for whichever key is present, in that
  // order, so pointing it at sensor.skolengo_..._delays or
  // sensor.skolengo_..._exemptions "just works" without a separate card.
  // ---------------------------------------------------------------------

  const ABSENCE_LIST_KEYS = ["absences", "delays", "exemptions"];

  function statusBadge(status) {
    if (!status) return "";
    if (status === "LOCKED") {
      return `<span class="skolengo-badge success">Clôturé</span>`;
    }
    if (status === "NEW" || status === "IN_PROGRESS") {
      return `<span class="skolengo-badge warning">En cours de traitement</span>`;
    }
    return `<span class="skolengo-badge neutral">${escapeHtml(status)}</span>`;
  }

  class SkolengoAbsencesCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error('"entity" est obligatoire dans la configuration de la carte');
      }
      this._config = {
        display_header: true,
        display_comment: true,
        max_items: 20,
        ...config,
      };
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    getCardSize() {
      const stateObj = this._hass && this._hass.states[this._config.entity];
      const attrs = (stateObj && stateObj.attributes) || {};
      const listKey = ABSENCE_LIST_KEYS.find((key) => Array.isArray(attrs[key]));
      const items = listKey ? attrs[listKey] : [];
      return 1 + Math.max(1, items.length);
    }

    connectedCallback() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._render();
    }

    _render() {
      if (!this.shadowRoot) return;
      if (!this._hass || !this._config) return;
      const stateObj = this._hass.states[this._config.entity];
      if (!stateObj) {
        this.shadowRoot.innerHTML = cardWrapper(
          `<div class="skolengo-empty">Entité "${escapeHtml(this._config.entity)}" introuvable.</div>`
        );
        return;
      }

      const attrs = stateObj.attributes || {};
      const listKey = ABSENCE_LIST_KEYS.find((key) => Array.isArray(attrs[key]));
      const items = listKey ? attrs[listKey] : [];
      const defaultTitles = { absences: "Absences", delays: "Retards", exemptions: "Dispenses" };
      const defaultEmpty = {
        absences: "Aucune absence enregistrée",
        delays: "Aucun retard enregistré",
        exemptions: "Aucune dispense enregistrée",
      };

      let html = "";
      if (this._config.display_header) {
        const title = this._config.title || defaultTitles[listKey] || "Absences";
        html += `<div class="skolengo-header">
          <span class="skolengo-title">${escapeHtml(title)}</span>
          <span class="skolengo-subtitle">${items.length}</span>
        </div>`;
      }

      if (!items.length) {
        html += `<div class="skolengo-empty">${escapeHtml(
          defaultEmpty[listKey] || "Aucune absence enregistrée"
        )}</div>`;
      } else {
        html += '<div class="skolengo-list">';
        for (const item of items.slice(0, this._config.max_items)) {
          const start = parseDate(item.start);
          const end = parseDate(item.end);
          const period =
            start && end
              ? `${FR_DATE_SHORT_FMT.format(start)} ${FR_TIME_FMT.format(start)} - ${
                  isSameDay(start, end) ? "" : FR_DATE_SHORT_FMT.format(end) + " "
                }${FR_TIME_FMT.format(end)}`
              : formatDateShort(item.start);

          html += `<div class="skolengo-item" style="--item-color:var(--primary-color)">
            <div class="skolengo-item-main">
              <div class="skolengo-item-top">
                <span class="skolengo-subject">${escapeHtml(period)}</span>
                ${statusBadge(item.status)}
              </div>
              ${item.reason ? `<div class="skolengo-line">${escapeHtml(item.reason)}</div>` : ""}
              ${
                this._config.display_comment && item.comment
                  ? `<div class="skolengo-line">${escapeHtml(item.comment)}</div>`
                  : ""
              }
            </div>
          </div>`;
        }
        html += "</div>";
      }

      this.shadowRoot.innerHTML = cardWrapper(html);
    }

    static getConfigElement() {
      return document.createElement("skolengo-absences-card-editor");
    }

    static getStubConfig(hass) {
      return { entity: findFirstCompatibleEntity(hass, ABSENCE_LIST_KEYS) };
    }
  }
  customElements.define("skolengo-absences-card", SkolengoAbsencesCard);
  customElements.define(
    "skolengo-absences-card-editor",
    createConfigEditor(
      [TITLE_FIELD, boolField("display_header"), boolField("display_comment"), MAX_ITEMS_FIELD],
      ABSENCE_LIST_KEYS
    )
  );

  // ---------------------------------------------------------------------
  // Enregistrement dans le sélecteur de cartes Lovelace
  // ---------------------------------------------------------------------

  window.customCards = window.customCards || [];
  window.customCards.push(
    {
      type: "skolengo-timetable-card",
      name: "Skolengo - Emploi du temps",
      description: "Affiche l'emploi du temps du jour (ou du prochain jour d'école) depuis un capteur Skolengo.",
      preview: false,
    },
    {
      type: "skolengo-homework-card",
      name: "Skolengo - Devoirs",
      description: "Affiche les devoirs à faire (et éventuellement déjà faits) depuis un capteur Skolengo.",
      preview: false,
    },
    {
      type: "skolengo-evaluations-card",
      name: "Skolengo - Notes",
      description: "Affiche les notes et évaluations de compétences depuis un capteur Skolengo.",
      preview: false,
    },
    {
      type: "skolengo-absences-card",
      name: "Skolengo - Absences",
      description:
        "Affiche les absences (ou, selon l'entité pointée, les retards / dispenses) depuis un capteur Skolengo.",
      preview: false,
    }
  );
})();
