# 🚀 PricePulse: Smart Amazon Price Tracker & Alert System

[![Live Demo](https://img.shields.io/badge/DEMO-LIVE-brightgreen?style=for-the-badge&logo=render)](https://pricepulse-frontend.onrender.com/)
[![Frontend](https://img.shields.io/badge/React-Vite-blue?style=flat&logo=react)](https://reactjs.org/)
[![Backend](https://img.shields.io/badge/Flask-Python-green?style=flat&logo=python)](https://flask.palletsprojects.com/)

**Never overpay again!** PricePulse tracks Amazon.in product prices, alerts you on drops, and visualizes trends—so you buy at the *perfect* moment.

---

## ✨ Key Features
| Feature | Description |
|---------|-------------|
| **Real-time Tracking** | Monitor any Amazon.in product via URL. |
| **Price History Charts** | Interactive graphs (Chart.js) show trends over time. |
| **Email Alerts** | Instant notifications when prices hit your target. |
| **User Auth** | Secure email-based login/signup. |
| **Lightning Fast** | React+Vite frontend, optimized Flask backend. |
| **Reliable Scraping** | BeautifulSoup + Requests with anti-bot bypass. |
| **AI-Powered Search** | Uses GenAI + Google Custom Search API to find the same product on Flipkart, Meesho, and more. |
| **Comparison Table** | View and compare real-time prices across platforms in a single table. |

---

## 🛠️ Tech Stack
**Frontend**  
![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react) ![Vite](https://img.shields.io/badge/Vite-B73BFE?style=flat&logo=vite) ![Recharts](https://img.shields.io/badge/Recharts-FF6384?style=flat&logo=chart.js)

**Backend**  
![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python) ![SQLite](https://img.shields.io/badge/SQLite-07405E?style=flat&logo=sqlite)

**AI & APIs**  
![GenAI](https://img.shields.io/badge/GenAI-powered-blueviolet) ![Google Custom Search](https://img.shields.io/badge/Google%20Search-API-red?logo=google)

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.9+, Node.js 16+
- Git, pip, npm/yarn

### 1. Clone & Setup
```bash
git clone https://github.com/fakubwoy/pricepulse.git
cd pricepulse
```
### 2. Backend (Flask)
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set up environment variables
echo "MAIL_SERVER=smtp.gmail.com" > .env
echo "MAIL_PORT=587" >> .env
echo "MAIL_USERNAME=your_email@gmail.com" >> .env
echo "MAIL_PASSWORD=your_app_password" >> .env  
echo "SECRET_KEY=your_secret_key" >> .env
echo "GOOGLE_API_KEY=your_google_api_key" >> .env
echo "GOOGLE_CSE_ID=your_google_cse_id" >> .env
echo "HUGGINGFACE_API_KEY=you_huggingface_api_key" >> .env
python3 main.py
```
### 3. Frontend (React)
```bash
cd ../frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) to see the app!
---

## 📦 Deployment
PricePulse is deployed on **Render**:
- **Frontend**: [pricepulse-frontend.onrender.com](https://pricepulse-frontend.onrender.com/)
- **Backend**: Hosted as a Render web service with PostgreSQL.

---