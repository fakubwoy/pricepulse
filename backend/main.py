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
    return Product(name="Samsung Galaxy M35", price=18499, url="https://www.amazon.in/Samsung-Daybreak-Storage-Corning-Gorilla/dp/B0D812DY6P/ref=pd_ci_mcx_mh_pe_im_d1_hxwPPE_sspa_dk_det_cav_p_1_1").dict()
