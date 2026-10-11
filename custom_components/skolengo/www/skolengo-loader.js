/**
 * Chargeur des cartes Skolengo (voir skolengo-cards.js).
 *
 * Observé sur Safari : le module des cartes pouvait être "chargé" (import
 * résolu) sans que les éléments soient définis, ce qui laissait toutes les
 * cartes en "Erreur de configuration" jusqu'à un rafraîchissement manuel.
 * Ce chargeur importe donc les cartes sous une URL unique à chaque chargement
 * de page (aucun module ni cache réutilisé), vérifie que les éléments sont
 * bien définis (sinon réessaie), puis force Lovelace à reconstruire les cartes
 * restées en erreur.
 */
(function () {
  "use strict";

  const CARDS_URL = "/skolengo_static/skolengo-cards.js";
  const PROBE_TAG = "skolengo-timetable-card";
  const MAX_ATTEMPTS = 3;

  // Lovelace shows a card whose element wasn't defined yet as an error card
  // and normally rebuilds it once the element appears; do it ourselves in
  // case that didn't happen.
  function rebuildErrorCards() {
    const walk = (root) =>
      Array.from(root.querySelectorAll("*")).flatMap((el) => [
        el,
        ...(el.shadowRoot ? walk(el.shadowRoot) : []),
      ]);
    for (const el of walk(document)) {
      if (el.localName !== "hui-error-card") continue;
      const message = String((el._config && el._config.message) || "");
      if (!message.includes("Custom element doesn't exist: skolengo-")) continue;
      el.dispatchEvent(new CustomEvent("ll-rebuild", { bubbles: true, composed: true }));
    }
  }

  async function load(attempt) {
    try {
      await import(`${CARDS_URL}?t=${Date.now()}-${attempt}`);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("Skolengo : échec du chargement des cartes", err);
    }
    if (customElements.get(PROBE_TAG)) {
      // Let Lovelace's own rebuild happen first, then catch the leftovers.
      setTimeout(rebuildErrorCards, 300);
      setTimeout(rebuildErrorCards, 2000);
      return;
    }
    if (attempt < MAX_ATTEMPTS) {
      setTimeout(() => load(attempt + 1), 1000 * attempt);
    }
  }

  load(1);
})();
