// Схемы аккордов (аппликатуры) и аппликатуры для генерации перебора.
// Для частых аккордов взяты привычные открытые позиции, для остальных
// аппликатура строится по «баррейной» форме от ноты на 6-й или 5-й струне.
(function () {
  'use strict';

  // Лады от 6-й (басовой) струны к 1-й; x — струна не звучит.
  var OPEN_SHAPES = {
    C: 'x32010', D: 'xx0232', E: '022100', G: '320003', A: 'x02220', F: '133211',
    Am: 'x02210', Dm: 'xx0231', Em: '022000', Bm: 'x24432', Fm: '133111',
    C7: 'x32310', D7: 'xx0212', E7: '020100', G7: '320001', A7: 'x02020', B7: 'x21202',
    Am7: 'x02010', Dm7: 'xx0211', Em7: '022030',
    Cmaj7: 'x32000', Dmaj7: 'xx0222', Fmaj7: 'xx3210', Gmaj7: '320002', Amaj7: 'x02120',
    Dsus2: 'xx0230', Dsus4: 'xx0233', Asus2: 'x02200', Asus4: 'x02230', Esus4: '022200',
    Csus2: 'x30013', Csus4: 'x33011', Gsus4: '320013',
    Cadd9: 'x32033', A6: 'x02222', D6: 'xx0202', E5: '022xxx', A5: 'x022xx'
  };

  // Подвижные формы: смещения ладов от ноты на 6-й (E) или 5-й (A) струне.
  var E_SHAPES = {
    '': [0, 2, 2, 1, 0, 0], m: [0, 2, 2, 0, 0, 0], '7': [0, 2, 0, 1, 0, 0], m7: [0, 2, 0, 0, 0, 0],
    sus4: [0, 2, 2, 2, 0, 0], aug: [0, 3, 2, 1, 1, 0], '5': [0, 2, 2, null, null, null]
  };
  var A_SHAPES = {
    '': [null, 0, 2, 2, 2, 0], m: [null, 0, 2, 2, 1, 0], '7': [null, 0, 2, 0, 2, 0], m7: [null, 0, 2, 0, 1, 0],
    maj7: [null, 0, 2, 1, 2, 0], sus2: [null, 0, 2, 2, 0, 0], sus4: [null, 0, 2, 2, 3, 0],
    dim: [null, 0, 1, 2, 1, null], '6': [null, 0, 2, 2, 2, 2], m6: [null, 0, 2, 2, 1, 2],
    aug: [null, 0, 3, 2, 2, 1], '5': [null, 0, 2, 2, null, null]
  };
  var NOTE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11, H: 11 };
  var NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

  /** Разбирает аккорд на ноту (0–11) и упрощённый вид: m, 7, maj7, sus4 и т.п. */
  function parse(name, useH) {
    var match = /^([A-H])(#|b)?(.*)$/.exec(name.split('/')[0]);
    if (!match) return null;
    var note = NOTE[match[1]];
    if (useH && match[1] === 'B') note = 10;  // в русской записи B — си-бемоль
    if (match[2] === '#') note += 1;
    if (match[2] === 'b') note -= 1;
    note = (note + 12) % 12;
    var rest = match[3];
    var kind;
    if (/^(maj7|M7|Δ)/.test(rest)) kind = 'maj7';
    else if (/^(m7|min7|-7)/.test(rest)) kind = 'm7';
    else if (/^(m6|min6)/.test(rest)) kind = 'm6';
    else if (/^(dim|°)/.test(rest)) kind = 'dim';
    else if (/^(aug|\+)/.test(rest)) kind = 'aug';
    else if (/^(m|min|-)/.test(rest)) kind = 'm';
    else if (/^sus2/.test(rest)) kind = 'sus2';
    else if (/^sus/.test(rest)) kind = 'sus4';
    else if (/^(7|9|11|13)/.test(rest)) kind = '7';
    else if (/^6/.test(rest)) kind = '6';
    else if (/^5/.test(rest)) kind = '5';
    else if (/^add9/.test(rest)) kind = 'add9';
    else kind = '';
    return { note: note, kind: kind };
  }

  function fromString(frets) {
    return frets.split('').map(function (c) { return c === 'x' ? null : Number(c); });
  }

  /** Аппликатура аккорда: массив из 6 ладов (null — не играть), от 6-й струны к 1-й. */
  function shape(name, useH) {
    var chord = parse(name, useH);
    if (!chord) return null;
    var key = NAMES[chord.note] + (chord.kind === '' ? '' : chord.kind);
    if (OPEN_SHAPES[key]) return fromString(OPEN_SHAPES[key]);
    var kind = chord.kind === 'add9' ? '' : chord.kind;
    var eRoot = (chord.note - 4 + 12) % 12;
    var aRoot = (chord.note - 9 + 12) % 12;
    var candidates = [];
    if (E_SHAPES[kind]) candidates.push({ base: E_SHAPES[kind], root: eRoot === 0 ? 12 : eRoot });
    if (A_SHAPES[kind]) candidates.push({ base: A_SHAPES[kind], root: aRoot === 0 ? 12 : aRoot });
    if (!candidates.length) {
      var fallback = /^m/.test(kind) ? 'm' : '';
      candidates.push({ base: E_SHAPES[fallback], root: eRoot || 12 });
      candidates.push({ base: A_SHAPES[fallback], root: aRoot || 12 });
    }
    candidates.sort(function (a, b) { return a.root - b.root; });
    var best = candidates[0];
    return best.base.map(function (offset) { return offset === null ? null : offset + best.root; });
  }

  /** Переводит аппликатуру в формат библиотеки svguitar (струна 1 — тонкая). */
  function toSvguitar(frets) {
    var pressed = frets.filter(function (f) { return f; });
    var min = pressed.length ? Math.min.apply(null, pressed) : 1;
    var max = pressed.length ? Math.max.apply(null, pressed) : 1;
    var position = max > 4 ? min : 1;
    var fingers = [];
    var barres = [];
    var barreFret = null;
    // Баррэ: самый нижний лад зажат на нескольких струнах, включая 1-ю.
    var onMin = frets.filter(function (f) { return f === min && f > 0; }).length;
    if (onMin >= 2 && frets[5] === min && min > 0) {
      var first = frets.indexOf(min);
      barreFret = min;
      barres.push({ fromString: 6 - first, toString: 1, fret: min - position + 1 });
    }
    frets.forEach(function (fret, i) {
      var string = 6 - i;
      if (fret === null) fingers.push([string, 'x']);
      else if (fret === 0) fingers.push([string, 0]);
      else if (fret !== barreFret) fingers.push([string, fret - position + 1]);
    });
    return { fingers: fingers, barres: barres, position: position };
  }

  /** Значение переменной темы для элемента (так схемы в PDF получают цвета светлой темы). */
  function cssVar(element, name) {
    return getComputedStyle(element).getPropertyValue(name).trim();
  }

  /** Рисует схемы всех аккордов песни в блок [data-diagrams]. */
  function renderDiagrams(root, chords, useH) {
    var box = root.querySelector('[data-diagrams]');
    if (!box || !window.svguitar) return;
    box.innerHTML = '';
    var text = cssVar(box, '--color-text');
    var muted = cssVar(box, '--color-text-muted');
    var accent = cssVar(box, '--color-accent');
    var font = cssVar(box, '--font-ui');
    chords.forEach(function (name) {
      var frets = shape(name, useH);
      var card = document.createElement('figure');
      card.className = 'diagram';
      var holder = document.createElement('div');
      card.appendChild(holder);
      var caption = document.createElement('figcaption');
      caption.textContent = name;
      card.appendChild(caption);
      box.appendChild(card);
      if (!frets) {
        holder.className = 'diagram-missing';
        holder.textContent = '?';
        return;
      }
      new window.svguitar.SVGuitarChord(holder)
        .configure({
          strings: 6, frets: 4, fontFamily: font, color: text, stringColor: muted, fretColor: muted,
          fingerColor: accent, fingerTextColor: text, titleColor: text, backgroundColor: 'none',
          fingerSize: 0.7, strokeWidth: 2, emptyStringIndicatorSize: 0.6, fixedDiagramPosition: true
        })
        .chord(toSvguitar(frets))
        .draw();
    });
  }

  window.chordShape = shape;
  window.renderDiagrams = renderDiagrams;
})();
