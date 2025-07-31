from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from flask_cors import CORS
from flask_pymongo import PyMongo
import urllib
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from functools import lru_cache
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta
import logging
import re
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
from bs4 import BeautifulSoup
from  urllib.parse import quote_plus
import certifi
import urllib


# ---------- FLASK APP CONFIG ---------- #
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
load_dotenv()

# Session Security

#MongoDB Configuration

username = "Stockuser"  # Updated to match Atlas
password = urllib.parse.quote_plus("Anthonyjc@14")  # Ensures @ becomes %40
cluster_url = "stock-app.nvlvlky.mongodb.net"
db_name = "Stockuser"  # Verify this matches your Atlas DB name

app.config["MONGO_URI"] = (
    f"mongodb+srv://{username}:{password}@{cluster_url}/"
    f"{db_name}?retryWrites=true&w=majority&appName=Stock-app"
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24))

# Initialize MongoDB with TLS/SSL certificate
mongo = PyMongo(app, tlsCAFile=certifi.where())
db = mongo.db  # This will automatically use the database from MONGO_URI

# Test connection
try:
    mongo.db.command("ping")
    print("✅ MongoDB connection successful!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")


# Rate limiting setup
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Security Headers
@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response

# Request Timing Logs
@app.before_request
def log_request_time():
    request.start_time = time.time()

@app.after_request
def log_response_time(response):
    if hasattr(request, "start_time"):
        elapsed = time.time() - request.start_time
        logger.info(f"{request.method} {request.path} completed in {elapsed:.2f}s")
    return response

# Error Handlers
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 - Not Found: {request.path}")
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 - Server Error: {str(e)} at {request.path}")
    return render_template("500.html"), 500

# Retry decorator
def retry_api(max_attempts=3, delay=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempts} failed for {func.__name__}: {e}. Retrying...")
                    time.sleep(delay)
        return wrapper
    return decorator

