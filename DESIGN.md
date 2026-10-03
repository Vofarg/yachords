# DESIGN.md — дизайн-система Guitar Chords from Yandex Music

Дополняет `CLAUDE.md`. Все UI-решения принимаются по этому файлу.
Если чего-то нет — Claude предлагает расширение и **сначала согласовывает с пользователем**.

---

## 1. Философия

Спокойный музыкальный инструмент, а не «приложение-комбайн».
Вдохновение: Notion (тишина, воздух), Spotify (тёмная база, акцент), Яндекс.Музыка (понятность).

**Ключевые принципы:**
1. **Воздух важнее плотности.** Лучше прокрутка, чем теснота.
2. **Один акцент на экран.** Не соревнуются фиолетовый и лайм.
3. **Аккорды — главное.** Всё остальное — фон для них.
4. **Тёмная тема первична.** Светлая — равноправная, но вторичная.
5. **Скругления — щедрые.** Кнопки — pill. Карточки — 16px. Поля — 12px.

---

## 2. Токены

Все значения — CSS-переменные в `static/style.css`.
Claude **никогда** не пишет цвета/отступы цифрами напрямую — только через `var(--...)`.

```css
:root {
  /* Цвета — светлая тема (по умолчанию при переключении) */
  --color-bg:            #fafafa;
  --color-surface:       #ffffff;
  --color-surface-2:     #f2f2f5;
  --color-border:        #e5e5ea;
  --color-text:          #1a1a1f;
  --color-text-muted:    #6b6b76;
  --color-text-subtle:   #9a9aa5;

  --color-accent:        #7a69f5;   /* фиолетовый — основной */
  --color-accent-hover:  #6a58e8;
  --color-accent-soft:   #efecfe;   /* фон под акцентом */

  --color-highlight:     #e4f569;   /* лаймовый — только акценты */
  --color-highlight-soft:#f6facd;

  --color-chord:         #7a69f5;   /* цвет аккорда над словом */
  --color-success:       #4caf7d;
  --color-warning:       #e8a33d;
  --color-error:         #e5484d;

  /* Типографика */
  --font-ui:    'Inter', system-ui, -apple-system, sans-serif;
  --font-mono:  'JetBrains Mono', 'Fira Code', monospace;

  --text-xs:    12px;
  --text-sm:    14px;
  --text-base:  16px;
  --text-lg:    18px;
  --text-xl:    24px;
  --text-2xl:   32px;
  --text-3xl:   40px;

  --weight-regular: 400;
  --weight-medium:  500;
  --weight-bold:    700;

  --leading-tight:  1.3;
  --leading-normal: 1.5;
  --leading-loose:  1.8;   /* для текста с аккордами */

  /* Сетка отступов — шаг 4px */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* Скругления */
  --radius-sm:   8px;
  --radius-md:   12px;
  --radius-lg:   16px;
  --radius-xl:   24px;
  --radius-pill: 999px;

  /* Тени — только для всплывающих элементов */
  --shadow-sm: 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,.08);
  --shadow-lg: 0 12px 32px rgba(0,0,0,.12);

  /* Переходы */
  --transition-fast: 120ms ease;
  --transition-base: 200ms ease;
}

/* Тёмная тема — переключается атрибутом на <html> */
[data-theme="dark"] {
  --color-bg:            #0f0f12;
  --color-surface:       #17171c;
  --color-surface-2:     #1f1f26;
  --color-border:        #2a2a33;
  --color-text:          #f2f2f7;
  --color-text-muted:    #a0a0ad;
  --color-text-subtle:   #6b6b78;

  --color-accent:        #9a8cff;   /* чуть светлее на тёмном */
  --color-accent-hover:  #ab9fff;
  --color-accent-soft:   #221f3d;

  --color-highlight:     #e4f569;
  --color-highlight-soft:#2e3219;

  --color-chord:         #b8aaff;

  --shadow-sm: 0 1px 2px rgba(0,0,0,.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,.4);
  --shadow-lg: 0 12px 32px rgba(0,0,0,.5);
}

/* Системная тема, если пользователь не выбирал вручную */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* те же значения, что в [data-theme="dark"] — вынести в общий блок */
  }
}