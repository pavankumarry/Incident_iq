import { useState, useEffect } from 'react'
import { ShoppingCart, Package, ClipboardList, Zap } from 'lucide-react'
import Home from './pages/Home'
import Cart from './pages/Cart'
import Orders from './pages/Orders'
import type { CartItem, Product } from './api'

type Tab = 'home' | 'cart' | 'orders'

const CART_KEY = 'shopapp_cart'

function loadCart(): CartItem[] {
  try {
    const raw = localStorage.getItem(CART_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveCart(items: CartItem[]) {
  localStorage.setItem(CART_KEY, JSON.stringify(items))
}

export default function App() {
  const [tab, setTab] = useState<Tab>('home')
  const [cart, setCart] = useState<CartItem[]>(loadCart)

  useEffect(() => {
    saveCart(cart)
  }, [cart])

  const cartCount = cart.reduce((sum, i) => sum + i.quantity, 0)

  function addToCart(product: Product) {
    setCart((prev) => {
      const existing = prev.find((i) => i.product.id === product.id)
      if (existing) {
        return prev.map((i) =>
          i.product.id === product.id
            ? { ...i, quantity: i.quantity + 1 }
            : i
        )
      }
      return [...prev, { product, quantity: 1 }]
    })
  }

  function updateQuantity(productId: number, delta: number) {
    setCart((prev) =>
      prev
        .map((i) =>
          i.product.id === productId
            ? { ...i, quantity: i.quantity + delta }
            : i
        )
        .filter((i) => i.quantity > 0)
    )
  }

  function clearCart() {
    setCart([])
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="text-indigo-400" size={22} />
            <span className="text-xl font-bold tracking-tight text-white">ShopApp</span>
            <span className="text-xs text-gray-500 ml-1">IncidentIQ Demo</span>
          </div>

          <nav className="flex items-center gap-1">
            <TabButton
              active={tab === 'home'}
              onClick={() => setTab('home')}
              icon={<Package size={16} />}
              label="Products"
            />
            <TabButton
              active={tab === 'cart'}
              onClick={() => setTab('cart')}
              icon={
                <span className="relative">
                  <ShoppingCart size={16} />
                  {cartCount > 0 && (
                    <span className="absolute -top-2 -right-2 bg-indigo-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center leading-none">
                      {cartCount > 9 ? '9+' : cartCount}
                    </span>
                  )}
                </span>
              }
              label="Cart"
            />
            <TabButton
              active={tab === 'orders'}
              onClick={() => setTab('orders')}
              icon={<ClipboardList size={16} />}
              label="Orders"
            />
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {tab === 'home' && (
          <Home onAddToCart={addToCart} onGoToCart={() => setTab('cart')} />
        )}
        {tab === 'cart' && (
          <Cart
            cart={cart}
            onUpdateQuantity={updateQuantity}
            onClearCart={clearCart}
            onOrderPlaced={() => {
              clearCart()
              setTab('orders')
            }}
          />
        )}
        {tab === 'orders' && <Orders />}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small helper component
// ---------------------------------------------------------------------------
function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-indigo-600 text-white'
          : 'text-gray-400 hover:text-white hover:bg-gray-700'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}
