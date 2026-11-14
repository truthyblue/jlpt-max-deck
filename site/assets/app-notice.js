(() => {
  const notice = document.querySelector('[data-app-notice]');
  // A new key so visitors who closed the pre-order popup still see the launch.
  const storageKey = 'jlpt-max-app-launch-alert-v3';
  if (!notice?.showModal || Date.now() >= Date.parse(notice.dataset.closesAt)) return;
  if (location.hash === '#sponsor') return;

  try {
    if (localStorage.getItem(storageKey) === 'seen') return;
  } catch {}

  const close = () => {
    try {
      localStorage.setItem(storageKey, 'seen');
    } catch {}
    if (notice.open) notice.close();
  };

  notice.querySelector('[data-app-notice-close]').addEventListener('click', close);
  notice.querySelector('[data-app-notice-open]').addEventListener('click', close);
  notice.addEventListener('cancel', close);
  notice.showModal();
  // Focus the sheet, not its first link, so no focus ring shows on open.
  notice.focus();
})();
