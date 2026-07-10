(function () {
  const BOT = 'https://t.me/MOracul_bot';
  const p = new URLSearchParams(location.search);
  const utm = p.get('src') || p.get('utm_source') || '';

  function botUrl(start) {
    if (start === 'premium') {
      return BOT + '?start=' + (utm ? 'pay_' + encodeURIComponent(utm) : 'pay');
    }
    if (utm && start && start.startsWith('src_')) {
      return BOT + '?start=' + encodeURIComponent(start);
    }
    if (utm) return BOT + '?start=src_' + encodeURIComponent(utm);
    if (start) return BOT + '?start=' + encodeURIComponent(start);
    return BOT + '?start=src_site';
  }

  document.querySelectorAll('[data-bot]').forEach(function (el) {
    var start = el.getAttribute('data-bot') || 'src_site';
    el.href = botUrl(start);
    el.addEventListener('click', function () {
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: location.pathname, action: start })
      }).catch(function () {});
    });
  });

  document.querySelectorAll('a[href^="/blog"]').forEach(function (a) {
    a.addEventListener('click', function () {
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: location.pathname, action: 'blog:' + a.getAttribute('href') })
      }).catch(function () {});
    });
  });
})();
