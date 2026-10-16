(() => {
  const notice = document.querySelector('[data-beta-notice]');
  const storageKey = 'jlpt-max-app-beta-notice-v1';
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

  notice.querySelector('[data-beta-notice-close]').addEventListener('click', close);
  notice.querySelector('[data-beta-notice-apply]').addEventListener('click', close);
  notice.addEventListener('cancel', close);
  notice.showModal();
})();
