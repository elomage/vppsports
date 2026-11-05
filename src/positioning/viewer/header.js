// Shared navigation for processing, map, analysis and time alignment.
(() => {
  const header = document.getElementById('site-header');
  if (!header) return;
  const current = location.pathname.split('/').pop() || 'map.html';
  const pages = [['recordings.html', 'Ieraksti'], ['map.html', 'Karte'], ['app.html', 'Apstrāde'], ['analysis.html', 'Datu analīze'], ['alignment.html', 'Sapludināšana']];
  header.innerHTML = `
    <a class="site-brand" href="map.html" aria-label="GNSS Lab — sākumlapa">
      <span class="site-mark" aria-hidden="true">◉</span> GNSS <small>LAB</small>
    </a>
    <nav class="site-nav" aria-label="Galvenā navigācija" lang="lv">
      ${pages.map(([url, label]) => `<a href="${url}"${url === current ? ' aria-current="page"' : ''}>${label}</a>`).join('')}
    </nav>
    <span class="site-local" lang="lv"><span aria-hidden="true">●</span> Lokālie ieraksti</span>`;
})();
