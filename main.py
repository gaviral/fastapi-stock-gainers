from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import yfinance as yf
from datetime import datetime
import logging

# Configure logging - console only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Predefined list of major U.S. stock tickers
TICKERS = [
  "AAPL",  # Apple
  "MSFT",  # Microsoft
  "GOOG",  # Google
  "AMZN",  # Amazon
  "META",  # Meta (Facebook)
  "NFLX",  # Netflix
  "TSLA",  # Tesla
  "NVDA",  # NVIDIA
  "JPM",   # JPMorgan Chase
  "BAC",   # Bank of America
  "SOXL",  # Direxion Daily Semiconductor Bull 3X
  "SOXS",  # Direxion Daily Semiconductor Bear 3X
  "AMD",   # Advanced Micro Devices
  "INTC",  # Intel
  "DIS",   # Disney
  "KO",    # Coca-Cola
  "PEP",   # PepsiCo
  "WMT",   # Walmart
  "COST",  # Costco
  "V",     # Visa
  "MA",    # Mastercard
  "PYPL",  # PayPal
  "SQ",    # Block (Square)
  "COIN"   # Coinbase
]

@app.get("/", response_class=HTMLResponse)
def get_top_gainers(request: Request):
    logger.info("Processing request for stock market movers")
    # Fetch current stock data for each ticker
    results = []
    for symbol in TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info  # Get a dictionary of stock info from Yahoo Finance
            
            # Check if we have the minimum required data
            if not info or "regularMarketPrice" not in info:
                logger.warning(f"Incomplete data for {symbol}, skipping")
                continue
                
            # Extract data with safe defaults
            price = info.get("regularMarketPrice")
            change = info.get("regularMarketChange", 0)
            change_percent = info.get("regularMarketChangePercent", 0)
            volume = info.get("regularMarketVolume")
            market_cap = info.get("marketCap")
            fifty_two_week_low = info.get("fiftyTwoWeekLow")
            fifty_two_week_high = info.get("fiftyTwoWeekHigh")
            company_name = info.get("shortName") or info.get("longName") or symbol
            
            results.append({
                "symbol": symbol,
                "name": company_name,
                "price": price,
                "change": change,
                "percent_change": change_percent,
                "volume": volume,
                "market_cap": market_cap,
                "fifty_two_week_low": fifty_two_week_low,
                "fifty_two_week_high": fifty_two_week_high
            })
            logger.debug(f"Processed {symbol}: price={price}, change={change}, percent_change={change_percent}")
        except IndexError as e:
            # Specific handling for the SQ ticker issue
            logger.error(f"Index error processing {symbol}: {str(e)}")
            # Add a placeholder entry with default values
            results.append({
                "symbol": symbol,
                "name": symbol,
                "price": 0,
                "change": 0,
                "percent_change": 0,
                "volume": 0,
                "market_cap": 0,
                "fifty_two_week_low": 0,
                "fifty_two_week_high": 0
            })
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
    
    # Sort the stocks by percentage change (descending)
    results.sort(key=lambda x: x["percent_change"], reverse=True)
    
    # Separate gainers and losers
    gainers = [stock for stock in results if stock["percent_change"] >= 0]
    losers = [stock for stock in results if stock["percent_change"] < 0]
    
    logger.info(f"Found {len(gainers)} gainers and {len(losers)} losers")
    
    # Timestamp for last update
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Render the HTML template with the data
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "gainers": gainers, 
            "losers": losers,
            "last_update": current_time
        },
        request=request
    )

@app.on_event("startup")
async def startup_event():
    logger.info("Stock Market Movers application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stock Market Movers application shutting down") 