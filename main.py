from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import yfinance as yf
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Predefined list of major U.S. stock tickers
TICKERS = [
  "AAPL",
  "MSFT",
  "GOOG",
  "AMZN",
  "META",
  "NFLX",
  "TSLA",
  "NVDA",
  "JPM",
  "BAC",
  "SOXL",
  "SOXS"
]

@app.get("/", response_class=HTMLResponse)
def get_top_gainers(request: Request):
    # Fetch current stock data for each ticker
    results = []
    for symbol in TICKERS:
        ticker = yf.Ticker(symbol)
        info = ticker.info  # Get a dictionary of stock info from Yahoo Finance
        price = info.get("regularMarketPrice")
        change = info.get("regularMarketChange")
        change_percent = info.get("regularMarketChangePercent")
        if price is None or change_percent is None:
            # Skip tickers if data is not available (e.g., during off-hours)
            continue
        results.append({
            "symbol": symbol,
            "price": price,
            "change": change,
            "percent_change": change_percent
        })
    # Sort the stocks by percentage change (descending) to find top gainers
    results.sort(key=lambda x: x["percent_change"], reverse=True)
    # Timestamp for last update
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Render the HTML template with the data
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "gainers": results, "last_update": current_time},
        request=request
    ) 