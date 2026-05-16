import { useEffect, useState } from 'react'
import { ShoppingCart, ArrowLeft, Tag, AlertCircle, Loader2 } from 'lucide-react'
import { fetchProduct, type Product } from '../api'

interface Props {
  productId: number
  onAddToCart: (product: Product) => void
  onBack: () => void
}

export default function ProductDetail({ productId, onAddToCart, onBack }: Props) {
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [added, setAdded] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchProduct(productId)
      .then(setProduct)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [productId])

  function handleAdd() {
    if (!product) return
    onAddToCart(product)
    setAdded(true)
    setTimeout(() => setAdded(false), 1500)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} />
        Loading…
      </div>
    )
  }

  if (error || !product) {
    return (
      <div className="flex items-center gap-2 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3">
        <AlertCircle size={16} />
        {error ?? 'Product not found'}
      </div>
    )
  }

  return (
    <div className="max-w-xl mx-auto">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-gray-400 hover:text-white text-sm mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to Products
      </button>

      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
        <div className="flex items-center gap-1.5 text-indigo-400 text-sm mb-3">
          <Tag size={14} />
          {product.category}
        </div>

        <h1 className="text-2xl font-bold text-white mb-2">{product.name}</h1>

        {product.description && (
          <p className="text-gray-400 mb-4">{product.description}</p>
        )}

        <div className="flex items-center justify-between mb-6">
          <span className="text-3xl font-bold text-white">${product.price.toFixed(2)}</span>
          <span
            className={`text-sm px-3 py-1 rounded-full ${
              product.stock === 0
                ? 'bg-red-900/50 text-red-400'
                : product.stock < 10
                ? 'bg-yellow-900/50 text-yellow-400'
                : 'bg-green-900/50 text-green-400'
            }`}
          >
            {product.stock === 0 ? 'Out of stock' : `${product.stock} in stock`}
          </span>
        </div>

        <button
          onClick={handleAdd}
          disabled={product.stock === 0}
          className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white font-medium transition-colors flex items-center justify-center gap-2"
        >
          <ShoppingCart size={18} />
          {added ? 'Added to Cart!' : 'Add to Cart'}
        </button>
      </div>
    </div>
  )
}
