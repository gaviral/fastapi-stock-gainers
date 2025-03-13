# FastAPI Stock Gainers

A web application that displays real-time stock market data, including top gainers and losers. Built with FastAPI, SQLAlchemy, and Yahoo Finance API.

## Live Demo

Visit: [https://fastapi-stock-gainers.onrender.com](https://fastapi-stock-gainers.onrender.com)

## Features

- Real-time stock market data from Yahoo Finance
- User authentication system with password recovery
- Password visibility toggle for improved user experience
- Ability to track custom stock symbols
- Automatic sorting by percentage change
- Color-coded display (green for gains, red for losses)
- Responsive UI with Bootstrap
- Auto-refresh every 120 seconds to keep data updated
- Admin dashboard for database management

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Copy `.env.example` to `.env` and configure your environment variables:
```bash
cp .env.example .env
```

## Usage

1. Start the application:
```bash
uvicorn main:app --reload
```

2. Open your browser and navigate to `http://localhost:8000`

## User Authentication

- Register a new account at `/signup`
- Login at `/login`
- Reset forgotten passwords at `/forgot-password`
- Once logged in, you can add custom stock symbols to track

## Admin Interface

The application includes an admin interface to manage users, stocks, and password reset requests:

- Access the admin login page at `/admin`
- Default credentials: username `admin`, password `changeme` (change these in production)
- The admin dashboard provides:
  - User management
  - Stock tracking overview
  - Password reset request monitoring
  - Data filtering and search capabilities

For security reasons, make sure to change the default admin credentials by setting the `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables.

## API Endpoints

- `/` - Main page with stock data
- `/login` - Login page
- `/signup` - Signup page
- `/forgot-password` - Forgot password page
- `/reset-password` - Reset password page with token validation
- `/auth/jwt/login` - JWT login endpoint
- `/auth/jwt/logout` - JWT logout endpoint
- `/add-stock` - Add a custom stock symbol (POST)
- `/remove-stock` - Remove a custom stock symbol (POST)
- `/admin` - Admin login page
- `/admin/login` - Process admin login (POST)
- `/admin/dashboard` - Admin dashboard with database management
- `/admin/logout` - Admin logout

## Environment Variables

- `DATABASE_URL` - Database connection string (default: `sqlite+aiosqlite:///./test.db`)
- `SECRET_KEY` - Secret key for JWT tokens (default: `CHANGEME`)
- `EMAIL_HOST` - SMTP server for sending emails (default: `smtp.gmail.com`)
- `EMAIL_PORT` - SMTP port (default: `587`)
- `EMAIL_USER` - Email username/address for sending password reset emails
- `EMAIL_PASSWORD` - Email password or app password
- `EMAIL_FROM` - From address for sent emails (default: `noreply@stockmarket.com`)
- `BASE_URL` - Base URL for the application, used in email links (default: `http://localhost:8000`)
- `ADMIN_USERNAME` - Username for admin login (default: `admin`)
- `ADMIN_PASSWORD` - Password for admin login (default: `changeme`)

## Password Reset Functionality

The password reset system sends emails using the configured SMTP settings. For this to work, make sure to set up the email environment variables properly.

### Setting Up Email for Password Reset

#### For Gmail Users:

1. Use your Gmail address for `EMAIL_USER`
2. For `EMAIL_PASSWORD`, you need to use an "App Password" (not your regular Gmail password):
   - Go to your Google Account settings: [https://myaccount.google.com/](https://myaccount.google.com/)
   - Enable 2-Step Verification if not already enabled
   - Go to "Security" > "App passwords"
   - Select "Mail" as the app and "Other" as the device (name it "Stock Market App")
   - Copy the generated 16-character password and use it for `EMAIL_PASSWORD`

#### For Other Email Providers:

1. Use your email address for `EMAIL_USER`
2. Use your email password for `EMAIL_PASSWORD`
3. Update `EMAIL_HOST` and `EMAIL_PORT` according to your provider's SMTP settings

#### For Deployment on Render.com:

1. Go to your service dashboard on Render
2. Navigate to "Environment" tab
3. Add all the required environment variables:
   - `EMAIL_HOST`
   - `EMAIL_PORT`
   - `EMAIL_USER`
   - `EMAIL_PASSWORD`
   - `EMAIL_FROM`
   - `BASE_URL` (set to your Render deployment URL)
4. Click "Save Changes" and wait for your service to redeploy

If email credentials are not configured, the system will log the password reset links instead of sending emails, which is useful for development and testing.

## License

MIT
