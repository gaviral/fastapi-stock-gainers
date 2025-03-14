from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import yfinance as yf
from datetime import datetime, timedelta
import logging, uuid, secrets, os, smtplib, hashlib, hmac
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from typing import Optional
from fastapi_users import schemas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm, HTTPBasic
from starlette.status import HTTP_401_UNAUTHORIZED
import json
from sqlalchemy.orm import Session

# Remove all relative imports
# from .database import SessionLocal, engine
# from . import models, schemas
# from .auth import current_active_user
# from .users import User

# Load environment variables
load_dotenv()

from app.db import create_db_and_tables, get_async_session, Stock, User, PasswordReset
from app.auth import fastapi_users, auth_backend, current_active_user, get_user_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("stocks.log")]
)
logger = logging.getLogger(__name__)

# Environment variables
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@stockmarket.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# User schemas
class UserRead(schemas.BaseUser[uuid.UUID]): pass
class UserCreate(schemas.BaseUserCreate): pass
class UserUpdate(schemas.BaseUserUpdate): pass

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

# Predefined stock tickers
TICKERS = [
  "AAPL", "MSFT", "GOOG", "AMZN", "META", "NFLX", "TSLA", "NVDA", 
  "JPM", "BAC", "SOXL", "SOXS", "AMD", "INTC", "DIS", "KO", "PEP", 
  "WMT", "COST", "V", "MA", "PYPL", "COIN"
]

# Add a request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    
    # Get client info
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referer = request.headers.get("referer", "direct")
    
    # Log request details
    logger.info(f"Request started: {request.method} {request.url.path} from {client_host} - Referer: {referer}")
    
    # Process the request
    response = await call_next(request)
    
    # Calculate duration
    duration = (datetime.now() - start_time).total_seconds()
    
    # Log response details including status code
    logger.info(f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration:.4f}s")
    
    return response

# Function to log user interactions
def log_user_interaction(action_type, action_details, user=None):
    user_id = str(user.id) if user else "anonymous"
    logger.info(f"User Interaction: {action_type} - User: {user_id} - Details: {action_details}")

# Function to format monetary values
def format_monetary_value(value):
    """
    Format monetary values to use M for millions and B for billions with 2 decimal places.
    
    Args:
        value: The numeric value to format
        
    Returns:
        Formatted string with M for millions, B for billions, limited to 2 decimal places
    """
    if value is None or value == "N/A":
        return "N/A"
    
    try:
        # Convert to float if it's not already
        value = float(value)
        
        # Format based on magnitude
        if value >= 1_000_000_000:  # Billions
            return f"${value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:  # Millions
            return f"${value / 1_000_000:.2f}M"
        else:
            return f"${value:.2f}"
    except (ValueError, TypeError):
        return str(value)

