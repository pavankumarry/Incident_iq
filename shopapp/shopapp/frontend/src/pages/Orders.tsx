import { useEffect, useState } from 'react'
import { ClipboardList, AlertCircle, Loader2, RefreshCw, Package } from 'lucide-react'
import { fetchOrders, type Order } from '../api'

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow-900/50 text-yellow-400',
  processing: 'bg-blue-900/50 text-blue-400',
  shipped: 'bg-indigo-900/50 text-indigo-400',
  delivered: 'bg-green-900/50 text-green-400',
  cancelled: 'bg-red-900/50 text-red-400',
}

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setLoading(true)
    setError(null)
    fetchOrders()
      .then(setOrders)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <ClipboardList size={20} className="text-indigo-400" />
          Order History
        </h2>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <Loader2 className="animate-spin mr-2" size={20} />
          Loading orders…
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {!loading && !error && orders.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500">
          <Package size={48} className="mb-4 opacity-30" />
          <p className="text-lg">No orders yet.</p>
          <p className="text-sm mt-1">Place an order from the Cart tab.</p>
        </div>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="space-y-4">
          {orders.map((order) => (
            <OrderCard key={order.id} order={order} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Order card
// ---------------------------------------------------------------------------
function OrderCard({ order }: { order: Order }) {
  const statusClass = STATUS_STYLES[order.status] ?? 'bg-gray-700 text-gray-400'
  const date = new Date(order.created_at).toLocaleString()

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-white font-semibold">Order #{order.id}</p>
          <p className="text-gray-500 text-xs mt-0.5">{date}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${statusClass}`}>
            {order.status}
          </span>
          <span className="text-white font-bold">${order.total_amount.toFixed(2)}</span>
        </div>
      </div>

      {/* Items */}
      {order.items.length > 0 && (
        <div className="border-t border-gray-700 pt-3 space-y-1.5">
          {order.items.map((item) => (
            <div key={item.id} className="flex justify-between text-sm">
              <span className="text-gray-400">
                Product #{item.product_id} × {item.quantity}
              </span>
              <span className="text-gray-300">${(item.price * item.quantity).toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
