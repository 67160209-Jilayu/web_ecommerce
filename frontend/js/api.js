/**
 * ฟังก์ชันเรียก FastAPI backend
 * สัปดาห์ 3: ตะกร้าสินค้าย้ายจาก localStorage มาเป็น DB จริงแล้ว
 * ฝั่ง browser เก็บแค่ "cart token" (ตัวระบุตะกร้า) ไว้ผูกกับ backend เท่านั้น
 * ยังไม่มีระบบล็อกอิน ตะกร้าจึงผูกกับเครื่อง/เบราว์เซอร์ ไม่ใช่ผูกกับผู้ใช้ (รอสัปดาห์ 4)
 */
const API_BASE = "/api";
const CART_TOKEN_KEY = "shopmarket_cart_token";

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

document.addEventListener("DOMContentLoaded", renderCartBadge);
