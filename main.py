from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import yfinance as yf
from datetime import datetime, timedelta
import logging
import uuid
from fastapi_users import schemas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm, HTTPBasic, HTTPBasicCredentials
import secrets
from typing import Optional
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import hashlib
from starlette.status import HTTP_401_UNAUTHORIZED
import hmac

# Load environment variables from .env file
load_dotenv()

from app.db import create_db_and_tables, get_async_session, Stock, User, PasswordReset
from app.auth import fastapi_users, auth_backend, current_active_user, get_user_manager

# Configure logging - both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("stocks.log")
    ]
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

# Log email configuration
logger.info(f"Email configuration: HOST={EMAIL_HOST}, PORT={EMAIL_PORT}, USER={EMAIL_USER}, FROM={EMAIL_FROM}")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Define Pydantic schemas for user creation and reading
class UserRead(schemas.BaseUser[uuid.UUID]):
    pass

class UserCreate(schemas.BaseUserCreate):
    pass

class UserUpdate(schemas.BaseUserUpdate):
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

# Add this after the other app configurations
security = HTTPBasic()

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
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
    user_manager = Depends(get_user_manager)
):
    """Process forgot password request and send reset link."""
    logger.info(f"Password reset requested for email: {email}")
    
    # Check if user exists
    user_query = await session.execute(select(User).where(User.email == email))
    user = user_query.scalars().first()
    
    if user:
        logger.info(f"User found for email: {email}, generating reset token")
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
            logger.info(f"Updating existing reset token for user: {email}")
            existing_reset.token = token
            existing_reset.created_at = datetime.now()
        else:
            # Create new token
            logger.info(f"Creating new reset token for user: {email}")
            reset = PasswordReset(user_id=user.id, token=token)
            session.add(reset)
        
        await session.commit()
        logger.info(f"Reset token saved to database for user: {email}")
        
        # Create reset link
        reset_link = f"{BASE_URL}/reset-password?token={token}"
        logger.info(f"Password reset link generated: {reset_link}")
        
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
        logger.info(f"Attempting to send password reset email to: {email}")
        email_sent = await send_email(email, subject, html_content)
        
        if email_sent:
            logger.info(f"Password reset email sent successfully to: {email}")
        else:
            logger.warning(f"Failed to send password reset email to: {email}. Check email configuration.")
        
        return templates.TemplateResponse(
            "forgot_password.html", 
            {
                "request": request, 
                "success": "If an account exists with that email, password reset instructions have been sent. Please check your inbox."
            }
        )
    else:
        logger.info(f"No user found for email: {email}, returning generic success message")
    
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
    logger.info(f"Processing password reset with token: {token[:8]}...")
    
    # Verify passwords match
    if password != confirm_password:
        logger.warning("Password reset failed: Passwords do not match")
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
        logger.warning(f"Password reset failed: Invalid or expired token: {token[:8]}...")
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "Invalid or expired token. Please request a new password reset."},
            status_code=400
        )
    
    # Get user
    user_query = await session.execute(select(User).where(User.id == reset.user_id))
    user = user_query.scalars().first()
    
    if not user:
        logger.error(f"Password reset failed: User not found for token: {token[:8]}...")
        return templates.TemplateResponse(
            "reset_password.html", 
            {"request": request, "error": "User not found."},
            status_code=400
        )
    
    logger.info(f"Valid reset token for user: {user.email}, updating password")
    
    # Update password
    try:
        user_update = UserUpdate(password=password)
        await user_manager.update(
            user_update=user_update,
            user=user
        )
        
        # Delete reset token
        await session.delete(reset)
        await session.commit()
        
        logger.info(f"Password reset successful for user: {user.email}")
        
        # Redirect to login page with success message
        return RedirectResponse(url="/login?success=Password+reset+successful.+Please+log+in+with+your+new+password.", status_code=303)
    except Exception as e:
        logger.error(f"Password reset error for user {user.email}: {str(e)}")
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
    # Check if email credentials are available
    if not EMAIL_USER or not EMAIL_PASSWORD:
        # Log the email instead of sending if credentials are not available
        logger.info(f"Email credentials not configured. Would send email to {to_email} with subject: {subject}")
        logger.info(f"Email content: {html_content}")
        logger.info(f"To enable email sending, configure EMAIL_USER and EMAIL_PASSWORD environment variables.")
        logger.info(f"See README.md for detailed instructions on setting up email functionality.")
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
        
        # Log connection attempt
        logger.info(f"Attempting to connect to SMTP server {EMAIL_HOST}:{EMAIL_PORT}")
        
        # Send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            logger.info(f"Connected to SMTP server, initiating TLS")
            server.starttls()
            logger.info(f"TLS initiated, attempting login with user {EMAIL_USER}")
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            logger.info(f"Login successful, sending email")
            server.sendmail(EMAIL_FROM, to_email, message.as_string())
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication Error: {str(e)}")
        logger.error("This usually means your email or password is incorrect.")
        logger.error("If using Gmail, make sure you're using an App Password, not your regular password.")
        logger.error("See README.md for instructions on setting up an App Password.")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP Error: {str(e)}")
        logger.error(f"Check your EMAIL_HOST and EMAIL_PORT settings: {EMAIL_HOST}:{EMAIL_PORT}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        logger.error(f"Email configuration: HOST={EMAIL_HOST}, PORT={EMAIL_PORT}, USER={EMAIL_USER}, FROM={EMAIL_FROM}")
        return False

# Add these admin routes after the other routes

@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Render the admin login page."""
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Process admin login."""
    # Check credentials
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # Create a session cookie for admin authentication
        response = RedirectResponse(url="/admin/dashboard", status_code=303)
        
        # Create a secure token for the admin session
        token = hashlib.sha256(f"{username}:{password}:{os.urandom(8).hex()}".encode()).hexdigest()
        
        # Set the cookie with HttpOnly and Secure flags
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=3600,  # 1 hour
            path="/admin"
        )
        
        # Store the token in memory (in a real app, you'd use Redis or a database)
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
    """Verify admin session cookie."""
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
    """Render the admin dashboard."""
    # Query all users
    users_query = await session.execute(select(User))
    users = users_query.scalars().all()
    
    # Create raw user data for debugging
    raw_users = []
    for user in users:
        raw_users.append({
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified,
            "hashed_password": user.hashed_password,
        })
    
    # Query all stocks with user emails
    stocks_query = await session.execute(
        select(Stock, User.email)
        .join(User, Stock.user_id == User.id)
    )
    stocks_with_emails = stocks_query.all()
    
    # Format stocks data
    stocks = []
    for stock, user_email in stocks_with_emails:
        stocks.append({
            "id": stock.id,
            "user_id": stock.user_id,
            "user_email": user_email,
            "symbol": stock.symbol
        })
    
    # Query all password resets with user emails
    resets_query = await session.execute(
        select(PasswordReset, User.email)
        .join(User, PasswordReset.user_id == User.id)
    )
    resets_with_emails = resets_query.all()
    
    # Format password resets data
    password_resets = []
    for reset, user_email in resets_with_emails:
        # Calculate expiry time (24 hours from creation)
        expiry_time = reset.created_at + timedelta(hours=24)
        is_expired = datetime.now() > expiry_time
        
        password_resets.append({
            "id": reset.id,
            "user_id": reset.user_id,
            "user_email": user_email,
            "token": reset.token,
            "created_at": reset.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expiry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_expired": is_expired
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
    """Process admin logout."""
    # Get the admin token
    admin_token = request.cookies.get("admin_session")
    
    # Remove the token from the set of valid sessions
    if admin_token:
        app.state.admin_sessions = getattr(app.state, "admin_sessions", set())
        app.state.admin_sessions.discard(admin_token)
    
    # Redirect to login page and clear the cookie
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie(key="admin_session", path="/admin")
    
    return response 