@app.get("/", response_class=HTMLResponse)
async def get_stock_data(
    request: Request,
    user = Depends(fastapi_users.current_user(optional=True)),
    session: AsyncSession = Depends(get_async_session)
):
    # Get user's custom symbols if logged in
    user_symbols = []
    if user:
        result = await session.execute(select(Stock.symbol).where(Stock.user_id == user.id))
        user_symbols = [row[0] for row in result.all()]
    
    # Combine predefined and user symbols
    all_symbols = list(set(TICKERS + user_symbols))
    
    # Fetch stock data
    results = []
    for symbol in all_symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or "regularMarketPrice" not in info:
                continue
                
            results.append({
                "symbol": symbol,
                "name": info.get("shortName") or info.get("longName") or symbol,
                "price": info.get("regularMarketPrice"),
                "change": info.get("regularMarketChange", 0),
                "percent_change": info.get("regularMarketChangePercent", 0),
                "volume": info.get("regularMarketVolume"),
                "market_cap": info.get("marketCap"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "prev_close": info.get("regularMarketPreviousClose", 0),
                "low": info.get("regularMarketDayLow", 0),
                "high": info.get("regularMarketDayHigh", 0)
            })
        except IndexError as e:
            logger.error(f"Index error processing {symbol}: {str(e)}")
            results.append({
                "symbol": symbol,
                "name": symbol,
                "price": 0,
                "change": 0,
                "percent_change": 0,
                "volume": 0,
                "market_cap": 0,
                "fifty_two_week_low": 0,
                "fifty_two_week_high": 0,
                "prev_close": 0,
                "low": 0,
                "high": 0
            })
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
    
    # Sort and separate gainers and losers
    results.sort(key=lambda x: x["percent_change"], reverse=True)
    gainers = [stock for stock in results if stock["percent_change"] >= 0]
    losers = [stock for stock in results if stock["percent_change"] < 0]
    
    # Filter out user's stocks for portfolio section
    user_stock_data = []
    if user and user_symbols:
        user_stock_data = [stock for stock in results if stock["symbol"] in user_symbols]
    
    # Format monetary values
    for stock_list in [gainers, losers, user_stock_data]:
        for stock in stock_list:
            stock["formatted_price"] = format_monetary_value(stock["price"])
            stock["formatted_market_cap"] = format_monetary_value(stock["market_cap"])
            stock["formatted_volume"] = format_monetary_value(stock["volume"]) if stock["volume"] else "N/A"
            stock["formatted_52_week_low"] = format_monetary_value(stock["fifty_two_week_low"])
            stock["formatted_52_week_high"] = format_monetary_value(stock["fifty_two_week_high"])
            stock["formatted_prev_close"] = format_monetary_value(stock["prev_close"])
            stock["formatted_low"] = format_monetary_value(stock["low"])
            stock["formatted_high"] = format_monetary_value(stock["high"])
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "gainers": gainers, 
            "losers": losers,
            "user_symbols": user_symbols,
            "user_stock_data": user_stock_data,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

@app.get("/login")
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    # Log logout attempt
    log_user_interaction("logout", "User initiated logout")
    # Don't show a separate logout page, just redirect to the home page
    # The frontend will handle the actual logout by calling the /auth/jwt/logout endpoint
    return RedirectResponse("/", status_code=303)

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request, user = Depends(fastapi_users.current_user(optional=True))):
    """About page with information about the application."""
    return templates.TemplateResponse("about.html", {"request": request, "user": user})

@app.post("/signup")
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_manager = Depends(get_user_manager)
):
    try:
        user = await user_manager.create(UserCreate(email=email, password=password, is_active=True))
        logger.info(f"User {email} registered successfully")
        # Log signup action
        log_user_interaction("signup", f"Email: {email}")
        return RedirectResponse(url="/login", status_code=303)
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": str(e)},
            status_code=400
        )

