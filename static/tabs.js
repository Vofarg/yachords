// Табы перебора: по аппликатурам аккордов песни строятся три стандартных
// рисунка — «восьмёрка» на 4/4, вальс на 3/4 и перебор на 6/8.
(function () {
  'use strict';

  var STRING_NAMES = ['e', 'B', 'G', 'D', 'A', 'E'];  // от 1-й (тонкой) к 6-й

  // Каждый шаг — список струн, которые звучат одновременно. 'bass' — басовая нота аккорда.
  var PATTERNS = [
    { title: 'Перебор 4/4', steps: [['bass'], [3], [2], [1], [2], [3], [2], [3]] },
    { title: 'Перебор 3/4', steps: [['bass'], [3, 2, 1], [3, 2, 1]] },
    { title: 'Перебор 6/8', steps: [['bass'], [3], [2], [1], [2], [3]] }
  ];

  /** Строит текст таба: по одному такту на аккорд. */
  function buildTab(chords, pattern, useH) {
    var rows = STRING_NAMES.map(function (name) { return name + '|'; });
    chords.forEach(function (name) {
      var frets = window.chordShape(name, useH);
      if (!frets) return;
      // frets идёт от 6-й струны к 1-й, а строки таба — от 1-й к 6-й.
      var bassIndex = frets.findIndex(function (f) { return f !== null; });
      var bassString = 6 - bassIndex;
      pattern.steps.forEach(function (step) {
        var playing = {};
        step.forEach(function (s) {
          var string = s === 'bass' ? bassString : s;
          var fret = frets[6 - string];
          if (fret !== null && fret !== undefined) playing[string] = String(fret);
        });
        var width = Math.max.apply(null, Object.keys(playing).map(function (k) { return playing[k].length; }).concat([1]));
        for (var string = 1; string <= 6; string++) {
          var cell = playing[string] || '';
          rows[string - 1] += '-' + cell + '-'.repeat(width - cell.length + 1);
        }
      });
      rows = rows.map(function (row) { return row + '|'; });
    });
    return rows.join('\n');
  }

  /** Рисует табы в блок [data-tabs] для первых четырёх аккордов песни. */
  function renderTabs(root, chords, useH) {
    var box = root.querySelector('[data-tabs]');
    if (!box || !window.chordShape) return;
    var progression = chords.slice(0, 4);
    box.innerHTML = '';
    PATTERNS.forEach(function (pattern) {
      var section = document.createElement('section');
      section.className = 'tab-block';
      var head = document.createElement('div');
      head.className = 'tab-head';
      var title = document.createElement('h3');
      title.textContent = pattern.title;
      var copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'button button-small';
      copy.setAttribute('data-html2canvas-ignore', '');
      copy.textContent = 'Копировать';
      head.appendChild(title);
      head.appendChild(copy);
      var pre = document.createElement('pre');
      pre.className = 'tab';
      pre.textContent = buildTab(progression, pattern, useH);
      var chordsLine = document.createElement('p');
      chordsLine.className = 'subtle';
      chordsLine.textContent = 'Аккорды по тактам: ' + progression.join(' – ');
      copy.addEventListener('click', function () {
        var done = function () {
          copy.textContent = 'Скопировано';
          setTimeout(function () { copy.textContent = 'Копировать'; }, 1500);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(pre.textContent).then(done, function () {});
      });
      section.appendChild(head);
      section.appendChild(pre);
      section.appendChild(chordsLine);
      box.appendChild(section);
    });
  }

  window.buildTab = buildTab;
  window.renderTabs = renderTabs;
})();
