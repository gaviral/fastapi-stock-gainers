# FastAPI Stock Gainers

A web application that displays real-time stock market data, including top gainers and losers. Built with FastAPI, SQLAlchemy, and Yahoo Finance API.

## Live Demo

Visit: [https://fastapi-stock-gainers.onrender.com](https://fastapi-stock-gainers.onrender.com)

## Features

- Real-time stock market data from Yahoo Finance
- User authentication system
- Ability to track custom stock symbols
- Automatic sorting by percentage change
- Color-coded display (green for gains, red for losses)
- Responsive UI with Bootstrap
- Auto-refresh to keep data updated

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
- Once logged in, you can add custom stock symbols to track

## API Endpoints

- `/` - Main page with stock data
- `/login` - Login page
- `/signup` - Signup page
- `/auth/jwt/login` - JWT login endpoint
- `/auth/jwt/logout` - JWT logout endpoint
- `/add-stock` - Add a custom stock symbol (POST)
- `/remove-stock` - Remove a custom stock symbol (POST)

## Environment Variables

- `DATABASE_URL` - Database connection string (default: `sqlite+aiosqlite:///./test.db`)
- `SECRET_KEY` - Secret key for JWT tokens (default: `CHANGEME`)

## License

MIT
