/**
 * ฟังก์ชันเรียก FastAPI backend
 * สัปดาห์ 3: ตะกร้าสินค้าย้ายจาก localStorage มาเป็น DB จริงแล้ว
 * สัปดาห์ 4: เพิ่มระบบสมัคร/ล็อกอิน (JWT) — ตะกร้ายังผูกกับ browser ผ่าน token เหมือนเดิม
 * (คนที่ยังไม่ล็อกอินยังสั่งซื้อแบบ guest ได้ ล็อกอินไว้สำหรับ endpoint ที่ต้องยืนยันตัวตน เช่น เพิ่มสินค้า/ร้านค้า)
 */
const API_BASE = "/api";
const CART_TOKEN_KEY = "shopmarket_cart_token";
const AUTH_TOKEN_KEY = "shopmarket_auth_token";

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

async function fetchProducts(search = "") {
  const url = search
    ? `${API_BASE}/products?search=${encodeURIComponent(search)}`
    : `${API_BASE}/products`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("โหลดรายการสินค้าไม่สำเร็จ");
  return res.json();
}

async function fetchProduct(id) {
  const res = await fetch(`${API_BASE}/products/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("โหลดข้อมูลสินค้าไม่สำเร็จ");
  return res.json();
}

async function fetchCart() {
  const res = await fetch(`${API_BASE}/cart/${getCartToken()}`);
  if (!res.ok) throw new Error("โหลดตะกร้าไม่สำเร็จ");
  return res.json();
}

async function addToCart(productId, qty) {
  const res = await fetch(`${API_BASE}/cart/${getCartToken()}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId, quantity: qty }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "เพิ่มสินค้าลงตะกร้าไม่สำเร็จ");
  }
  return res.json();
}

async function updateCartItemQty(productId, qty) {
  const res = await fetch(`${API_BASE}/cart/${getCartToken()}/items/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quantity: qty }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "ปรับจำนวนไม่สำเร็จ");
  }
  return res.json();
}

async function removeCartItem(productId) {
  const res = await fetch(`${API_BASE}/cart/${getCartToken()}/items/${productId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "ลบสินค้าไม่สำเร็จ");
  }
  return res.json();
}

function formatBaht(amount) {
  return "฿" + amount.toLocaleString("th-TH");
}

/** อัปเดตตัวเลขบนไอคอนตะกร้าที่ header ทุกหน้า (อ่านจาก backend จริง) */
async function renderCartBadge() {
  const badge = document.getElementById("cart-badge");
  if (!badge) return;
  try {
    const cart = await fetchCart();
    const count = cart.items.reduce((sum, item) => sum + item.quantity, 0);
    badge.textContent = count;
  } catch {
    badge.textContent = "0";
  }
}

// ---------- Auth (สัปดาห์ 4) ----------

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setAuthToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

async function registerAccount(email, password, name) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "สมัครสมาชิกไม่สำเร็จ");
  }
  return res.json();
}

async function login(email, password) {
  // ใช้ field ชื่อ username ตามมาตรฐาน OAuth2PasswordRequestForm ของ FastAPI (ส่งเป็นอีเมลจริงๆ)
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
  return data;
}

function logoutAccount() {
  clearAuthToken();
}

async function fetchMe() {
  const token = getAuthToken();
  if (!token) return null;
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    clearAuthToken(); // token หมดอายุ/ไม่ถูกต้อง เคลียร์ทิ้งกันค้าง
    return null;
  }
  return res.json();
}

/** แสดงสถานะล็อกอินที่ header ทุกหน้า (ต้องมี <span id="auth-status" data-login-href="..."> ในหน้า) */
async function renderAuthStatus() {
  const el = document.getElementById("auth-status");
  if (!el) return;
  const loginHref = el.dataset.loginHref || "login.html";
  const user = await fetchMe();
  if (user) {
    el.innerHTML = `สวัสดี, ${user.name} · <button type="button" class="auth-link-btn" onclick="handleLogoutClick()">ออกจากระบบ</button>`;
  } else {
    el.innerHTML = `<a href="${loginHref}" class="auth-link">เข้าสู่ระบบ</a>`;
  }
}

function handleLogoutClick() {
  logoutAccount();
  renderAuthStatus();
}

document.addEventListener("DOMContentLoaded", () => {
  renderCartBadge();
  renderAuthStatus();
});
