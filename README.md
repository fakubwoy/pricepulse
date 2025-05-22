#  PricePulse

**PricePulse** is a smart Amazon price tracking tool that allows users to monitor product prices on [Amazon.in](https://www.amazon.in/) and get notified when prices drop. It includes a user-friendly frontend and a Flask-powered backend that scrapes product data, stores historical prices, and sends alert emails.

##  Features

-  Track Amazon.in product prices by URL  
-  Visualize price history over time  
-  Get email alerts when prices drop  
-  User login & authentication (email-based)  
-  Fast, responsive frontend (React + Vite)  
-  Efficient scraping and database architecture  

##  Tech Stack

### Frontend
- React
- Vite
- Chart.js or Recharts

### Backend
- Python + Flask
- BeautifulSoup + requests
- SQLite or PostgreSQL
- Flask-Mail


##  Installation

### 1. Clone the Repository

```bash
git clone https://github.com/fakubwoy/pricepulse.git
cd pricepulse
```
### 2. Setup Backend (Flask)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
### 3. Setup Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```
##  Email Alerts

Add a `.env` file in the `backend/` directory with:

```env
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USERNAME=your_email@example.com
MAIL_PASSWORD=your_password
MAIL_USE_TLS=True
```
