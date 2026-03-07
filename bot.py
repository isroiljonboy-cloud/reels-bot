import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN    = os.environ["BOT_TOKEN"]
TZ       = ZoneInfo("Asia/Tashkent")
DB_FILE  = "data.json"

# Conversation states
ASK_TYPE, ASK_PLATFORM, ASK_SCRIPT, ASK_DATE = range(4)

# ── DB helpers ────────────────────────────────────────────────────────────────
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user(db, uid):
    uid = str(uid)
    if uid not in db:
        db[uid] = {"contents": []}
    return db[uid]

def now_tz():
    return datetime.now(TZ)

def fmt_dt(iso_str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    days = ["Dush","Sesh","Chor","Pay","Juma","Shan","Yak"]
    months = ["Yan","Feb","Mar","Apr","May","Iyun","Iyul","Avg","Sen","Okt","Noy","Dek"]
    return f"{days[dt.weekday()]}, {dt.day} {months[dt.month-1]} • {dt.strftime('%H:%M')}"

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Salom! Reels Planner botga xush kelibsiz.*\n\n"
        "Bu bot sizning Instagram/Telegram kontent rejangizni boshqaradi.\n\n"
        "📌 *Buyruqlar:*\n"
        "/add — Yangi kontent qo'shish\n"
        "/list — Barcha kontentlar\n"
        "/week — Haftalik reja\n"
        "/help — Yordam\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /add conversation ─────────────────────────────────────────────────────────
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Reels", callback_data="type_reels"),
         InlineKeyboardButton("📸 Story", callback_data="type_story")]
    ])
    await update.message.reply_text("*Kontent turini tanlang:*", reply_markup=kb, parse_mode="Markdown")
    return ASK_TYPE

async def got_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["type"] = q.data.replace("type_", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Instagram", callback_data="plat_Instagram"),
         InlineKeyboardButton("✈️ Telegram", callback_data="plat_Telegram")],
        [InlineKeyboardButton("🌐 Ikkalasi", callback_data="plat_Ikkalasi")]
    ])
    await q.edit_message_text("*Platforma:*", reply_markup=kb, parse_mode="Markdown")
    return ASK_PLATFORM

