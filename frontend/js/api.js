/**
 * ฟังก์ชันเรียก FastAPI backend และจัดการตะกร้าสินค้า (เก็บใน localStorage ชั่วคราว
 * สัปดาห์ 3 จะย้ายไปผูกกับ backend จริงเมื่อมีระบบผู้ใช้)
 */
const API_BASE = "/api";
const CART_KEY = "shopmarket_cart";

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

function getCart() {
  try {
    return JSON.parse(localStorage.getItem(CART_KEY)) || [];
  } catch {
    return [];
  }
}

function saveCart(cart) {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
}

function addToCart(product, qty) {
  const cart = getCart();
  const existing = cart.find((item) => item.id === product.id);
  if (existing) {
    existing.qty = Math.min(existing.qty + qty, product.stock);
  } else {
    cart.push({
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image,
      stock: product.stock,
      qty: Math.min(qty, product.stock),
    });
  }
  saveCart(cart);
  return cart;
}

function updateCartQty(id, qty) {
  const cart = getCart();
  const item = cart.find((i) => i.id === id);
  if (item) {
    item.qty = Math.max(1, Math.min(qty, item.stock));
  }
  saveCart(cart);
  return cart;
}

function removeFromCart(id) {
  const cart = getCart().filter((i) => i.id !== id);
  saveCart(cart);
  return cart;
}

function cartItemCount() {
  return getCart().reduce((sum, item) => sum + item.qty, 0);
}

function cartTotal() {
  return getCart().reduce((sum, item) => sum + item.qty * item.price, 0);
}

function formatBaht(amount) {
  return "฿" + amount.toLocaleString("th-TH");
}

/** อัปเดตตัวเลขบนไอคอนตะกร้าที่ header ทุกหน้า */
function renderCartBadge() {
  const badge = document.getElementById("cart-badge");
  if (badge) badge.textContent = cartItemCount();
}

document.addEventListener("DOMContentLoaded", renderCartBadge);
