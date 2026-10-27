(function () {
  'use strict';

  const app = document.getElementById('app');
  const toastRoot = document.getElementById('toast-root');
  const modalRoot = document.getElementById('modal-root');
  const assetBase = window.__STATIC_WEB_BASE__ || '/';
  const apiBase = location.protocol === 'file:'
    ? (localStorage.getItem('xiaozhi_api_base') || 'http://localhost:8080')
    : location.origin;

  const state = {
    user: readUser(),
    branding: {
      name: 'Xiaozhi Server',
      title: 'Bảng Điều Khiển Xiaozhi',
      welcome: 'Chào mừng bạn đến với Bảng Điều Khiển Quản Trị Xiaozhi',
      logoUrl: asset('logo.png'),
      homeLink: 'https://github.com/AnimeAIChat/xiaozhi-server-go/tree/main',
      copyright: 'Xiaozhi Vietnam',
    },
    advancedTab: 'application',
  };

  const routeTitles = {
    login: 'Đăng nhập',
    welcome: 'Chào mừng',
    agents: 'Trợ lý AI',
    agentConfig: 'Cấu hình nhân vật',
    devices: 'Quản lý thiết bị',
    history: 'Lịch sử hội thoại',
    profile: 'Cài đặt cá nhân',
    dashboard: 'Bảng tổng quan',
    adminSettings: 'Cấu hình hệ thống',
    providers: 'Nhà cung cấp AI',
    unbindDevice: 'Hủy liên kết thiết bị',
    advancedConfig: 'Cấu hình nâng cao',
    diagnostics: 'Hướng dẫn cấu hình ban đầu',
    whiteList: 'Danh sách cho phép',
  };

  function asset(path) {
    return `${assetBase}${path}`.replace(/\/{2,}/g, '/').replace(':/', '://');
  }

  function readUser() {
    try {
      return JSON.parse(localStorage.getItem('user') || 'null');
    } catch (_error) {
      return null;
    }
  }

  function saveUser(user) {
    state.user = user;
    localStorage.setItem('user', JSON.stringify(user));
  }

  function clearUser() {
    state.user = null;
    localStorage.removeItem('user');
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function prettyJson(value) {
    try {
      return JSON.stringify(value ?? {}, null, 2);
    } catch (_error) {
      return '{}';
    }
  }

  function parseJson(value, fallback = {}) {
    if (value == null || value === '') return fallback;
    if (typeof value === 'object') return value;
    try {
      return JSON.parse(value);
    } catch (_error) {
      return fallback;
    }
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function formatDate(value) {
    if (!value) return 'Chưa có';
    let date;
    if (typeof value === 'number') {
      date = new Date(value * 1000);
    } else {
      date = new Date(value);
    }
    if (Number.isNaN(date.getTime()) || date.getFullYear() < 2020) return 'Chưa có';
    return date.toLocaleString();
  }

  function formatPercent(value) {
    if (value == null || value === '') return '-';
    const number = Number(value);
    if (Number.isNaN(number)) return String(value);
    return `${Number(number.toFixed(2))}%`;
  }

  function normalizeList(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.data)) return payload.data;
    if (Array.isArray(payload?.data?.data)) return payload.data.data;
    if (Array.isArray(payload?.list)) return payload.list;
    return [];
  }

  function normalizeTablePayload(payload) {
    const data = normalizeList(payload);
    return {
      data,
      total: payload?.total ?? payload?.data?.total ?? data.length,
      success: payload?.success ?? payload?.status === 'ok' ?? true,
    };
  }

  function formValues(form) {
    const values = {};
    const data = new FormData(form);
    data.forEach((value, key) => {
      values[key] = value;
    });
    qsa('input[type="checkbox"]', form).forEach((input) => {
      values[input.name] = input.checked;
    });
    return values;
  }

  function toast(message, type = 'info') {
    const item = document.createElement('div');
    item.className = `toast ${type}`;
    item.textContent = message;
    toastRoot.appendChild(item);
    setTimeout(() => {
      item.remove();
    }, 3600);
  }

  function showError(error, fallback = 'Thao tác thất bại') {
    const message = error?.data?.message || error?.data?.error || error?.message || fallback;
    toast(message, 'error');
  }

  function openModal({ title, body, footer }) {
    modalRoot.innerHTML = `
      <div class="modal-backdrop" role="dialog" aria-modal="true">
        <div class="modal">
          <div class="modal-header">
            <h3>${escapeHtml(title)}</h3>
            <button class="btn ghost small" data-close-modal>Đóng</button>
          </div>
          <div class="modal-body">${body}</div>
          <div class="modal-footer">${footer || ''}</div>
        </div>
      </div>
    `;
    qsa('[data-close-modal]', modalRoot).forEach((button) => {
      button.addEventListener('click', closeModal);
    });
  }

  function closeModal() {
    modalRoot.innerHTML = '';
  }

  function confirmAction(title, content, onConfirm) {
    openModal({
      title,
      body: `<p>${escapeHtml(content)}</p>`,
      footer: `
        <button class="btn" data-close-modal>Hủy</button>
        <button class="btn danger" id="confirm-ok">Xác nhận</button>
      `,
    });
    byId('confirm-ok').addEventListener('click', async () => {
      try {
        await onConfirm();
        closeModal();
      } catch (error) {
        showError(error);
      }
    });
  }

  async function request(path, options = {}) {
    const url = path.startsWith('http') ? path : `${apiBase}${path}`;
    const headers = new Headers(options.headers || {});
    headers.set('Accept', headers.get('Accept') || 'application/json');
    if (state.user?.token) {
      headers.set('Authorization', `Bearer ${state.user.token}`);
    }

    const init = {
      method: options.method || 'GET',
      headers,
      credentials: 'same-origin',
    };

    if (options.body instanceof FormData) {
      init.body = options.body;
    } else if (options.body !== undefined) {
      headers.set('Content-Type', headers.get('Content-Type') || 'application/json');
      init.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(url, init);
    } catch (error) {
      const networkError = new Error(`Không thể kết nối đến máy chủ: ${apiBase}`);
      networkError.cause = error;
      throw networkError;
    }

    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => ({}))
      : await response.text();

    if (!response.ok) {
      const error = new Error(payload?.message || payload?.error || response.statusText);
      error.status = response.status;
      error.data = payload;
      if (response.status === 401) {
        clearUser();
        navigate('/login');
      }
      throw error;
    }

    return payload;
  }

  function getRoutePath() {
    if (location.protocol === 'file:') {
      return (location.hash || '#/welcome').slice(1) || '/welcome';
    }
    return location.pathname === '/' ? '/welcome' : location.pathname;
  }

  function routeInfo(path = getRoutePath()) {
    const clean = path.replace(/\/+$/, '') || '/welcome';
    if (clean === '/login' || clean === '/console/login') return { key: 'login', public: true, path: '/login' };
    if (clean === '/welcome' || clean === '/') return { key: 'welcome', path: '/welcome' };
    if (clean === '/console/agents') return { key: 'agents', path: '/console/agents' };
    if (clean === '/console/settings') return { key: 'profile', path: '/console/settings' };
    let match = clean.match(/^\/console\/agents\/([^/]+)\/config$/);
    if (match) return { key: 'agentConfig', path: clean, params: { id: match[1] } };
    match = clean.match(/^\/console\/agents\/([^/]+)\/device$/);
    if (match) return { key: 'devices', path: clean, params: { id: match[1] } };
    match = clean.match(/^\/console\/agents\/([^/]+)\/history$/);
    if (match) return { key: 'history', path: clean, params: { id: match[1] } };
    if (clean === '/admin/dashboard') return { key: 'dashboard', path: clean };
    if (clean === '/admin/settings') return { key: 'adminSettings', path: clean };
    if (clean === '/admin/providers') return { key: 'providers', path: clean };
    if (clean === '/admin/unbindDevice') return { key: 'unbindDevice', path: clean };
    if (clean === '/admin/systemConfig') return { key: 'advancedConfig', path: clean };
    if (clean === '/admin/diagnostics') return { key: 'diagnostics', path: clean };
    if (clean === '/admin/whiteList') return { key: 'whiteList', path: clean };
    return { key: 'welcome', path: '/welcome' };
  }

  function navigate(path) {
    if (location.protocol === 'file:') {
      location.hash = path;
      render();
      return;
    }
    history.pushState({}, '', path);
    render();
  }

  function canSeeAdmin() {
    return state.user?.role === 'admin' || state.user?.role === 'observer';
  }

  function canWriteAdmin() {
    return state.user?.role === 'admin';
  }

  function shell(route) {
    const adminItems = canSeeAdmin()
      ? `
        <div class="nav-group">
          <div class="nav-title">Quản trị hệ thống</div>
          ${navItem('/admin/dashboard', 'Bảng tổng quan', route.path)}
          ${navItem('/admin/settings', 'Cấu hình hệ thống', route.path)}
          ${navItem('/admin/providers', 'Nhà cung cấp AI', route.path)}
          ${navItem('/admin/diagnostics', 'Hướng dẫn cấu hình', route.path)}
          ${navItem('/admin/unbindDevice', 'Hủy liên kết thiết bị', route.path)}
          ${navItem('/admin/systemConfig', 'Cấu hình nâng cao', route.path)}
          ${navItem('/admin/whiteList', 'Danh sách cho phép', route.path)}
        </div>
      `
      : '';

    app.innerHTML = `
      <div class="layout">
        <aside class="sidebar" id="sidebar">
          <div class="brand">
            <img src="${escapeHtml(state.branding.logoUrl || asset('logo.png'))}" alt="">
            <span>${escapeHtml(state.branding.name || 'Xiaozhi Server')}</span>
          </div>
          <nav class="nav">
            <div class="nav-group">
              ${navItem('/welcome', 'Chào mừng', route.path)}
            </div>
            <div class="nav-group">
              <div class="nav-title">Bảng điều khiển</div>
              ${navItem('/console/agents', 'Trợ lý AI', route.path)}
              ${navItem('/console/settings', 'Cài đặt cá nhân', route.path)}
            </div>
            ${adminItems}
          </nav>
        </aside>
        <section class="main">
          <header class="topbar">
            <div class="topbar-left">
              <button class="btn ghost mobile-menu" id="mobile-menu">Menu</button>
              <h1 class="page-title" id="page-title">${escapeHtml(routeTitles[route.key] || '')}</h1>
            </div>
            <div class="topbar-right">
              <a href="${escapeHtml(state.branding.homeLink || '#')}" target="_blank" rel="noreferrer">GitHub</a>
              <div class="user-menu">
                <button class="avatar-button" id="avatar-button">
                  <span class="avatar">${escapeHtml((state.user?.username || 'U').slice(0, 1).toUpperCase())}</span>
                  <span>${escapeHtml(state.user?.username || 'Người dùng')}</span>
                </button>
                <div class="dropdown" id="user-dropdown">
                  <button data-link="/console/settings">Thông tin cá nhân</button>
                  <button data-action="logout">Đăng xuất</button>
                </div>
              </div>
            </div>
          </header>
          <main class="content" id="page"></main>
        </section>
      </div>
    `;

    byId('mobile-menu')?.addEventListener('click', () => {
      byId('sidebar')?.classList.toggle('open');
    });
    byId('avatar-button')?.addEventListener('click', (event) => {
      event.stopPropagation();
      byId('user-dropdown')?.classList.toggle('open');
    });
  }

  function navItem(path, label, currentPath) {
    const active = currentPath === path || (path !== '/welcome' && currentPath.startsWith(path));
    return `
      <a class="nav-item ${active ? 'active' : ''}" href="${path}" data-link="${path}">
        <span class="nav-icon">•</span>
        <span>${escapeHtml(label)}</span>
      </a>
    `;
  }

  function setTitle(title) {
    const fullTitle = title ? `${title} - ${state.branding.title}` : state.branding.title;
    document.title = fullTitle;
    const titleEl = byId('page-title');
    if (titleEl) titleEl.textContent = title;
  }

  function page() {
    return byId('page');
  }

  function pageHeader(title, subtitle = '', actions = '') {
    return `
      <div class="page-header">
        <div>
          <h2>${escapeHtml(title)}</h2>
          ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}
        </div>
        <div class="toolbar">${actions}</div>
      </div>
    `;
  }

  function loadingCard(text = 'Đang tải...') {
    return `<div class="card"><div class="app-loading" style="min-height:180px"><div class="loading-mark"></div><div>${escapeHtml(text)}</div></div></div>`;
  }

  function emptyState(text, action = '') {
    return `<div class="empty">${escapeHtml(text)}${action ? `<div style="margin-top:16px">${action}</div>` : ''}</div>`;
  }

  async function render() {
    const route = routeInfo();
    state.user = readUser();

    if (route.key !== 'login' && !state.user) {
      renderLogin();
      return;
    }

    if (route.key === 'login') {
      renderLogin();
      return;
    }

    shell(route);
    setTitle(routeTitles[route.key] || 'Chào mừng');

    const renderers = {
      welcome: renderWelcome,
      agents: renderAgents,
      agentConfig: renderAgentConfig,
      devices: renderDevices,
      history: renderHistory,
      profile: renderProfile,
      dashboard: renderDashboard,
      adminSettings: renderAdminSettings,
      providers: renderProviders,
      unbindDevice: renderUnbindDevice,
      advancedConfig: renderAdvancedConfig,
      diagnostics: renderDiagnostics,
      whiteList: renderWhiteList,
    };

    try {
      await (renderers[route.key] || renderWelcome)(route);
    } catch (error) {
      page().innerHTML = `
        ${pageHeader(routeTitles[route.key] || 'Trang', '')}
        <div class="alert error">${escapeHtml(error.message || 'Tải trang thất bại')}</div>
      `;
    }
  }

  function renderLogin() {
    setTitle('Đăng nhập');
    app.innerHTML = `
      <div class="login-page">
        <main class="login-main">
          <form class="login-card" id="login-form">
            <div class="login-brand">
              <img src="${escapeHtml(state.branding.logoUrl || asset('logo.png'))}" alt="">
              <h1 class="login-title">${escapeHtml(state.branding.title)}</h1>
              <div class="login-subtitle">Đăng nhập tài khoản & mật khẩu</div>
            </div>
            <div class="form">
              <div class="field">
                <label for="login-username">Tên đăng nhập</label>
                <input id="login-username" name="username" autocomplete="username" placeholder="admin" required>
              </div>
              <div class="field">
                <label for="login-password">Mật khẩu</label>
                <input id="login-password" name="password" type="password" autocomplete="current-password" placeholder="Mật khẩu tạm thời trong log khi khởi động lần đầu" required>
              </div>
              <label class="field checkbox">
                <input type="checkbox" name="autoLogin" checked>
                <span>Tự động đăng nhập</span>
              </label>
              <button class="btn primary" type="submit">Đăng nhập</button>
              <div class="subtle">Tài khoản mặc định: admin, mật khẩu: 123456 (hoặc mật khẩu tạm trong log). Vui lòng đổi mật khẩu sau khi đăng nhập.</div>
            </div>
          </form>
        </main>
        <footer class="footer-note">© ${escapeHtml(state.branding.copyright || 'Xiaozhi Server')}</footer>
      </div>
    `;

    byId('login-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      try {
        const result = await request('/api/user/login', {
          method: 'POST',
          body: {
            username: values.username,
            password: values.password,
          },
        });
        if (result?.status === 'ok' && result?.data?.token) {
          saveUser(result.data);
          toast('Đăng nhập thành công', 'success');
          navigate('/welcome');
          return;
        }
        toast(result?.message || 'Đăng nhập thất bại', 'error');
      } catch (error) {
        showError(error, 'Đăng nhập thất bại');
      }
    });
  }

  async function renderDiagnostics() {
    page().innerHTML = `
      ${pageHeader('Hướng dẫn cấu hình ban đầu', 'Sau khi cấu hình nhà cung cấp mô hình và địa chỉ thiết bị, hãy chạy kiểm tra để xác nhận từng bước. Kết quả kiểm tra không hiển thị khóa bí mật.')}
      <div class="card">
        <h3>1. Cấu hình dịch vụ mô hình AI</h3>
        <p class="muted">Trong mục "Nhà cung cấp AI", nhập và chọn ASR, LLM, TTS; địa chỉ và khóa bí mật chỉ lưu trong cấu hình máy chủ.</p>
        <button class="btn" data-link="/admin/providers">Mở Nhà cung cấp AI</button>
      </div>
      <div class="card">
        <h3>2. Cấu hình địa chỉ truy cập của thiết bị</h3>
        <p class="muted">Trong mục "Cấu hình nâng cao", điền địa chỉ WebSocket mà thiết bị có thể kết nối. Lưu ý: Thiết bị không thể dùng localhost.</p>
        <button class="btn" data-link="/admin/systemConfig">Mở Cấu hình nâng cao</button>
      </div>
      <div class="card">
        <div class="toolbar" style="justify-content:space-between;align-items:center">
          <div>
            <h3 style="margin:0">3. Chạy kiểm tra kết nối</h3>
            <p class="muted" style="margin:6px 0 0">Kiểm tra kết nối WebSocket, dịch vụ HTTP hiện tại và cấu hình ASR, LLM, TTS đã chọn.</p>
          </div>
          <button class="btn primary" id="run-diagnostics">Bắt đầu kiểm tra</button>
        </div>
        <div id="diagnostics-results" style="margin-top:16px"></div>
      </div>
      <div class="card">
        <div class="toolbar" style="justify-content:space-between;align-items:center;gap:16px">
          <div>
            <h3 style="margin:0">4. Tạo trợ lý thiết lập ban đầu</h3>
            <p class="muted" style="margin:6px 0 0">Xác nhận cấu hình ASR, LLM, TTS hoàn tất trước khi tạo. Hệ thống duy trì 1 trợ lý thiết lập; trợ lý này sẽ tự động liên kết với các thiết bị mới.</p>
          </div>
          <button class="btn primary" id="activate-onboarding" disabled>Đang kiểm tra cấu hình…</button>
        </div>
        <div id="onboarding-status" class="provider-test-result" aria-live="polite" style="margin-top:12px"></div>
      </div>
    `;

    const resultHost = byId('diagnostics-results');
    const onboardingHost = byId('onboarding-status');
    const onboardingButton = byId('activate-onboarding');
    const refreshOnboarding = async () => {
      try {
        const payload = await request('/api/admin/onboarding');
        const status = payload.data || {};
        const issues = Array.isArray(status.issues) ? status.issues : [];
        const ready = status.ready === true;
        const exists = status.exists === true;
        onboardingButton.disabled = !ready || !canWriteAdmin();
        onboardingButton.textContent = exists ? 'Đồng bộ cấu hình trợ lý ban đầu' : 'Tạo trợ lý thiết lập ban đầu';
        if (ready) {
          const assistantState = exists
            ? `Trợ lý thiết lập ban đầu đã tồn tại (ID ${escapeHtml(status.agentId)}), có thể đồng bộ cấu hình Provider hiện tại.`
            : 'Cấu hình ASR, LLM, TTS đã sẵn sàng, có thể tạo trợ lý thiết lập ban đầu.';
          onboardingHost.innerHTML = `<div class="provider-test-message success">${assistantState} ${Number(status.pendingDevices || 0)}  thiết bị chưa liên kết sẽ tự động được tiếp nhận sau khi tạo.</div>`;
        } else {
          onboardingHost.innerHTML = `<div class="provider-test-message error">Vui lòng xử lý trước khi tạo: ${escapeHtml(issues.join('；') || 'Cấu hình Provider chưa sẵn sàng')}</div>`;
        }
      } catch (error) {
        onboardingButton.disabled = true;
        onboardingButton.textContent = 'Không thể kiểm tra cấu hình';
        onboardingHost.innerHTML = `<div class="provider-test-message error">${escapeHtml(error?.data?.message || error?.message || 'Không thể đọc trạng thái trợ lý thiết lập ban đầu')}</div>`;
      }
    };
    onboardingButton.addEventListener('click', () => {
      confirmAction('Tạo trợ lý thiết lập ban đầu', 'Thao tác này sẽ tạo trợ lý thiết lập và tự động liên kết các thiết bị chưa liên kết. Bạn có chắc chắn muốn tiếp tục không?', async () => {
        onboardingButton.disabled = true;
        onboardingButton.textContent = 'Đang tạo…';
        try {
          const result = await request('/api/admin/onboarding', { method: 'POST' });
          toast(result.message || 'Đã tạo trợ lý thiết lập ban đầu thành công', 'success');
          await refreshOnboarding();
        } catch (error) {
          showError(error, 'Tạo trợ lý thiết lập ban đầu thất bại');
          await refreshOnboarding();
        }
      });
    });
    refreshOnboarding();
    const renderResults = (results) => {
      if (!results?.length) {
        resultHost.innerHTML = emptyState('Chưa có kết quả kiểm tra');
        return;
      }
      resultHost.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Mục kiểm tra</th><th>Kết quả</th><th>Mô tả</th><th>Thời gian</th></tr></thead><tbody>${results.map((result) => {
        const status = result.status === 'ok' ? 'Đạt' : result.status === 'ready' ? 'Đã cấu hình' : 'Cần xử lý';
        const className = result.status === 'ok' ? 'green' : result.status === 'ready' ? 'blue' : 'red';
        return `<tr><td>${escapeHtml(result.name)}</td><td><span class="tag ${className}">${status}</span></td><td>${escapeHtml(result.message)}</td><td>${result.latencyMs == null ? '-' : `${escapeHtml(result.latencyMs)} ms`}</td></tr>`;
      }).join('')}</tbody></table></div>`;
    };

    byId('run-diagnostics').addEventListener('click', async () => {
      const button = byId('run-diagnostics');
      button.disabled = true;
      button.textContent = 'Đang kiểm tra...';
      resultHost.innerHTML = loadingCard('Đang kiểm tra từng cấu hình và địa chỉ dịch vụ...');
      try {
        const payload = await request('/api/admin/config/diagnostics', { method: 'POST', body: {} });
        renderResults(payload.data || []);
      } catch (error) {
        resultHost.innerHTML = `<div class="alert error">${escapeHtml(error.message || 'Kiểm tra thất bại')}</div>`;
      } finally {
        button.disabled = false;
        button.textContent = 'Kiểm tra lại';
      }
    });
  }

  async function renderWelcome() {
    page().innerHTML = `
      ${pageHeader('Chào mừng', state.branding.welcome)}
      <div class="card welcome-host" id="welcome-host">${loadingCard('Đang tải trang chào mừng...')}</div>
    `;
    const host = byId('welcome-host');
    try {
      const response = await fetch(asset('welcome.html'), { cache: 'no-cache' });
      const text = await response.text();
      const styles = Array.from(text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi))
        .map((match) => `<style>${match[1]}</style>`)
        .join('');
      const bodyMatch = text.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
      host.innerHTML = `${styles}${bodyMatch ? bodyMatch[1] : text}`;
    } catch (_error) {
      host.innerHTML = `
        <div class="empty">
          <h3>${escapeHtml(state.branding.welcome)}</h3>
          <p>Chào mừng bạn đến với Bảng điều khiển quản trị Xiaozhi.</p>
        </div>
      `;
    }
  }

  async function renderDashboard() {
    page().innerHTML = `${pageHeader('Bảng tổng quan', 'Tổng quan vận hành hệ thống')}${loadingCard()}`;
    const data = await request('/api/user/summary').then((res) => res.data || {});
    const stats = [
      ['Số lượng người dùng', data.totle_users ?? '-'],
      ['Số lượng thiết bị', data.totle_devices ?? '-'],
      ['Số lượng trợ lý AI', data.totle_agents ?? '-'],
      ['Người dùng trực tuyến', data.online_users ?? '-'],
      ['Thiết bị đang đàm thoại', data.session_devices ?? '-'],
      ['Mức sử dụng RAM', formatPercent(data.system_memory_use)],
      ['Mức sử dụng CPU', formatPercent(data.system_cpu_use)],
    ];
    page().innerHTML = `
      ${pageHeader('Bảng tổng quan', 'Tổng quan vận hành hệ thống')}
      <div class="grid stats-grid">
        ${stats.map(([title, value]) => `
          <div class="card">
            <div class="muted">${escapeHtml(title)}</div>
            <div class="stat-value">${escapeHtml(value)}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  async function getProvidersByType(type) {
    try {
      const payload = await request(`/api/user/providers/${type}`);
      return parseProviderMap(payload, type);
    } catch (_error) {
      return [];
    }
  }

  function parseProviderMap(payload, type) {
    const source = payload?.data || {};
    return Object.entries(source).map(([name, raw]) => {
      const config = parseJson(raw, {});
      return {
        id: `${type}:${name}`,
        name,
        type,
        status: 'active',
        config,
      };
    });
  }

  async function getModelProviders() {
    const groups = await Promise.all(['ASR', 'TTS', 'LLM', 'VLLLM'].map(getProvidersByType));
    return groups.flat();
  }

  function providerDisplay(provider) {
    const config = provider.config || {};
    if (provider.type === 'LLM' || provider.type === 'VLLLM') {
      return config.model_name || config.model || config.url || '';
    }
    if (provider.type === 'TTS') {
      return config.voice || config.type || '';
    }
    return config.type || config.url || config.output_dir || '';
  }

  function collectVoices(ttsProviders) {
    const voices = [];
    const seen = new Set();
    ttsProviders.forEach((provider) => {
      const config = provider.config || {};
      const raw = config.supported_voices || config.surported_voices || config.supportedVoices || [];
      if (Array.isArray(raw)) {
        raw.forEach((item) => {
          const value = typeof item === 'string' ? item : item?.name;
          if (!value || seen.has(value)) return;
          seen.add(value);
          voices.push({
            value,
            label: typeof item === 'string'
              ? item
              : (item.display_name_zh || item.display_name_cn || item.display_name || item.displayName || item.name),
            language: typeof item === 'object' && item.language ? item.language : 'Tiếng Việt',
          });
        });
      }
      if (config.voice && !seen.has(config.voice)) {
        seen.add(config.voice);
        voices.push({ value: config.voice, label: config.voice, language: 'Tiếng Việt' });
      }
    });
    return voices;
  }

  function voiceLabel(voices, value) {
    return voices.find((voice) => voice.value === value)?.label || value || '';
  }

  async function renderAgents() {
    page().innerHTML = `
      ${pageHeader('Trợ lý AI', 'Quản lý các trợ lý AI và cấu hình nhân vật. Thiết bị mới kết nối sẽ tự động liên kết với trợ lý mặc định', `
        <input id="agent-search" placeholder="Tìm kiếm trợ lý AI" style="min-height:32px;padding:6px 10px;border:1px solid var(--line);border-radius:6px">
        <button class="btn primary" id="create-agent">Tạo trợ lý mới</button>
        <button class="btn" id="agent-add-device">Thêm thiết bị</button>
      `)}
      <div id="agents-body">${loadingCard('Đang tải danh sách trợ lý AI...')}</div>
    `;

    byId('agent-add-device').addEventListener('click', () => openBindDeviceModal());
    byId('create-agent').addEventListener('click', () => openCreateAgentModal());

    const [agentPayload, ttsProviders] = await Promise.all([
      request('/api/user/agent/list'),
      getProvidersByType('TTS'),
    ]);
    const voices = collectVoices(ttsProviders);
    const agents = normalizeList(agentPayload);

    const draw = () => {
      const keyword = byId('agent-search')?.value?.trim().toLowerCase() || '';
      const filtered = agents.filter((agent) => !keyword || String(agent.name || '').toLowerCase().includes(keyword));
      byId('agents-body').innerHTML = filtered.length
        ? `<div class="grid agent-grid">${filtered.map((agent) => agentCard(agent, voices)).join('')}</div>`
        : emptyState('Chưa có trợ lý AI', '<button class="btn primary" id="create-first-agent">Tạo trợ lý AI đầu tiên</button>');
      byId('create-first-agent')?.addEventListener('click', openCreateAgentModal);
    };

    byId('agent-search').addEventListener('input', draw);
    draw();
  }

  function agentCard(agent, voices) {
    const deviceCount = Array.isArray(agent.deviceIDs) ? agent.deviceIDs.length : 0;
    return `
      <div class="card">
        <div class="card-title">
          <h3>${escapeHtml(agent.name || 'Trợ lý chưa đặt tên')}</h3>
          ${agent.isOnboarding ? '<span class="tag blue">Mặc định</span>' : `<button class="btn ghost danger small" data-delete-agent="${escapeHtml(agent.id)}">Xóa</button>`}
        </div>
        <div class="chip-row">
          <span class="tag blue">ID ${escapeHtml(agent.id)}</span>
          <span class="tag">${escapeHtml(agent.LLM || '-')}</span>
        </div>
        <div class="divider"></div>
        <div class="form">
          <div><span class="muted">Giọng đọc: </span>${escapeHtml(voiceLabel(voices, agent.voice) || '-')}</div>
          ${agent.isOnboarding ? '<div><span class="muted">Vai trò: </span>Trợ lý tiếp nhận & thiết lập mặc định cho thiết bị mới</div>' : ''}
          <div><span class="muted">Hội thoại gần nhất: </span>${escapeHtml(formatDate(agent.lastConversationAt))}</div>
          <div><span class="muted">Số lượng thiết bị: </span>${deviceCount}</div>
        </div>
        <div class="divider"></div>
        <div class="inline-actions">
          <button class="btn" data-link="/console/agents/${escapeHtml(agent.id)}/config">Cấu hình nhân vật</button>
          <button class="btn" data-link="/console/agents/${escapeHtml(agent.id)}/history">Lịch sử hội thoại</button>
          <button class="btn" data-link="/console/agents/${escapeHtml(agent.id)}/device">Quản lý thiết bị</button>
        </div>
      </div>
    `;
  }

  async function openCreateAgentModal() {
    openModal({
      title: 'Tạo trợ lý AI mới',
      body: `
        <form class="form" id="create-agent-form">
          <div class="field">
            <label>Tên trợ lý AI</label>
            <input name="name" placeholder="Nhập tên trợ lý AI" required>
          </div>
        </form>
      `,
      footer: `
        <button class="btn" data-close-modal>Hủy</button>
        <button class="btn primary" id="create-agent-submit">Tạo mới</button>
      `,
    });
    byId('create-agent-submit').addEventListener('click', async () => {
      const form = byId('create-agent-form');
      if (!form.reportValidity()) return;
      const values = formValues(form);
      try {
        const [ttsProviders, llmProviders] = await Promise.all([
          getProvidersByType('TTS'),
          getProvidersByType('LLM'),
        ]);
        const voices = collectVoices(ttsProviders);
        const defaultVoice = voices[0]?.value || 'zh_female_wanwanxiaohe_moon_bigtts';
        const defaultVoiceName = voices[0]?.label || defaultVoice;
        const defaultLLM = llmProviders[0]?.name || 'Qwen';
        await request('/api/user/agent/create', {
          method: 'POST',
          body: {
            prompt: '',
            name: values.name,
            LLM: defaultLLM,
            language: 'Tiếng Việt',
            voice: defaultVoice,
            voiceName: defaultVoiceName,
            asrSpeed: 2,
            speakSpeed: 2,
            tone: 50,
          },
        });
        toast('Tạo trợ lý AI thành công', 'success');
        closeModal();
        render();
      } catch (error) {
        showError(error, 'Tạo thất bại');
      }
    });
  }

  async function openBindDeviceModal(selectedAgentId = '') {
    const agents = normalizeList(await request('/api/user/agent/list'));
    if (!agents.length) {
      toast('Vui lòng tạo một trợ lý AI trước', 'warning');
      return;
    }
    openModal({
      title: 'Liên kết thiết bị',
      body: `
        <form class="form" id="bind-device-form">
          <div class="field">
            <label>Trợ lý AI</label>
            <select name="agentID" required>
              ${agents.map((agent) => `<option value="${escapeHtml(agent.id)}" ${String(agent.id) === String(selectedAgentId) ? 'selected' : ''}>${escapeHtml(agent.name || `Trợ lý ${agent.id}`)}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>Địa chỉ MAC thiết bị</label>
            <input name="mac" placeholder="Ví dụ: 94:A9:90:31:E2:E4" autocomplete="off" spellcheck="false" required>
          </div>
          <p class="muted">Thiết bị phải đã gửi yêu cầu đến địa chỉ OTA của máy chủ ít nhất một lần. Hỗ trợ định dạng MAC có dấu hai chấm, gạch ngang hoặc liền nhau.</p>
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="bind-device-submit">Liên kết</button>`,
    });
    byId('bind-device-submit').addEventListener('click', async () => {
      const form = byId('bind-device-form');
      if (!form.reportValidity()) return;
      try {
        await request('/api/user/device/bind', { method: 'POST', body: formValues(form) });
        closeModal();
        toast('Liên kết thiết bị thành công', 'success');
        render();
      } catch (error) {
        showError(error, 'Liên kết thất bại: Vui lòng kiểm tra thiết bị đã kết nối và chưa bị tài khoản khác liên kết');
      }
    });
  }

  async function renderAgentConfig(route) {
    const id = route.params.id;
    page().innerHTML = `
      ${pageHeader('Cấu hình nhân vật', `Trợ lý AI ID: ${id}`, `<button class="btn" data-link="/console/agents">Quay lại</button>`)}
      <div id="agent-config-body">${loadingCard()}</div>
    `;
    const [agentPayload, ttsProviders, llmProviders, templates] = await Promise.all([
      request(`/api/user/agent/${id}`),
      getProvidersByType('TTS'),
      getProvidersByType('LLM'),
      fetch(asset('role_template.json'), { cache: 'no-cache' }).then((res) => res.json()).catch(() => []),
    ]);
    const agent = agentPayload.data || {};
    const voices = collectVoices(ttsProviders);
    if (agent.voice && !voices.some((voice) => voice.value === agent.voice)) {
      voices.unshift({ value: agent.voice, label: agent.voiceName || agent.voice, language: agent.language || 'Tiếng Việt' });
    }
    const languages = Array.from(new Set(voices.map((voice) => voice.language || 'Tiếng Việt')));

    byId('agent-config-body').innerHTML = `
      <form class="form" id="agent-config-form">
        <div class="card">
          <div class="card-title"><h3>Mẫu nhân vật</h3></div>
          <div class="chip-row">
            ${templates.map((tpl, index) => `
              <button type="button" class="btn small" data-template-index="${index}">${escapeHtml(tpl.name)}</button>
            `).join('') || '<span class="muted">Chưa có mẫu</span>'}
          </div>
        </div>
        <div class="card">
          <div class="card-title"><h3>Cấu hình cơ bản</h3></div>
          <div class="form-grid">
            <div class="field">
              <label>Tên gợi nhớ của trợ lý</label>
              <input name="assistantName" value="${escapeHtml(agent.name)}" required>
            </div>
            <div class="field">
              <label>Ngôn ngữ hội thoại</label>
              <select name="dialogLanguage" id="dialog-language">
                ${languages.map((language) => `<option value="${escapeHtml(language)}" ${language === agent.language ? 'selected' : ''}>${escapeHtml(language)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label>Giọng đọc nhân vật</label>
              <select name="voiceType" id="voice-type"></select>
            </div>
            <div class="field">
              <label>Mô hình ngôn ngữ (LLM)</label>
              <select name="languageModel" required>
                ${llmProviders.map((provider) => `
                  <option value="${escapeHtml(provider.name)}" ${provider.name === agent.LLM ? 'selected' : ''}>
                    ${escapeHtml(provider.name)}${providerDisplay(provider) ? ` (${escapeHtml(providerDisplay(provider))})` : ''}
                  </option>
                `).join('')}
              </select>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><h3>Giới thiệu nhân vật</h3></div>
          <div class="field">
            <label>Lời nhắc hệ thống (Prompt)</label>
            <textarea name="roleDescription" rows="8" required>${escapeHtml(agent.prompt || '')}</textarea>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><h3>Cài đặt nâng cao</h3></div>
          <div class="form-grid">
            <div class="field">
              <label>Tốc độ nhận dạng ASR</label>
              <select name="recognitionSpeed">
                <option value="1" ${agent.asrSpeed === 1 ? 'selected' : ''}>Kiên nhẫn (Chờ nói xong)</option>
                <option value="2" ${agent.asrSpeed !== 1 && agent.asrSpeed !== 3 ? 'selected' : ''}>Bình thường</option>
                <option value="3" ${agent.asrSpeed === 3 ? 'selected' : ''}>Nhanh</option>
              </select>
            </div>
            <div class="field">
              <label>Tốc độ nói</label>
              <select name="speechSpeed">
                <option value="1" ${agent.speakSpeed === 1 ? 'selected' : ''}>Chậm</option>
                <option value="2" ${agent.speakSpeed !== 1 && agent.speakSpeed !== 3 ? 'selected' : ''}>Bình thường</option>
                <option value="3" ${agent.speakSpeed === 3 ? 'selected' : ''}>Nhanh</option>
              </select>
            </div>
            <div class="field">
              <label>Cao độ giọng nói</label>
              <input name="pitchValue" type="range" min="0" max="100" value="${escapeHtml(agent.tone ?? 50)}">
            </div>
          </div>
        </div>
        <div class="inline-actions">
          <button type="button" class="btn" id="agent-reset">Đặt lại</button>
          <button type="submit" class="btn primary">Lưu</button>
        </div>
      </form>
    `;

    const syncVoiceOptions = () => {
      const selectedLanguage = byId('dialog-language').value;
      const filtered = voices.filter((voice) => (voice.language || 'Tiếng Việt') === selectedLanguage);
      const options = (filtered.length ? filtered : voices).map((voice) => `
        <option value="${escapeHtml(voice.value)}" ${voice.value === agent.voice ? 'selected' : ''}>${escapeHtml(voice.label)}</option>
      `).join('');
      byId('voice-type').innerHTML = options || `<option value="${escapeHtml(agent.voice || '')}">${escapeHtml(agent.voiceName || agent.voice || 'Giọng mặc định')}</option>`;
    };
    syncVoiceOptions();
    byId('dialog-language').addEventListener('change', syncVoiceOptions);

    qsa('[data-template-index]').forEach((button) => {
      button.addEventListener('click', () => {
        const tpl = templates[Number(button.dataset.templateIndex)];
        const name = qs('[name="assistantName"]').value || '';
        qs('[name="roleDescription"]').value = String(tpl.prompt || '').replace(/\{\{\s*assistant_name\s*\}\}/g, name);
      });
    });

    byId('agent-reset').addEventListener('click', () => renderAgentConfig(route));
    byId('agent-config-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      const selectedVoice = voices.find((voice) => voice.value === values.voiceType);
      try {
        await request(`/api/user/agent/${id}`, {
          method: 'PUT',
          body: {
            prompt: values.roleDescription,
            name: values.assistantName,
            LLM: values.languageModel,
            language: values.dialogLanguage,
            voice: values.voiceType,
            voiceName: selectedVoice?.label || values.voiceType,
            asrSpeed: Number(values.recognitionSpeed),
            speakSpeed: Number(values.speechSpeed),
            tone: Number(values.pitchValue),
          },
        });
        toast('Lưu thành công', 'success');
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  async function renderDevices(route) {
    const id = route.params.id;
    page().innerHTML = `
      ${pageHeader('Quản lý thiết bị', `Trợ lý AI ID: ${id}`, `
        <button class="btn" data-link="/console/agents">Quay lại</button>
        <button class="btn primary" id="add-device">Thêm thiết bị</button>
      `)}
      <div id="devices-body">${loadingCard()}</div>
    `;
    byId('add-device').addEventListener('click', () => openBindDeviceModal(id));
    const payload = await request(`/api/user/device/list/${id}`);
    const devices = normalizeList(payload);
    byId('devices-body').innerHTML = devices.length
      ? `<div class="grid device-grid">${devices.map(deviceCard).join('')}</div>`
      : emptyState('Chưa có thiết bị nào');
  }

  function deviceCard(device) {
    const deviceId = device.deviceId || device.DeviceID || '';
	    const macAddress = device.macAddress || device.MACAddress || deviceId;
    return `
      <div class="card">
        <div class="card-title">
          <h3>${escapeHtml(device.name || 'Thiết bị chưa đặt tên')}</h3>
          <button class="btn ghost danger small" data-unbind-device="${escapeHtml(deviceId)}">Hủy liên kết</button>
        </div>
        <div class="form">
          <div><span class="muted">Địa chỉ MAC: </span>${escapeHtml(maskDeviceId(macAddress))}</div>
          <div><span class="muted">Phiên bản Firmware: </span>${escapeHtml(device.version || '-')}</div>
          <div><span class="muted">Hoạt động gần nhất: </span>${escapeHtml(formatDate(device.lastActiveTimeV2 || device.lastActiveTime))}</div>
          <div><span class="muted">Trạng thái thiết bị: </span>${device.mode === 'ban' ? '<span class="tag red">Đã vô hiệu</span>' : '<span class="tag green">Hoạt động</span>'}</div>
          <div><span class="muted">Nâng cấp OTA: </span>${device.ota ? '<span class="tag green">Bật</span>' : '<span class="tag">Tắt</span>'}</div>
        </div>
        <div class="divider"></div>
        <button class="btn small" data-copy="${escapeHtml(macAddress)}">Sao chép MAC</button>
        <button class="btn small" data-toggle-device="${escapeHtml(deviceId)}" data-disabled="${device.mode === 'ban' ? 'true' : 'false'}">${device.mode === 'ban' ? 'Bật thiết bị' : 'Vô hiệu thiết bị'}</button>
        <button class="btn ghost small" data-clear-device-memory="${escapeHtml(deviceId)}">Xóa trí nhớ ngắn hạn</button>
      </div>
    `;
  }

  function maskDeviceId(value) {
    const parts = String(value || '').split(':');
    if (parts.length === 6) return `${parts[0]}:${parts[1]}:**:**:${parts[4]}:${parts[5]}`;
    return value || '-';
  }

  async function renderHistory(route) {
    const id = route.params.id;
    page().innerHTML = `
      ${pageHeader('Lịch sử hội thoại', `Trợ lý AI ID: ${id}`, `<button class="btn" data-link="/console/agents">Quay lại</button>`)}
      <div class="history-layout">
        <div class="conversation-list" id="conversation-list">${loadingCard()}</div>
        <div class="message-panel" id="message-panel">
          <div class="empty">Vui lòng chọn một phiên hội thoại</div>
        </div>
      </div>
    `;
    const payload = await request(`/api/user/agent/history_dialog_list/${id}`, { method: 'POST' });
    const conversations = normalizeList(payload);
    const list = byId('conversation-list');
    list.innerHTML = conversations.length
      ? conversations.map((item) => `
        <button class="conversation-item" data-conversation="${escapeHtml(item.id)}">
          <strong>${escapeHtml(formatDate(item.createdAt))}</strong>
          <div class="subtle">ID ${escapeHtml(item.id)} · ${escapeHtml(item.conversationId || '')}</div>
        </button>
      `).join('')
      : emptyState('Chưa có lịch sử hội thoại');
  }

  async function selectConversation(id) {
    qsa('.conversation-item').forEach((button) => {
      button.classList.toggle('active', button.dataset.conversation === String(id));
    });
    const panel = byId('message-panel');
    panel.innerHTML = loadingCard('Đang tải chi tiết hội thoại...');
    const payload = await request(`/api/user/agent/history_dialog/${id}`);
    const dialog = payload?.data || {};
    const messages = parseJson(dialog.dialog, []);
    panel.innerHTML = `
      <div class="message-header">
        Chi tiết hội thoại - ${escapeHtml(formatDate(dialog.createdAt))}
        <button class="btn danger small" style="float:right" data-delete-dialog="${escapeHtml(id)}">Xóa hội thoại</button>
      </div>
      <div class="message-list">
        ${Array.isArray(messages) && messages.length
          ? messages.map((message, index) => `
            <div class="message ${escapeHtml(message.role || 'assistant')}">
              <div class="subtle">${escapeHtml(message.role || `Tin nhắn ${index + 1}`)}</div>
              ${escapeHtml(message.content || '')}
            </div>
          `).join('')
          : emptyState('Chưa có tin nhắn')}
      </div>
    `;
  }

  async function renderProfile() {
    page().innerHTML = `${pageHeader('Cài đặt cá nhân', 'Quản lý thông tin hồ sơ và mật khẩu đăng nhập')}${loadingCard()}`;
    const payload = await request('/api/user/profile');
    const user = payload.data || {};
    page().innerHTML = `
      ${pageHeader('Cài đặt cá nhân', 'Quản lý thông tin hồ sơ và mật khẩu đăng nhập')}
      <div class="card">
        <form class="form" id="profile-form">
          <div class="form-grid">
            <div class="field">
              <label>Tên người dùng</label>
              <input value="${escapeHtml(user.username)}" disabled>
            </div>
            <div class="field">
              <label>Biệt danh</label>
              <input name="nickname" value="${escapeHtml(user.nickname || user.username || '')}">
            </div>
            <div class="field">
              <label>Email</label>
              <input name="email" type="email" value="${escapeHtml(user.email || '')}">
            </div>
            <div class="field">
              <label>URL Ảnh đại diện</label>
              <input name="head_img" value="${escapeHtml(user.head_img || '')}">
            </div>
          </div>
          <div class="inline-actions">
            <button class="btn primary" type="submit">Lưu thông tin</button>
            <button class="btn" type="button" id="change-password">Đổi mật khẩu</button>
          </div>
        </form>
      </div>
    `;
    byId('profile-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await request('/api/user/profile', { method: 'PUT', body: formValues(event.currentTarget) });
        toast('Lưu thành công', 'success');
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
    byId('change-password').addEventListener('click', openPasswordModal);
  }

  function openPasswordModal() {
    openModal({
      title: 'Đổi mật khẩu',
      body: `
        <form class="form" id="password-form">
          <div class="field"><label>Mật khẩu cũ</label><input name="old_password" type="password" required></div>
          <div class="field"><label>Mật khẩu mới</label><input name="new_password" type="password" minlength="6" required></div>
          <div class="field"><label>Xác nhận mật khẩu mới</label><input name="confirm_password" type="password" minlength="6" required></div>
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="password-submit">Lưu</button>`,
    });
    byId('password-submit').addEventListener('click', async () => {
      const form = byId('password-form');
      if (!form.reportValidity()) return;
      const values = formValues(form);
      if (values.new_password !== values.confirm_password) {
        toast('Mật khẩu xác nhận không khớp', 'warning');
        return;
      }
      try {
        await request('/api/user/change-password', {
          method: 'POST',
          body: {
            old_password: values.old_password,
            new_password: values.new_password,
          },
        });
        toast('Đổi mật khẩu thành công', 'success');
        closeModal();
      } catch (error) {
        showError(error, 'Đổi mật khẩu thất bại');
      }
    });
  }

  async function renderAdminSettings() {
    page().innerHTML = `${pageHeader('Cấu hình hệ thống', 'Lựa chọn mô hình AI & Lời nhắc toàn cục')}${loadingCard()}`;
    const payload = await request('/api/admin/system');
    const config = payload.data || {};
    page().innerHTML = `
      ${pageHeader('Cấu hình hệ thống', 'Lựa chọn mô hình AI & Lời nhắc toàn cục')}
      <div class="card">
        <form class="form" id="admin-settings-form">
          <div class="form-grid">
            ${selectField('selectedASR', 'Dịch vụ ASR (Nhận dạng giọng nói)', config.selectedASR, config.asrList || [])}
            ${selectField('selectedTTS', 'Dịch vụ TTS (Tổng hợp giọng nói)', config.selectedTTS, config.ttsList || [])}
            ${selectField('selectedLLM', 'Dịch vụ LLM (Mô hình ngôn ngữ)', config.selectedLLM, config.llmList || [])}
            ${selectField('selectedVLLLM', 'Dịch vụ VLLM (Thị giác AI)', config.selectedVLLLM, config.vllmList || [])}
          </div>
          <div class="field">
            <label>Cài đặt lời nhắc hệ thống (Prompt)</label>
            <textarea name="prompt" rows="10">${escapeHtml(config.prompt || '')}</textarea>
          </div>
          <div class="field">
            <label>Từ phản hồi nhanh</label>
            <div class="chip-row" id="quick-reply-list">
              ${(config.quickReplyWords || []).map((word, index) => quickReplyTag(word, index)).join('')}
            </div>
            <div class="input-with-button">
              <input id="quick-reply-input" placeholder="Nhập cụm từ phản hồi nhanh mới (ví dụ: Dạ em đây)">
              <button type="button" class="btn" id="quick-reply-add">Thêm</button>
            </div>
          </div>
          <div class="inline-actions">
            <button type="button" class="btn" id="settings-reset">Đặt lại</button>
            <button type="submit" class="btn primary" ${canWriteAdmin() ? '' : 'disabled'}>Lưu cấu hình</button>
          </div>
        </form>
      </div>
    `;
    let quickReplies = [...(config.quickReplyWords || [])];
    const drawQuickReplies = () => {
      byId('quick-reply-list').innerHTML = quickReplies.map((word, index) => quickReplyTag(word, index)).join('');
    };
    byId('quick-reply-add').addEventListener('click', () => {
      const input = byId('quick-reply-input');
      const value = input.value.trim();
      if (!value || quickReplies.includes(value)) return;
      quickReplies.push(value);
      input.value = '';
      drawQuickReplies();
    });
    byId('quick-reply-list').addEventListener('click', (event) => {
      const target = event.target.closest('[data-remove-quick]');
      if (!target) return;
      event.stopPropagation();
      quickReplies.splice(Number(target.dataset.removeQuick), 1);
      drawQuickReplies();
    });
    byId('settings-reset').addEventListener('click', renderAdminSettings);
    byId('admin-settings-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      const next = {
        selectedASR: values.selectedASR,
        selectedTTS: values.selectedTTS,
        selectedLLM: values.selectedLLM,
        selectedVLLLM: values.selectedVLLLM,
        prompt: values.prompt,
        quickReplyWords: quickReplies,
      };
      try {
        await request('/api/admin/system', { method: 'POST', body: { data: JSON.stringify(next) } });
        toast('Lưu cấu hình thành công', 'success');
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  function selectField(name, label, value, options) {
    return `
      <div class="field">
        <label>${escapeHtml(label)}</label>
        <select name="${escapeHtml(name)}">
          <option value="">-- Vui lòng chọn --</option>
          ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}
        </select>
      </div>
    `;
  }

  function quickReplyTag(word, index) {
    return `<span class="tag blue">${escapeHtml(word)} <button type="button" class="btn link" data-remove-quick="${index}">×</button></span>`;
  }

  async function renderProviders() {
    page().innerHTML = `
      ${pageHeader('Nhà cung cấp AI', 'Quản lý thông tin xác thực ASR, TTS, LLM và VLLM', `
        <input id="provider-search" placeholder="Tìm kiếm nhà cung cấp" style="min-height:32px;padding:6px 10px;border:1px solid var(--line);border-radius:6px">
        <select id="provider-filter" style="min-height:32px;padding:6px 10px;border:1px solid var(--line);border-radius:6px">
          <option value="all">Tất cả các loại</option>
          <option value="ASR">ASR</option>
          <option value="TTS">TTS</option>
          <option value="LLM">LLM</option>
          <option value="VLLLM">VLLLM</option>
        </select>
        <button class="btn primary" id="provider-add">Thêm nhà cung cấp</button>
      `)}
      <div id="providers-body">${loadingCard()}</div>
    `;
    byId('provider-add').addEventListener('click', () => openProviderModal());
    const providers = await getModelProviders();
    const draw = () => {
      const keyword = byId('provider-search').value.trim().toLowerCase();
      const filter = byId('provider-filter').value;
      const filtered = providers.filter((provider) => {
        const text = `${provider.name} ${provider.type} ${providerDisplay(provider)}`.toLowerCase();
        return (filter === 'all' || provider.type === filter) && (!keyword || text.includes(keyword));
      });
      const stats = ['ASR', 'TTS', 'LLM', 'VLLLM'].map((type) => `${type}: ${providers.filter((p) => p.type === type).length}`).join('，');
      byId('providers-body').innerHTML = `
        <div class="card"><span class="muted">${escapeHtml(stats)}</span></div>
        ${filtered.length ? `<div class="grid provider-grid section">${filtered.map(providerCard).join('')}</div>` : emptyState('Không tìm thấy nhà cung cấp phù hợp')}
      `;
    };
    byId('provider-search').addEventListener('input', draw);
    byId('provider-filter').addEventListener('change', draw);
    draw();
  }

  function providerCard(provider) {
    const config = provider.config || {};
    const configRows = Object.entries(config).filter(([key]) => key !== 'type').slice(0, 5).map(([key, value]) => `
      <div><span class="muted">${escapeHtml(providerFieldLabel(key))}：</span>${escapeHtml(displayProviderValue(key, value))}</div>
    `).join('');
    return `
      <div class="card provider-card">
        <div class="card-title">
          <div>
            <h3>${escapeHtml(provider.name)}</h3>
            <span class="subtle">${escapeHtml(providerTypeLabel(provider.type))}</span>
          </div>
          <div class="chip-row"><span class="tag blue">${escapeHtml(provider.type)}</span><span class="tag">${escapeHtml(config.type || 'Chưa đặt loại')}</span></div>
        </div>
        <div class="form">${configRows || '<span class="muted">Chưa có cấu hình</span>'}</div>
        <div class="divider"></div>
        <div class="inline-actions">
          <button class="btn small" data-test-provider="${escapeHtml(provider.type)}:${escapeHtml(provider.name)}">Kiểm tra</button>
          <button class="btn small" data-edit-provider="${escapeHtml(provider.type)}:${escapeHtml(provider.name)}">Chỉnh sửa</button>
          <button class="btn danger small" data-delete-provider="${escapeHtml(provider.type)}:${escapeHtml(provider.name)}">Xóa</button>
        </div>
        <div class="provider-test-result" aria-live="polite"></div>
      </div>
    `;
  }

  const PROVIDER_FIELDS = {
    ASR: {
      doubao: { label: 'Volcengine ASR (Doubao)', fields: [['appid', 'App ID', 'Ví dụ: 1234567890', true], ['access_token', 'Access Token', 'Nhập Access Token từ bảng điều khiển', true], ['output_dir', 'Thư mục tạm', 'tmp/'], ['end_window_size', 'Thời gian im lặng kết thúc (ms)', '300', false, 'number']] },
      deepgram: { label: 'Deepgram', fields: [['addr', 'Địa chỉ máy chủ', 'wss://api.deepgram.com/v1/listen'], ['api_key', 'API Key', 'Nhập Deepgram API Key', true], ['lang', 'Ngôn ngữ nhận dạng', 'vi-VN'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
      gosherpa: { label: 'GoSherpa', fields: [['addr', 'Địa chỉ máy chủ', 'ws://127.0.0.1:8848/asr']] },
      stepfun: { label: 'StepFun', fields: [['api_key', 'API Key', 'Nhập StepFun API Key', true], ['model', 'Tên mô hình', 'step-audio-2-mini'], ['voice', 'Giọng đọc', 'qingchunshaonv']] },
      iflytek: { label: 'iFlytek ASR', fields: [['appid', 'App ID', 'Nhập App ID', true], ['api_key', 'API Key', 'Nhập API Key', true], ['api_secret', 'API Secret', 'Nhập API Secret', true], ['asr_url', 'Địa chỉ máy chủ', 'wss://iat-api.xfyun.cn/v2/iat']] },
    },
    TTS: {
      edge: { label: 'Microsoft Edge TTS', fields: [['voice', 'Giọng đọc (ví dụ: vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural)', 'vi-VN-HoaiMyNeural'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
      doubao: { label: 'Volcengine TTS (Doubao)', fields: [['appid', 'App ID', 'Nhập App ID', true], ['token', 'Access Token', 'Nhập Access Token', true], ['cluster', 'Cụm tài nguyên', 'Nhập tên cluster'], ['voice', 'Giọng đọc', 'zh_female_wanwanxiaohe_moon_bigtts'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
      gosherpa: { label: 'GoSherpa', fields: [['cluster', 'Địa chỉ máy chủ', 'ws://127.0.0.1:8848/tts'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
      deepgram: { label: 'Deepgram', fields: [['cluster', 'Địa chỉ máy chủ', 'wss://api.deepgram.com/v1/speak'], ['token', 'API Key', 'Nhập Deepgram API Key', true], ['voice', 'Giọng đọc', 'aura-2-zeus-en'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
      iflytek: { label: 'iFlytek TTS', fields: [['appid', 'App ID', 'Nhập App ID', true], ['token', 'API Key', 'Nhập API Key', true], ['cluster', 'API Secret', 'Nhập API Secret', true], ['voice', 'Giọng đọc', 'xiaoyan'], ['output_dir', 'Thư mục tạm', 'tmp/']] },
    },
    LLM: {
      openai: { label: 'OpenAI / Tương thích OpenAI', fields: [['url', 'Địa chỉ API (URL)', 'https://api.openai.com/v1'], ['api_key', 'API Key', 'Nhập API Key', true], ['model_name', 'Tên mô hình', 'Ví dụ: gpt-4o-mini, gpt-4o, gemini-2.0-flash'], ['max_tokens', 'Số Token tối đa', '1000', false, 'number']] },
      ollama: { label: 'Ollama (Mô hình cục bộ)', fields: [['url', 'Địa chỉ Ollama', 'http://127.0.0.1:11434'], ['model_name', 'Tên mô hình', 'Ví dụ: qwen2.5:7b']] },
      dsh: { label: 'DSH Xiaozhi Bridge', suggestedName: 'DSHBridge', fields: [['url', 'Địa chỉ Bridge WebSocket', 'ws://127.0.0.1:17980/xiaozhi', false, 'url', 'ws://127.0.0.1:17980/xiaozhi'], ['api_key', 'Token Bridge', 'Giống với XIAOZHI_BRIDGE_TOKEN', true]] },
      doubao: { label: 'Volcengine Ark (Doubao LLM)', fields: [['url', 'Địa chỉ API (URL)', 'https://ark.cn-beijing.volces.com/api/v3'], ['api_key', 'API Key', 'Nhập API Key', true], ['model_name', 'Tên mô hình / Endpoint ID', 'Nhập ID endpoint mô hình'], ['max_tokens', 'Số Token tối đa', '4000', false, 'number']] },
      coze: { label: 'Coze Bot', fields: [['bot_id', 'Bot ID', 'Nhập Bot ID', true], ['user_id', 'User ID', 'Nhập User ID', true], ['personal_access_token', 'Personal Access Token', 'Nhập PAT', true], ['url', 'Địa chỉ API (URL)', 'https://api.coze.cn']] },
    },
    VLLLM: {
      openai: { label: 'OpenAI VLLM (Thị giác)', fields: [['url', 'Địa chỉ API (URL)', 'https://api.openai.com/v1'], ['api_key', 'API Key', 'Nhập API Key', true], ['model_name', 'Tên mô hình', 'Ví dụ: gpt-4o, glm-4v-flash'], ['max_tokens', 'Số Token tối đa', '1024', false, 'number']] },
      ollama: { label: 'Ollama VLLM (Thị giác)', fields: [['url', 'Địa chỉ Ollama', 'http://127.0.0.1:11434'], ['model_name', 'Tên mô hình', 'Ví dụ: qwen2.5vl:7b']] },
    },
  };

  const PROVIDER_FIELD_LABELS = { url: 'Địa chỉ máy chủ (URL)', addr: 'Địa chỉ máy chủ', asr_url: 'Địa chỉ ASR', cluster: 'Địa chỉ / Cụm dịch vụ', model_name: 'Tên mô hình', model: 'Tên mô hình', voice: 'Giọng đọc', type: 'Loại cụ thể', appid: 'App ID', lang: 'Ngôn ngữ', output_dir: 'Thư mục tạm', max_tokens: 'Số Token tối đa' };

  function providerTypeLabel(type) {
    return { ASR: 'Nhận dạng giọng nói (ASR)', TTS: 'Tổng hợp giọng nói (TTS)', LLM: 'Mô hình ngôn ngữ (LLM)', VLLLM: 'Mô hình thị giác (VLLM)' }[type] || type;
  }

  function providerFieldLabel(key) {
    return PROVIDER_FIELD_LABELS[key] || key;
  }

  function displayProviderValue(key, value) {
    if (/(token|secret|key|password)/i.test(key)) return 'Đã nhập (Ẩn vì bảo mật)';
    if (value == null) return '';
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    return text.length > 64 ? `${text.slice(0, 56)}…` : text;
  }

  async function openProviderModal(provider = null) {
    const config = provider?.config || { type: 'openai' };
    const selectedType = provider?.type || 'LLM';
    const selectedSubType = config.type || Object.keys(PROVIDER_FIELDS[selectedType] || {})[0] || 'openai';
    openModal({
      title: provider ? 'Chỉnh sửa nhà cung cấp' : 'Thêm nhà cung cấp',
      body: `
        <form class="form" id="provider-form">
          <div class="alert provider-form-intro">Chọn loại dịch vụ và nhà cung cấp, sau đó điền các trường tương ứng. Khóa bí mật API sẽ được bảo mật và không hiển thị trên thẻ.</div>
          <div class="form-grid">
            <div class="field">
              <label>Phân loại dịch vụ</label>
              <select name="type" ${provider ? 'disabled' : ''}>
                ${['ASR', 'TTS', 'LLM', 'VLLLM'].map((type) => `<option value="${type}" ${selectedType === type ? 'selected' : ''}>${type} · ${providerTypeLabel(type)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label>Tên nhà cung cấp</label>
              <input name="name" value="${escapeHtml(provider?.name || '')}" placeholder="Ví dụ: OpenAI Chính, EdgeTTS, Ollama..." ${provider ? 'disabled' : ''} required>
            </div>
            <div class="field">
              <label>Loại triển khai cụ thể</label>
              <select name="subType" id="provider-subtype" required></select>
            </div>
            <div class="field" id="provider-custom-subtype-field" hidden>
              <label for="provider-custom-subtype">Loại tự định nghĩa</label>
              <input name="customSubType" id="provider-custom-subtype" placeholder="Ví dụ: my_provider">
            </div>
          </div>
          <div id="provider-config-fields" class="form-grid"></div>
          <details class="provider-advanced">
            <summary>Cấu hình JSON nâng cao (Tùy chọn)</summary>
            <p class="subtle">Biểu mẫu sẽ đồng bộ vào đây; chỉ chỉnh sửa trực tiếp khi bạn cần thêm tham số nâng cao.</p>
            <textarea class="codebox" name="configJson" spellcheck="false">${escapeHtml(prettyJson(config))}</textarea>
          </details>
          <div id="provider-form-status" class="subtle">Sau khi lưu, bạn có thể bấm nút Kiểm tra trên thẻ nhà cung cấp.</div>
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="provider-submit">Lưu</button>`,
    });

    const form = byId('provider-form');
    const typeInput = form.elements.type;
    const subTypeInput = form.elements.subType;
    const customSubTypeInput = form.elements.customSubType;
    const jsonInput = form.elements.configJson;
    const currentConfig = () => parseJson(jsonInput.value, {}) || {};
    const effectiveSubType = () => (subTypeInput.value === '__custom__' ? customSubTypeInput.value.trim() : subTypeInput.value.trim());
    const renderProviderFields = (resetConfig = false) => {
      const type = provider?.type || typeInput.value;
      const definitions = PROVIDER_FIELDS[type] || {};
      const knownSubType = Object.prototype.hasOwnProperty.call(definitions, selectedSubType.toLowerCase()) ? selectedSubType.toLowerCase() : '';
      const shouldSetInitialSubType = !resetConfig && !subTypeInput.dataset.initialized;
      const selectedBeforeRender = subTypeInput.value;
      subTypeInput.innerHTML = `${Object.entries(definitions).map(([value, definition]) => `<option value="${escapeHtml(value)}">${escapeHtml(`${value} · ${definition.label}`)}</option>`).join('')}<option value="__custom__">Tự định nghĩa loại…</option>`;
      if (resetConfig) subTypeInput.value = Object.keys(definitions)[0] || '__custom__';
      if (shouldSetInitialSubType) {
        subTypeInput.value = knownSubType || '__custom__';
        customSubTypeInput.value = knownSubType ? '' : selectedSubType;
        subTypeInput.dataset.initialized = 'true';
      } else if (!resetConfig) {
        subTypeInput.value = selectedBeforeRender;
      }
      if (!subTypeInput.value) subTypeInput.value = '__custom__';
      const customType = subTypeInput.value === '__custom__';
      const customTypeField = byId('provider-custom-subtype-field');
      customTypeField.hidden = !customType;
      customSubTypeInput.required = customType;
      const subType = effectiveSubType().toLowerCase();
      const definition = definitions[subType];
      if (resetConfig) {
        jsonInput.value = prettyJson({ type: subType || Object.keys(definitions)[0] || 'openai' });
      }
      const configValue = currentConfig();
      const fields = definition?.fields || [];
      byId('provider-config-fields').innerHTML = fields.length ? fields.map(([key, label, placeholder, secret, inputType, defaultValue]) => `
        <div class="field">
          <label for="provider-field-${escapeHtml(key)}">${escapeHtml(label)}</label>
          <div class="${secret ? 'input-with-button' : ''}">
            <input id="provider-field-${escapeHtml(key)}" data-provider-config-field="${escapeHtml(key)}" type="${secret ? 'password' : (inputType || 'text')}" value="${escapeHtml(configValue[key] ?? defaultValue ?? '')}" placeholder="${escapeHtml(placeholder || '')}" ${['appid', 'access_token', 'api_key', 'api_secret', 'token', 'model_name', 'model', 'voice'].includes(key) || (subType === 'dsh' && key === 'url') ? 'required' : ''}>
            ${secret ? `<button class="btn small" type="button" data-toggle-provider-secret aria-label="Hiện hoặc ẩn ${escapeHtml(label)}">Hiện</button>` : ''}
          </div>
        </div>
      `).join('') : '<div class="alert warning">Loại này chưa có trường dựng sẵn, vui lòng nhập cấu hình trong JSON nâng cao.</div>';
      qsa('[data-provider-config-field]', form).forEach((input) => input.addEventListener('input', syncProviderJson));
      qsa('[data-toggle-provider-secret]', form).forEach((button) => button.addEventListener('click', () => {
        const input = button.parentElement.querySelector('[data-provider-config-field]');
        const hidden = input.type === 'password';
        input.type = hidden ? 'text' : 'password';
        button.textContent = hidden ? 'Ẩn' : 'Hiện';
      }));
      if (definition?.suggestedName && !provider && !form.elements.name.value.trim()) form.elements.name.placeholder = `Tên gợi ý: ${definition.suggestedName}`;
      byId('provider-form-status').textContent = definition ? `Đã chọn: ${providerTypeLabel(type)} · ${definition.label}${definition.suggestedName ? `; Tên nhà cung cấp gợi ý: ${definition.suggestedName}` : ''}` : 'Vui lòng nhập loại tự định nghĩa và bổ sung cấu hình trong JSON.';
    };
    const syncProviderJson = () => {
      const configValue = currentConfig();
      configValue.type = effectiveSubType();
      qsa('[data-provider-config-field]', form).forEach((input) => {
        const value = input.value.trim();
        if (!value) return;
        configValue[input.dataset.providerConfigField] = input.type === 'number' ? Number(value) : value;
      });
      jsonInput.value = prettyJson(configValue);
    };
    typeInput.addEventListener('change', () => {
      const type = typeInput.value;
      subTypeInput.innerHTML = '';
      customSubTypeInput.value = '';
      renderProviderFields(true);
    });
    subTypeInput.addEventListener('change', () => { syncProviderJson(); renderProviderFields(false); });
    customSubTypeInput.addEventListener('input', syncProviderJson);
    renderProviderFields(false);
    byId('provider-submit').addEventListener('click', async () => {
      if (!form.reportValidity()) return;
      const values = formValues(form);
      const type = provider?.type || values.type;
      const name = provider?.name || values.name;
      syncProviderJson();
      const config = parseJson(values.configJson, null);
      if (!config) {
        toast('Định dạng JSON cấu hình không hợp lệ', 'warning');
        return;
      }
      config.type = effectiveSubType() || config.type;
      try {
        if (provider) {
          await request(`/api/user/providers/${encodeURIComponent(type)}/${encodeURIComponent(name)}`, {
            method: 'PUT',
            body: { data: config },
          });
        } else {
          await request('/api/user/providers/create', {
            method: 'POST',
            body: { type, name, data: config },
          });
        }
        toast('Lưu thành công', 'success');
        closeModal();
        render();
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  async function renderUnbindDevice() {
    page().innerHTML = `
      ${pageHeader('Hủy liên kết thiết bị', 'Quản trị viên có thể hủy liên kết thiết bị theo ID')}
      <div class="card">
        <form class="form" id="unbind-form">
          <div class="field">
            <label>ID Thiết bị (hoặc MAC)</label>
            <input name="deviceID" placeholder="Nhập ID thiết bị hoặc MAC" required>
          </div>
          <button class="btn danger" type="submit" ${canWriteAdmin() ? '' : 'disabled'}>Hủy liên kết</button>
        </form>
      </div>
    `;
    byId('unbind-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      try {
        await request('/api/admin/system/device', { method: 'DELETE', body: { deviceID: values.deviceID } });
        toast('Hủy liên kết thiết bị thành công', 'success');
      } catch (error) {
        showError(error, 'Hủy liên kết thất bại');
      }
    });
  }

  async function renderAdvancedConfig() {
    page().innerHTML = `
      ${pageHeader('Cấu hình nâng cao', 'Quản lý các thông số vận hành hệ thống')}
      <div class="card">
        <div class="tabs">
          ${[
            ['application', 'Cấu hình ứng dụng'],
            ['transport', 'Cấu hình truyền dẫn'],
            ['web', 'Cấu hình Web'],
            ['auth', 'Cấu hình xác thực'],
            ['roles', 'Cấu hình nhân vật'],
            ['mcp-functions', 'Chức năng MCP cục bộ'],
            ['exit-commands', 'Khẩu lệnh thoát'],
            ['log', 'Cấu hình nhật ký (Log)'],
          ].map(([key, label]) => `<button class="tab ${state.advancedTab === key ? 'active' : ''}" data-advanced-tab="${key}">${label}</button>`).join('')}
        </div>
        <div id="advanced-body">${loadingCard()}</div>
      </div>
    `;
    await drawAdvancedTab(state.advancedTab);
  }

  async function drawAdvancedTab(tab) {
    state.advancedTab = tab;
    qsa('[data-advanced-tab]').forEach((button) => button.classList.toggle('active', button.dataset.advancedTab === tab));
    const body = byId('advanced-body');
    body.innerHTML = loadingCard();
    if (tab === 'application') return drawSimpleConfig('application', [
      ['quickReply', 'Bật phản hồi nhanh', 'checkbox'],
      ['saveTtsAudio', 'Lưu file âm thanh TTS', 'checkbox'],
      ['saveUserAudio', 'Lưu file âm thanh người dùng', 'checkbox'],
    ]);
    if (tab === 'web') return drawSimpleConfig('web', [
      ['port', 'Cổng dịch vụ Web', 'number'],
      ['staticDir', 'Thư mục tài nguyên tĩnh', 'text'],
      ['websocket', 'Địa chỉ WebSocket cho thiết bị', 'text'],
      ['visionUrl', 'URL dịch vụ thị giác (Vision)', 'text'],
      ['activateText', 'Văn bản kích hoạt', 'text'],
    ]);
    if (tab === 'auth') return drawSimpleConfig('auth', [
      ['token', 'Mã xác thực máy chủ (Token)', 'password'],
      ['expiry', 'Thời gian hết hạn (giờ)', 'number'],
    ]);
    if (tab === 'log') return drawSimpleConfig('log', [
      ['logLevel', 'Mức độ log', 'select:debug,info,warn,error'],
      ['logDir', 'Thư mục chứa log', 'text'],
      ['logFile', 'Tên file log', 'text'],
    ]);
    if (tab === 'transport') return drawTransportConfig();
    if (tab === 'roles') return drawCollectionConfig('roles', 'nhân vật', ['name', 'description', 'enabled']);
    if (tab === 'mcp-functions') return drawCollectionConfig('mcp-functions', 'chức năng MCP cục bộ', ['functionName', 'description', 'enabled']);
    if (tab === 'exit-commands') return drawCollectionConfig('exit-commands', 'khẩu lệnh thoát', ['command', 'enabled']);
  }

  async function drawSimpleConfig(type, fields) {
    const config = await request(`/api/admin/config/${type}`).then((res) => res.data || {});
    byId('advanced-body').innerHTML = `
      <form class="form" id="simple-config-form">
        <div class="form-grid">
          ${fields.map(([key, label, fieldType]) => simpleField(key, label, fieldType, config[key])).join('')}
        </div>
        <button class="btn primary" type="submit" ${canWriteAdmin() ? '' : 'disabled'}>Lưu cấu hình</button>
      </form>
    `;
    byId('simple-config-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      fields.forEach(([key, _label, fieldType]) => {
        if (fieldType === 'number') values[key] = Number(values[key]);
      });
      try {
        await request(`/api/admin/config/${type}`, { method: 'PUT', body: values });
        toast('Lưu thành công', 'success');
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  function simpleField(key, label, fieldType, value) {
    if (fieldType === 'checkbox') {
      return `<label class="field checkbox"><input type="checkbox" name="${escapeHtml(key)}" ${value ? 'checked' : ''}><span>${escapeHtml(label)}</span></label>`;
    }
    if (fieldType.startsWith('select:')) {
      const options = fieldType.slice(7).split(',');
      return `
        <div class="field">
          <label>${escapeHtml(label)}</label>
          <select name="${escapeHtml(key)}">
            ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}
          </select>
        </div>
      `;
    }
    return `
      <div class="field">
        <label>${escapeHtml(label)}</label>
        <input name="${escapeHtml(key)}" type="${fieldType}" value="${escapeHtml(value ?? '')}">
      </div>
    `;
  }

  async function drawTransportConfig() {
    const configs = await request('/api/admin/config/transport').then((res) => res.data || []);
    byId('advanced-body').innerHTML = `
      <form class="form" id="transport-form">
        <div class="field">
          <label>JSON cấu hình truyền dẫn</label>
          <textarea class="codebox" name="transportJson" rows="18" spellcheck="false">${escapeHtml(prettyJson(configs))}</textarea>
        </div>
        <button class="btn primary" type="submit" ${canWriteAdmin() ? '' : 'disabled'}>Lưu cấu hình</button>
      </form>
    `;
    byId('transport-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formValues(event.currentTarget);
      const next = parseJson(values.transportJson, null);
      if (!Array.isArray(next)) {
        toast('Cấu hình truyền dẫn phải là mảng JSON', 'warning');
        return;
      }
      try {
        await request('/api/admin/config/transport', { method: 'PUT', body: next });
        toast('Lưu thành công', 'success');
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  async function drawCollectionConfig(endpoint, label, fields) {
    const payload = await request(`/api/admin/config/${endpoint}`);
    const rows = normalizeList(payload);
    byId('advanced-body').innerHTML = `
      <div class="toolbar" style="justify-content:space-between;margin-bottom:12px">
        <span class="muted">Tổng cộng ${rows.length} mục</span>
        <button class="btn primary" id="collection-add" ${canWriteAdmin() ? '' : 'disabled'}>Thêm ${escapeHtml(label)}</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>${fields.map((field) => `<th>${escapeHtml(field)}</th>`).join('')}<th>Thao tác</th></tr></thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                ${fields.map((field) => `<td>${field === 'enabled' ? (row[field] ? '<span class="tag green">Bật</span>' : '<span class="tag">Tắt</span>') : escapeHtml(row[field] ?? '')}</td>`).join('')}
                <td>
                  <button class="btn small" data-edit-collection="${escapeHtml(endpoint)}:${escapeHtml(collectionId(row, endpoint))}">Chỉnh sửa</button>
                  <button class="btn danger small" data-delete-collection="${escapeHtml(endpoint)}:${escapeHtml(collectionId(row, endpoint))}">Xóa</button>
                </td>
              </tr>
            `).join('') || `<tr><td colspan="${fields.length + 1}">${emptyState(`Chưa có ${label}`)}</td></tr>`}
          </tbody>
        </table>
      </div>
    `;
    byId('collection-add')?.addEventListener('click', () => openCollectionModal(endpoint, label, fields));
  }

  function collectionId(row, endpoint) {
    if (endpoint === 'roles') return row.name;
    if (endpoint === 'mcp-functions') return row.functionName;
    if (endpoint === 'exit-commands') return row.command;
    return row.id || row.name || '';
  }

  function openCollectionModal(endpoint, label, fields, row = null) {
    openModal({
      title: `${row ? 'Chỉnh sửa ' : 'Thêm '}${label}`,
      body: `
        <form class="form" id="collection-form">
          ${fields.map((field) => field === 'enabled'
            ? `<label class="field checkbox"><input type="checkbox" name="enabled" ${row?.enabled ? 'checked' : ''}><span>Bật</span></label>`
            : `<div class="field"><label>${escapeHtml(field)}</label><input name="${escapeHtml(field)}" value="${escapeHtml(row?.[field] ?? '')}" required></div>`
          ).join('')}
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="collection-submit">Lưu</button>`,
    });
    byId('collection-submit').addEventListener('click', async () => {
      const form = byId('collection-form');
      if (!form.reportValidity()) return;
      const values = formValues(form);
      try {
        if (row) {
          await request(`/api/admin/config/${endpoint}/${encodeURIComponent(collectionId(row, endpoint))}`, { method: 'PUT', body: values });
        } else {
          await request(`/api/admin/config/${endpoint}`, { method: 'POST', body: values });
        }
        closeModal();
        toast('Lưu thành công', 'success');
        drawAdvancedTab(endpoint);
      } catch (error) {
        showError(error, 'Lưu thất bại');
      }
    });
  }

  async function renderWhiteList() {
    page().innerHTML = `
      ${pageHeader('Danh sách cho phép (Whitelist)', 'Quản lý các địa chỉ MAC được phép kết nối', `
        <button class="btn primary" id="white-add">Thêm</button>
        <button class="btn" id="white-batch">Thêm hàng loạt</button>
      `)}
      <div id="white-body">${loadingCard()}</div>
    `;
    byId('white-add').addEventListener('click', openWhiteListModal);
    byId('white-batch').addEventListener('click', openWhiteListUpload);
    try {
      const payload = await request('/api/admin/system/whiteList?current=1&pageSize=50');
      const table = normalizeTablePayload(payload);
      byId('white-body').innerHTML = `
        <div class="card">
          <div class="table-wrap">
            <table>
              <thead><tr><th>Địa chỉ MAC</th><th>Thao tác</th></tr></thead>
              <tbody>
                ${table.data.map((row) => `
                  <tr>
                    <td>${escapeHtml(row.mac || row.deviceId || '')}</td>
                    <td><button class="btn danger small" data-delete-white="${escapeHtml(row.mac || row.deviceId || '')}">Xóa</button></td>
                  </tr>
                `).join('') || `<tr><td colspan="2">${emptyState('Chưa có địa chỉ MAC nào trong danh sách')}</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>
      `;
    } catch (_error) {
      byId('white-body').innerHTML = `<div class="alert warning">Dịch vụ hiện tại chưa bật API whitelist hoặc tài khoản không có quyền truy cập.</div>`;
    }
  }

  function openWhiteListModal() {
    openModal({
      title: 'Thêm vào danh sách cho phép',
      body: `
        <form class="form" id="white-form">
          <div class="field">
            <label>Địa chỉ MAC</label>
            <input name="mac" pattern="^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$" placeholder="AA:BB:CC:DD:EE:FF" required>
          </div>
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="white-submit">Thêm</button>`,
    });
    byId('white-submit').addEventListener('click', async () => {
      const form = byId('white-form');
      if (!form.reportValidity()) return;
      try {
        await request('/api/admin/system/whiteList/add', { method: 'POST', body: formValues(form) });
        closeModal();
        toast('Thêm thành công', 'success');
        render();
      } catch (error) {
        showError(error, 'Thêm thất bại');
      }
    });
  }

  function openWhiteListUpload() {
    openModal({
      title: 'Thêm hàng loạt vào danh sách cho phép',
      body: `
        <form class="form" id="white-upload-form">
          <div class="field">
            <label>Tệp CSV</label>
            <input name="file" type="file" accept=".csv" required>
          </div>
        </form>
      `,
      footer: `<button class="btn" data-close-modal>Hủy</button><button class="btn primary" id="white-upload-submit">Tải lên</button>`,
    });
    byId('white-upload-submit').addEventListener('click', async () => {
      const form = byId('white-upload-form');
      if (!form.reportValidity()) return;
      const file = qs('input[type="file"]', form).files[0];
      const data = new FormData();
      data.append('file', file);
      try {
        await request('/api/admin/system/whiteList/batchAdd', { method: 'POST', body: data });
        closeModal();
        toast('Tải lên thành công', 'success');
        render();
      } catch (error) {
        showError(error, 'Tải lên thất bại');
      }
    });
  }

  document.addEventListener('click', async (event) => {
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    if (!target) return;

    const link = target.closest('[data-link]');
    if (link) {
      event.preventDefault();
      navigate(link.dataset.link || link.getAttribute('href'));
      return;
    }

    if (target.closest('[data-action="logout"]')) {
      clearUser();
      navigate('/login');
      return;
    }

    if (!target.closest('.user-menu')) {
      byId('user-dropdown')?.classList.remove('open');
    }

    const copy = target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard?.writeText(copy.dataset.copy);
      toast('Đã sao chép vào bộ nhớ tạm', 'success');
      return;
    }

    const removeQuick = target.closest('[data-remove-quick]');
    if (removeQuick) {
      removeQuick.closest('.tag')?.remove();
      return;
    }

    const deleteAgent = target.closest('[data-delete-agent]');
    if (deleteAgent) {
      confirmAction('Xóa trợ lý AI', 'Sau khi xóa, cấu hình và lịch sử hội thoại sẽ không thể khôi phục. Bạn có chắc chắn muốn xóa không?', async () => {
        await request(`/api/user/agent/${deleteAgent.dataset.deleteAgent}`, { method: 'DELETE' });
        toast('Xóa thành công', 'success');
        render();
      });
      return;
    }

    const unbind = target.closest('[data-unbind-device]');
    if (unbind) {
      confirmAction('Hủy liên kết thiết bị', 'Sau khi hủy liên kết, thiết bị cần được liên kết lại để sử dụng. Bạn có chắc chắn tiếp tục không?', async () => {
        await request('/api/user/device', { method: 'DELETE', body: { deviceID: unbind.dataset.unbindDevice } });
        toast('Hủy liên kết thiết bị thành công', 'success');
        render();
      });
      return;
    }

    const toggleDevice = target.closest('[data-toggle-device]');
    if (toggleDevice) {
      const currentlyDisabled = toggleDevice.dataset.disabled === 'true';
      confirmAction(currentlyDisabled ? 'Bật thiết bị' : 'Vô hiệu thiết bị', currentlyDisabled ? 'Sau khi kích hoạt, thiết bị có thể tiếp tục đàm thoại bằng giọng nói. Bạn có chắc chắn tiếp tục?' : 'Sau khi vô hiệu hóa, thiết bị sẽ bị từ chối đàm thoại mới. Bạn có chắc chắn tiếp tục?', async () => {
        await request(`/api/user/device/${encodeURIComponent(toggleDevice.dataset.toggleDevice)}`, {
          method: 'PUT',
          body: { disabled: !currentlyDisabled },
        });
        toast(currentlyDisabled ? 'Thiết bị đã được bật' : 'Thiết bị đã bị vô hiệu hóa', 'success');
        render();
      });
      return;
    }

    const clearDeviceMemory = target.closest('[data-clear-device-memory]');
    if (clearDeviceMemory) {
      confirmAction('Xóa trí nhớ ngắn hạn', 'Thao tác này sẽ xóa ngữ cảnh hội thoại gần đây của thiết bị với trợ lý AI này. Bạn có chắc chắn tiếp tục?', async () => {
        await request(`/api/user/device/${encodeURIComponent(clearDeviceMemory.dataset.clearDeviceMemory)}/memory`, { method: 'DELETE' });
        toast('Đã xóa trí nhớ ngắn hạn thành công', 'success');
      });
      return;
    }

    const conversation = target.closest('[data-conversation]');
    if (conversation) {
      try {
        await selectConversation(conversation.dataset.conversation);
      } catch (error) {
        showError(error, 'Tải hội thoại thất bại');
      }
      return;
    }

    const deleteDialog = target.closest('[data-delete-dialog]');
    if (deleteDialog) {
      confirmAction('Xóa hội thoại', 'Sau khi xóa không thể khôi phục. Bạn có chắc chắn muốn xóa không?', async () => {
        await request(`/api/user/agent/history_dialog/${deleteDialog.dataset.deleteDialog}`, { method: 'DELETE' });
        toast('Xóa thành công', 'success');
        render();
      });
      return;
    }

    const editProvider = target.closest('[data-edit-provider]');
    if (editProvider) {
      const [type, ...nameParts] = editProvider.dataset.editProvider.split(':');
      const name = nameParts.join(':');
      const providers = await getModelProviders();
      const provider = providers.find((item) => item.type === type && item.name === name);
      openProviderModal(provider);
      return;
    }

    const testProvider = target.closest('[data-test-provider]');
    if (testProvider) {
      const [type, ...nameParts] = testProvider.dataset.testProvider.split(':');
      const name = nameParts.join(':');
      const resultNode = testProvider.closest('.provider-card')?.querySelector('.provider-test-result');
      const previousText = testProvider.textContent;
      testProvider.disabled = true;
      testProvider.textContent = 'Đang kiểm tra…';
      if (resultNode) resultNode.innerHTML = '<span class="subtle">Đang xác thực cấu hình đã lưu, vui lòng đợi…</span>';
      try {
        const result = await request(`/api/user/providers/${encodeURIComponent(type)}/${encodeURIComponent(name)}/test`, { method: 'POST' });
        const success = result?.success === true;
        if (resultNode) {
          resultNode.innerHTML = `<div class="provider-test-message ${success ? 'success' : 'error'}">${escapeHtml(result?.message || (success ? 'Kiểm tra kết nối thành công' : 'Kiểm tra kết nối thất bại'))}</div>`;
          const audioData = result?.data?.audio_base64;
          const audioFormat = String(result?.data?.audio_format || '').toLowerCase();
          if (success && typeof audioData === 'string' && /^(wav|mp3|ogg)$/.test(audioFormat)) {
            const player = document.createElement('audio');
            player.className = 'provider-test-audio';
            player.controls = true;
            player.setAttribute('aria-label', 'Trình phát âm thanh kiểm tra TTS');
            player.src = `data:audio/${audioFormat};base64,${audioData}`;
            resultNode.append(player);
          }
        }
        toast(result?.message || (success ? 'Kiểm tra kết nối thành công' : 'Kiểm tra kết nối thất bại'), success ? 'success' : 'error');
      } catch (error) {
        if (resultNode) resultNode.innerHTML = `<div class="provider-test-message error">${escapeHtml(error?.data?.message || error?.message || 'Kiểm tra thất bại')}</div>`;
        showError(error, 'Kiểm tra thất bại');
      } finally {
        testProvider.disabled = false;
        testProvider.textContent = previousText;
      }
      return;
    }

    const deleteProvider = target.closest('[data-delete-provider]');
    if (deleteProvider) {
      const [type, ...nameParts] = deleteProvider.dataset.deleteProvider.split(':');
      const name = nameParts.join(':');
      confirmAction('Xóa nhà cung cấp', `Bạn có chắc chắn muốn xóa ${type}/${name} không?`, async () => {
        await request(`/api/user/providers/${encodeURIComponent(type)}/${encodeURIComponent(name)}`, { method: 'DELETE' });
        toast('Xóa thành công', 'success');
        render();
      });
      return;
    }

    const tab = target.closest('[data-advanced-tab]');
    if (tab) {
      await drawAdvancedTab(tab.dataset.advancedTab);
      return;
    }

    const editCollection = target.closest('[data-edit-collection]');
    if (editCollection) {
      const [endpoint, ...idParts] = editCollection.dataset.editCollection.split(':');
      const id = idParts.join(':');
      const payload = await request(`/api/admin/config/${endpoint}`);
      const rows = normalizeList(payload);
      const row = rows.find((item) => collectionId(item, endpoint) === id);
      const labelMap = { roles: 'nhân vật', 'mcp-functions': 'chức năng MCP cục bộ', 'exit-commands': 'khẩu lệnh thoát' };
      const fieldsMap = {
        roles: ['name', 'description', 'enabled'],
        'mcp-functions': ['functionName', 'description', 'enabled'],
        'exit-commands': ['command', 'enabled'],
      };
      openCollectionModal(endpoint, labelMap[endpoint], fieldsMap[endpoint], row);
      return;
    }

    const deleteCollection = target.closest('[data-delete-collection]');
    if (deleteCollection) {
      const [endpoint, ...idParts] = deleteCollection.dataset.deleteCollection.split(':');
      const id = idParts.join(':');
      confirmAction('Xóa mục cấu hình', 'Bạn có chắc chắn muốn xóa mục này không?', async () => {
        await request(`/api/admin/config/${endpoint}/${encodeURIComponent(id)}`, { method: 'DELETE' });
        toast('Xóa thành công', 'success');
        drawAdvancedTab(endpoint);
      });
      return;
    }

    const deleteWhite = target.closest('[data-delete-white]');
    if (deleteWhite) {
      confirmAction('Xóa khỏi danh sách cho phép', 'Bạn có chắc chắn muốn xóa địa chỉ MAC này không?', async () => {
        await request('/api/admin/system/whiteList', {
          method: 'DELETE',
          body: { mac: deleteWhite.dataset.deleteWhite },
        });
        toast('Xóa thành công', 'success');
        render();
      });
    }
  });

  window.addEventListener('popstate', render);
  window.addEventListener('hashchange', render);

  fetch(asset('branding.json'), { cache: 'no-cache' })
    .then((response) => response.ok ? response.json() : null)
    .then((branding) => {
      if (branding) {
        state.branding = {
          ...state.branding,
          ...branding,
          logoUrl: branding.logoUrl || state.branding.logoUrl,
        };
      }
    })
    .catch(() => null)
    .finally(render);
})();
