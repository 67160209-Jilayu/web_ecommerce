/**
 * ฟังก์ชันกลางสำหรับเรียก FastAPI backend + จัดการ token
 *
 * - cart token : ตัวระบุตะกร้า เก็บใน localStorage (guest ก็ใช้ได้)
 * - auth token : JWT จากการล็อกอิน แนบไปกับทุก request ที่ต้องยืนยันตัวตน
 */
const API_BASE = "/api";
const CART_TOKEN_KEY = "shopmarket_cart_token";
const AUTH_TOKEN_KEY = "shopmarket_auth_token";

/* ---------- token helpers ---------- */

function getCartToken() {
  let token = localStorage.getItem(CART_TOKEN_KEY);
  if (!token) {
    token = crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, "")
      : `cart${Date.now()}${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(CART_TOKEN_KEY, token);
  }
  return token;
}

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setAuthToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function isLoggedIn() {
  return !!getAuthToken();
}

/* ---------- ตัวช่วยเรียก API ---------- */

/** เรียก API พร้อมแนบ auth token อัตโนมัติ แล้วโยน Error ที่มีข้อความจาก backend ถ้าไม่สำเร็จ */
async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearAuthToken();
    throw new Error("กรุณาเข้าสู่ระบบก่อนใช้งานส่วนนี้");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    // FastAPI validation error จะส่ง detail มาเป็น array
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join(", ")
      : detail || `เกิดข้อผิดพลาด (${res.status})`;
    throw new Error(message);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- Products / Categories ---------- */

async function fetchProducts(params = {}) {
  const query = new URLSearchParams();
  if (typeof params === "string") {
    // รองรับการเรียกแบบเดิม fetchProducts("คำค้น")
    if (params) query.set("search", params);
  } else {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") query.set(k, v);
    });
  }
  const qs = query.toString();
  return apiFetch(`/products${qs ? `?${qs}` : ""}`);
}

async function fetchProduct(id) {
  try {
    return await apiFetch(`/products/${id}`);
  } catch (err) {
    if (err.message.includes("ไม่พบสินค้า")) return null;
    throw err;
  }
}

const fetchMyProducts = () => apiFetch("/products/me");
const createProduct = (data) =>
  apiFetch("/products", { method: "POST", body: JSON.stringify(data) });
const updateProduct = (id, data) =>
  apiFetch(`/products/${id}`, { method: "PATCH", body: JSON.stringify(data) });
const deleteProduct = (id) => apiFetch(`/products/${id}`, { method: "DELETE" });
const fetchCategories = () => apiFetch("/categories");
const fetchProductReviews = (id) => apiFetch(`/products/${id}/reviews`);

/* ---------- Shops ---------- */

const fetchShop = (id) => apiFetch(`/shops/${id}`);
const fetchShopProducts = (id) => apiFetch(`/shops/${id}/products`);
const createShop = (data) =>
  apiFetch("/shops", { method: "POST", body: JSON.stringify(data) });
const updateMyShop = (data) =>
  apiFetch("/shops/me", { method: "PATCH", body: JSON.stringify(data) });

/** คืน null ถ้ายังไม่เปิดร้าน (ไม่โยน error) เพื่อให้หน้า seller ตัดสินใจแสดงฟอร์มเปิดร้าน */
async function fetchMyShop() {
  try {
    return await apiFetch("/shops/me");
  } catch (err) {
    if (err.message.includes("ยังไม่มีร้าน")) return null;
    throw err;
  }
}

/* ---------- Upload ---------- */

/** อัปโหลดไฟล์ 1 ไฟล์ คืน {url, media_type} */
async function uploadMedia(file) {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch("/uploads", { method: "POST", body: formData });
}

/* ---------- Cart ---------- */

const fetchCart = () => apiFetch(`/cart/${getCartToken()}`);
const addToCart = (productId, qty) =>
  apiFetch(`/cart/${getCartToken()}/items`, {
    method: "POST",
    body: JSON.stringify({ product_id: productId, quantity: qty }),
  });
const updateCartItemQty = (productId, qty) =>
  apiFetch(`/cart/${getCartToken()}/items/${productId}`, {
    method: "PATCH",
    body: JSON.stringify({ quantity: qty }),
  });
const removeCartItem = (productId) =>
  apiFetch(`/cart/${getCartToken()}/items/${productId}`, { method: "DELETE" });
const mergeCart = () => apiFetch(`/cart/${getCartToken()}/merge`, { method: "POST" });

/* ---------- Orders ---------- */

const checkout = (data) =>
  apiFetch(`/orders/checkout?token=${encodeURIComponent(getCartToken())}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
const fetchMyOrders = () => apiFetch("/orders/me");
const fetchSellingOrders = () => apiFetch("/orders/selling");
const fetchOrder = (id) => apiFetch(`/orders/${id}`);
const payOrder = (id) => apiFetch(`/orders/${id}/pay`, { method: "POST" });
const shipOrder = (id) => apiFetch(`/orders/${id}/ship`, { method: "POST" });
const receiveOrder = (id) => apiFetch(`/orders/${id}/receive`, { method: "POST" });
const cancelOrder = (id) => apiFetch(`/orders/${id}/cancel`, { method: "POST" });

/* ---------- Reviews ---------- */

const createReview = (data) =>
  apiFetch("/reviews", { method: "POST", body: JSON.stringify(data) });

/* ---------- Auth ---------- */

const registerAccount = (email, password, name) =>
  apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });

