const BASE = '/api'

export interface Product {
  id: number
  name: string
  description: string | null
  price: number
  stock: number
  category: string
  created_at: string
}

export interface OrderItem {
  id: number
  product_id: number
  quantity: number
  price: number
}

export interface Order {
  id: number
  user_id: number
  total_amount: number
  status: string
  created_at: string
  items: OrderItem[]
}

export interface CartItem {
  product: Product
  quantity: number
}

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------
export async function fetchProducts(category?: string): Promise<Product[]> {
  const url = category
    ? `${BASE}/products?category=${encodeURIComponent(category)}`
    : `${BASE}/products`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch products: ${res.status}`)
  return res.json()
}

export async function fetchProduct(id: number): Promise<Product> {
  const res = await fetch(`${BASE}/products/${id}`)
  if (!res.ok) throw new Error(`Product not found: ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------
export async function createOrder(
  userId: number,
  items: { product_id: number; quantity: number }[]
): Promise<Order> {
  const res = await fetch(`${BASE}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, items }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail ?? `Order failed: ${res.status}`)
  }
  return res.json()
}

export async function fetchOrders(userId?: number): Promise<Order[]> {
  const url = userId ? `${BASE}/orders?user_id=${userId}` : `${BASE}/orders`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch orders: ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------
export async function registerUser(email: string, password: string) {
  const res = await fetch(`${BASE}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail ?? `Registration failed: ${res.status}`)
  }
  return res.json()
}

export async function loginUser(email: string, password: string) {
  const res = await fetch(`${BASE}/users/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail ?? `Login failed: ${res.status}`)
  }
  return res.json()
}
