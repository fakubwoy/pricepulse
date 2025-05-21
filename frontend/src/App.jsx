import { useState } from 'react';
import './App.css';

function App() {
  const [product, setProduct] = useState(null);

  const fetchTestProduct = async () => {
    try {
      const res = await fetch('http://localhost:8000/test-product');
      const data = await res.json();
      setProduct(data);
    } catch (err) {
      console.error('Failed to fetch product:', err);
    }
  };

  return (
    <div className="container">
      <h1>PricePulse</h1>
      <input type="text" placeholder="Enter Amazon Product URL" />
      <button onClick={fetchTestProduct}>Start Tracking</button>

      {product && (
        <div className="product-card">
          <h2>{product.name}</h2>
          <p><strong>Price:</strong> ₹{product.price}</p>
          <p><a href={product.url} target="_blank">View Product</a></p>
          <img src="https://via.placeholder.com/300x200?text=Product+Image" alt="Product" />
        </div>
      )}
    </div>
  );
}

export default App;
