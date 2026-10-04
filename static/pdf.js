// Кнопка «Скачать PDF»: снимает аккорды, схемы и табы в светлой теме и собирает PDF прямо в браузере.
// Библиотеки для PDF тяжёлые, поэтому подгружаются только по нажатию кнопки.
(function () {
  'use strict';

  var LIBS = ['/static/vendor/html2canvas.min.js', '/static/vendor/jspdf.umd.min.js'];
  var PAGE_WIDTH_PX = 794;  // ширина листа A4 при 96 точках на дюйм
  var TOP_MARGIN_MM = 10;   // отступ сверху на второй и следующих страницах

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (document.querySelector('script[src="' + src + '"]')) return resolve();
      var script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = function () { reject(new Error('Не загрузилась библиотека ' + src)); };
      document.head.appendChild(script);
    });
  }

  /** Копия нужной части страницы в светлой теме и ширине листа A4. */
  function printableCopy(source) {
    var holder = document.createElement('div');
    holder.className = 'pdf-sheet';
    holder.setAttribute('data-theme', 'light');
    holder.style.width = PAGE_WIDTH_PX + 'px';
    source.forEach(function (node) {
      if (node) holder.appendChild(node.cloneNode(true));
    });
    holder.querySelectorAll('[data-html2canvas-ignore], .transpose, .sheet-foot').forEach(function (el) { el.remove(); });
    document.body.appendChild(holder);
    return holder;
  }

  /** Места, где страницу можно разрезать, не разрывая строку с аккордами, схему или таб.
   *  Возвращает два списка отступов от верха копии (в экранных точках): лучшие места
   *  (перед куплетом или блоком) и запасные (между строками песни). */
  function safeBreaks(holder) {
    var origin = holder.getBoundingClientRect().top;
    var best = [];
    var spare = [];
    holder.querySelectorAll('.track-head, .extras-top, .diagram, .tab-block, .sheet-wrap')
      .forEach(function (el) { best.push(el.getBoundingClientRect().bottom - origin); });
    holder.querySelectorAll('.line-section, h2')
      .forEach(function (el) { best.push(el.getBoundingClientRect().top - origin - 4); });
    // Между строкой текста и следующей строкой: посередине промежутка, чтобы не задеть буквы.
    holder.querySelectorAll('.line-text').forEach(function (el) {
      var next = el.nextElementSibling;
      var bottom = el.getBoundingClientRect().bottom;
      var gapEnd = next ? next.getBoundingClientRect().top : bottom;
      spare.push((bottom + Math.max(gapEnd, bottom)) / 2 - origin);
    });
    return { best: best, spare: spare };
  }

  /** Режет длинный снимок на страницы A4 по безопасным местам и сохраняет PDF. */
  function savePdf(canvas, filename, breaks, sourceHeight) {
    var pdf = new window.jspdf.jsPDF({ unit: 'mm', format: 'a4' });
    var pageWidth = pdf.internal.pageSize.getWidth();
    var pageHeight = pdf.internal.pageSize.getHeight();
    var pxPerMm = canvas.width / pageWidth;
    var scale = canvas.height / sourceHeight;
    function toCanvas(list) { return list.map(function (b) { return Math.round(b * scale); }); }
    var best = toCanvas(breaks.best);
    var spare = toCanvas(breaks.spare);
    var top = 0;
    for (var page = 0; top < canvas.height; page++) {
      var margin = page > 0 ? TOP_MARGIN_MM : 0;
      var room = Math.floor((pageHeight - margin) * pxPerMm);
      var end = Math.min(top + room, canvas.height);
      if (end < canvas.height) {
        // Ближайшее безопасное место выше края листа, но не выше его середины.
        var limit = end;
        var fits = function (c) { return c > top + room / 2 && c <= limit; };
        var found = best.filter(fits);
        if (!found.length) found = spare.filter(fits);
        if (found.length) end = Math.max.apply(null, found);
      }
      var slice = document.createElement('canvas');
      slice.width = canvas.width;
      slice.height = end - top;
      slice.getContext('2d').drawImage(canvas, 0, -top);
      if (page > 0) pdf.addPage();
      pdf.addImage(slice.toDataURL('image/jpeg', 0.92), 'JPEG', 0, margin, pageWidth, slice.height / pxPerMm);
      top = end;
    }
    pdf.save(filename);
  }

  /** Подключает кнопку [data-pdf] внутри блока root. */
  function setupPdf(root) {
    var button = root.querySelector('[data-pdf]');
    if (!button) return;
    button.addEventListener('click', function () {
      var label = button.innerHTML;
      button.disabled = true;
      button.textContent = 'Готовлю PDF…';
      var holder;
      var breaks;
      var sourceHeight;
      Promise.all(LIBS.map(loadScript))
        .then(function () {
          holder = printableCopy([document.querySelector('.track-head'), root]);
          // Схемы перерисовываются заново, чтобы взять цвета светлой темы.
          if (window.renderDiagrams && root.dataset.shown) {
            window.renderDiagrams(holder, JSON.parse(root.dataset.shown), root.dataset.useH === '1');
          }
          breaks = safeBreaks(holder);
          sourceHeight = holder.getBoundingClientRect().height;
          var background = getComputedStyle(holder).getPropertyValue('--color-bg').trim();
          return window.html2canvas(holder, { scale: 2, backgroundColor: background || null, useCORS: true });
        })
        .then(function (canvas) { savePdf(canvas, button.dataset.pdf + '.pdf', breaks, sourceHeight); })
        .catch(function (error) {
          console.error(error);
          alert('Не получилось сделать PDF. Попробуйте ещё раз.');
        })
        .finally(function () {
          if (holder) holder.remove();
          button.disabled = false;
          button.innerHTML = label;
        });
    });
  }

  window.setupPdf = setupPdf;
})();
