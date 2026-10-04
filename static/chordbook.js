// Справочник аккордов: все виды аккордов от выбранной ноты и поиск по названию.
// Аппликатуры берутся из diagrams.js — тех же, что показываются у песен.
(function () {
  'use strict';

  var NOTES = [
    { name: 'C', ru: 'до' }, { name: 'C#', ru: 'до-диез' }, { name: 'D', ru: 'ре' },
    { name: 'D#', ru: 'ре-диез' }, { name: 'E', ru: 'ми' }, { name: 'F', ru: 'фа' },
    { name: 'F#', ru: 'фа-диез' }, { name: 'G', ru: 'соль' }, { name: 'G#', ru: 'соль-диез' },
    { name: 'A', ru: 'ля' }, { name: 'A#', ru: 'ля-диез' }, { name: 'B', ru: 'си' }
  ];
  var KINDS = [
    { suffix: '', ru: 'мажор' },
    { suffix: 'm', ru: 'минор' },
    { suffix: '7', ru: 'септаккорд' },
    { suffix: 'm7', ru: 'минорный септаккорд' },
    { suffix: 'maj7', ru: 'большой мажорный септаккорд' },
    { suffix: '6', ru: 'мажор с секстой' },
    { suffix: 'm6', ru: 'минор с секстой' },
    { suffix: 'sus2', ru: 'задержание на секунду' },
    { suffix: 'sus4', ru: 'задержание на кварту' },
    { suffix: 'add9', ru: 'мажор с добавленной ноной' },
    { suffix: 'dim', ru: 'уменьшённый' },
    { suffix: 'aug', ru: 'увеличенный' },
    { suffix: '5', ru: 'квинта (пауэр-аккорд)' }
  ];
  var FLATS = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#', Hb: 'A#', Cb: 'B', Fb: 'E' };

  var picker = document.querySelector('[data-notes]');
  var book = document.querySelector('[data-chordbook]');
  var form = document.querySelector('[data-chord-search]');
  var input = form.querySelector('input');
  var error = document.querySelector('[data-search-error]');
  var current = { note: 'C', only: null };

  /** Подпись под схемой: открытая позиция или с какого лада. */
  function positionLabel(frets) {
    var pressed = frets.filter(function (f) { return f; });
    if (frets.some(function (f) { return f === 0; })) return 'открытая позиция';
    return 'с ' + Math.min.apply(null, pressed) + '-го лада';
  }

  /** Разбирает то, что ввели в поиск, в ноту из списка и вид аккорда. */
  function parseQuery(text) {
    var clean = text.trim().replace(/\s+/g, '').replace(/♯/g, '#').replace(/♭/g, 'b');
    var match = /^([A-Ha-h])([#b]?)(.*)$/.exec(clean);
    if (!match) return null;
    var letter = match[1].toUpperCase();
    var note = letter === 'H' ? 'B' : letter;
    if (match[2] === '#') note += '#';
    if (match[2] === 'b') note = FLATS[letter + 'b'] || null;
    if (note && note.length === 2 && !NOTES.some(function (n) { return n.name === note; })) {
      note = { 'E#': 'F', 'B#': 'C' }[note] || null;
    }
    if (!note) return null;
    var rest = match[3].toLowerCase().replace('min', 'm').replace('major', 'maj').replace('-', 'm');
    var kind = KINDS.filter(function (k) { return k.suffix.toLowerCase() === rest; })[0];
    if (!kind && rest === '') kind = KINDS[0];
    if (!kind) return { note: note, kind: null };
    return { note: note, kind: kind };
  }

  /** Блок одного аккорда: заголовок и все способы его взять. */
  function renderChord(note, kind) {
    var name = note + kind.suffix;
    var section = document.createElement('section');
    section.className = 'chordbook-item';
    section.id = 'chord-' + name.replace('#', 's');
    var head = document.createElement('h2');
    head.innerHTML = '';
    var title = document.createElement('span');
    title.className = 'chordbook-name';
    title.textContent = name;
    var desc = document.createElement('span');
    desc.className = 'subtle';
    desc.textContent = kind.ru;
    head.appendChild(title);
    head.appendChild(desc);
    section.appendChild(head);
    var grid = document.createElement('div');
    grid.className = 'diagrams';
    section.appendChild(grid);
    book.appendChild(section);
    var variants = window.chordShapes(name, false);
    if (!variants.length) {
      window.drawChord(grid, null, name, 'схемы пока нет');
      return;
    }
    variants.forEach(function (frets) {
      window.drawChord(grid, frets, name, positionLabel(frets));
    });
  }

  /** Перерисовывает справочник для выбранной ноты (или одного найденного аккорда). */
  function render() {
    picker.querySelectorAll('button').forEach(function (b) {
      b.setAttribute('aria-selected', String(b.dataset.note === current.note));
    });
    book.innerHTML = '';
    var kinds = current.only ? [current.only] : KINDS;
    kinds.forEach(function (kind) { renderChord(current.note, kind); });
    if (current.only) {
      var all = document.createElement('button');
      all.type = 'button';
      all.className = 'button';
      all.textContent = 'Все аккорды от ' + current.note;
      all.addEventListener('click', function () { select(current.note, null); });
      book.appendChild(all);
    }
  }

  /** Выбирает ноту (и, если задан, один вид аккорда) и запоминает выбор в адресе страницы. */
  function select(note, only) {
    current = { note: note, only: only };
    var hash = '#' + encodeURIComponent(note + (only ? only.suffix : ''));
    if (location.hash !== hash) history.replaceState(null, '', hash);
    render();
  }

  NOTES.forEach(function (n) {
    var button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('role', 'tab');
    button.dataset.note = n.name;
    button.innerHTML = '<b></b><span></span>';
    button.querySelector('b').textContent = n.name;
    button.querySelector('span').textContent = n.ru;
    button.addEventListener('click', function () { error.hidden = true; select(n.name, null); });
    picker.appendChild(button);
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var found = parseQuery(input.value);
    if (!found || !found.kind) {
      error.textContent = found
        ? 'Такого вида аккорда в справочнике пока нет. Показываю все аккорды от ' + found.note + '.'
        : 'Не понял название. Пишите как на сайтах с аккордами: Am, F#m, G7, Cmaj7.';
      error.hidden = false;
      if (found) select(found.note, null);
      return;
    }
    error.hidden = true;
    select(found.note, found.kind);
  });

  // Цвета схем берутся из темы, поэтому при её смене справочник перерисовывается.
  new MutationObserver(render).observe(document.documentElement, {
    attributes: true, attributeFilter: ['data-theme']
  });

  var start = parseQuery(decodeURIComponent(location.hash.slice(1)) || 'C');
  if (start) {
    select(start.note, location.hash.length > 1 && start.kind && start.kind.suffix !== '' ? start.kind : null);
  } else {
    select('C', null);
  }
})();
