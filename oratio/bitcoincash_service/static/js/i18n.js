/**
 * Client-side i18n for BCH Payment Service pages
 * Detects language from: localStorage (i18nextLng) → navigator.language → 'en'
 */
(function() {
  'use strict';

  // Detect user language
  function detectLanguage() {
    // 1. Lemmy UI stores language in localStorage
    try {
      var lng = localStorage.getItem('i18nextLng');
      if (lng) return lng.split('-')[0].split('_')[0].toLowerCase();
    } catch(e) {}
    // 2. Browser language
    var nav = navigator.language || navigator.userLanguage || 'en';
    return nav.split('-')[0].toLowerCase();
  }

  var currentLang = detectLanguage();
  var translations = {};
  var loaded = false;

  function applyTranslations() {
    if (!loaded) return;
    var lang = translations[currentLang] ? currentLang : 'en';
    var t = translations[lang] || {};

    // Replace text in elements with data-i18n attribute
    var elements = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var key = el.getAttribute('data-i18n');
      if (t[key] !== undefined) {
        // Check if element has child elements we should preserve
        if (el.getAttribute('data-i18n-html') === 'true') {
          el.innerHTML = t[key];
        } else {
          el.textContent = t[key];
        }
      }
    }

    // Replace placeholder text
    var placeholders = document.querySelectorAll('[data-i18n-placeholder]');
    for (var j = 0; j < placeholders.length; j++) {
      var ph = placeholders[j];
      var pkey = ph.getAttribute('data-i18n-placeholder');
      if (t[pkey] !== undefined) {
        ph.setAttribute('placeholder', t[pkey]);
      }
    }

    // Replace title attributes
    var titles = document.querySelectorAll('[data-i18n-title]');
    for (var k = 0; k < titles.length; k++) {
      var tl = titles[k];
      var tkey = tl.getAttribute('data-i18n-title');
      if (t[tkey] !== undefined) {
        tl.setAttribute('title', t[tkey]);
      }
    }

    // Set html lang
    document.documentElement.lang = lang;
  }

  // Load translations JSON
  function loadTranslations() {
    var script = document.querySelector('script[src*="i18n.js"]');
    var basePath = '/payments/static/js/';
    
    var xhr = new XMLHttpRequest();
    xhr.open('GET', basePath + 'translations.json', true);
    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4 && xhr.status === 200) {
        try {
          translations = JSON.parse(xhr.responseText);
          loaded = true;
          applyTranslations();
        } catch(e) {
          console.error('i18n: Failed to parse translations', e);
        }
      }
    };
    xhr.send();
  }

  // Language switcher (optional, for future use)
  window.i18nSetLanguage = function(lang) {
    currentLang = lang;
    try { localStorage.setItem('i18nextLng', lang); } catch(e) {}
    applyTranslations();
  };

  window.i18nGetLanguage = function() {
    return currentLang;
  };

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTranslations);
  } else {
    loadTranslations();
  }
})();
