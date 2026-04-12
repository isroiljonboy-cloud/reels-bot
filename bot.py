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
TOKEN = os.environ["BOT_TOKEN"]
TZ = ZoneInfo("Asia/Tashkent")
DB_FILE = "data.json"

# Vazifa turlari
TASK_TYPES = {
    "dars": "📚 Dars / Mashg'ulot",
    "suhbat": "🗣 O'quvchi suhbati",
    "hujjat": "📝 Hujjat / Vazifa",
    "uchrashuv": "🤝 Uchrashuv",
    "boshqa": "📌 Boshqa",
}

# Status
STATUS = {
    "kutmoqda": "⏳ Kutmoqda",
    "bajarildi": "✅ Bajarildi",
    "kechikdi": "⚠️ Kechikdi",
}

# Conversation states
ASK_TYPE, ASK_TITLE, ASK_TIME, ASK_NOTE = range(4)

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
        db[uid] = {"tasks": []}
    return db[uid]

def now_tz():
    return datetime.now(TZ)

def fmt_time(iso_str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    days = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]
    months = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"]
    return f"{days[dt.weekday()]}, {dt.day} {months[dt.month-1]} • {dt.strftime('%H:%M')}"

def parse_time(text):
    """HH:MM formatini bugungi sanaga bog'laydi"""
    text = text.strip()
    today = now_tz().date()
    formats = ["%H:%M", "%H.%M", "%H %M"]
    for fmt in formats:
        try:
            t = datetime.strptime(text, fmt)
            dt = datetime.combine(today, t.time(), tzinfo=TZ)
            return dt
        except ValueError:
            continue
    # To'liq format: KK.OO.YYYY SS:MM
    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
        return dt
    except ValueError:
        return None

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Assalomu alaykum! Maslahatchi Ish Rejasi botiga xush kelibsiz.*\n\n"
        "Bu bot sizning kunlik ish jadvalingizni boshqaradi va "
        "har kuni *07:30* da yangi kun rejasini yuboradi.\n\n"
        "📌 *Buyruqlar:*\n"
        "/qosh — Yangi vazifa qo'shish\n"
        "/bugun — Bugungi ish rejasi\n"
        "/hafta — Haftalik ko'rinish\n"
        "/help — Yordam\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /qosh conversation ────────────────────────────────────────────────────────
async def cmd_qosh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 Dars", callback_data="type_dars"),
            InlineKeyboardButton("🗣 Suhbat", callback_data="type_suhbat"),
        ],
        [
            InlineKeyboardButton("📝 Hujjat", callback_data="type_hujjat"),
            InlineKeyboardButton("🤝 Uchrashuv", callback_data="type_uchrashuv"),
        ],
        [InlineKeyboardButton("📌 Boshqa", callback_data="type_boshqa")],
    ])
    await update.message.reply_text(
        "*Vazifa turini tanlang:*", reply_markup=kb, parse_mode="Markdown"
    )
    return ASK_TYPE

async def got_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["type"] = q.data.replace("type_", "")
    type_label = TASK_TYPES[ctx.user_data["type"]]
    await q.edit_message_text(
        f"{type_label} tanlandi.\n\n✍️ *Vazifa nomini yuboring:*\n\n"
        f"_Misol: 9-A sinf bilan individual suhbat_",
        parse_mode="Markdown"
    )
    return ASK_TITLE

async def got_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "🕐 *Vaqtini yuboring:*\n\n"
        "Format: `SS:MM` — masalan, `10:30`\n"
        "Yoki to'liq: `15.04.2026 14:00`",
        parse_mode="Markdown"
    )
    return ASK_TIME

async def got_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dt = parse_time(update.message.text)
    if not dt:
        await update.message.reply_text(
            "❌ Format noto'g'ri. Qaytadan yuboring:\n`10:30` yoki `15.04.2026 14:00`",
            parse_mode="Markdown"
        )
        return ASK_TIME
    ctx.user_data["datetime"] = dt.isoformat()
    await update.message.reply_text(
        "📎 *Izoh qo'shing* (ixtiyoriy):\n\n"
        "Agar izoh kerak bo'lmasa — `/skip` yuboring.",
        parse_mode="Markdown"
    )
    return ASK_NOTE

async def got_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ctx.user_data["note"] = "" if text == "/skip" else text
    return await save_task(update, ctx)

async def skip_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["note"] = ""
    return await save_task(update, ctx)

