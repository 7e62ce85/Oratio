import { initializeSite } from "@utils/app";
import { hydrate } from "inferno-hydrate";
import { render } from "inferno";
import { BrowserRouter } from "inferno-router";
import App from "../shared/components/app/app";
import { lazyHighlightjs } from "../shared/lazy-highlightjs";
import {
  I18NextService,
  loadUserLanguage,
} from "../shared/services/I18NextService";
import { verifyDynamicImports } from "../shared/dynamic-imports";

import "bootstrap/js/dist/collapse";
import "bootstrap/js/dist/dropdown";
import "bootstrap/js/dist/modal";

async function startClient() {
  // Allows to test imports from the browser console.
  window.checkLazyScripts = () => {
    verifyDynamicImports(true).then(x => console.log(x));
  };

  window.history.scrollRestoration = "manual";

  initializeSite(window.isoData.site_res);

  lazyHighlightjs.enableLazyLoading();

  // Detect language before hydrate so we know if SSR language matches
  await loadUserLanguage();
  const clientLang = I18NextService.i18n.resolvedLanguage;

  // Check what language SSR used (embedded in <html lang="...">)
  const ssrLang = document.documentElement.lang;
  // If languages mismatch, we need a full render to show correct translations
  const languageMismatch = !!(
    ssrLang &&
    clientLang &&
    ssrLang !== clientLang
  );

  const wrapper = (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );

  const root = document.getElementById("root");

  if (root) {
    // If SSR rendered in a different language than the user's setting,
    // use full render instead of hydrate to force correct translations.
    if (languageMismatch) {
      render(wrapper, root);
    } else {
      hydrate(wrapper, root);
    }

    root.dispatchEvent(new CustomEvent("lemmy-hydrated", { bubbles: true }));
  }
}

startClient();
