from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import yfinance as yf
from datetime import datetime
import logging
import uuid
from fastapi_users import schemas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm

from app.db import create_db_and_tables, get_async_session, Stock, User
from app.auth import fastapi_users, auth_backend, current_active_user, get_user_manager

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

# Define Pydantic schemas for user creation and reading
class UserRead(schemas.BaseUser[uuid.UUID]):
    pass

class UserCreate(schemas.BaseUserCreate):
    pass

# Include authentication routers
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"]
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"]
)

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
async def get_stock_data(
    request: Request,
    user = Depends(fastapi_users.current_user(optional=True)),
    session: AsyncSession = Depends(get_async_session)
):
    logger.info("Processing request for stock market movers")
    
    # Get user's custom symbols if logged in
    user_symbols = []
    if user is not None:
        result = await session.execute(
            select(Stock.symbol).where(Stock.user_id == user.id)
        )
        user_symbols = [row[0] for row in result.all()]
    
    # Combine predefined and user symbols, removing duplicates
    all_symbols = list(set(TICKERS + user_symbols))
    
    # Fetch current stock data for each ticker
    results = []
    for symbol in all_symbols:
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
            "user": user,
            "gainers": gainers, 
            "losers": losers,
            "user_symbols": user_symbols,
            "last_update": current_time
        }
    )

@app.get("/login")
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_manager = Depends(get_user_manager)
):
    try:
        await user_manager.create(UserCreate(email=email, password=password, is_active=True))
    except Exception as e:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": str(e)},
            status_code=400
        )
    return RedirectResponse("/login", status_code=303)

@app.post("/add-stock")
async def add_stock(
    symbol: str = Form(...),
    user = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    symbol = symbol.strip().upper()
    if not symbol:
        return RedirectResponse("/", status_code=400)
    
    # Check if the stock already exists for this user
    result = await session.execute(
        select(Stock).where(Stock.user_id == user.id, Stock.symbol == symbol)
    )
    existing_stock = result.scalars().first()
    
    if not existing_stock:
        new_stock = Stock(user_id=user.id, symbol=symbol)
        session.add(new_stock)
        await session.commit()
    
    return RedirectResponse("/", status_code=303)

@app.post("/remove-stock")
async def remove_stock(
    symbol: str = Form(...),
    user = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    symbol = symbol.strip().upper()
    
    # Find the stock for this user
    result = await session.execute(
        select(Stock).where(Stock.user_id == user.id, Stock.symbol == symbol)
    )
    stock = result.scalars().first()
    
    if stock:
        await session.delete(stock)
        await session.commit()
    
    return RedirectResponse("/", status_code=303)

@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()
    logger.info("Stock Market Movers application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stock Market Movers application shutting down") 