async def save_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    user = get_user(db, update.effective_user.id)
    task = {
        "id": int(datetime.now().timestamp() * 1000),
        "type": ctx.user_data["type"],
        "title": ctx.user_data["title"],
        "datetime": ctx.user_data["datetime"],
        "note": ctx.user_data.get("note", ""),
        "status": "kutmoqda",
        "reminded_30m": False,
        "reminded_now": False,
        "created_at": now_tz().isoformat(),
    }
    user["tasks"].append(task)
    save_db(db)

    emoji = TASK_TYPES[task["type"]].split()[0]
    await update.message.reply_text(
        f"✅ *Saqlandi!*\n\n"
        f"{emoji} *{task['title']}*\n"
        f"🕐 {fmt_time(task['datetime'])}\n"
        f"{'📎 ' + task['note'] if task['note'] else ''}",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.")
    ctx.user_data.clear()
    return ConversationHandler.END

# ── /bugun ────────────────────────────────────────────────────────────────────
async def cmd_bugun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_daily_plan(update.effective_chat.id, ctx, update=update)

async def send_daily_plan(chat_id, ctx, update=None):
    db = load_db()
    user = get_user(db, chat_id)
    now = now_tz()
    today = now.date()

    tasks = [
        t for t in user["tasks"]
        if datetime.fromisoformat(t["datetime"]).replace(tzinfo=TZ).date() == today
    ]
    tasks.sort(key=lambda x: x["datetime"])

    done = [t for t in tasks if t["status"] == "bajarildi"]
    pending = [t for t in tasks if t["status"] != "bajarildi"]

    day_names = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]
    months = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"]
    day_str = f"{day_names[today.weekday()]}, {today.day} {months[today.month-1]}"

    header = (
        f"📋 *Bugungi ish rejasi*\n"
        f"📅 {day_str}\n"
        f"{'─' * 28}\n"
    )

    if not tasks:
        msg = header + "\n📭 Bugun hali vazifa yo'q.\n/qosh bilan qo'shing."
        if update:
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        return

    summary = f"📊 Jami: *{len(tasks)}* vazifa • ✅ {len(done)} bajarildi • ⏳ {len(pending)} kutmoqda\n\n"

    if update:
        await update.message.reply_text(header + summary, parse_mode="Markdown")
    else:
        await ctx.bot.send_message(chat_id=chat_id, text=header + summary, parse_mode="Markdown")

    for t in tasks:
        dt = datetime.fromisoformat(t["datetime"]).replace(tzinfo=TZ)
        emoji = TASK_TYPES[t["type"]].split()[0]
        overdue = dt < now and t["status"] == "kutmoqda"
        status_icon = "✅" if t["status"] == "bajarildi" else ("⚠️" if overdue else "⏳")

        text = (
            f"{status_icon} {emoji} *{t['title']}*\n"
            f"🕐 {dt.strftime('%H:%M')}"
            + (f"\n📎 _{t['note']}_" if t["note"] else "")
        )

        if t["status"] != "bajarildi":
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Bajarildi", callback_data=f"done_{t['id']}"),
                    InlineKeyboardButton("⏰ Kechikdi", callback_data=f"late_{t['id']}"),
                    InlineKeyboardButton("🗑 O'chir", callback_data=f"del_{t['id']}"),
                ]
            ])
        else:
            kb = None

        if update:
            await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await ctx.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown")

# ── /hafta ────────────────────────────────────────────────────────────────────
async def cmd_hafta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    user = get_user(db, update.effective_user.id)
    now = now_tz()
    week_end = now + timedelta(days=7)
    day_names = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

    week_tasks = [
        t for t in user["tasks"]
        if now.date() <= datetime.fromisoformat(t["datetime"]).replace(tzinfo=TZ).date() <= week_end.date()
    ]
    week_tasks.sort(key=lambda x: x["datetime"])

    if not week_tasks:
        await update.message.reply_text(
            "📭 Keyingi 7 kunda rejalashtirilgan vazifa yo'q.\n/qosh bilan qo'shing."
        )
        return

    text = f"📅 *Haftalik reja* ({len(week_tasks)} ta vazifa)\n\n"
    current_day = None

    for t in week_tasks:
        dt = datetime.fromisoformat(t["datetime"]).replace(tzinfo=TZ)
        day = day_names[dt.weekday()]
        if day != current_day:
            current_day = day
            text += f"\n📌 *{day}* — {dt.strftime('%d.%m')}\n"
        emoji = TASK_TYPES[t["type"]].split()[0]
        status = "✅" if t["status"] == "bajarildi" else "⏳"
        text += f"  {status} {emoji} `{dt.strftime('%H:%M')}` {t['title']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ── Callbacks ─────────────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    db = load_db()
    user = get_user(db, update.effective_user.id)

    if data.startswith("done_"):
        tid = int(data.replace("done_", ""))
        for t in user["tasks"]:
            if t["id"] == tid:
                t["status"] = "bajarildi"
                save_db(db)
                await q.edit_message_reply_markup(reply_markup=None)
                await q.message.reply_text(
                    f"✅ *{t['title']}* — bajarildi deb belgilandi!", parse_mode="Markdown"
                )
                return

    elif data.startswith("late_"):
        tid = int(data.replace("late_", ""))
        for t in user["tasks"]:
            if t["id"] == tid:
                t["status"] = "kechikdi"
                save_db(db)
                await q.edit_message_reply_markup(reply_markup=None)
                await q.message.reply_text(
                    f"⚠️ *{t['title']}* — kechikdi deb belgilandi.", parse_mode="Markdown"
                )
                return

    elif data.startswith("del_"):
        tid = int(data.replace("del_", ""))
        before = len(user["tasks"])
        user["tasks"] = [t for t in user["tasks"] if t["id"] != tid]
        if len(user["tasks"]) < before:
            save_db(db)
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text("🗑 Vazifa o'chirildi.")

