// Транспонирование аккордов прямо в браузере: кнопки −1 / +1 / Сброс и каподастр.
// Сдвиг запоминается для каждой песни, чтобы при следующем открытии не настраивать заново.
(function () {
  'use strict';

  var SHARPS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var FLATS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  var INDEX = {
    C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4, Fb: 4, 'E#': 5, F: 5, 'F#': 6, Gb: 6,
    G: 7, 'G#': 8, Ab: 8, A: 9, 'A#': 10, Bb: 10, B: 11, Cb: 11, 'B#': 0,
    H: 11, 'H#': 0, Hb: 10
  };
  var ROOT = /^([A-H])(#|b)?/;

  /** Сдвигает одну ноту на steps полутонов. useH — писать си как H (русская запись). */
  function shiftNote(note, steps, preferFlats, useH) {
    var index = INDEX[note];
    if (index === undefined) return note;
    var result = (preferFlats ? FLATS : SHARPS)[((index + steps) % 12 + 12) % 12];
    if (useH) {
      if (result === 'B') result = 'H';
      else if (result === 'Bb') result = 'B';
    }
    return result;
  }

  /** Сдвигает аккорд целиком, включая бас после «/» (например, C/G). */
  function shiftChord(chord, steps, useH) {
    if (!steps) return chord;
    return chord.split('/').map(function (part) {
      var match = part.match(ROOT);
      if (!match) return part;
      var root = match[1] + (match[2] || '');
      if (useH && root === 'B') root = 'Bb';  // в русской записи B — это си-бемоль
      var preferFlats = match[2] === 'b';
      return shiftNote(root, steps, preferFlats, useH) + part.slice(match[0].length);
    }).join('/');
  }

  function load(key) {
    try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { return null; }
  }

  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* без памяти тоже работает */ }
  }

  /** Подключает панель транспонирования внутри блока root. */
  function setupTranspose(root) {
    var panel = root.querySelector('[data-transpose]');
    if (!panel) {
      setupExample(root);
      return;
    }
    var chords = root.querySelectorAll('.chord');
    var keyLabel = panel.querySelector('[data-key]');
    var capoSelect = panel.querySelector('[data-capo]');
    var first = panel.dataset.first;
    var useH = Array.prototype.some.call(chords, function (el) { return /^H/.test(el.dataset.chord); });
    var storageKey = 'transpose:' + panel.dataset.track;
    var state = load(storageKey) || { shift: 0, capo: 0 };

    function render() {
      // С каподастром на N ладу аккорды играются на N полутонов ниже, а звучат в выбранной тональности.
      var steps = state.shift - state.capo;
      chords.forEach(function (el) { el.textContent = shiftChord(el.dataset.chord, steps, useH); });
      keyLabel.textContent = shiftChord(first, state.shift, useH);
      capoSelect.value = String(state.capo);
      panel.classList.toggle('changed', state.shift !== 0 || state.capo !== 0);
      save(storageKey, state);
      renderExtras();
    }

    /** Схемы и табы для аккордов в том виде, в каком их сейчас играть. */
    function renderExtras() {
      var shown = [];
      chords.forEach(function (el) {
        if (shown.indexOf(el.textContent) === -1) shown.push(el.textContent);
      });
      root.dataset.shown = JSON.stringify(shown);
      root.dataset.useH = useH ? '1' : '';
      if (window.renderDiagrams) window.renderDiagrams(root, shown, useH);
      if (window.renderTabs) window.renderTabs(root, shown, useH);
    }

    // Цвета схем берутся из темы, поэтому при её смене схемы перерисовываются.
    new MutationObserver(renderExtras).observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-theme']
    });

    panel.querySelectorAll('[data-step]').forEach(function (button) {
      button.addEventListener('click', function () {
        state.shift = ((state.shift + Number(button.dataset.step)) % 12 + 12) % 12;
        if (state.shift > 6) state.shift -= 12;  // держим сдвиг в пределах −5…+6
        render();
      });
    });
    panel.querySelector('[data-reset]').addEventListener('click', function () {
      state = { shift: 0, capo: 0 };
      render();
    });
    capoSelect.addEventListener('change', function () {
      state.capo = Number(capoSelect.value) || 0;
      render();
    });
    render();
  }

  /** Если аккордов не нашлось: кнопка «Показать табы» открывает перебор на примере Am – F – C – G. */
  function setupExample(root) {
    var button = root.querySelector('[data-show-tabs]');
    var box = root.querySelector('[data-example]');
    if (!button || !box) return;
    button.addEventListener('click', function () {
      box.hidden = false;
      button.hidden = true;
      var example = box.dataset.example.split(' ');
      if (window.renderDiagrams) window.renderDiagrams(box, example, false);
      if (window.renderTabs) window.renderTabs(box, example, false);
    });
  }

  window.setupTranspose = setupTranspose;
  window.shiftChord = shiftChord;
})();
