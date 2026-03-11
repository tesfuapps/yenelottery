# Yene Lottery Bot

An automated, transparent, and provably fair lottery platform on Telegram. Features include a referral system, manual payment verification (CBE/Telebirr) with OCR support, and an admin dashboard.

## 🚀 Features

- **Transparency**: Provably fair draws using cryptographic methods.
- **Admin Bridge**: Manual approval/rejection of payments with automatic transaction ID extraction via OCR.
- **Member Space**: Interactive menus, ticket tracking, and draw history.
- **Referral System**: Grow the platform with unique referral links and trackable points.
- **Bot Menu**: Permanent Telegram command menu for ease of use.

## 🛠 Tech Stack

- **Language**: Python 3.10+
- **Library**: `aiogram` (v3+)
- **Database**: SQLite with `aiosqlite`
- **OCR**: `pytesseract` (Tesseract OCR Engine)
- **Environment**: Window/Linux compatible

## 📦 Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd "Yene Lottery"
   ```

2. **Set up virtual environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Tesseract OCR**:
   Download and install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (required for payment verification).

5. **Configure environment**:
   Copy `.env.example` to `.env` and fill in your details:
   - `BOT_TOKEN`: From @BotFather
   - `ADMIN_GROUP_ID`: Your Telegram ID or Admin group ID

## 🚦 Usage

Start the bot:
```bash
python bot.py
```

## 📜 License

This project is licensed under the MIT License.