@app.post("/add-stock")
async def add_stock(
    symbol: str = Form(...),
    user = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    symbol = symbol.strip().upper()
    if not symbol:
        return RedirectResponse("/", status_code=400)
    
    result = await session.execute(
        select(Stock).where(Stock.user_id == user.id, Stock.symbol == symbol)
    )
    if not result.scalars().first():
        session.add(Stock(user_id=user.id, symbol=symbol))
        await session.commit()
        # Log stock addition
        log_user_interaction("add_stock", f"Symbol: {symbol}", user)
    
    return RedirectResponse("/", status_code=303)

@app.post("/remove-stock")
async def remove_stock(
    symbol: str = Form(...),
    user = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    symbol = symbol.strip().upper()
    result = await session.execute(
        select(Stock).where(Stock.user_id == user.id, Stock.symbol == symbol)
    )
    stock = result.scalars().first()
    if stock:
        await session.delete(stock)
        await session.commit()
        # Log stock removal
        log_user_interaction("remove_stock", f"Symbol: {symbol}", user)
    
    return RedirectResponse("/", status_code=303)

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
    user_manager = Depends(get_user_manager)
):
    logger.info(f"Password reset requested for email: {email}")
    
    # Log password reset request
    log_user_interaction("password_reset_request", f"Email: {email}")
    
    # Check if user exists
    user_query = await session.execute(select(User).where(User.email == email))
    user = user_query.scalars().first()
    
    if user:
        # Generate reset token
        token = secrets.token_urlsafe(32)
        
        # Save token to database
        reset_query = await session.execute(
            select(PasswordReset).where(PasswordReset.user_id == user.id)
        )
        existing_reset = reset_query.scalars().first()
        
        if existing_reset:
            existing_reset.token = token
            existing_reset.created_at = datetime.now()
        else:
            session.add(PasswordReset(user_id=user.id, token=token))
        
        await session.commit()
        
        # Create reset link
        reset_link = f"{BASE_URL}/reset-password?token={token}"
        
        # Email content
        subject = "Password Reset - Stock Market Tracker"
        html_content = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>You have requested to reset your password for the Stock Market Tracker application.</p>
            <p>Please click the link below to set a new password:</p>
            <p><a href="{reset_link}">Reset Your Password</a></p>
            <p>If you did not request this password reset, please ignore this email.</p>
            <p>This link will expire in 24 hours.</p>
            <p>Thank you,<br>Stock Market Tracker Team</p>
        </body>
        </html>
        """
        
        # Try to send email
        await send_email(email, subject, html_content)
    
    # Always return a success message even if email is not found for security
    return templates.TemplateResponse(
        "forgot_password.html", 
        {
            "request": request, 
            "success": "If an account exists with that email, password reset instructions have been sent. Please check your inbox."
        }
    )

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_async_session)
):
    # Verify token exists and is not expired
    reset_query = await session.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )
    reset = reset_query.scalars().first()
    
    if not reset:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "Invalid or expired token. Please request a new password reset."},
            status_code=400
        )
    
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})

@app.post("/reset-password", response_class=HTMLResponse)
async def reset_password_post(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
    user_manager = Depends(get_user_manager)
):
    # Verify passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "token": token, "error": "Passwords do not match."},
            status_code=400
        )
    
    # Verify token exists
    reset_query = await session.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )
    reset = reset_query.scalars().first()
    
    if not reset:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "Invalid or expired token. Please request a new password reset."},
            status_code=400
        )
    
    # Get user
    user_query = await session.execute(select(User).where(User.id == reset.user_id))
    user = user_query.scalars().first()
    
    if not user:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "User not found."},
            status_code=400
        )
    
    try:
        # Update password
        await user_manager.update(UserUpdate(password=password), user)
        
        # Delete reset token
        await session.delete(reset)
        await session.commit()
        
        # Log successful password reset
        log_user_interaction("password_reset_success", f"User ID: {reset.user_id}")
        
        # Redirect to login page with success message
        return RedirectResponse(url="/login?success=Password+reset+successful.+Please+log+in+with+your+new+password.", status_code=303)
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "token": token, "error": str(e)},
            status_code=400
        )

@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()
    logger.info("Application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")

# Function to send emails
async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    # Check if email credentials are available
    if not EMAIL_USER or not EMAIL_PASSWORD:
        logger.info(f"Email credentials not configured. Would send email to {to_email}")
        logger.info(f"Email content: {html_content}")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        message.attach(MIMEText(html_content, "html"))
        
        # Send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, message.as_string())
        
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

# Admin routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    # Log admin login attempt
    logger.info(f"Admin login attempt: {username}")
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin/dashboard", status_code=303)
        token = hashlib.sha256(f"{username}:{password}:{os.urandom(8).hex()}".encode()).hexdigest()
        
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=3600,
            path="/admin"
        )
        
        app.state.admin_sessions = getattr(app.state, "admin_sessions", set())
        app.state.admin_sessions.add(token)
        
        return response
    else:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401
        )

async def verify_admin(request: Request):
    admin_token = request.cookies.get("admin_session")
    admin_sessions = getattr(app.state, "admin_sessions", set())
    
    if not admin_token or admin_token not in admin_sessions:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    _: bool = Depends(verify_admin)
):
    # Log admin dashboard access
    logger.info("Admin accessed dashboard")
    
    # Query all users
    users_query = await session.execute(select(User))
    users = users_query.scalars().all()
    
    # Create raw user data for debugging
    raw_users = [
        {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified,
            "hashed_password": user.hashed_password,
        } for user in users
    ]
    
    # Query all stocks with user emails
    stocks_query = await session.execute(
        select(Stock, User.email).join(User, Stock.user_id == User.id)
    )
    stocks = [
        {
            "id": stock.id,
            "user_id": stock.user_id,
            "user_email": user_email,
            "symbol": stock.symbol
        } for stock, user_email in stocks_query.all()
    ]
    
    # Query all password resets with user emails
    resets_query = await session.execute(
        select(PasswordReset, User.email).join(User, PasswordReset.user_id == User.id)
    )
    
    password_resets = []
    for reset, user_email in resets_query.all():
        expiry_time = reset.created_at + timedelta(hours=24)
        password_resets.append({
            "id": reset.id,
            "user_id": reset.user_id,
            "user_email": user_email,
            "token": reset.token,
            "created_at": reset.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expiry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_expired": datetime.now() > expiry_time
        })
    
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "users": users,
            "raw_users": raw_users,
            "stocks": stocks,
            "password_resets": password_resets
        }
    )

@app.get("/admin/logout", response_class=HTMLResponse)
async def admin_logout(request: Request):
    # Log admin logout
    logger.info("Admin logged out")
    
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie(key="admin_session", path="/admin")
    
    return response

@app.get("/chart/{symbol}", response_class=HTMLResponse)
async def get_stock_chart(request: Request, symbol: str, period: str = "1y", user = Depends(fastapi_users.current_user(optional=True))):
    """Display detailed stock information for the given stock symbol."""
    # Log stock details access
    log_user_interaction("view_stock_details", f"Symbol: {symbol}, Period: {period}", user)
    try:
        # Validate period input
        valid_periods = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
        if period not in valid_periods:
            period = "1y"  # Default to 1 year if invalid period
        
        # Fetch historical stock data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        
        if hist.empty:
            # No data available for this symbol
            return templates.TemplateResponse(
                "error.html", 
                {"request": request, "error": f"No data available for symbol: {symbol}", "user": user, "current_year": datetime.now().year}
            )
        
        # Get company name if available
        company_name = ticker.info.get('shortName', symbol) if hasattr(ticker, 'info') else symbol
        
        # Calculate some basic statistics
        if not hist.empty:
            current_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            change = current_price - prev_close
            percent_change = (change / prev_close) * 100 if prev_close != 0 else 0
            
            # Get min and max prices for the period
            period_high = hist['High'].max()
            period_low = hist['Low'].min()
            
            # Get the latest volume
            latest_volume = hist['Volume'].iloc[-1]
            avg_volume = hist['Volume'].mean()
            
            # Calculate moving averages
            if len(hist) >= 50:
                ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            else:
                ma50 = None
                
            if len(hist) >= 200:
                ma200 = hist['Close'].rolling(window=200).mean().iloc[-1]
            else:
                ma200 = None
        else:
            current_price = prev_close = change = percent_change = period_high = period_low = latest_volume = avg_volume = ma50 = ma200 = None
        
        # Get additional stock information for the template
        try:
            stock_info = {
                "market_cap": ticker.info.get("marketCap", "N/A"),
                "pe_ratio": ticker.info.get("trailingPE", "N/A"),
                "dividend_yield": ticker.info.get("dividendYield", "N/A"),
                "avg_volume": ticker.info.get("averageVolume", "N/A"),
                "fifty_two_week_high": ticker.info.get("fiftyTwoWeekHigh", "N/A"),
                "fifty_two_week_low": ticker.info.get("fiftyTwoWeekLow", "N/A"),
                "current_price": current_price,
                "prev_close": prev_close,
                "change": change,
                "percent_change": percent_change,
                "period_high": period_high,
                "period_low": period_low,
                "latest_volume": latest_volume,
                "avg_volume_period": avg_volume,
                "ma50": ma50,
                "ma200": ma200
            }
            
            # Format monetary values
            stock_info["formatted_market_cap"] = format_monetary_value(stock_info["market_cap"])
            stock_info["formatted_current_price"] = format_monetary_value(stock_info["current_price"])
            stock_info["formatted_prev_close"] = format_monetary_value(stock_info["prev_close"])
            stock_info["formatted_period_high"] = format_monetary_value(stock_info["period_high"])
            stock_info["formatted_period_low"] = format_monetary_value(stock_info["period_low"])
            stock_info["formatted_fifty_two_week_high"] = format_monetary_value(stock_info["fifty_two_week_high"])
            stock_info["formatted_fifty_two_week_low"] = format_monetary_value(stock_info["fifty_two_week_low"])
            stock_info["formatted_latest_volume"] = format_monetary_value(stock_info["latest_volume"])
            stock_info["formatted_avg_volume"] = format_monetary_value(stock_info["avg_volume"])
            stock_info["formatted_ma50"] = format_monetary_value(stock_info["ma50"])
            stock_info["formatted_ma200"] = format_monetary_value(stock_info["ma200"])
            
        except:
            stock_info = {
                "market_cap": "N/A",
                "pe_ratio": "N/A",
                "dividend_yield": "N/A",
                "avg_volume": "N/A",
                "fifty_two_week_high": "N/A",
                "fifty_two_week_low": "N/A",
                "current_price": current_price,
                "prev_close": prev_close,
                "change": change,
                "percent_change": percent_change,
                "period_high": period_high,
                "period_low": period_low,
                "latest_volume": latest_volume,
                "avg_volume_period": avg_volume,
                "ma50": ma50,
                "ma200": ma200,
                "formatted_market_cap": "N/A",
                "formatted_current_price": format_monetary_value(current_price),
                "formatted_prev_close": format_monetary_value(prev_close),
                "formatted_period_high": format_monetary_value(period_high),
                "formatted_period_low": format_monetary_value(period_low),
                "formatted_fifty_two_week_high": format_monetary_value(period_high),
                "formatted_fifty_two_week_low": format_monetary_value(period_low),
                "formatted_latest_volume": format_monetary_value(latest_volume),
                "formatted_avg_volume": format_monetary_value(avg_volume),
                "formatted_ma50": format_monetary_value(ma50),
                "formatted_ma200": format_monetary_value(ma200)
            }
        
        return templates.TemplateResponse(
            "stock_details.html", 
            {
                "request": request, 
                "symbol": symbol,
                "company_name": company_name,
                "user": user,
                "current_year": datetime.now().year,
                "current_period": period,
                "stock_info": stock_info
            }
        )
    except Exception as e:
        # Log the error
        logging.error(f"Error retrieving stock details for {symbol}: {str(e)}")
        
        # Return error template
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "error": f"Error retrieving stock details: {str(e)}", "user": user, "current_year": datetime.now().year}
        )

@app.post("/log-action")
async def log_client_action(request: Request):
    """Endpoint to handle client-side logging from JavaScript."""
    try:
        log_data = await request.json()
        action = log_data.get("action", "unknown")
        details = log_data.get("details", "none")
        page = log_data.get("page", "unknown")
        timestamp = log_data.get("timestamp", datetime.now().isoformat())
        
        logger.info(f"Client Action: {action} - Page: {page} - Details: {details} - Time: {timestamp}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error logging client action: {str(e)}")
        return {"status": "error", "message": str(e)}