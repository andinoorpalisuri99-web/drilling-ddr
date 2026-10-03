(() => {
  const rail = document.getElementById('mainNav');
  const home = document.getElementById('railHome');
  const drawer = document.getElementById('navDrawer');
  const opener = document.getElementById('openNav');
  const closer = document.getElementById('closeNav');
  const accountMenu = document.getElementById('accountMenu');
  const accountTrigger = accountMenu.querySelector('summary');
  document.addEventListener('click', event => {
    if (!accountMenu.contains(event.target) || event.target.closest('#openPassword, #logout, [data-view]')) accountMenu.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && accountMenu.open) {event.preventDefault();event.stopImmediatePropagation();accountMenu.open = false;accountTrigger.focus();}
  }, true);
  const mobile = window.matchMedia('(max-width: 960px)');
  function close() {
    accountMenu.open = false;
    if (drawer.open) drawer.close();
    document.body.classList.remove('nav-open');
    opener.setAttribute('aria-expanded', 'false');
  }
  function placeNavigation() {
    close();
    if (mobile.matches) drawer.appendChild(rail);
    else home.after(rail);
  }
  opener.addEventListener('click', () => {
    drawer.showModal();
    document.body.classList.add('nav-open');
    opener.setAttribute('aria-expanded', 'true');
  });
  closer.addEventListener('click', close);
  drawer.addEventListener('close', close);
  drawer.addEventListener('click', event => {
    if (event.target === drawer) {
      const box = drawer.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
    }
  });
  rail.addEventListener('click', event => {
    if (event.target.closest('[data-view], #logout')) close();
  });
  let scrollPending = false;
  function updateHeader() {
    document.body.classList.toggle('headerCompact', window.scrollY > 122);
    scrollPending = false;
  }
  window.addEventListener('scroll', () => {
    if (scrollPending) return;
    scrollPending = true;
    requestAnimationFrame(updateHeader);
  }, {passive: true});
  updateHeader();
  mobile.addEventListener('change', placeNavigation);
  window.closeNavigation = close;
  placeNavigation();
})();
