function zuriToast(message, ok) {
  var el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.className = 'toast ' + (ok ? 'toast-ok' : 'toast-err');
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(function () { el.hidden = true; }, 3200);
}

document.addEventListener('DOMContentLoaded', function () {
  var header = document.querySelector('.home-hero .site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('scrolled', window.scrollY > window.innerHeight * 0.55); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    var syncHeaderHeight = function () {
      document.documentElement.style.setProperty('--header-h', header.offsetHeight + 'px');
    };
    if (window.ResizeObserver) { new ResizeObserver(syncHeaderHeight).observe(header); }
    window.addEventListener('resize', syncHeaderHeight);
    syncHeaderHeight();
  }

  var navToggle = document.getElementById('nav-toggle');
  var navPanel = document.getElementById('main-nav');
  if (navToggle && navPanel) {
    var setNav = function (open) {
      navPanel.classList.toggle('is-open', open);
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    navToggle.addEventListener('click', function () {
      setNav(!navPanel.classList.contains('is-open'));
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && navPanel.classList.contains('is-open')) {
        setNav(false);
        navToggle.focus();
      }
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 600) setNav(false);
    });
  }

  var serverToast = document.getElementById('server-toast');
  if (serverToast) {
    zuriToast(serverToast.dataset.message, serverToast.dataset.ok === 'true');
  }

  var promoInput = document.getElementById('promo-input');
  if (promoInput) {
    var msg = document.getElementById('promo-msg');
    var apply = document.getElementById('promo-apply');
    var run = function () {
      var code = promoInput.value.trim();
      var csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
      fetch(promoInput.dataset.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'fetch' },
        body: 'csrfmiddlewaretoken=' + encodeURIComponent(csrf) + '&code=' + encodeURIComponent(code),
      })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var total = document.getElementById('grand-total');
          var row = document.getElementById('discount-row');
          var base = parseFloat(total.dataset.base);
          if (j.ok) {
            document.getElementById('promo-field').value = code.toUpperCase();
            msg.textContent = j.message || '';
            msg.removeAttribute('data-error');
            row.hidden = parseFloat(j.discount) <= 0;
            document.getElementById('discount-amount').textContent = '− KSh ' + j.discount;
            total.textContent = 'KSh ' + Number(j.total).toLocaleString('en-KE', { minimumFractionDigits: 2 });
          } else {
            document.getElementById('promo-field').value = '';
            msg.textContent = j.message || 'Invalid code';
            msg.setAttribute('data-error', '');
            row.hidden = true;
            total.textContent = 'KSh ' + base.toLocaleString('en-KE', { minimumFractionDigits: 2 });
          }
        });
    };
    apply.addEventListener('click', run);
    if (msg.textContent.trim()) run();
  }

  document.querySelectorAll('form.js-add-cart').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch' },
      })
        .then(function (r) { return r.json().then(function (j) { return { status: r.status, json: j }; }); })
        .then(function (res) {
          zuriToast(res.json.message || (res.json.ok ? 'Added to cart' : 'Could not add item'), res.json.ok);
          if (res.json.cart_count !== undefined) {
            var bn = document.getElementById('bn-badge');
            if (bn) { bn.textContent = res.json.cart_count; bn.hidden = false; }
            var badge = document.getElementById('cart-badge');
            if (badge) {
              badge.textContent = res.json.cart_count;
              badge.hidden = false;
              badge.classList.remove('pop');
              void badge.offsetWidth;
              badge.classList.add('pop');
            }
          }
        })
        .catch(function () { form.submit(); })
        .finally(function () { btn.disabled = false; });
    });
  });
});

(function () {
  var t = document.querySelector('.filter-toggle');
  if (!t) return;
  t.addEventListener('click', function () {
    var open = t.closest('.filter-side').classList.toggle('is-open');
    t.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
})();

(function () {
  document.querySelectorAll('.stepper').forEach(function (st) {
    var input = st.querySelector('input');
    var form = st.closest('form');
    var timer;
    st.querySelectorAll('.step-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = Math.max(1, Math.min(99, (parseInt(input.value, 10) || 1) + parseInt(b.dataset.step, 10)));
        input.value = v;
        clearTimeout(timer);
        timer = setTimeout(function () { form.submit(); }, 450);
      });
    });
    input.addEventListener('change', function () { form.submit(); });
  });
})();

(function () {
  var btn = document.getElementById('place-btn');
  if (!btn) return;
  var total = document.getElementById('grand-total');
  function label() {
    var cod = document.querySelector('input[name="payment_method"]:checked');
    var amt = total ? total.textContent : btn.dataset.total;
    btn.textContent = cod && cod.value === 'cod' ? 'Place order · ' + amt : 'Pay ' + amt + ' with M-Pesa';
  }
  document.querySelectorAll('input[name="payment_method"]').forEach(function (r) { r.addEventListener('change', label); });
  if (total) new MutationObserver(label).observe(total, { childList: true, characterData: true, subtree: true });
  label();
})();
