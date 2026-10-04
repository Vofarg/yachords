// Кнопка «Скачать PDF»: снимает аккорды, схемы и табы в светлой теме и собирает PDF прямо в браузере.
// Библиотеки для PDF тяжёлые, поэтому подгружаются только по нажатию кнопки.
(function () {
  'use strict';

  var LIBS = ['/static/vendor/html2canvas.min.js', '/static/vendor/jspdf.umd.min.js'];
  var PAGE_WIDTH_PX = 794;  // ширина листа A4 при 96 точках на дюйм

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

  /** Режет длинный снимок на страницы A4 и сохраняет PDF. */
  function savePdf(canvas, filename) {
    var pdf = new window.jspdf.jsPDF({ unit: 'mm', format: 'a4' });
    var pageWidth = pdf.internal.pageSize.getWidth();
    var pageHeight = pdf.internal.pageSize.getHeight();
    var pxPerMm = canvas.width / pageWidth;
    var pageHeightPx = Math.floor(pageHeight * pxPerMm);
    for (var top = 0, page = 0; top < canvas.height; top += pageHeightPx, page++) {
      var slice = document.createElement('canvas');
      slice.width = canvas.width;
      slice.height = Math.min(pageHeightPx, canvas.height - top);
      slice.getContext('2d').drawImage(canvas, 0, -top);
      if (page > 0) pdf.addPage();
      pdf.addImage(slice.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, pageWidth, slice.height / pxPerMm);
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
      Promise.all(LIBS.map(loadScript))
        .then(function () {
          holder = printableCopy([document.querySelector('.track-head'), root]);
          // Схемы перерисовываются заново, чтобы взять цвета светлой темы.
          if (window.renderDiagrams && root.dataset.shown) {
            window.renderDiagrams(holder, JSON.parse(root.dataset.shown), root.dataset.useH === '1');
          }
          var background = getComputedStyle(holder).getPropertyValue('--color-bg').trim();
          return window.html2canvas(holder, { scale: 2, backgroundColor: background || null, useCORS: true });
        })
        .then(function (canvas) { savePdf(canvas, button.dataset.pdf + '.pdf'); })
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