async function login(email, password) {
  // ใช้ field ชื่อ username ตามมาตรฐาน OAuth2PasswordRequestForm ของ FastAPI (ส่งเป็นอีเมล)
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "เข้าสู่ระบบไม่สำเร็จ");
  }
  const data = await res.json();
  setAuthToken(data.access_token);
  // ผูกตะกร้า guest เข้ากับบัญชีที่เพิ่งล็อกอิน (ถ้าพลาดก็ไม่ควรทำให้ล็อกอินล้มเหลว)
  try {
    await mergeCart();
  } catch (_) {}
  return data;
}

function logoutAccount() {
  clearAuthToken();
  // ล้าง cart token ด้วย ไม่งั้นคนถัดไปที่ล็อกอินบนเครื่องเดียวกันจะเห็นตะกร้าของคนก่อน
  localStorage.removeItem(CART_TOKEN_KEY);
}

async function fetchMe() {
  if (!getAuthToken()) return null;
  try {
    return await apiFetch("/auth/me");
  } catch (_) {
    return null;
  }
}

/* ---------- ตัวช่วยแสดงผล ---------- */

function formatBaht(amount) {
  return "฿" + Number(amount || 0).toLocaleString("th-TH");
}

/** escape ข้อความจากผู้ใช้ก่อนใส่ลง innerHTML — สินค้า/รีวิวเป็นข้อความที่ผู้ใช้คนอื่นกรอก */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

/** แสดงรูปปกสินค้า ถ้ายังไม่อัปโหลดรูปให้ใช้ emoji แทน */
function productThumb(product, extraClass = "") {
  const cover = product.cover_url || product.product_cover_url;
  if (cover) {
    return `<img src="${escapeHtml(cover)}" alt="${escapeHtml(
      product.name || product.product_name || ""
    )}" class="thumb-img ${extraClass}" loading="lazy" />`;
  }
  return `<span class="thumb-emoji ${extraClass}">${
    product.image || product.product_image || "📦"
  }</span>`;
}

const ORDER_STATUS_LABEL = {
  PENDING_PAYMENT: "รอชำระเงิน",
  PAID: "ชำระแล้ว รอร้านจัดส่ง",
  SHIPPED: "กำลังจัดส่ง",
  DELIVERED: "ได้รับสินค้าแล้ว",
  COMPLETED: "สำเร็จ",
  CANCELLED: "ยกเลิกแล้ว",
};

const PAYMENT_LABEL = {
  COD: "เก็บเงินปลายทาง",
  BANK_TRANSFER: "โอนผ่านธนาคาร",
  CARD: "บัตรเครดิต/เดบิต",
};

/* ---------- header ทุกหน้า ---------- */

async function renderCartBadge() {
  const badge = document.getElementById("cart-badge");
  if (!badge) return;
  try {
    const cart = await fetchCart();
    badge.textContent = cart.items.reduce((sum, item) => sum + item.quantity, 0);
  } catch {
    badge.textContent = "0";
  }
}

/** แสดงสถานะล็อกอิน + เมนูผู้ขาย/คำสั่งซื้อ ที่ header */
async function renderAuthStatus() {
  const el = document.getElementById("auth-status");
  if (!el) return;
  const base = el.dataset.base || ""; // "" สำหรับหน้าราก, "../" สำหรับหน้าใน pages/
  const user = await fetchMe();

  if (user) {
    el.innerHTML = `
      <a href="${base}pages/orders.html" class="auth-link">คำสั่งซื้อ</a>
      <a href="${base}pages/seller.html" class="auth-link">ร้านของฉัน</a>
      <span class="auth-name">${escapeHtml(user.name)}</span>
      <button type="button" class="auth-link-btn" onclick="handleLogoutClick()">ออกจากระบบ</button>`;
  } else {
    el.innerHTML = `<a href="${base}pages/login.html" class="auth-link">เข้าสู่ระบบ</a>`;
  }
}

function handleLogoutClick() {
  logoutAccount();
  renderAuthStatus();
  renderCartBadge();
}

/** เด้งไปหน้าล็อกอินพร้อมจำหน้าเดิมไว้กลับมาต่อ */
function requireLogin(base = "") {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `${base}pages/login.html?next=${next}`;
}

document.addEventListener("DOMContentLoaded", () => {
  renderCartBadge();
  renderAuthStatus();
});

/** แจ้งผลลัพธ์แบบ toast ลอยด้านล่าง (ใช้แทน alert() ให้ไม่ขัดจังหวะผู้ใช้) */
function showToast(message, type = "success") {
  let toast = document.getElementById("app-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "app-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.className = `toast show${type === "error" ? " error" : ""}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.className = "toast";
  }, 2800);
}

/** แปลง ISO date เป็นรูปแบบไทยอ่านง่าย */
function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** แถบดาว (แสดงผลอย่างเดียว) */
function starsHtml(rating) {
  const full = Math.round(Number(rating) || 0);
  return "★".repeat(full) + "☆".repeat(Math.max(0, 5 - full));
}
