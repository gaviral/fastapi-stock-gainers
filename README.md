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

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
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

## Environment Variables

- `DATABASE_URL` - Database connection string (default: `sqlite+aiosqlite:///./test.db`)
- `SECRET_KEY` - Secret key for JWT tokens (default: `CHANGEME`)
- `IS_LOCAL` - Set to "true" for local development mode, "false" for production (default: `true`)
- `EMAIL_HOST` - SMTP server for sending emails (default: `smtp.gmail.com`)
- `EMAIL_PORT` - SMTP port (default: `587`)
- `EMAIL_USER` - Email username/address for sending password reset emails
- `EMAIL_PASSWORD` - Email password or app password
- `EMAIL_FROM` - From address for sent emails (default: `noreply@stockmarket.com`)
- `BASE_URL` - Base URL for the application, used in email links (default: `http://localhost:8000`)

## Password Reset Functionality

In local development mode (`IS_LOCAL=true`), password reset links are displayed directly in the browser for testing purposes. No actual emails are sent.

In production mode (`IS_LOCAL=false`), the application will attempt to send password reset emails using the configured SMTP settings. Make sure to set up the email environment variables properly for this to work.

## License

MIT