# ---------- STOCK DATA ---------- #
@lru_cache(maxsize=100)
@retry_api(max_attempts=3, delay=2)
def get_stock_data(ticker, cache_bust=datetime.now().strftime('%Y%m%d')):
    try:
        for suffix in ['.NS', '.BO']:
            yf_ticker = ticker + suffix
            stock = yf.Ticker(yf_ticker)
            info = stock.info
            hist = stock.history(period="1d")
            if not hist.empty and info.get('symbol') == yf_ticker:
                price = hist['Close'].iloc[-1]
                change = ((price - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
                exchange = 'NSE' if suffix == '.NS' else 'BSE'
                return {
                    'ticker': ticker,
                    'name': info.get('longName', ticker),
                    'price': round(price, 2),
                    'change': round(change, 2),
                    'sector': info.get('sector', 'N/A'),
                    'summary': info.get('longBusinessSummary', '')[:500],
                    'high52': info.get('fiftyTwoWeekHigh', 'N/A'),
                    'low52': info.get('fiftyTwoWeekLow', 'N/A'),
                    'pe': info.get('trailingPE', 'N/A'),
                    'eps': info.get('trailingEps', 'N/A'),
                    'marketCap': info.get('marketCap', 'N/A'),
                    'dividendYield': info.get('dividendYield', 'N/A'),
                    'exchange': exchange
                }
        return None
    except Exception as e:
        logger.error(f"Error getting stock data for {ticker}: {e}")
        return None

# ---------- CHART DATA ---------- #
@lru_cache(maxsize=50)
@retry_api(max_attempts=3, delay=2)
def get_chart_data(ticker, cache_bust=datetime.now().strftime('%Y%m%d')):
    try:
        for suffix in ['.NS', '.BO']:
            yf_ticker = ticker + suffix
            stock = yf.Ticker(yf_ticker)
            hist = stock.history(period="6mo")
            if not hist.empty:
                hist['MA20'] = hist['Close'].rolling(window=20).mean()
                hist['Upper'] = hist['MA20'] + 2 * hist['Close'].rolling(window=20).std()
                hist['Lower'] = hist['MA20'] - 2 * hist['Close'].rolling(window=20).std()
                hist.reset_index(inplace=True)
                hist['Date'] = hist['Date'].astype(str)

                hist['Day'] = np.arange(len(hist))
                X = hist[['Day']].values
                y = hist['Close'].values
                model = LinearRegression().fit(X, y)
                mse = mean_squared_error(y, model.predict(X))
                std = np.sqrt(mse)

                last_date = pd.to_datetime(hist['Date'].iloc[-1])
                future_days = np.arange(len(hist), len(hist) + 30).reshape(-1, 1)
                future_dates = [(last_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 31)]
                predicted_prices = model.predict(future_days)
                predicted_upper = predicted_prices + std
                predicted_lower = predicted_prices - std

                data = []
                for _, row in hist.iterrows():
                    data.append({
                        'Date': row['Date'],
                        'Close': round(row['Close'], 2),
                        'MA20': round(row['MA20'], 2) if not pd.isna(row['MA20']) else None,
                        'Upper': round(row['Upper'], 2) if not pd.isna(row['Upper']) else None,
                        'Lower': round(row['Lower'], 2) if not pd.isna(row['Lower']) else None,
                        'Predicted': None,
                        'PredictedUpper': None,
                        'PredictedLower': None
                    })
                for i in range(30):
                    data.append({
                        'Date': future_dates[i],
                        'Close': None,
                        'MA20': None,
                        'Upper': None,
                        'Lower': None,
                        'Predicted': round(predicted_prices[i], 2),
                        'PredictedUpper': round(predicted_upper[i], 2),
                        'PredictedLower': round(predicted_lower[i], 2)
                    })
                return data
        return []
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        return []

# ---------- FIXED NEWS DATA (Yahoo Finance Scraper) ---------- #
@lru_cache(maxsize=50)
@retry_api(max_attempts=3, delay=2)
def get_news_data(ticker, cache_bust=datetime.now().strftime('%Y%m%d%H')):
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        news_items = soup.select('section[data-test-locator="mega"] h3 a')[:5]
        articles = []
        for item in news_items:
            title = item.get_text(strip=True)
            link = item['href']
            if not link.startswith('http'):
                link = "https://finance.yahoo.com" + link
            articles.append({
                'title': title,
                'source': 'Yahoo Finance',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'description': '',
                'url': link
            })
        return articles
    except Exception as e:
        logger.error(f"Error fetching Yahoo Finance news for {ticker}: {e}")
        return []

# ---------- INDICES DATA ---------- #
@lru_cache(maxsize=10)
@retry_api(max_attempts=3, delay=2)
def get_indices_data(cache_bust=datetime.now().strftime('%Y%m%d')):
    try:
        index_map = {
            'NIFTY 50': '^NSEI',
            'SENSEX': '^BSESN',
            'NIFTY BANK': '^NSEBANK',
            'INDIA VIX': '^INDIAVIX'
        }
        indices = []
        for name, symbol in index_map.items():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='2d')
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
                change = ((price - prev_close) / prev_close) * 100 if prev_close else 0
                indices.append({'name': name, 'value': f"{price:.2f}", 'change': round(change, 2)})
            else:
                indices.append({'name': name, 'value': 'N/A', 'change': 0})
        return indices
    except Exception as e:
        logger.error(f"Error fetching indices: {e}")
        return []

# ---------- TRENDING STOCKS ---------- #
def get_trending_stocks():
    sample = ['INFY', 'TCS', 'RELIANCE', 'HDFCBANK', 'ICICIBANK']
    trending = []
    for ticker in sample:
        stock_data = get_stock_data(ticker)
        if stock_data:
            trending.append({
                'ticker': ticker,
                'name': stock_data['name'],
                'price': stock_data['price'],
                'change': stock_data['change']
            })
    return trending

# ---------- WATCHLIST HELPERS ---------- #
def get_watchlist_data(tickers):
    return [stock for ticker in tickers if (stock := get_stock_data(ticker))]

# ---------- ROUTES ---------- #
@app.route('/')
def home():
    trending = get_trending_stocks()
    return render_template('index.html', trending=trending, year=datetime.now().year)

@app.route('/all_stocks')
@limiter.limit("50 per hour")
def all_stocks():
    return render_template('all_stocks.html')

@app.route('/watchlist')
def watchlist():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = session['user']
    user_watchlist = mongo.db.watchlists.find_one({'user': user}) or {'tickers': []}
    watchlist_data = get_watchlist_data(user_watchlist.get('tickers', []))
    return render_template('watchlist.html', watchlist=watchlist_data)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            return render_template('login.html', error="Username and password are required.")
        user_record = mongo.db.users.find_one({'username': username})
        if user_record and check_password_hash(user_record['password'], password):
            session['user'] = username
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            return render_template('signup.html', error="Username and password are required.")
        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
            return render_template('signup.html', error="Username must be 3-20 characters, alphanumeric or underscore.")
        existing_user = mongo.db.users.find_one({'username': username})
        if existing_user:
            return render_template('signup.html', error="Username already exists!")
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        mongo.db.users.insert_one({'username': username, 'password': hashed_pw})
        mongo.db.watchlists.insert_one({'user': username, 'tickers': []})
        session['user'] = username
        return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/analyze')
def analyze():
    ticker = request.args.get('ticker', '').upper()
    if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
        return render_template('analysis.html', stock=None, chart=[], news=[])
    data = get_stock_data(ticker)
    chart_data = get_chart_data(ticker)
    news_data = get_news_data(ticker)
    return render_template('analysis.html', stock=data, chart=chart_data, news=news_data)

@app.route('/api/trending')
@limiter.limit("100 per hour")
def api_trending():
    return jsonify(get_trending_stocks())

@app.route('/api/indices')
@limiter.limit("100 per hour")
def api_indices():
    indices = get_indices_data()
    return jsonify({'indices': indices})

@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = session['user']
    watchlist = mongo.db.watchlists.find_one({'user': user}) or {'tickers': []}
    return jsonify(get_watchlist_data(watchlist.get('tickers', [])))

@app.route('/api/watchlist/add', methods=['POST'])
@limiter.limit("20 per minute")
def add_to_watchlist():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = session['user']
    ticker = request.json.get('ticker', '').upper()
    if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
        return jsonify({'error': 'Invalid ticker format. Use symbols like INFY, TCS.'}), 400
    stock_data = get_stock_data(ticker)
    if not stock_data:
        return jsonify({'error': 'Invalid or unavailable ticker.'}), 400
    mongo.db.watchlists.update_one(
        {'user': user},
        {'$addToSet': {'tickers': ticker}},
        upsert=True
    )
    return jsonify({'status': 'added', 'ticker': ticker})

@app.route('/api/watchlist/remove', methods=['POST'])
@limiter.limit("20 per minute")
def remove_from_watchlist():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = session['user']
    ticker = request.json.get('ticker', '').upper()
    if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
        return jsonify({'error': 'Invalid ticker format.'}), 400
    mongo.db.watchlists.update_one(
        {'user': user},
        {'$pull': {'tickers': ticker}}
    )
    return jsonify({'status': 'removed', 'ticker': ticker})

@app.route('/api/stocks')
@limiter.limit("50 per hour")
def api_all_stocks():
    symbols = [
        'INFY', 'TCS', 'RELIANCE', 'HDFCBANK', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'LT', 'SBIN', 'AXISBANK',
        'MARUTI', 'BAJFINANCE', 'HCLTECH', 'KOTAKBANK', 'WIPRO', 'TATAMOTORS', 'ONGC', 'ADANIGREEN',
        'BHARTIARTL', 'ASIANPAINT', 'ULTRACEMCO', 'TATAPOWER', 'TECHM', 'JSWSTEEL', 'HDFCLIFE', 'CIPLA',
        'SUNPHARMA', 'DRREDDY', 'DIVISLAB', 'POWERGRID', 'NTPC', 'HINDALCO', 'GRASIM', 'VEDL',
        'TATACONSUMER', 'HAVELLS', 'PIDILITIND', 'M&M', 'ADANIPORTS', 'SHREECEM', 'BAJAJFINSV',
        'BAJAJ-AUTO', 'YESBANK', 'ZOMATO', 'PAYTM'
    ]
    stocks = []
    for symbol in symbols:
        stock_data = get_stock_data(symbol)
        if stock_data:
            stocks.append({
                'symbol': symbol,
                'name': stock_data['name'],
                'sector': stock_data['sector'],
                'currentPrice': stock_data['price'],
                'peRatio': stock_data['pe']
            })
    return jsonify(stocks)

@app.route('/api/news/<ticker>')
@limiter.limit("100 per hour")
def api_news(ticker):
    ticker = ticker.upper()
    if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
        return jsonify({'error': 'Invalid ticker format. Use symbols like INFY, TCS.'}), 400
    articles = get_news_data(ticker)
    return jsonify(articles)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5003)))
