import { useEffect, useState } from 'react'
import { ShoppingCart, Tag, AlertCircle, Loader2 } from 'lucide-react'
import { fetchProducts, type Product } from '../api'

const CATEGORIES = ['All', 'Electronics', 'Clothing', 'Books', 'Home']

interface Props {
  onAddToCart: (product: Product) => void
  onGoToCart: () => void
}

export default function Home({ onAddToCart, onGoToCart }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState('All')
  const [addedId, setAddedId] = useState<number | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const cat = activeCategory === 'All' ? undefined : activeCategory
    fetchProducts(cat)
      .then(setProducts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [activeCategory])

  function handleAdd(product: Product) {
    onAddToCart(product)
    setAddedId(product.id)
    setTimeout(() => setAddedId(null), 1200)
  }

  return (
    <div>
      {/* Category filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              activeCategory === cat
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* States */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <Loader2 className="animate-spin mr-2" size={20} />
          Loading products…
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-4">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      {!loading && !error && products.length === 0 && (
        <p className="text-gray-500 text-center py-20">No products found.</p>
      )}

      {/* Product grid */}
      {!loading && !error && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {products.map((p) => (
            <ProductCard
              key={p.id}
              product={p}
              added={addedId === p.id}
              onAdd={() => handleAdd(p)}
              onGoToCart={onGoToCart}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product card
// ---------------------------------------------------------------------------
function ProductCard({
  product,
  added,
  onAdd,
  onGoToCart,
}: {
  product: Product
  added: boolean
  onAdd: () => void
  onGoToCart: () => void
}) {
  const outOfStock = product.stock === 0

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex flex-col gap-3 hover:border-indigo-500 transition-colors">
      {/* Category badge */}
      <div className="flex items-center gap-1 text-xs text-indigo-400">
        <Tag size={12} />
        {product.category}
      </div>

      {/* Name & description */}
      <div className="flex-1">
        <h3 className="font-semibold text-white text-base leading-snug">{product.name}</h3>
        {product.description && (
          <p className="text-gray-400 text-sm mt-1 line-clamp-2">{product.description}</p>
        )}
      </div>

      {/* Price & stock */}
      <div className="flex items-center justify-between">
        <span className="text-lg font-bold text-white">${product.price.toFixed(2)}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            outOfStock
              ? 'bg-red-900/50 text-red-400'
              : product.stock < 10
              ? 'bg-yellow-900/50 text-yellow-400'
              : 'bg-green-900/50 text-green-400'
          }`}
        >
          {outOfStock ? 'Out of stock' : `${product.stock} left`}
        </span>
      </div>

      {/* Action */}
      {added ? (
        <button
          onClick={onGoToCart}
          className="w-full py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium transition-colors flex items-center justify-center gap-1"
        >
          <ShoppingCart size={14} />
          View Cart
        </button>
      ) : (
        <button
          onClick={onAdd}
          disabled={outOfStock}
          className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors flex items-center justify-center gap-1"
        >
          <ShoppingCart size={14} />
          Add to Cart
        </button>
      )}
    </div>
  )
}
