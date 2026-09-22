// Тонкая обёртка над API + хранение токена в localStorage (per-device браузер, это ок для этого приложения).
const API = {
  base: "",
  tokenKey: "ab_token",
  roleKey: "ab_role",

  getToken() { return localStorage.getItem(this.tokenKey); },
  getRole() { return localStorage.getItem(this.roleKey); },
  setSession(token, role) {
    localStorage.setItem(this.tokenKey, token);
    localStorage.setItem(this.roleKey, role);
  },
  clearSession() {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.roleKey);
  },

  async request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(this.base + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch (_) { /* пустой ответ */ }
    if (!res.ok) {
      const err = new Error((data && data.detail) || `Ошибка запроса (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  },

  get(path) { return this.request("GET", path); },
  post(path, body) { return this.request("POST", path, body); },
  patch(path, body) { return this.request("PATCH", path, body); },
};

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}