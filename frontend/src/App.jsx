import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { AlertTriangle, Trash2, RefreshCw, Plus, ShoppingCart, Bell, ChevronRight, ExternalLink, TrendingDown, Zap, User, LogIn, LogOut, UserPlus } from 'lucide-react';
import './App.css';

const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? 'https://pricepulse-backend.onrender.com/api'  // Replace with YOUR actual backend URL
  : 'http://localhost:5000/api';
function App() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newProductUrl, setNewProductUrl] = useState('');
  const [addingProduct, setAddingProduct] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [historyDays, setHistoryDays] = useState(30);
  const [alerts, setAlerts] = useState([]);
  const [newAlert, setNewAlert] = useState({ target_price: '' });
  const [auth, setAuth] = useState({
    isAuthenticated: false,
    user: null,
    token: null
  });
  const [authForm, setAuthForm] = useState({
    email: '',
    password: '',
    name: '',
    isLogin: true
  });

  // Check for existing token on initial load
  useEffect(() => {
    const token = localStorage.getItem('pricepulse_token');
    if (token) {
      verifyToken(token);
    } else {
      setLoading(false);
    }
  }, []);

  // Fetch products when authenticated
  useEffect(() => {
    if (auth.isAuthenticated) {
      fetchProducts();
    }
  }, [auth.isAuthenticated]);

  // Fetch price history when a product is selected
  useEffect(() => {
    if (selectedProduct && auth.isAuthenticated) {
      fetchPriceHistory(selectedProduct.id);
      fetchAlerts(selectedProduct.id);
    }
  }, [selectedProduct, historyDays, auth.isAuthenticated]);

  const verifyToken = async (token) => {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Invalid token');
      }
      
      const user = await response.json();
      setAuth({
        isAuthenticated: true,
        user,
        token
      });
    } catch (err) {
      localStorage.removeItem('pricepulse_token');
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAuth = async (e) => {
    e.preventDefault();
    setError(null);
    
    try {
      const endpoint = authForm.isLogin ? 'login' : 'register';
      const response = await fetch(`${API_BASE_URL}/auth/${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: authForm.email,
          password: authForm.password,
          name: authForm.name
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Authentication failed');
      }
      
      const data = await response.json();
      localStorage.setItem('pricepulse_token', data.token);
      
      setAuth({
        isAuthenticated: true,
        user: data.user,
        token: data.token
      });
      
      setAuthForm({
        email: '',
        password: '',
        name: '',
        isLogin: true
      });
    } catch (err) {
      setError(err.message);
    }
  };

  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      
      localStorage.removeItem('pricepulse_token');
      setAuth({
        isAuthenticated: false,
        user: null,
        token: null
      });
      setProducts([]);
      setSelectedProduct(null);
      setPriceHistory([]);
      setAlerts([]);
    } catch (err) {
      setError(err.message);
    }
  };

  const fetchProducts = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/products`, {
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      if (!response.ok) {
        throw new Error('Failed to fetch products');
      }
      const data = await response.json();
      setProducts(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchPriceHistory = async (productId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/products/${productId}/history?days=${historyDays}`, {
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      if (!response.ok) {
        throw new Error('Failed to fetch price history');
      }
      const data = await response.json();
      
      const formattedData = data.map(item => ({
        date: new Date(item.timestamp).toLocaleDateString(),
        price: item.price
      }));
      
      setPriceHistory(formattedData);
    } catch (err) {
      console.error('Error fetching price history:', err);
    }
  };

  const fetchAlerts = async (productId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/products/${productId}/alerts`, {
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      if (!response.ok) {
        throw new Error('Failed to fetch alerts');
      }
      const data = await response.json();
      setAlerts(data);
    } catch (err) {
      console.error('Error fetching alerts:', err);
    }
  };

  const addProduct = async () => {
    if (!newProductUrl.trim()) return;
    
    try {
      setAddingProduct(true);
      const response = await fetch(`${API_BASE_URL}/products`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify({ url: newProductUrl })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to add product');
      }
      
      const newProduct = await response.json();
      setProducts([...products, newProduct]);
      setNewProductUrl('');
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setAddingProduct(false);
    }
  };

  const deleteProduct = async (productId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/products/${productId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete product');
      }
      
      setProducts(products.filter(product => product.id !== productId));
      if (selectedProduct && selectedProduct.id === productId) {
        setSelectedProduct(null);
        setPriceHistory([]);
        setAlerts([]);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const refreshProduct = async (productId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/products/${productId}/refresh`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to refresh product');
      }
      
      const updatedProduct = await response.json();
      setProducts(products.map(product => 
        product.id === productId ? updatedProduct : product
      ));
      
      if (selectedProduct && selectedProduct.id === productId) {
        setSelectedProduct(updatedProduct);
        fetchPriceHistory(productId);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const createAlert = async () => {
    if (!selectedProduct || !newAlert.target_price) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/alerts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify({
          product_id: selectedProduct.id,
          target_price: parseFloat(newAlert.target_price)
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to create alert');
      }
      
      const createdAlert = await response.json();
      setAlerts([...alerts, createdAlert]);
      setNewAlert({ target_price: '' });
    } catch (err) {
      setError(err.message);
    }
  };

  const deleteAlert = async (alertId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/alerts/${alertId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${auth.token}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete alert');
      }
      
      setAlerts(alerts.filter(alert => alert.id !== alertId));
    } catch (err) {
      setError(err.message);
    }
  };

  const testEmailAlert = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/alerts/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${auth.token}`
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to send test email');
      }
      
      alert('Test email sent successfully!');
    } catch (err) {
      setError(err.message);
    }
  };

  const formatPrice = (price, currency = '$') => {
    return `${currency}${price.toFixed(2)}`;
  };

  const calculateDiscount = (current, original) => {
    if (!original || original <= current) return null;
    const discount = ((original - current) / original) * 100;
    return Math.round(discount);
  };

  if (!auth.isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-lg shadow-lg overflow-hidden">
            <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 text-white p-6 text-center">
              <div className="flex items-center justify-center mb-4">
                <ShoppingCart className="mr-3 h-8 w-8" />
                <h1 className="text-3xl font-bold">PricePulse</h1>
              </div>
              <p className="text-indigo-100">Track Amazon prices and get alerts when prices drop</p>
            </div>
            
            <div className="p-6">
              {error && (
                <div className="alert alert-error mb-6">
                  <AlertTriangle className="mr-3 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              
              <form onSubmit={handleAuth}>
                <h2 className="text-xl font-semibold mb-6 text-center">
                  {authForm.isLogin ? 'Sign In' : 'Create Account'}
                </h2>
                
                {!authForm.isLogin && (
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                    <input
                      type="text"
                      value={authForm.name}
                      onChange={(e) => setAuthForm({...authForm, name: e.target.value})}
                      placeholder="Your name"
                      className="input w-full"
                      required={!authForm.isLogin}
                    />
                  </div>
                )}
                
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                  <input
                    type="email"
                    value={authForm.email}
                    onChange={(e) => setAuthForm({...authForm, email: e.target.value})}
                    placeholder="your@email.com"
                    className="input w-full"
                    required
                  />
                </div>
                
                <div className="mb-6">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                  <input
                    type="password"
                    value={authForm.password}
                    onChange={(e) => setAuthForm({...authForm, password: e.target.value})}
                    placeholder="••••••••"
                    className="input w-full"
                    required
                    minLength="6"
                  />
                </div>
                
                <button
                  type="submit"
                  className="btn btn-primary w-full mb-4"
                >
                  {authForm.isLogin ? (
                    <span className="flex items-center justify-center">
                      <LogIn className="mr-2" size={18} />
                      Sign In
                    </span>
                  ) : (
                    <span className="flex items-center justify-center">
                      <UserPlus className="mr-2" size={18} />
                      Register
                    </span>
                  )}
                </button>
                
                <p className="text-center text-sm text-gray-600">
                  {authForm.isLogin ? "Don't have an account?" : "Already have an account?"}{' '}
                  <button
                    type="button"
                    onClick={() => setAuthForm({...authForm, isLogin: !authForm.isLogin})}
                    className="text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    {authForm.isLogin ? 'Register here' : 'Sign in here'}
                  </button>
                </p>
              </form>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-indigo-600 to-indigo-700 text-white p-6 shadow-lg">
      <div className="container mx-auto flex items-center justify-between">
        <div className="flex items-center">
            <ShoppingCart className="mr-3 h-8 w-8" />
            <h1 className="text-3xl font-bold">PricePulse</h1>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="flex items-center bg-indigo-500 bg-opacity-20 px-3 py-1 rounded-full">
              <User className="mr-2" size={18} />
              <span>{auth.user?.name || auth.user?.email}</span>
            </div>
            <button 
              onClick={logout}
              className="btn btn-sm btn-ghost hover:bg-indigo-500 hover:bg-opacity-20"
              title="Logout"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4 md:p-6">
        {/* Error Alert */}
        {error && (
          <div className="alert alert-error mb-6">
            <AlertTriangle className="mr-3 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Add Product Card */}
        <div className="card mb-6">
          <div className="card-header">
            <h2 className="text-xl font-semibold">Add New Product</h2>
          </div>
          <div className="p-4">
            <div className="flex flex-col md:flex-row gap-3">
              <input
                type="text"
                value={newProductUrl}
                onChange={(e) => setNewProductUrl(e.target.value)}
                placeholder="Paste Amazon product URL here..."
                className="input flex-1"
                disabled={addingProduct}
              />
              <button
                onClick={addProduct}
                disabled={addingProduct || !newProductUrl}
                className={`btn btn-primary ${addingProduct ? 'opacity-75' : ''}`}
              >
                {addingProduct ? (
                  <span className="flex items-center">
                    <RefreshCw className="animate-spin mr-2" size={18} />
                    Adding...
                  </span>
                ) : (
                  <span className="flex items-center">
                    <Plus className="mr-2" size={18} />
                    Track Product
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Product List Column */}
          <div className="card">
            <div className="card-header">
              <h2 className="text-xl font-semibold">Your Tracked Products</h2>
            </div>
            <div className="p-4">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-8">
                  <RefreshCw className="animate-spin text-indigo-500 mb-3" size={24} />
                  <p>Loading your products...</p>
                </div>
              ) : products.length === 0 ? (
                <div className="empty-state">
                  <ShoppingCart className="empty-state-icon" size={48} />
                  <h3 className="text-lg font-medium mb-2">No products tracked yet</h3>
                  <p className="text-gray-500">Add your first product using the form above</p>
                </div>
              ) : (
                <ul className="product-list divide-y divide-gray-100">
                  {products.map(product => (
                    <li key={product.id} className="product-item">
                      <div className="flex items-center">
                        <div 
                          className="product-image flex-shrink-0 mr-4 cursor-pointer"
                          onClick={() => setSelectedProduct(product)}
                        >
                          {product.image ? (
                            <img src={product.image} alt={product.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-gray-400">
                              <ShoppingCart size={24} />
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 
                            className="product-name text-md font-medium truncate mb-1 cursor-pointer"
                            onClick={() => setSelectedProduct(product)}
                          >
                            {product.name}
                          </h3>
                          <div className="flex items-center flex-wrap gap-2">
                            <span className="price-current text-lg font-bold">
                              {formatPrice(product.current_price, product.currency)}
                            </span>
                            {product.original_price > product.current_price && (
                              <>
                                <span className="price-original text-sm">
                                  {formatPrice(product.original_price, product.currency)}
                                </span>
                                <span className="discount-badge text-xs px-2 py-1 rounded-full flex items-center">
                                  <TrendingDown size={14} className="mr-1" />
                                  {calculateDiscount(product.current_price, product.original_price)}% OFF
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center ml-2">
                          <button 
                            onClick={() => refreshProduct(product.id)}
                            className="btn-icon"
                            title="Refresh product"
                          >
                            <RefreshCw size={18} />
                          </button>
                          <button 
                            onClick={() => deleteProduct(product.id)}
                            className="btn-icon text-red-500 hover:bg-red-50 ml-1"
                            title="Delete product"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          
          {/* Product Detail Column */}
          <div className="card md:col-span-2">
            {selectedProduct ? (
              <div>
                <div className="card-header flex justify-between items-center">
                  <h2 className="text-xl font-semibold">Product Details</h2>
                </div>
                
                <div className="p-6">
                  {/* Product Header */}
                  <div className="flex flex-col md:flex-row mb-8">
                    <div className="w-full md:w-1/3 mb-4 md:mb-0 md:mr-6">
                      <div className="product-image w-full h-64 rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center">
                        {selectedProduct.image ? (
                          <img 
                            src={selectedProduct.image} 
                            alt={selectedProduct.name} 
                            className="w-full h-full object-contain"
                          />
                        ) : (
                          <ShoppingCart size={48} className="text-gray-400" />
                        )}
                      </div>
                    </div>
                    <div className="flex-1">
                      <h2 className="text-2xl font-bold mb-3">{selectedProduct.name}</h2>
                      
                      <div className="flex items-center mb-4">
                        <span className="text-3xl font-bold text-indigo-600 mr-3">
                          {formatPrice(selectedProduct.current_price, selectedProduct.currency)}
                        </span>
                        {selectedProduct.original_price > selectedProduct.current_price && (
                          <>
                            <span className="line-through text-gray-500 text-lg mr-2">
                              {formatPrice(selectedProduct.original_price, selectedProduct.currency)}
                            </span>
                            <span className="discount-badge px-3 py-1 rounded-full text-sm font-bold">
                              {calculateDiscount(selectedProduct.current_price, selectedProduct.original_price)}% OFF
                            </span>
                          </>
                        )}
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-3 mb-6">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                          selectedProduct.in_stock 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {selectedProduct.in_stock ? 'In Stock' : 'Out of Stock'}
                        </span>
                        
                        {selectedProduct.rating && (
                          <span className="inline-flex items-center px-3 py-1 rounded-full bg-amber-100 text-amber-800 text-sm font-medium">
                            ★ {selectedProduct.rating}
                          </span>
                        )}
                        
                        <a 
                          href={selectedProduct.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="inline-flex items-center text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                        >
                          View on Amazon <ExternalLink className="ml-1" size={14} />
                        </a>
                      </div>
                      
                      <div className="text-sm text-gray-500">
                        <p>Last updated: {new Date(selectedProduct.last_updated).toLocaleString()}</p>
                      </div>
                    </div>
                  </div>
                  
                  {/* Price History Chart */}
                  <div className="mb-8">
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      <Zap className="mr-2 text-indigo-500" size={20} />
                      Price History
                    </h3>
                    <div className="flex items-center space-x-2 mb-4">
                      <select 
                        value={historyDays} 
                        onChange={(e) => setHistoryDays(Number(e.target.value))}
                        className="input select text-sm"
                      >
                        <option value={7}>Last 7 days</option>
                        <option value={30}>Last 30 days</option>
                        <option value={90}>Last 90 days</option>
                        <option value={180}>Last 6 months</option>
                        <option value={365}>Last year</option>
                      </select>
                    </div>
                    {priceHistory.length > 1 ? (
                      <div className="chart-container">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={priceHistory}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis 
                              dataKey="date" 
                              tick={{ fontSize: 12, fill: '#64748b' }}
                              tickMargin={10}
                            />
                            <YAxis 
                              domain={['dataMin - 5', 'dataMax + 5']}
                              tick={{ fontSize: 12, fill: '#64748b' }}
                              tickFormatter={(value) => `${selectedProduct.currency}${value}`}
                              tickMargin={10}
                            />
                            <Tooltip 
                              formatter={(value) => [`${selectedProduct.currency}${value.toFixed(2)}`, 'Price']}
                              labelFormatter={(label) => `Date: ${label}`}
                              contentStyle={{
                                borderRadius: '8px',
                                border: 'none',
                                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                              }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="price" 
                              stroke="#6366f1" 
                              strokeWidth={2}
                              dot={{ fill: '#6366f1', strokeWidth: 2, r: 4 }}
                              activeDot={{ r: 6, stroke: '#6366f1', strokeWidth: 2, fill: '#fff' }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    ) : priceHistory.length === 1 ? (
                      <div className="bg-gray-50 rounded-lg p-4 text-center">
                        <p className="text-gray-500">Only one price point available. More data will appear as prices change.</p>
                      </div>
                    ) : (
                      <div className="bg-gray-50 rounded-lg p-4 text-center">
                        <p className="text-gray-500">No price history available yet.</p>
                      </div>
                    )}
                  </div>
                  
                  {/* Price Alerts Section */}
                  <div>
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      <Bell className="mr-2 text-indigo-500" size={20} />
                      Price Alerts
                    </h3>
                    
                    <div className="bg-indigo-50 p-4 rounded-lg border border-indigo-100 mb-6">
                      <h4 className="font-medium text-indigo-800 mb-3">Create New Alert</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Target Price ({selectedProduct.currency})</label>
                          <input
                            type="number"
                            value={newAlert.target_price}
                            onChange={(e) => setNewAlert({...newAlert, target_price: e.target.value})}
                            placeholder="e.g. 499"
                            className="input w-full"
                            min="0.01"
                            step="0.01"
                          />
                        </div>
                        <div className="flex items-end">
                          <button
                            onClick={createAlert}
                            disabled={!newAlert.target_price}
                            className="btn btn-primary"
                          >
                            Create Price Alert
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <p className="text-sm text-indigo-700">
                          Alerts will be sent to: {auth.user?.email}
                        </p>
                        <button
                          onClick={testEmailAlert}
                          className="btn btn-sm btn-ghost text-indigo-600 hover:bg-indigo-100"
                        >
                          Test Email
                        </button>
                      </div>
                    </div>
                    
                    {alerts.length > 0 ? (
                      <div className="border rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="alert-table w-full">
                            <thead>
                              <tr>
                                <th className="text-left">Target Price</th>
                                <th className="text-left">Created</th>
                                <th className="text-right">Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {alerts.map(alert => (
                                <tr key={alert.id} className="hover:bg-gray-50">
                                  <td className="py-3 px-4 font-medium">
                                    {formatPrice(alert.target_price, selectedProduct.currency)}
                                  </td>
                                  <td className="py-3 px-4 text-sm text-gray-500">
                                    {new Date(alert.created_at).toLocaleDateString()}
                                  </td>
                                  <td className="py-3 px-4 text-right">
                                    <button 
                                      onClick={() => deleteAlert(alert.id)}
                                      className="text-red-500 hover:text-red-700 text-sm font-medium"
                                    >
                                      Remove
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <div className="bg-gray-50 rounded-lg p-6 text-center">
                        <Bell className="mx-auto mb-3 text-gray-400" size={32} />
                        <h4 className="text-gray-500 font-medium mb-1">No alerts set up yet</h4>
                        <p className="text-gray-400 text-sm">Create a price alert to get notified when this product drops to your target price</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty-state p-8">
                <ShoppingCart className="empty-state-icon mb-4" size={48} />
                <h3 className="text-lg font-medium mb-2">No Product Selected</h3>
                <p className="text-gray-500 max-w-md mx-auto">
                  Select a product from your tracked items to view detailed price history and set up price alerts.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;