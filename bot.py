import os
import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in Render
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # your Telegram ID
MONGO_URI = os.getenv("MONGO_URI")  # your MongoDB Atlas URI
DB_NAME = "ott_reseller_bot"

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== DB ==================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]
sales_col = db["sales"]

# ================== HANDLERS ==================
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one(
            {"user_id": user_id, "first_name": first_name, "joined_at": datetime.now()}
        )
        # Notify admin
        await context.bot.send_message(
            ADMIN_ID, f"👤 New user started the bot:\nID: {user_id}\nName: {first_name}"
        )

    keyboard = [
        [InlineKeyboardButton("📦 My Subscriptions", callback_data="subs")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👋 Welcome {first_name}!\nUse the buttons below to navigate.", reply_markup=reply_markup
    )


async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "subs":
        await query.edit_message_text("📦 You currently have no active subscriptions.")
    elif query.data == "stats":
        total_sales = sales_col.count_documents({})
        await query.edit_message_text(f"📊 Total sales recorded: {total_sales}")


async def add_sale(update: Update, context: CallbackContext):
    """Admin manually adds a sale: /addsale amount profit days username"""
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        amount = float(context.args[0])
        profit = float(context.args[1])
        days = int(context.args[2])
        username = context.args[3]

        expiry = datetime.now() + timedelta(days=days)
        sales_col.insert_one(
            {
                "amount": amount,
                "profit": profit,
                "expiry": expiry,
                "username": username,
                "date": datetime.now(),
            }
        )
        await update.message.reply_text(
            f"✅ Sale added!\n💰 Amount: {amount}\n📈 Profit: {profit}\n📅 Expires: {expiry.date()}"
        )
    except Exception as e:
        await update.message.reply_text("❌ Usage: /addsale amount profit days username")
        logger.error(e)


async def report(update: Update, context: CallbackContext):
    """Manual report command"""
    if update.effective_user.id != ADMIN_ID:
        return
    await send_report(context)


async def send_report(context: CallbackContext):
    """Generate and send report to admin"""
    sales = list(sales_col.find({}))
    total_sales = sum(s["amount"] for s in sales)
    total_profit = sum(s["profit"] for s in sales)
    count = len(sales)

    msg = (
        "📊 Daily Report\n\n"
        f"🛒 Total Sales: {count}\n"
        f"💰 Revenue: {total_sales}\n"
        f"📈 Profit: {total_profit}\n"
        f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}"
    )

    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)


async def broadcast(update: Update, context: CallbackContext):
    """Broadcast a message to all users"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /broadcast your_message")
        return

    text = " ".join(context.args)
    users = users_col.find({})
    count = 0
    for user in users:
        try:
            await context.bot.send_message(user["user_id"], text)
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")


# ================== SCHEDULER ==================
def schedule_reports(app: Application):
    def run():
        while True:
            schedule.run_pending()
            time.sleep(60)

    async def job():
        await send_report(app.bot)

    schedule.every().day.at("00:00").do(lambda: app.create_task(job()))
    threading.Thread(target=run, daemon=True).start()


# ================== MAIN ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsale", add_sale))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))

    schedule_reports(app)

    app.run_polling()


if __name__ == "__main__":
    main()
