(() => {
  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');

  const setNavOpen = (open) => {
    if (!navToggle || !nav) return;
    navToggle.setAttribute('aria-expanded', String(open));
    nav.dataset.open = String(open);
    document.body.classList.toggle('nav-open', open);
    const label = navToggle.querySelector('.sr-only');
    if (label) label.textContent = open ? '메뉴 닫기' : '메뉴 열기';
  };

  navToggle?.addEventListener('click', () => {
    setNavOpen(navToggle.getAttribute('aria-expanded') !== 'true');
  });

  nav?.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => setNavOpen(false));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setNavOpen(false);
  });

  const detectPlatform = () => {
    const platform = `${navigator.userAgentData?.platform || ''} ${navigator.platform || ''}`;
    const source = `${platform} ${navigator.userAgent || ''}`;
    if (/Android/i.test(source)) return 'android';
    if (
      /iPhone|iPad|iPod/i.test(source)
      || (/Mac/i.test(platform) && navigator.maxTouchPoints > 1)
    ) return 'ios';
    if (/Windows/i.test(source)) return 'windows';
    if (/Linux/i.test(source)) return 'linux';
    if (/Mac/i.test(source)) return 'macos';
    return null;
  };

  document.querySelectorAll('[data-tabs]').forEach((root) => {
    const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    const panels = Array.from(root.querySelectorAll('[role="tabpanel"]'));
    if (!tabs.length || tabs.length !== panels.length) return;

    const select = (tab, focus = false) => {
      tabs.forEach((candidate) => {
        const selected = candidate === tab;
        candidate.setAttribute('aria-selected', String(selected));
        candidate.tabIndex = selected ? 0 : -1;
      });
      panels.forEach((panel) => {
        panel.hidden = panel.getAttribute('aria-labelledby') !== tab.id;
      });
      const tabList = tab.closest('[role="tablist"]');
      if (tabList) {
        window.requestAnimationFrame(() => {
          const left = tab.offsetLeft
            - (tabList.clientWidth - tab.offsetWidth) / 2;
          tabList.scrollTo({
            left: Math.max(0, left),
            behavior: focus ? 'smooth' : 'auto',
          });
        });
      }
      if (focus) tab.focus();
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', (event) => {
        let next = null;
        if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next === null) return;
        event.preventDefault();
        select(tabs[next], true);
      });
    });

    const platform = root.hasAttribute('data-platform-tabs') ? detectPlatform() : null;
    const initial = tabs.find((tab) => tab.dataset.platform === platform)
      || tabs.find((tab) => tab.getAttribute('aria-selected') === 'true')
      || tabs[0];
    select(initial);
  });

  const fallbackCopy = (value) => {
    const field = document.createElement('textarea');
    field.value = value;
    field.setAttribute('readonly', '');
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand('copy');
    field.remove();
    return copied;
  };

  document.querySelectorAll('[data-copy-target]').forEach((button) => {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const value = target.textContent.trim();
      try {
        if (navigator.clipboard?.writeText && window.isSecureContext) {
          await navigator.clipboard.writeText(value);
        } else if (!fallbackCopy(value)) {
          throw new Error('copy failed');
        }
        const original = button.textContent;
        button.textContent = '복사됨';
        window.setTimeout(() => { button.textContent = original; }, 1600);
      } catch (_error) {
        button.textContent = '직접 복사';
      }
    });
  });
})();
