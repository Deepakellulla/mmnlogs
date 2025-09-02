import logging
import os
import datetime
import pandas as pd
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI")

# --- Database ---
client = MongoClient(MONGO_URI)
db = client["ott_bot"]
users_collection = db["users"]
sales_collection = db["sales"]

# --- Start Command ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Store user in DB if not already
    if not users_collection.find_one({"user_id": user.id}):
        users_collection.insert_one(
            {
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "joined_at": datetime.datetime.utcnow(),
            }
        )
        # Notify admin
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👤 New user started bot:\n\nID: {user.id}\nUsername: @{user.username}",
            )

    keyboard = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")],
        [InlineKeyboardButton("🛒 My Purchases", callback_data="purchases")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to OTT Subscription Bot!\nChoose an option:", reply_markup=reply_markup
    )

# --- Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "dashboard":
        await query.edit_message_text("📊 Your Dashboard (coming soon...)")
    elif query.data == "purchases":
        await query.edit_message_text("🛒 Your Purchases (coming soon...)")

# --- Admin: Add Sale ---
async def add_sale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        amount = float(context.args[0])
        profit = float(context.args[1])
        customer_id = int(context.args[2])

        sales_collection.insert_one(
            {
                "customer_id": customer_id,
                "amount": amount,
                "profit": profit,
                "date": datetime.datetime.utcnow(),
            }
        )

        await update.message.reply_text("✅ Sale recorded successfully!")

    except Exception as e:
        await update.message.reply_text(
            "❌ Usage: /addsale <amount> <profit> <customer_id>"
        )
        logger.error(e)

# --- Daily Report to Admin ---
async def send_daily_report(application: Application):
    today = datetime.datetime.utcnow().date()
    sales = list(
        sales_collection.find(
            {"date": {"$gte": datetime.datetime(today.year, today.month, today.day)}}
        )
    )

    if not sales:
        text = "📊 Daily Report:\nNo sales recorded today."
    else:
        total_amount = sum(s["amount"] for s in sales)
        total_profit = sum(s["profit"] for s in sales)
        text = (
            f"📊 Daily Report\n\n"
            f"Total Sales: {len(sales)}\n"
            f"Total Amount: ₹{total_amount}\n"
            f"Total Profit: ₹{total_profit}"
        )

    if ADMIN_ID:
        await application.bot.send_message(chat_id=ADMIN_ID, text=text)

# --- Scheduler ---
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context.application)

# --- Main Function ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("addsale", add_sale))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Daily Report Job
    app.job_queue.run_daily(daily_job, time=datetime.time(hour=21, minute=0))  # 9 PM UTC

    # Start Bot
    app.run_polling()

if __name__ == "__main__":
    main()
