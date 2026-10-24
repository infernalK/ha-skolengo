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
  const started = Date.now();

  // Diagnostic trace (visible in the browser console, filter on "Skolengo
  // loader"), useful to compare browsers when cards stay in error.
  function log(...args) {
    // eslint-disable-next-line no-console
    console.info(`[Skolengo loader +${Date.now() - started}ms]`, ...args);
  }

  // Lovelace shows a card whose element wasn't defined yet as an error card
  // and normally rebuilds it once the element appears; do it ourselves in
  // case that didn't happen.
  function rebuildErrorCards() {
    const walk = (root) =>
      Array.from(root.querySelectorAll("*")).flatMap((el) => [
        el,
        ...(el.shadowRoot ? walk(el.shadowRoot) : []),
      ]);
    let errorCards = 0;
    let rebuilt = 0;
    for (const el of walk(document)) {
      if (el.localName !== "hui-error-card") continue;
      errorCards++;
      const message = String((el._config && el._config.message) || "");
      if (!message.includes("Custom element doesn't exist: skolengo-")) {
        log("carte en erreur ignorée :", message);
        continue;
      }
      rebuilt++;
      el.dispatchEvent(new CustomEvent("ll-rebuild", { bubbles: true, composed: true }));
    }
    log(`reconstruction : ${rebuilt} carte(s) Skolengo relancée(s) sur ${errorCards} en erreur`);
  }

  // Registry the cards were first defined in. Observed on Firefox: the cards
  // module ran (its console banner was printed) yet customElements.get() no
  // longer found the elements a bit later, while cards from other modules
  // (loaded later) were found -- as if the page's registry had been replaced
  // after our early load. Re-check for a while and import again if needed.
  const initialRegistry = window.customElements;

  async function load(attempt) {
    log(`tentative ${attempt}/${MAX_ATTEMPTS}, readyState=${document.readyState}`);
    try {
      await import(`${CARDS_URL}?t=${Date.now()}-${attempt}`);
      log(`import résolu (tentative ${attempt})`);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("Skolengo : échec du chargement des cartes", err);
      log(`import en échec (tentative ${attempt}) :`, err && (err.message || err));
    }
    const defined = Boolean(customElements.get(PROBE_TAG));
    log(`customElements.get("${PROBE_TAG}") =`, defined);
    if (defined) {
      // Let Lovelace's own rebuild happen first, then catch the leftovers.
      setTimeout(rebuildErrorCards, 300);
      setTimeout(rebuildErrorCards, 2000);
      return;
    }
    if (attempt >= MAX_ATTEMPTS) {
      log("abandon : les cartes ne sont toujours pas définies");
    } else {
      setTimeout(() => load(attempt + 1), 1000 * attempt);
    }
  }

  // Elements lost after a successful load (see above): import again.
  let reloads = 0;
  function watch(delayMs) {
    setTimeout(() => {
      const registrySwapped = window.customElements !== initialRegistry;
      const defined = Boolean(customElements.get(PROBE_TAG));
      log(`contrôle +${delayMs}ms : défini=${defined}, registre remplacé=${registrySwapped}`);
      if (!defined && reloads < 4) {
        reloads++;
        load(MAX_ATTEMPTS).then(() => setTimeout(rebuildErrorCards, 300));
      }
    }, delayMs);
  }

  load(1);
  [1500, 4000, 8000, 15000].forEach(watch);
})();
