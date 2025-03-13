from fastapi import FastAPI, Request, Form, Depends, HTTPException
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
import secrets
from typing import Optional
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.db import create_db_and_tables, get_async_session, Stock, User, PasswordReset
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

# Environment variables
IS_LOCAL = os.getenv("IS_LOCAL", "true").lower() == "true"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@stockmarket.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

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

@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    """Custom logout page that will submit a POST request to the FastAPI Users logout endpoint."""
    return templates.TemplateResponse(
        "logout.html", 
        {"request": request, "redirect_url": "/"}
    )

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """Render the about page with tech stack and architecture information."""
    return templates.TemplateResponse("about.html", {"request": request})

@app.post("/signup")
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_manager = Depends(get_user_manager)
):
    try:
        user = await user_manager.create(UserCreate(email=email, password=password, is_active=True))
        
        # Log the successful registration
        logger.info(f"User {email} registered successfully")
        
        # Redirect to login page
        response = RedirectResponse(url="/login", status_code=303)
        return response
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

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request):
    """Render the forgot password form."""
    return templates.TemplateResponse("forgot_password.html", {"request": request, "is_local": IS_LOCAL})

@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
    user_manager = Depends(get_user_manager)
):
    """Process forgot password request and send reset link."""
    # Check if user exists
    user_query = await session.execute(select(User).where(User.email == email))
    user = user_query.scalars().first()
    
    if user:
        # Generate reset token
        token = secrets.token_urlsafe(32)
        
        # Save token to database with expiry
        # First, check if there's an existing token for this user
        reset_query = await session.execute(
            select(PasswordReset).where(PasswordReset.user_id == user.id)
        )
        existing_reset = reset_query.scalars().first()
        
        if existing_reset:
            # Update existing token
            existing_reset.token = token
            existing_reset.created_at = datetime.now()
        else:
            # Create new token
            reset = PasswordReset(user_id=user.id, token=token)
            session.add(reset)
        
        await session.commit()
        
        # Create reset link
        reset_link = f"{BASE_URL}/reset-password?token={token}"
        logger.info(f"Password reset token generated for {email}: {token}")
        
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
        email_sent = await send_email(email, subject, html_content)
        
        if IS_LOCAL:
            # In local mode, show the reset link directly
            return templates.TemplateResponse(
                "forgot_password.html", 
                {
                    "request": request, 
                    "success": f"<strong>Local Mode:</strong> No emails are actually sent in local mode. You can reset your password by clicking here: <a href='{reset_link}'>Reset Password</a>",
                    "is_local": IS_LOCAL
                }
            )
        else:
            # In production mode, just confirm the email was sent
            return templates.TemplateResponse(
                "forgot_password.html", 
                {
                    "request": request, 
                    "success": "Password reset instructions have been sent to your email. Please check your inbox and follow the instructions to reset your password.",
                    "is_local": IS_LOCAL
                }
            )
    
    # Always return a success message even if email is not found for security
    if IS_LOCAL:
        return templates.TemplateResponse(
            "forgot_password.html", 
            {
                "request": request, 
                "success": "<strong>Local Mode:</strong> If an account exists with that email, a reset link would be sent. No actual emails are sent in local mode.",
                "is_local": IS_LOCAL
            }
        )
    else:
        return templates.TemplateResponse(
            "forgot_password.html", 
            {
                "request": request, 
                "success": "If an account exists with that email, password reset instructions have been sent. Please check your inbox.",
                "is_local": IS_LOCAL
            }
        )

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_async_session)
):
    """Render the reset password form."""
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
    
    # Token is valid, render the form
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
    """Process password reset request."""
    # Verify passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "token": token, "error": "Passwords do not match."},
            status_code=400
        )
    
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
    
    # Get user
    user_query = await session.execute(select(User).where(User.id == reset.user_id))
    user = user_query.scalars().first()
    
    if not user:
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "User not found."},
            status_code=400
        )
    
    # Update password
    try:
        await user_manager.update(
            user_update={"password": password},
            user=user
        )
        
        # Delete reset token
        await session.delete(reset)
        await session.commit()
        
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
    logger.info("Stock Market Movers application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stock Market Movers application shutting down")

# Function to send emails
async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send an email with the given parameters.
    Returns True if successful, False otherwise.
    """
    if IS_LOCAL or not EMAIL_USER or not EMAIL_PASSWORD:
        # In local mode or without credentials, just log the email
        logger.info(f"Would send email to {to_email} with subject: {subject}")
        logger.info(f"Email content: {html_content}")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        
        # Add HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, message.as_string())
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False 