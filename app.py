from flask import Flask, render_template, request, jsonify, redirect, session
from flask_cors import CORS
from flask_pymongo import PyMongo
import yfinance as yf
import pandas as pd

app = Flask(__name__)
CORS(app)

app.config["MONGO_URI"] = "mongodb+srv://anthony14carvalho:WXdcDYAadRCHj3Sw@cluster0.1xu9vzs.mongodb.net/stockanalyzer?retryWrites=true&w=majority"
app.secret_key = 'your_secret_key_here'
mongo = PyMongo(app)

# Helper Functions
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker + ".NS")
        info = stock.info
        hist = stock.history(period="1d")
        if hist.empty:
            return None
        price = hist['Close'].iloc[-1]
        change = ((price - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
        return {
            'ticker': ticker,
            'name': info.get('longName', ticker),
            'price': round(price, 2),
            'change': round(change, 2),
            'sector': info.get('sector', 'N/A'),
            'summary': info.get('longBusinessSummary', '')[:500],
            'high52': info.get('fiftyTwoWeekHigh'),
            'low52': info.get('fiftyTwoWeekLow'),
            'pe': info.get('trailingPE'),
            'eps': info.get('trailingEps'),
            'marketCap': info.get('marketCap'),
            'dividendYield': info.get('dividendYield'),
        }
    except Exception as e:
        print(f"Error getting stock data: {e}")
        return None

def get_chart_data(ticker):
    try:
        stock = yf.Ticker(ticker + ".NS")
        hist = stock.history(period="6mo")
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        hist['Upper'] = hist['MA20'] + 2 * hist['Close'].rolling(window=20).std()
        hist['Lower'] = hist['MA20'] - 2 * hist['Close'].rolling(window=20).std()
        hist.reset_index(inplace=True)
        hist['Date'] = hist['Date'].astype(str)
        return hist.to_dict(orient='records')
    except Exception as e:
        print(f"Error getting chart data: {e}")
        return []

def get_trending_stocks():
    sample = ['INFY', 'TCS', 'RELIANCE', 'HDFCBANK', 'ICICIBANK']
    trending = []
    for ticker in sample:
        try:
            stock = yf.Ticker(ticker + ".NS")
            hist = stock.history(period="1d")
            price = hist['Close'].iloc[-1]
            prev = hist['Open'].iloc[-1]
            change = ((price - prev) / prev) * 100
            trending.append({
                'ticker': ticker,
                'price': price,
                'change': change
            })
        except:
            continue
    return trending

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/all_stocks')
def all_stocks():
    return render_template('all_stocks.html')

@app.route('/watchlist')
def watchlist():
    user_watchlist = mongo.db.watchlists.find_one({'user': 'default'}) or {'tickers': []}
    return render_template('watchlist.html', watchlist=user_watchlist.get('tickers', []))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        session['user'] = user
        if not mongo.db.watchlists.find_one({'user': user}):
            mongo.db.watchlists.insert_one({'user': user, 'tickers': []})
        return redirect('/')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/analyze')
def analyze():
    ticker = request.args.get('ticker')
    data = get_stock_data(ticker)
    chart_data = get_chart_data(ticker)
    return render_template('analysis.html', stock=data, chart=chart_data)

@app.route('/api/trending')
def api_trending():
    return jsonify(get_trending_stocks())

@app.route('/api/watchlist/add', methods=['POST'])
def add_to_watchlist():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 403
    ticker = request.json.get('ticker')
    mongo.db.watchlists.update_one(
        {'user': session['user']},
        {'$addToSet': {'tickers': ticker}}
    )
    return jsonify({'status': 'added'})

@app.route('/api/watchlist/remove', methods=['POST'])
def remove_from_watchlist():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 403
    ticker = request.json.get('ticker')
    mongo.db.watchlists.update_one(
        {'user': session['user']},
        {'$pull': {'tickers': ticker}}
    )
    return jsonify({'status': 'removed'})

# ✅ New API for all stocks
@app.route('/api/stocks')
def api_all_stocks():
    symbols = ['INFY', 'TCS', 'RELIANCE', 'HDFCBANK', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'LT', 'SBIN', 'AXISBANK','MARUTI', 'BAJFINANCE', 'HCLTECH', 'KOTAKBANK', 'WIPRO', 'TATAMOTORS', 'ONGC', 'ADANIGREEN', 'BHARTIARTL', 'ASIANPAINT', 'ULTRACEMCO', 'TATAPOWER', 'TECHM', 'JSWSTEEL', 'HDFCLIFE', 'CIPLA', 'SUNPHARMA', 'DRREDDY', 'DIVISLAB', 'POWERGRID', 'NTPC', 'TATAMOTORS']
    stocks = []
    for symbol in symbols:
        try:
            stock = yf.Ticker(symbol + ".NS")
            info = stock.info
            stocks.append({
                'symbol': symbol,
                'name': info.get('longName', symbol),
                'sector': info.get('sector', 'N/A'),
                'currentPrice': round(info.get('currentPrice', 0), 2),
                'peRatio': info.get('trailingPE', 'N/A')
            })
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            continue
    return jsonify(stocks)

if __name__ == '__main__':
    app.run(debug=True, port=5003)
