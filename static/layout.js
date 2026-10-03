/* Presentation helpers for current and dynamically loaded modules. */
(() => {
  const root = document.querySelector('main');
  const filterLabels = {dashboardPeriod:'Periode',dateFilter:'Tanggal / periode',overviewRig:'Rig',reportDate:'Tanggal laporan',rigFilter:'Rig'};
  function decorate() {
    for (const [id, text] of Object.entries(filterLabels)) {
      const input = document.getElementById(id);
      if (!input || input.closest('.filterField')) continue;
      const label = document.createElement('label');
      label.className = 'filterField';
      const caption = document.createElement('span');
      caption.textContent = text;
      input.before(label);label.append(caption, input);
    }
    root.querySelectorAll('.view .tablewrap').forEach(wrap => {
      const table = wrap.querySelector('table');
      if (!table) return;
      wrap.classList.add('workspaceTable');
      const headings = Array.from(table.querySelectorAll('thead tr:last-child th')).map(th => th.textContent.trim());
      const rows = Array.from(table.querySelectorAll('tbody tr'));
      wrap.classList.toggle('isEmpty', rows.length === 1 && !!rows[0].querySelector('td.empty[colspan]'));
      if (!wrap.hasAttribute('tabindex')) {
        wrap.tabIndex = 0;
        wrap.setAttribute('role', 'region');
        const section = wrap.closest('.targetSection,.moduleSurface,.formgroup,.productionChart');
        const title = section?.querySelector('h3')?.textContent.trim() || document.getElementById(wrap.closest('.view').id)?.querySelector('h2')?.textContent.trim() || 'Data';
        wrap.setAttribute('aria-label', 'Tabel ' + title);
      }
      rows.forEach(row => Array.from(row.cells).forEach((cell, i) => {
        if (!cell.hasAttribute('colspan') && !cell.hasAttribute('data-cell-label')) cell.setAttribute('data-cell-label', headings[i] || 'Aksi');
      }));
    });
  }
  let pending = false;
  const schedule = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; decorate(); });
  };
  new MutationObserver(schedule).observe(root, {childList:true,subtree:true});
  decorate();
})();
