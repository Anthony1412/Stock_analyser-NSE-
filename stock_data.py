import yfinance as yf
import pandas as pd

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period='1d')

        if hist.empty or not info:
            return None

        price = hist['Close'].iloc[-1]
        open_price = hist['Open'].iloc[-1]
        change = ((price - open_price) / open_price * 100)

        return {
            'name': info.get('longName', ticker),
            'symbol': info.get('symbol', ticker),
            'currentPrice': round(price, 2),
            'change': round(change, 2),
            'sector': info.get('sector', 'N/A'),
            'marketCap': info.get('marketCap', 'N/A'),
            'peRatio': info.get('trailingPE', 'N/A'),
            'eps': info.get('trailingEps', 'N/A'),
            'dividendYield': info.get('dividendYield', 'N/A'),
            'weekHigh52': info.get('fiftyTwoWeekHigh', 'N/A'),
            'weekLow52': info.get('fiftyTwoWeekLow', 'N/A'),
            'beta': info.get('beta', 'N/A'),
            'summary': info.get('longBusinessSummary', 'No summary available.')[:500]
        }
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return None

def get_chart_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period='6mo')
        if df.empty:
            return []

        df['SMA50'] = df['Close'].rolling(window=50).mean()
        df['SMA200'] = df['Close'].rolling(window=200).mean()
        df['RSI'] = compute_rsi(df['Close'], 14)
        df['MACD'], df['MACDSignal'] = compute_macd(df['Close'])
        df['BollingerUpper'], df['BollingerLower'] = compute_bollinger_bands(df['Close'])

        df.reset_index(inplace=True)
        return df.tail(100).to_dict('records')
    except Exception as e:
        print(f"Error fetching chart data: {e}")
        return []

def get_trending_stocks():
    symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
    trending = []
    for sym in symbols:
        try:
            stock = yf.Ticker(sym)
            hist = stock.history(period='1d')
            if hist.empty:
                continue
            price = hist['Close'].iloc[-1]
            trending.append({
                'symbol': sym.replace('.NS', ''),
                'price': round(price, 2)
            })
        except:
            continue
    return trending

def compute_rsi(data, window):
    delta = data.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(data, slow=26, fast=12, signal=9):
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def compute_bollinger_bands(data, period=20, std_dev=2):
    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, lower
