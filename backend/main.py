from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from models import Product

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

@app.get("/")
def root():
    return {"message": "PricePulse API up and running"}

@app.get("/test-product")
def test_product():
    return Product(name="Samsung Galaxy M14", price=12999, url="https://amazon.in/...").dict()