# ── Reminder job ──────────────────────────────────────────────────────────────
async def send_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    now = now_tz()
    for uid, user in db.items():
        for t in user["tasks"]:
            if t["status"] == "bajarildi":
                continue
            dt = datetime.fromisoformat(t["datetime"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            diff_min = (dt - now).total_seconds() / 60
            emoji = TASK_TYPES[t["type"]].split()[0]

            # 30 daqiqa oldin
            if 28 <= diff_min <= 32 and not t.get("reminded_30m"):
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"⏰ *30 daqiqadan keyin:*\n\n"
                        f"{emoji} *{t['title']}*\n"
                        f"🕐 {dt.strftime('%H:%M')}"
                        + (f"\n📎 _{t['note']}_" if t.get("note") else "")
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Bajarildi", callback_data=f"done_{t['id']}"),
                    ]])
                )
                t["reminded_30m"] = True

            # Aynan vaqtida
            elif -2 <= diff_min <= 2 and not t.get("reminded_now"):
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"🔔 *Hozir vaqt keldi!*\n\n"
                        f"{emoji} *{t['title']}*\n"
                        f"🕐 {dt.strftime('%H:%M')}"
                        + (f"\n📎 _{t['note']}_" if t.get("note") else "")
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Bajarildi", callback_data=f"done_{t['id']}"),
                        InlineKeyboardButton("⏰ Kechikdi", callback_data=f"late_{t['id']}"),
                    ]])
                )
                t["reminded_now"] = True

    save_db(db)

# ── Ertalabki kunlik reja job (07:30) ─────────────────────────────────────────
async def morning_plan_job(ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    for uid in db:
        await send_daily_plan(int(uid), ctx)

# ── /help ─────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Yordam*\n\n"
        "/qosh — Yangi vazifa qo'shish\n"
        "/bugun — Bugungi ish rejasi\n"
        "/hafta — Keyingi 7 kunlik ko'rinish\n\n"
        "📌 *Vazifa turlari:*\n"
        "📚 Dars / Mashg'ulot\n"
        "🗣 O'quvchi suhbati\n"
        "📝 Hujjat / Vazifa\n"
        "🤝 Uchrashuv\n"
        "📌 Boshqa\n\n"
        "⏰ *Eslatmalar:*\n"
        "• Har kuni *07:30* da kunlik reja\n"
        "• Har bir vazifadan *30 daqiqa* oldin\n"
        "• Aynan *vaqtida* eslatma\n\n"
        "✅ Har bir vazifani *Bajarildi* yoki *Kechikdi* deb belgilashingiz mumkin.",
        parse_mode="Markdown"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("qosh", cmd_qosh)],
        states={
            ASK_TYPE: [CallbackQueryHandler(got_type, pattern="^type_")],
            ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_title)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_time)],
            ASK_NOTE: [
                CommandHandler("skip", skip_note),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_note),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("bugun", cmd_bugun))
    app.add_handler(CommandHandler("hafta", cmd_hafta))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Har 1 daqiqada eslatmalarni tekshir
    app.job_queue.run_repeating(send_reminders, interval=60, first=10)

    # Har kuni 07:30 da kunlik reja
    app.job_queue.run_daily(
        morning_plan_job,
        time=datetime.strptime("07:30", "%H:%M").replace(tzinfo=TZ).timetz(),
    )

    print("✅ Maslahatchi ish rejasi boti ishga tushdi!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("🟢 Polling boshlandi.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
