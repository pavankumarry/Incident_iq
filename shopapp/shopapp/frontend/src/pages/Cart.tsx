import { useState } from 'react'
import { Minus, Plus, Trash2, ShoppingBag, AlertCircle, CheckCircle2 } from 'lucide-react'
import { createOrder, type CartItem } from '../api'

// Guest user ID used when no auth is implemented
const GUEST_USER_ID = 1

interface Props {
  cart: CartItem[]
  onUpdateQuantity: (productId: number, delta: number) => void
  onClearCart: () => void
  onOrderPlaced: () => void
}

export default function Cart({ cart, onUpdateQuantity, onClearCart, onOrderPlaced }: Props) {
  const [placing, setPlacing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const total = cart.reduce((sum, i) => sum + i.product.price * i.quantity, 0)

  async function handlePlaceOrder() {
    if (cart.length === 0) return
    setPlacing(true)
    setError(null)
    try {
      await createOrder(
        GUEST_USER_ID,
        cart.map((i) => ({ product_id: i.product.id, quantity: i.quantity }))
      )
      setSuccess(true)
      setTimeout(() => {
        setSuccess(false)
        onOrderPlaced()
      }, 1500)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to place order')
    } finally {
      setPlacing(false)
    }
  }

  if (cart.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-500">
        <ShoppingBag size={48} className="mb-4 opacity-30" />
        <p className="text-lg">Your cart is empty.</p>
        <p className="text-sm mt-1">Head to Products to add items.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-white mb-4">Your Cart</h2>

      {/* Items */}
      <div className="space-y-3 mb-6">
        {cart.map(({ product, quantity }) => (
          <div
            key={product.id}
            className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 flex items-center gap-4"
          >
            <div className="flex-1 min-w-0">
              <p className="font-medium text-white truncate">{product.name}</p>
              <p className="text-sm text-gray-400">${product.price.toFixed(2)} each</p>
            </div>

            {/* Quantity controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => onUpdateQuantity(product.id, -1)}
                className="w-7 h-7 rounded-md bg-gray-700 hover:bg-gray-600 flex items-center justify-center text-gray-300 transition-colors"
                aria-label="Decrease quantity"
              >
                {quantity === 1 ? <Trash2 size={13} /> : <Minus size={13} />}
              </button>
              <span className="w-6 text-center text-white font-medium">{quantity}</span>
              <button
                onClick={() => onUpdateQuantity(product.id, 1)}
                disabled={quantity >= product.stock}
                className="w-7 h-7 rounded-md bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center text-gray-300 transition-colors"
                aria-label="Increase quantity"
              >
                <Plus size={13} />
              </button>
            </div>

            {/* Line total */}
            <span className="text-white font-semibold w-20 text-right">
              ${(product.price * quantity).toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 mb-4">
        <div className="flex justify-between text-gray-400 text-sm mb-2">
          <span>Items ({cart.reduce((s, i) => s + i.quantity, 0)})</span>
          <span>${total.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-white font-bold text-lg border-t border-gray-700 pt-2 mt-2">
          <span>Total</span>
          <span>${total.toFixed(2)}</span>
        </div>
      </div>

      {/* Feedback */}
      {error && (
        <div className="flex items-center gap-2 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-4">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-4 py-3 mb-4">
          <CheckCircle2 size={16} />
          Order placed successfully! Redirecting…
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={onClearCart}
          className="flex-1 py-2.5 rounded-lg border border-gray-600 text-gray-400 hover:text-white hover:border-gray-500 text-sm font-medium transition-colors"
        >
          Clear Cart
        </button>
        <button
          onClick={handlePlaceOrder}
          disabled={placing || success}
          className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
        >
          {placing ? 'Placing Order…' : 'Place Order'}
        </button>
      </div>
    </div>
  )
}