async def got_platform(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["platform"] = q.data.replace("plat_", "")
    await q.edit_message_text(
        "✍️ *Ssenariy matnini yuboring:*\n\n"
        "_Hook, asosiy qism, call to action — hammasini yozing._",
        parse_mode="Markdown"
    )
    return ASK_SCRIPT

async def got_script(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["script"] = update.message.text
    await update.message.reply_text(
        "📅 *Chiqarish vaqtini yuboring:*\n\n"
        "Format: `KK.OO.YYYY SS:MM`\n"
        "Misol: `15.03.2026 18:00`",
        parse_mode="Markdown"
    )
    return ASK_DATE

async def got_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
    except ValueError:
        await update.message.reply_text(
            "❌ Format noto'g'ri. Qaytadan yuboring:\n`15.03.2026 18:00`",
            parse_mode="Markdown"
        )
        return ASK_DATE

    db = load_db()
    user = get_user(db, update.effective_user.id)
    item = {
        "id": int(datetime.now().timestamp() * 1000),
        "type": ctx.user_data["type"],
        "platform": ctx.user_data["platform"],
        "script": ctx.user_data["script"],
        "date": dt.isoformat(),
        "published": False,
        "created_at": now_tz().isoformat()
    }
    user["contents"].append(item)
    save_db(db)

    emoji = "🎬" if item["type"] == "reels" else "📸"
    await update.message.reply_text(
        f"✅ *Saqlandi!*\n\n"
        f"{emoji} {item['type'].capitalize()} • {item['platform']}\n"
        f"📅 {fmt_dt(item['date'])}\n\n"
        f"Vaqti kelganda sizga eslatma yuboriladi.",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.")
    ctx.user_data.clear()
    return ConversationHandler.END

# ── /list ─────────────────────────────────────────────────────────────────────
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    user = get_user(db, update.effective_user.id)
    contents = user["contents"]

    if not contents:
        await update.message.reply_text("📭 Hali kontent yo'q. /add bilan qo'shing.")
        return

    # Sort by date
    contents.sort(key=lambda x: x["date"])
    pending   = [c for c in contents if not c["published"]]
    published = [c for c in contents if c["published"]]

    now = now_tz()

    text = f"📋 *Barcha kontentlar* ({len(contents)} ta)\n\n"

    if pending:
        text += "⏳ *Kutmoqda:*\n"
        for c in pending:
            dt = datetime.fromisoformat(c["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            overdue = dt <= now
            emoji = "🎬" if c["type"] == "reels" else "📸"
            flag  = " ⚠️" if overdue else ""
            short = c["script"][:60] + "..." if len(c["script"]) > 60 else c["script"]
            text += f"\n{emoji} *{c['type'].capitalize()}* • {c['platform']}{flag}\n"
            text += f"📅 {fmt_dt(c['date'])}\n"
            text += f"_{short}_\n"

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Chiqdi", callback_data=f"pub_{c['id']}"),
                InlineKeyboardButton("🗑 O'chir", callback_data=f"del_{c['id']}")
            ]])
            await update.message.reply_text(
                f"{emoji} *{c['type'].capitalize()}* • {c['platform']}{flag}\n"
                f"📅 {fmt_dt(c['date'])}\n\n"
                f"{c['script'][:300]}{'...' if len(c['script'])>300 else ''}",
                reply_markup=kb,
                parse_mode="Markdown"
            )

    if published:
        text = f"\n✅ *Chiqarildi:* {len(published)} ta"
        await update.message.reply_text(text, parse_mode="Markdown")

# ── /week ─────────────────────────────────────────────────────────────────────
async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    user = get_user(db, update.effective_user.id)
    now  = now_tz()
    week_end = now + timedelta(days=7)

    week = [
        c for c in user["contents"]
        if not c["published"] and
        now <= datetime.fromisoformat(c["date"]).replace(tzinfo=TZ) <= week_end
    ]
    week.sort(key=lambda x: x["date"])

    if not week:
        await update.message.reply_text(
            "📭 Keyingi 7 kunda rejalashtirilgan kontent yo'q.\n/add bilan qo'shing."
        )
        return

    text = f"📅 *Haftalik reja* ({len(week)} ta kontent)\n\n"
    days_uz = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

    current_day = None
    for c in week:
        dt = datetime.fromisoformat(c["date"]).replace(tzinfo=TZ)
        day_name = days_uz[dt.weekday()]
        if day_name != current_day:
            current_day = day_name
            text += f"\n📌 *{day_name}*\n"
        emoji = "🎬" if c["type"] == "reels" else "📸"
        short = c["script"][:50] + "..." if len(c["script"]) > 50 else c["script"]
        text += f"  {emoji} {dt.strftime('%H:%M')} • {c['platform']}\n  _{short}_\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ── Callbacks (publish / delete) ──────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    db   = load_db()
    user = get_user(db, update.effective_user.id)

    if data.startswith("pub_"):
        cid = int(data.replace("pub_", ""))
        for c in user["contents"]:
            if c["id"] == cid:
                c["published"] = True
                save_db(db)
                await q.edit_message_reply_markup(reply_markup=None)
                await q.message.reply_text("🎉 *Chiqdi deb belgilandi!*", parse_mode="Markdown")
                return

    elif data.startswith("del_"):
        cid = int(data.replace("del_", ""))
        user["contents"] = [c for c in user["contents"] if c["id"] != cid]
        save_db(db)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("🗑 O'chirildi.")

# ── Reminder job ──────────────────────────────────────────────────────────────
async def send_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    now = now_tz()

    for uid, user in db.items():
        for c in user["contents"]:
            if c["published"]:
                continue
            dt = datetime.fromisoformat(c["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)

            diff_minutes = (dt - now).total_seconds() / 60

            # 60 daqiqa oldin
            if 58 <= diff_minutes <= 62 and not c.get("reminded_1h"):
                emoji = "🎬" if c["type"] == "reels" else "📸"
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"⏰ *1 soatdan keyin chiqarish vaqti!*\n\n"
                         f"{emoji} {c['type'].capitalize()} • {c['platform']}\n"
                         f"📅 {fmt_dt(c['date'])}\n\n"
                         f"_{c['script'][:200]}_",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Chiqdi", callback_data=f"pub_{c['id']}")
                    ]])
                )
                c["reminded_1h"] = True

            # Aynan vaqtida
            elif -2 <= diff_minutes <= 2 and not c.get("reminded_now"):
                emoji = "🎬" if c["type"] == "reels" else "📸"
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"🚨 *HOZIR CHIQARISH VAQTI!*\n\n"
                         f"{emoji} {c['type'].capitalize()} • {c['platform']}\n\n"
                         f"_{c['script'][:300]}_",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Chiqdi", callback_data=f"pub_{c['id']}")
                    ]])
                )
                c["reminded_now"] = True

    save_db(db)

# ── /help ─────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Yordam*\n\n"
        "/add — Yangi Reels yoki Story qo'shish\n"
        "/list — Barcha kontentlarni ko'rish\n"
        "/week — Keyingi 7 kunlik reja\n\n"
        "⏰ Bot vaqti kelganda avtomatik eslatma yuboradi:\n"
        "• 1 soat oldin\n"
        "• Aynan vaqtida\n\n"
        "✅ Har bir kontentni 'Chiqdi' deb belgilashingiz mumkin.",
        parse_mode="Markdown"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            ASK_TYPE:     [CallbackQueryHandler(got_type, pattern="^type_")],
            ASK_PLATFORM: [CallbackQueryHandler(got_platform, pattern="^plat_")],
            ASK_SCRIPT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_script)],
            ASK_DATE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("list",  cmd_list))
    app.add_handler(CommandHandler("week",  cmd_week))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Har 1 daqiqada eslatmalarni tekshir
    app.job_queue.run_repeating(send_reminders, interval=60, first=10)

    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
