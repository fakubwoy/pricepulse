from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from database import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship to products
    products = db.relationship('Product', backref='user', lazy=True)
    alerts = db.relationship('PriceAlert', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    url = db.Column(db.String(500))
    name = db.Column(db.String(200))
    image = db.Column(db.String(500))
    current_price = db.Column(db.Float)
    original_price = db.Column(db.Float)
    currency = db.Column(db.String(10), default="₹")
    description = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, nullable=True)
    in_stock = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Added this field
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to price history
    price_history = db.relationship('PriceHistory', backref='product', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'url': self.url,
            'name': self.name,
            'image': self.image,
            'current_price': self.current_price,
            'original_price': self.original_price,
            'currency': self.currency,
            'description': self.description,
            'rating': self.rating,
            'in_stock': self.in_stock,
            'created_at': self.created_at.isoformat() if self.created_at else None,  # Added this field
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    price = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'price': self.price,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class PriceAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    target_price = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'target_price': self.target_price,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }