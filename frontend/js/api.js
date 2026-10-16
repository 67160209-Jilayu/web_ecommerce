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

/* ---------- Notice ราคาลดในตะกร้า (เฉพาะผู้ใช้ที่ล็อกอิน) ---------- */

const fetchNotices = () => apiFetch("/account/notices");
/** ทำเครื่องหมายว่าอ่านแล้ว — ไม่ส่ง ids = อ่านทั้งหมด */
const markNoticesRead = (ids) =>
  apiFetch("/account/notices/read", {
    method: "PATCH",
    body: JSON.stringify(ids && ids.length ? { ids } : {}),
  });

/* ---------- Seller: สถานะราคา ---------- */

const fetchPriceStatus = () => apiFetch("/seller/price-status");

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

/**
 * ราคาขาย + ราคาก่อนลด (ขีดฆ่า) + ป้าย % ส่วนลด
 * แสดงตามที่ API ส่งมาเท่านั้น: original_price คือราคาก่อนลดที่ระบบคำนวณ (ราคาต่ำสุด 30 วันก่อนลด)
 * ถ้าระบบตัดสินว่าต้องซ่อน (ขึ้นราคาก่อนลด) API จะไม่ส่งมา → ไม่แสดงอะไรเลย
 * ห้ามแสดงกราฟ/ป้ายประวัติราคาให้ผู้ซื้อเห็น
 */
function priceHtml(p) {
  const showOriginal = p.original_price && p.original_price > p.price;
  const pct = Number(p.discount_percent) || 0;
  return `${formatBaht(p.price)}${
    showOriginal ? `<span class="original">${formatBaht(p.original_price)}</span>` : ""
  }${showOriginal && pct > 0 ? `<span class="discount-tag">-${pct}%</span>` : ""}`;
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
  let cart = null;
  try {
    cart = await fetchCart();
    badge.textContent = cart.items.reduce((sum, item) => sum + item.quantity, 0);
  } catch {
    badge.textContent = "0";
  }
  renderCartDot(cart);
}

/** จำนวน notice ราคาลดที่ยังไม่อ่าน จากข้อมูลที่ GET /api/cart แนบมา (guest = 0 เสมอ) */
function unreadNoticeCount(cart) {
  if (!cart || !isLoggedIn()) return 0;
  if (typeof cart.unread_notice_count === "number") return cart.unread_notice_count;
  return (cart.notices || []).filter((n) => !n.read_at).length;
}

/** จุดแจ้งที่ไอคอนตะกร้า — แสดงเฉพาะผู้ใช้ที่ล็อกอินและมี notice ที่ยังไม่อ่าน */
function renderCartDot(cart) {
  const link = document.querySelector(".cart-link");
  if (!link) return;
  let dot = link.querySelector(".cart-dot");
  // อยู่หน้าตะกร้าแล้ว = เห็น notice แล้ว ไม่ต้องมีจุดแจ้ง
  const onCartPage = /\/cart\.html$/.test(window.location.pathname);
  const count = onCartPage ? 0 : unreadNoticeCount(cart);
  if (count > 0) {
    if (!dot) {
      dot = document.createElement("span");
      dot.className = "cart-dot";
      link.appendChild(dot);
    }
    const label = `มีสินค้าในตะกร้าลดราคา ${count} รายการ`;
    dot.title = label;
    dot.setAttribute("aria-hidden", "true");
    link.setAttribute("aria-label", `ตะกร้าสินค้า — ${label}`);
  } else {
    dot?.remove();
    link.setAttribute("aria-label", "ตะกร้าสินค้า");
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
      <span class="auth-name">👤 ${escapeHtml(user.name)}</span>
      <button type="button" class="auth-link-btn auth-logout" onclick="handleLogoutClick()">ออกจากระบบ</button>`;
    el.setAttribute("aria-label", `เข้าสู่ระบบแล้วในชื่อ ${user.name}`);
  } else {
    el.innerHTML = `<a href="${base}pages/login.html" class="auth-link">เข้าสู่ระบบ</a>`;
  }
}

function handleLogoutClick() {
  if (!confirm("ต้องการออกจากระบบใช่ไหม?")) return;
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
/**
 * แจ้งผลแบบ toast ลอยด้านล่าง
 * action = {label, onClick} → มีปุ่ม (เช่น "เอากลับคืน") และค้างนานขึ้นให้กดทัน
 * error ใช้ role="alert" ให้โปรแกรมอ่านหน้าจออ่านทันที
 */
function showToast(message, type = "success", action = null) {
  let toast = document.getElementById("app-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "app-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  toast.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
  toast.textContent = message;
  if (action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toast-action";
    btn.textContent = action.label;
    btn.addEventListener("click", () => {
      toast.className = "toast";
      action.onClick();
    });
    toast.appendChild(btn);
  }
  toast.className = `toast show${type === "error" ? " error" : ""}${action ? " has-action" : ""}`;
  clearTimeout(toast._timer);
  // ผู้ใช้สูงวัยอ่านช้ากว่า: ข้อความทั่วไป 4 วินาที, มีปุ่มให้กด 7 วินาที
  toast._timer = setTimeout(() => {
    toast.className = "toast";
  }, action ? 7000 : 4000);
}

/** แจ้งว่าเพิ่มลงตะกร้าแล้ว พร้อมปุ่มไปดูตะกร้า */
function showAddedToCart() {
  showToast("เพิ่มลงตะกร้าแล้ว ✓", "success", {
    label: "ดูตะกร้า",
    onClick: () => (window.location.href = `${pageBase()}pages/cart.html`),
  });
}

/** แสดง/ล้างข้อความผิดพลาดใต้ช่องกรอก (ไม่ลบสิ่งที่ผู้ใช้กรอกไว้) */
function setFieldError(input, message) {
  if (!input) return;
  const id = `${input.id}-error`;
  let el = document.getElementById(id);
  if (!message) {
    input.removeAttribute("aria-invalid");
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement("span");
    el.id = id;
    el.className = "field-error";
    (input.closest(".unit-input, .password-row, .cart-item-qty") || input).insertAdjacentElement("afterend", el);
  }
  el.textContent = message;
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", id);
}

/**
 * ตรวจช่องที่ต้องกรอกในฟอร์มด้วยข้อความภาษาไทยที่บอกวิธีแก้
 * คืน true ถ้าผ่าน; ไม่ผ่าน → ขึ้นข้อความใต้ช่องแรกที่ผิด แล้วเลื่อนไป focus ช่องนั้น
 */
function validateRequired(form) {
  let first = null;
  form.querySelectorAll("input, select, textarea").forEach((el) => {
    if (el.disabled || el.type === "hidden" || el.type === "file") return;
    let msg = "";
    const label = el.labels?.[0]?.textContent.replace("*", "").trim() || "ช่องนี้";
    if (el.required && !String(el.value).trim()) msg = `กรุณากรอก${label}`;
    else if (el.type === "email" && el.value && !el.checkValidity()) msg = "รูปแบบอีเมลไม่ถูกต้อง เช่น somchai@gmail.com";
    else if (el.type === "number" && el.value !== "" && el.min !== "" && Number(el.value) < Number(el.min))
      msg = `${label}ต้องไม่น้อยกว่า ${el.min}`;
    else if (el.type === "tel" && el.value) {
      const digits = el.value.replace(/\D/g, "");
      if (digits.length < 9 || digits.length > 10) msg = "เบอร์โทรควรเป็นตัวเลข 9–10 หลัก เช่น 0812345678";
    } else if (el.minLength > 0 && el.value && el.value.length < el.minLength)
      msg = `${label}ต้องยาวอย่างน้อย ${el.minLength} ตัวอักษร`;
    setFieldError(el, msg);
    if (msg && !first) first = el;
  });
  if (first) {
    first.scrollIntoView({ block: "center" });
    first.focus({ preventScroll: true });
  }
  return !first;
}

/** ล้างข้อความผิดพลาดของช่องทันทีที่ผู้ใช้เริ่มแก้ */
document.addEventListener("input", (e) => {
  if (e.target.getAttribute?.("aria-invalid") === "true") setFieldError(e.target, "");
});

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

/* ============================================================
   ถาดเปรียบเทียบ (เฟส 2) — แถบลอยด้านล่างทุกหน้า
   จำไว้ใน localStorage (guest ก็ใช้ได้) + บันทึกเข้าบัญชีเมื่อล็อกอิน
   ============================================================ */

const COMPARE_KEY = "shopmarket_compare_items";
const COMPARE_MAX = 4;
const PROVINCE_KEY = "shopmarket_province";
// ข้อมูลย่อของสินค้าที่เห็นบนหน้านี้ ใช้แสดงในถาดโดยไม่ต้องเรียก API ซ้ำ
const _compareSeen = {};

const fetchCompare = (ids, params = {}) => {
  const q = new URLSearchParams({ ids: ids.join(","), ...params });
  return apiFetch(`/compare?${q}`);
};
const fetchCategoryAttributes = (categoryId) => apiFetch(`/categories/${categoryId}/attributes`);
const fetchProvinces = () => apiFetch("/shipping/provinces");
const fetchAccountProvince = () => apiFetch("/account/province");
const fetchSameModel = (id, province) =>
  apiFetch(`/products/${id}/same-model${province ? `?province=${encodeURIComponent(province)}` : ""}`);
const fetchMaybeSame = (id, province) =>
  apiFetch(`/products/${id}/maybe-same${province ? `?province=${encodeURIComponent(province)}` : ""}`);
const fetchReviewSummary = (id) => apiFetch(`/products/${id}/review-summary`);
const fetchSimilar = (id, limit = 3) => apiFetch(`/products/${id}/similar?limit=${limit}`);
const fetchCompareList = () => apiFetch("/account/compare-list");
const saveCompareList = (ids) =>
  apiFetch("/account/compare-list", { method: "PUT", body: JSON.stringify({ ids }) });
const fetchMyShipping = () => apiFetch("/shops/me/shipping");
const saveMyShipping = (data) =>
  apiFetch("/shops/me/shipping", { method: "PUT", body: JSON.stringify(data) });
const fetchSpecSuggestions = (id) => apiFetch(`/products/${id}/spec-suggestions`);
const confirmSpecSuggestions = (id, keys) =>
  apiFetch(`/products/${id}/spec-suggestions/confirm`, { method: "POST", body: JSON.stringify({ keys }) });
const generateSpecSuggestions = (id) =>
  apiFetch(`/products/${id}/spec-suggestions/generate`, { method: "POST" });
/** ค่าส่งของตะกร้าตามจังหวัด — ใช้ engine เดียวกับ checkout (ตัวเลขตรงกับใบสั่งซื้อ) */
const fetchShippingQuote = (province) =>
  apiFetch(`/cart/${getCartToken()}/shipping-quote${province ? `?province=${encodeURIComponent(province)}` : ""}`);
const saveAccountProvince = (province) =>
  apiFetch("/account/province", { method: "PUT", body: JSON.stringify({ province }) });
const dismissSpecSuggestions = (id, keys) =>
  apiFetch(`/products/${id}/spec-suggestions/dismiss`, { method: "POST", body: JSON.stringify({ keys }) });

/** ฟีเจอร์ที่เปิดอยู่ (AI เสนอสเปก, แชท ฯลฯ) — ถ้า backend ยังไม่มี endpoint นี้ถือว่าไม่รู้ (null) */
let _featuresPromise = null;
function fetchFeatures() {
  if (!_featuresPromise) _featuresPromise = apiFetch("/features").catch(() => null);
  return _featuresPromise;
}

/** ข้อความค่าส่ง: "ส่งฟรี (เหตุผล)" หรือ "฿40" */
function shippingFeeText(s) {
  if (!s) return "—";
  if (Number(s.fee) !== 0) return formatBaht(s.fee);
  if (s.free_reason === "item") return "ส่งฟรี <span class=\"cmp-sub-inline\">(สินค้านี้ส่งฟรี)</span>";
  if (s.free_reason === "threshold" && s.free_over)
    return `ส่งฟรี <span class="cmp-sub-inline">(ร้านนี้ส่งฟรีเมื่อซื้อครบ ${formatBaht(s.free_over)})</span>`;
  return "ส่งฟรี";
}

/** "" สำหรับหน้าราก, "../" สำหรับหน้าใน pages/ (อ่านจาก data-base ที่ header) */
function pageBase() {
  return document.getElementById("auth-status")?.dataset.base || "";
}

function getCompareItems() {
  try {
    const items = JSON.parse(localStorage.getItem(COMPARE_KEY) || "[]");
    return Array.isArray(items) ? items.filter((x) => x && x.id).slice(0, COMPARE_MAX) : [];
  } catch {
    return [];
  }
}

function setCompareItems(items, { sync = true } = {}) {
  try {
    localStorage.setItem(COMPARE_KEY, JSON.stringify(items.slice(0, COMPARE_MAX)));
  } catch {}
  if (sync && isLoggedIn()) saveCompareList(items.map((x) => x.id)).catch(() => {});
  renderCompareTray();
  document.querySelectorAll("[data-compare-id]").forEach(updateCompareButton);
}

function compareLite(p) {
  return {
    id: p.id ?? p.product_id,
    name: p.name || p.product_name || "",
    image: p.image || "📦",
    cover_url: p.cover_url || null,
    category_id: p.category_id ?? null,
  };
}

function isInCompare(id) {
  return getCompareItems().some((x) => x.id === id);
}

/** ปุ่ม "+ เทียบ" บนการ์ด/หน้าสินค้า (หยุด event ไม่ให้การ์ดพาไปหน้าสินค้า) */
function compareButtonHtml(p, extraClass = "") {
  const lite = compareLite(p);
  _compareSeen[lite.id] = lite;
  const on = isInCompare(lite.id);
  return `<button type="button" class="compare-btn ${on ? "on" : ""} ${extraClass}" data-compare-id="${lite.id}"
    title="เพิ่มเข้าถาดเพื่อเปรียบเทียบกับสินค้าอื่น (สูงสุด ${COMPARE_MAX} ชิ้น)"
    aria-pressed="${on}" onclick="event.stopPropagation(); toggleCompare(${lite.id})">${on ? "✓ เลือกเทียบแล้ว" : "+ เทียบ"}</button>`;
}

function updateCompareButton(btn) {
  const on = isInCompare(Number(btn.dataset.compareId));
  btn.classList.toggle("on", on);
  btn.setAttribute("aria-pressed", on);
  btn.textContent = on ? "✓ เลือกเทียบแล้ว" : "+ เทียบ";
}

/** เพิ่มเข้าถาด — รับได้ทั้งสินค้าเต็มจาก API และข้อมูลย่อ */
function addToCompare(p) {
  const lite = compareLite(p);
  const items = getCompareItems();
  if (items.some((x) => x.id === lite.id)) return true;
  if (items.length >= COMPARE_MAX) {
    showToast(`เทียบได้สูงสุด ${COMPARE_MAX} ชิ้น — เอาบางชิ้นออกจากถาดก่อน`, "error");
    return false;
  }
  if (items.length && lite.category_id && items[0].category_id && items[0].category_id !== lite.category_id) {
    showToast("สินค้าต่างหมวด จะเทียบได้แค่ราคา รีวิว และค่าส่ง");
  }
  setCompareItems([...items, lite]);
  return true;
}

function removeFromCompare(id) {
  setCompareItems(getCompareItems().filter((x) => x.id !== id));
}

/** ล้างถาดทั้งหมด แต่กด "เอากลับคืน" ได้ภายใน 7 วินาที */
function clearCompareWithUndo() {
  const before = getCompareItems();
  setCompareItems([]);
  showToast("ล้างถาดเทียบแล้ว", "success", {
    label: "เอากลับคืน",
    onClick: () => setCompareItems(before),
  });
}

function toggleCompare(id) {
  if (isInCompare(id)) removeFromCompare(id);
  else if (_compareSeen[id]) addToCompare(_compareSeen[id]);
}

function compareUrl(ids) {
  return `${pageBase()}pages/compare.html?ids=${ids.join(",")}`;
}

let _trayExpanded = false; // มือถือ: ถาดย่อเป็นแถบเดียว กดเพื่อกาง

function renderCompareTray() {
  // หน้าเทียบมีตารางอยู่แล้ว / หน้าตะกร้า-ชำระเงิน-ล็อกอิน ต้องไม่มีอะไรมาบังปุ่มหลัก
  if (/\/(compare|cart|checkout|login)\.html$/.test(window.location.pathname)) return;
  let tray = document.getElementById("compare-tray");
  const items = getCompareItems();
  if (!items.length) {
    tray?.remove();
    document.body.classList.remove("has-compare-tray");
    _trayExpanded = false;
    return;
  }
  if (!tray) {
    tray = document.createElement("div");
    tray.id = "compare-tray";
    tray.className = "compare-tray";
    tray.setAttribute("role", "region");
    tray.setAttribute("aria-label", "ถาดเปรียบเทียบสินค้า");
    document.body.appendChild(tray);
  }
  tray.classList.toggle("expanded", _trayExpanded);
  document.body.classList.add("has-compare-tray");
  const slots = Array.from({ length: COMPARE_MAX }, (_, i) => items[i]);
  const goBtn =
    items.length >= 2
      ? `<a class="btn btn-primary btn-sm" href="${compareUrl(items.map((x) => x.id))}">เปรียบเทียบ ${items.length} ชิ้น</a>`
      : `<span class="compare-hint">เลือกสินค้าอีกอย่างน้อย 1 ชิ้นเพื่อเทียบ</span>`;
  tray.innerHTML = `
    <button type="button" class="compare-tray-toggle" aria-expanded="${_trayExpanded}" aria-controls="compare-tray-body"
      onclick="toggleCompareTray()">
      <span>⚖️ เลือกเทียบไว้ ${items.length} ชิ้น</span>
      <span class="compare-tray-toggle-hint">${_trayExpanded ? "ย่อ ▾" : "ดู/เทียบ ▴"}</span>
    </button>
    <div class="compare-tray-body" id="compare-tray-body">
      <ul class="compare-tray-items" aria-label="สินค้าที่เลือกเทียบ">
        ${slots
          .map((it) =>
            it
              ? `<li class="compare-slot">
                   <div class="compare-slot-thumb">${productThumb(it)}</div>
                   <span class="compare-slot-name">${escapeHtml(it.name)}</span>
                   <button type="button" class="compare-slot-remove" aria-label="เอา ${escapeHtml(it.name)} ออกจากถาดเทียบ"
                     onclick="removeFromCompare(${it.id})"><span aria-hidden="true">✕</span><span class="compare-slot-remove-text">เอาออก</span></button>
                 </li>`
              : `<li class="compare-slot empty" aria-hidden="true">ว่าง</li>`
          )
          .join("")}
      </ul>
      <div class="compare-tray-actions">
        <button type="button" class="btn-ghost compare-clear" onclick="clearCompareWithUndo()">ล้างทั้งหมด</button>
        ${goBtn}
      </div>
    </div>`;
}

function toggleCompareTray() {
  _trayExpanded = !_trayExpanded;
  renderCompareTray();
  document.querySelector(".compare-tray-toggle")?.focus();
}

/** ล็อกอินแล้วและเครื่องนี้ยังไม่มีรายการ → ดึงถาดที่บันทึกไว้ในบัญชีมาใช้ */
async function restoreCompareFromAccount() {
  if (!isLoggedIn() || getCompareItems().length) return;
  try {
    const res = await fetchCompareList();
    const ids = (res?.ids || []).slice(0, COMPARE_MAX);
    if (!ids.length) return;
    const products = (await Promise.all(ids.map((id) => fetchProduct(id).catch(() => null)))).filter(Boolean);
    if (products.length) setCompareItems(products.map(compareLite), { sync: false });
  } catch {}
}

/** จังหวัดสำหรับคำนวณค่าส่ง: ที่ผู้ใช้เลือกไว้ในเครื่อง → ของบัญชี (ที่อยู่ล่าสุด) → ไม่มี */
async function getBuyerProvince() {
  try {
    const saved = localStorage.getItem(PROVINCE_KEY);
    if (saved) return saved;
  } catch {}
  if (isLoggedIn()) {
    try {
      const res = await fetchAccountProvince();
      if (res?.province) return res.province;
    } catch {}
  }
  return "";
}

function setBuyerProvince(name) {
  try {
    if (name) localStorage.setItem(PROVINCE_KEY, name);
    else localStorage.removeItem(PROVINCE_KEY);
  } catch {}
  // ล็อกอินอยู่ → จำไว้ในบัญชีด้วย ใช้ได้ทุกเครื่อง
  if (name && isLoggedIn()) saveAccountProvince(name).catch(() => {});
}

/** <option> จังหวัดจัดกลุ่มตามภาค */
function provinceOptionsHtml(provinces, selected) {
  const byRegion = {};
  (provinces || []).forEach((p) => {
    const name = typeof p === "string" ? p : p.name;
    const region = (typeof p === "string" ? "" : p.region) || "จังหวัด";
    (byRegion[region] = byRegion[region] || []).push(name);
  });
  return Object.entries(byRegion)
    .map(
      ([region, names]) => `<optgroup label="${escapeHtml(region)}">${names
        .map((n) => `<option value="${escapeHtml(n)}" ${n === selected ? "selected" : ""}>${escapeHtml(n)}</option>`)
        .join("")}</optgroup>`
    )
    .join("");
}

/** ป้าย "ข้อมูลครบ" — ผู้ขายกรอกสเปกที่จำเป็นครบตามแม่แบบหมวด */
function specCompleteBadge(p) {
  return p && p.spec_complete
    ? `<span class="badge-spec-complete" title="ร้านใส่รายละเอียดสินค้าครบ เทียบกับสินค้าอื่นได้ง่าย">✓ ข้อมูลครบ</span>`
    : "";
}

document.addEventListener("DOMContentLoaded", () => {
  renderCompareTray();
  restoreCompareFromAccount();
});

// เปิดหลายแท็บ → ถาดตรงกันทุกแท็บ
window.addEventListener("storage", (e) => {
  if (e.key === COMPARE_KEY) {
    renderCompareTray();
    document.querySelectorAll("[data-compare-id]").forEach(updateCompareButton);
  }
});
