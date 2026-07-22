(() => {
  const detectPlatform = () => {
    const modernPlatform = navigator.userAgentData?.platform || '';
    const legacyPlatform = navigator.platform || '';
    const userAgent = navigator.userAgent || '';
    const platformHint = modernPlatform || legacyPlatform || userAgent;
    const isiPad = /iPad/i.test(userAgent)
      || (legacyPlatform === 'MacIntel' && navigator.maxTouchPoints > 1);

    if (/Android/i.test(userAgent)) return 'android';
    if (isiPad || /iPhone|iPod/i.test(userAgent)) return 'ios';
    if (/Windows|Win32|Win64/i.test(platformHint)) return 'windows';
    if (/macOS|Macintosh|MacIntel|MacPPC|Mac68K/i.test(platformHint)) return 'macos';
    return null;
  };

  const detectedPlatform = detectPlatform();
  if (detectedPlatform === 'ios' || detectedPlatform === 'android') {
    document.documentElement.classList.add('mobile-device');
  }

  document.querySelectorAll('[data-platform-switcher]').forEach((switcher) => {
    const tabs = Array.from(switcher.querySelectorAll('[data-platform-tab]'));
    const panels = Array.from(switcher.querySelectorAll('[data-platform-panel]'));
    if (tabs.length < 2 || tabs.length !== panels.length) return;

    const revealSelectedTab = (tab) => {
      const tabList = tab.parentElement;
      if (!(tabList instanceof HTMLElement)) return;
      const tabRect = tab.getBoundingClientRect();
      const tabListRect = tabList.getBoundingClientRect();
      if (tabRect.left < tabListRect.left) {
        tabList.scrollLeft -= tabListRect.left - tabRect.left + 4;
      } else if (tabRect.right > tabListRect.right) {
        tabList.scrollLeft += tabRect.right - tabListRect.right + 4;
      }
    };

    const selectPlatform = (platform, { focus = false } = {}) => {
      if (!tabs.some((tab) => tab.dataset.platformTab === platform)) return;
      tabs.forEach((tab) => {
        const isSelected = tab.dataset.platformTab === platform;
        tab.setAttribute('aria-selected', String(isSelected));
        tab.tabIndex = isSelected ? 0 : -1;
        if (isSelected && focus) tab.focus();
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.platformPanel !== platform;
      });
      const selectedTab = tabs.find((tab) => tab.dataset.platformTab === platform);
      if (selectedTab) {
        window.requestAnimationFrame(() => revealSelectedTab(selectedTab));
      }
    };

    const syncGroup = switcher.dataset.platformSync;
    const selectSynchronizedPlatform = (platform, { focus = false } = {}) => {
      selectPlatform(platform, { focus });
      if (!syncGroup) return;
      document.dispatchEvent(new CustomEvent('platform-sync-change', {
        detail: { group: syncGroup, platform, source: switcher },
      }));
    };

    document.addEventListener('platform-sync-change', (event) => {
      if (event.detail?.source === switcher) return;
      if (!syncGroup || event.detail?.group !== syncGroup) return;
      selectPlatform(event.detail.platform);
    });

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        selectSynchronizedPlatform(tab.dataset.platformTab);
      });
      tab.addEventListener('keydown', (event) => {
        let nextIndex = null;
        if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
        if (event.key === 'Home') nextIndex = 0;
        if (event.key === 'End') nextIndex = tabs.length - 1;
        if (nextIndex === null) return;
        event.preventDefault();
        selectSynchronizedPlatform(
          tabs[nextIndex].dataset.platformTab,
          { focus: true },
        );
      });
    });

    const initialPlatform = detectedPlatform
      && tabs.some((tab) => tab.dataset.platformTab === detectedPlatform)
      ? detectedPlatform
      : tabs.find((tab) => tab.getAttribute('aria-selected') === 'true')?.dataset.platformTab
        || tabs[0].dataset.platformTab;
    selectPlatform(initialPlatform);
  });

  document.documentElement.classList.add('platform-tabs-ready');

  const fallbackCopyText = (value) => {
    const focusedElement = document.activeElement;
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.readOnly = true;
    textarea.setAttribute('aria-hidden', 'true');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    try {
      textarea.select();
      return document.execCommand('copy');
    } finally {
      textarea.remove();
      if (focusedElement instanceof HTMLElement) {
        focusedElement.focus({ preventScroll: true });
      }
    }
  };

  const copyText = async (value) => {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(value);
        return true;
      } catch (_error) {
        // Some browsers expose the API but deny it. Use the selection fallback.
      }
    }
    return fallbackCopyText(value);
  };

  const copyStatus = document.querySelector('[data-copy-status]');
  document.querySelectorAll('[data-copy-command]').forEach((button) => {
    const originalLabel = button.textContent;
    button.addEventListener('click', async () => {
      const command = document.getElementById(button.dataset.copyCommand);
      if (!command) return;
      try {
        const copied = await copyText(command.textContent.trim());
        if (!copied) throw new Error('copy failed');
        button.textContent = '복사했습니다';
        if (copyStatus) {
          copyStatus.textContent = '빌더 실행 명령을 복사했습니다. 터미널이나 PowerShell에 붙여 넣고 Enter를 누르세요.';
        }
        window.setTimeout(() => {
          button.textContent = originalLabel;
        }, 1800);
      } catch (_error) {
        if (copyStatus) {
          copyStatus.textContent = '자동 복사가 되지 않았습니다. 표시된 명령을 직접 선택해 복사해 주세요.';
        }
      }
    });
  });
  document.documentElement.classList.add('copy-ready');
})();
