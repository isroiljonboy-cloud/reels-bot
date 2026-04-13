const { Telegraf, Markup } = require('telegraf');
const fs = require('fs');
const path = require('path');

const TOKEN = process.env.BOT_TOKEN;
const DB_FILE = path.join(__dirname, 'data.json');
const TZ = 'Asia/Tashkent';

const bot = new Telegraf(TOKEN);

// ── DB helpers ────────────────────────────────────────────────────────────────
function loadDB() {
  if (!fs.existsSync(DB_FILE)) return {};
  return JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
}

function saveDB(db) {
  fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf8');
}

function getUser(db, uid) {
  uid = String(uid);
  if (!db[uid]) db[uid] = { tasks: [] };
  return db[uid];
}

function nowTZ() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: TZ }));
}

function fmtTime(isoStr) {
  const dt = new Date(isoStr);
  const days = ['Yakshanba','Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba'];
  const months = ['Yanvar','Fevral','Mart','Aprel','May','Iyun','Iyul','Avgust','Sentabr','Oktabr','Noyabr','Dekabr'];
  const local = new Date(dt.toLocaleString('en-US', { timeZone: TZ }));
  const h = String(local.getHours()).padStart(2, '0');
  const m = String(local.getMinutes()).padStart(2, '0');
  return `${days[local.getDay()]}, ${local.getDate()} ${months[local.getMonth()]} • ${h}:${m}`;
}

function parseTime(text) {
  text = text.trim();
  const now = nowTZ();

  // HH:MM
  let match = text.match(/^(\d{1,2})[:\.](\d{2})$/);
  if (match) {
    const d = new Date(now);
    d.setHours(parseInt(match[1]), parseInt(match[2]), 0, 0);
    return d;
  }

  // DD.MM.YYYY HH:MM
  match = text.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})$/);
  if (match) {
    return new Date(`${match[3]}-${match[2]}-${match[1]}T${match[4].padStart(2,'0')}:${match[5]}:00`);
  }

  return null;
}

const TASK_TYPES = {
  dars: '📚 Dars / Mashg\'ulot',
  suhbat: '🗣 O\'quvchi suhbati',
  hujjat: '📝 Hujjat / Vazifa',
  uchrashuv: '🤝 Uchrashuv',
  boshqa: '📌 Boshqa',
};

// Foydalanuvchi holati (conversation state)
const userState = {};

// ── /start ────────────────────────────────────────────────────────────────────
bot.start((ctx) => {
  ctx.replyWithMarkdown(
    `👋 *Assalomu alaykum! Maslahatchi Ish Rejasi botiga xush kelibsiz.*\n\n` +
    `Bu bot sizning kunlik ish jadvalingizni boshqaradi va ` +
    `har kuni *07:30* da yangi kun rejasini yuboradi.\n\n` +
    `📌 *Buyruqlar:*\n` +
    `/qosh — Yangi vazifa qo'shish\n` +
    `/bugun — Bugungi ish rejasi\n` +
    `/hafta — Haftalik ko'rinish\n` +
    `/help — Yordam`
  );
});

// ── /qosh ────────────────────────────────────────────────────────────────────
bot.command('qosh', (ctx) => {
  const uid = String(ctx.from.id);
  userState[uid] = { step: 'type' };

  ctx.replyWithMarkdown(
    '*Vazifa turini tanlang:*',
    Markup.inlineKeyboard([
      [
        Markup.button.callback('📚 Dars', 'type_dars'),
        Markup.button.callback('🗣 Suhbat', 'type_suhbat'),
      ],
      [
        Markup.button.callback('📝 Hujjat', 'type_hujjat'),
        Markup.button.callback('🤝 Uchrashuv', 'type_uchrashuv'),
      ],
      [Markup.button.callback('📌 Boshqa', 'type_boshqa')],
    ])
  );
});

// Vazifa turi tanlandi
Object.keys(TASK_TYPES).forEach((type) => {
  bot.action(`type_${type}`, (ctx) => {
    const uid = String(ctx.from.id);
    if (!userState[uid]) userState[uid] = {};
    userState[uid].type = type;
    userState[uid].step = 'title';
    ctx.answerCbQuery();
    ctx.editMessageText(
      `${TASK_TYPES[type]} tanlandi.\n\n✍️ *Vazifa nomini yuboring:*\n\n_Misol: 9-A sinf bilan individual suhbat_`,
      { parse_mode: 'Markdown' }
    );
  });
});

// ── /cancel ───────────────────────────────────────────────────────────────────
bot.command('cancel', (ctx) => {
  const uid = String(ctx.from.id);
  delete userState[uid];
  ctx.reply('❌ Bekor qilindi.');
});

// ── /bugun ────────────────────────────────────────────────────────────────────
bot.command('bugun', (ctx) => {
  sendDailyPlan(ctx.chat.id, ctx);
});

async function sendDailyPlan(chatId, ctx) {
  const db = loadDB();
  const user = getUser(db, chatId);
  const now = nowTZ();
  const today = now.toDateString();

  const tasks = user.tasks
    .filter((t) => new Date(t.datetime).toDateString() === today)
    .sort((a, b) => new Date(a.datetime) - new Date(b.datetime));

  const days = ['Yakshanba','Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba'];
  const months = ['Yanvar','Fevral','Mart','Aprel','May','Iyun','Iyul','Avgust','Sentabr','Oktabr','Noyabr','Dekabr'];
  const dayStr = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;

  const header = `📋 *Bugungi ish rejasi*\n📅 ${dayStr}\n${'─'.repeat(28)}\n`;

  const send = (text, extra) => {
    if (ctx && ctx.replyWithMarkdown) {
      return ctx.replyWithMarkdown(text, extra);
    } else {
      return bot.telegram.sendMessage(chatId, text, { parse_mode: 'Markdown', ...extra });
    }
  };

  if (!tasks.length) {
    await send(header + '\n📭 Bugun hali vazifa yo\'q.\n/qosh bilan qo\'shing.');
    return;
  }

  const done = tasks.filter((t) => t.status === 'bajarildi').length;
  const pending = tasks.length - done;
  await send(header + `\n📊 Jami: *${tasks.length}* vazifa • ✅ ${done} bajarildi • ⏳ ${pending} kutmoqda`);

  for (const t of tasks) {
    const dt = new Date(t.datetime);
    const local = new Date(dt.toLocaleString('en-US', { timeZone: TZ }));
    const h = String(local.getHours()).padStart(2, '0');
    const m = String(local.getMinutes()).padStart(2, '0');
    const emoji = TASK_TYPES[t.type]?.split(' ')[0] || '📌';
    const overdue = dt < now && t.status === 'kutmoqda';
    const icon = t.status === 'bajarildi' ? '✅' : overdue ? '⚠️' : '⏳';

    const text = `${icon} ${emoji} *${t.title}*\n🕐 ${h}:${m}${t.note ? `\n📎 _${t.note}_` : ''}`;

    if (t.status !== 'bajarildi') {
      await send(text, Markup.inlineKeyboard([
        [
          Markup.button.callback('✅ Bajarildi', `done_${t.id}`),
          Markup.button.callback('⏰ Kechikdi', `late_${t.id}`),
          Markup.button.callback('🗑 O\'chir', `del_${t.id}`),
        ],
      ]));
    } else {
      await send(text);
    }
  }
}

// ── /hafta ────────────────────────────────────────────────────────────────────
bot.command('hafta', (ctx) => {
  const db = loadDB();
  const user = getUser(db, ctx.from.id);
  const now = nowTZ();
  const weekLater = new Date(now);
  weekLater.setDate(weekLater.getDate() + 7);

  const days = ['Yakshanba','Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba'];

  const tasks = user.tasks
    .filter((t) => {
      const d = new Date(t.datetime);
      return d >= now && d <= weekLater;
    })
    .sort((a, b) => new Date(a.datetime) - new Date(b.datetime));

  if (!tasks.length) {
    ctx.reply('📭 Keyingi 7 kunda rejalashtirilgan vazifa yo\'q.\n/qosh bilan qo\'shing.');
    return;
  }

  let text = `📅 *Haftalik reja* (${tasks.length} ta vazifa)\n`;
  let currentDay = null;

  for (const t of tasks) {
    const dt = new Date(t.datetime);
    const local = new Date(dt.toLocaleString('en-US', { timeZone: TZ }));
    const dayName = days[local.getDay()];
    const h = String(local.getHours()).padStart(2, '0');
    const m = String(local.getMinutes()).padStart(2, '0');
    const emoji = TASK_TYPES[t.type]?.split(' ')[0] || '📌';
    const icon = t.status === 'bajarildi' ? '✅' : '⏳';

    if (dayName !== currentDay) {
      currentDay = dayName;
      text += `\n📌 *${dayName}* — ${local.getDate()}.${String(local.getMonth()+1).padStart(2,'0')}\n`;
    }
    text += `  ${icon} ${emoji} \`${h}:${m}\` ${t.title}\n`;
  }

  ctx.replyWithMarkdown(text);
});

// ── Callback: done / late / del ───────────────────────────────────────────────
bot.action(/^done_(.+)$/, (ctx) => {
  const id = parseInt(ctx.match[1]);
  const db = loadDB();
  const user = getUser(db, ctx.from.id);
  const task = user.tasks.find((t) => t.id === id);
  if (task) {
    task.status = 'bajarildi';
    saveDB(db);
    ctx.answerCbQuery('✅ Bajarildi!');
    ctx.editMessageReplyMarkup({ inline_keyboard: [] });
    ctx.replyWithMarkdown(`✅ *${task.title}* — bajarildi deb belgilandi!`);
  }
});

bot.action(/^late_(.+)$/, (ctx) => {
  const id = parseInt(ctx.match[1]);
  const db = loadDB();
  const user = getUser(db, ctx.from.id);
  const task = user.tasks.find((t) => t.id === id);
  if (task) {
    task.status = 'kechikdi';
    saveDB(db);
    ctx.answerCbQuery('⚠️ Kechikdi');
    ctx.editMessageReplyMarkup({ inline_keyboard: [] });
    ctx.replyWithMarkdown(`⚠️ *${task.title}* — kechikdi deb belgilandi.`);
  }
});

bot.action(/^del_(.+)$/, (ctx) => {
  const id = parseInt(ctx.match[1]);
  const db = loadDB();
  const user = getUser(db, ctx.from.id);
  const before = user.tasks.length;
  user.tasks = user.tasks.filter((t) => t.id !== id);
  if (user.tasks.length < before) {
    saveDB(db);
    ctx.answerCbQuery('🗑 O\'chirildi');
    ctx.editMessageReplyMarkup({ inline_keyboard: [] });
    ctx.reply('🗑 Vazifa o\'chirildi.');
  }
});

// ── Matn xabarlari (conversation) ─────────────────────────────────────────────
bot.on('text', (ctx) => {
  const uid = String(ctx.from.id);
  const state = userState[uid];
  if (!state) return;

  const text = ctx.message.text.trim();

  if (state.step === 'title') {
    state.title = text;
    state.step = 'time';
    ctx.replyWithMarkdown(
      '🕐 *Vaqtini yuboring:*\n\n' +
      'Format: `SS:MM` — masalan, `10:30`\n' +
      'Yoki to\'liq: `15.04.2026 14:00`'
    );
    return;
  }

  if (state.step === 'time') {
    const dt = parseTime(text);
    if (!dt) {
      ctx.replyWithMarkdown('❌ Format noto\'g\'ri. Qaytadan yuboring:\n`10:30` yoki `15.04.2026 14:00`');
      return;
    }
    state.datetime = dt.toISOString();
    state.step = 'note';
    ctx.replyWithMarkdown(
      '📎 *Izoh qo\'shing* (ixtiyoriy):\n\nIzoh kerak bo\'lmasa — `/skip` yuboring.'
    );
    return;
  }

  if (state.step === 'note') {
    state.note = text === '/skip' ? '' : text;
    saveTask(ctx, uid);
  }
});

// /skip buyrug'i
bot.command('skip', (ctx) => {
  const uid = String(ctx.from.id);
  const state = userState[uid];
  if (state && state.step === 'note') {
    state.note = '';
    saveTask(ctx, uid);
  }
});

function saveTask(ctx, uid) {
  const state = userState[uid];
  const db = loadDB();
  const user = getUser(db, uid);

  const task = {
    id: Date.now(),
    type: state.type,
    title: state.title,
    datetime: state.datetime,
    note: state.note || '',
    status: 'kutmoqda',
    reminded30m: false,
    remindedNow: false,
    createdAt: new Date().toISOString(),
  };

  user.tasks.push(task);
  saveDB(db);
  delete userState[uid];

  const emoji = TASK_TYPES[task.type]?.split(' ')[0] || '📌';
  ctx.replyWithMarkdown(
    `✅ *Saqlandi!*\n\n` +
    `${emoji} *${task.title}*\n` +
    `🕐 ${fmtTime(task.datetime)}` +
    (task.note ? `\n📎 ${task.note}` : '')
  );
}

// ── /help ─────────────────────────────────────────────────────────────────────
bot.command('help', (ctx) => {
  ctx.replyWithMarkdown(
    `📖 *Yordam*\n\n` +
    `/qosh — Yangi vazifa qo'shish\n` +
    `/bugun — Bugungi ish rejasi\n` +
    `/hafta — Keyingi 7 kunlik ko'rinish\n\n` +
    `📌 *Vazifa turlari:*\n` +
    `📚 Dars / Mashg'ulot\n` +
    `🗣 O'quvchi suhbati\n` +
    `📝 Hujjat / Vazifa\n` +
    `🤝 Uchrashuv\n` +
    `📌 Boshqa\n\n` +
    `⏰ *Eslatmalar:*\n` +
    `• Har kuni *07:30* da kunlik reja\n` +
    `• Har bir vazifadan *30 daqiqa* oldin\n` +
    `• Aynan *vaqtida* eslatma\n\n` +
    `✅ Har bir vazifani *Bajarildi* yoki *Kechikdi* deb belgilashingiz mumkin.`
  );
});

// ── Eslatmalar (har 1 daqiqada) ───────────────────────────────────────────────
setInterval(() => {
  const db = loadDB();
  const now = nowTZ();

  for (const [uid, user] of Object.entries(db)) {
    for (const t of user.tasks) {
      if (t.status === 'bajarildi') continue;

      const dt = new Date(t.datetime);
      const diffMin = (dt - now) / 60000;
      const emoji = TASK_TYPES[t.type]?.split(' ')[0] || '📌';

      // 30 daqiqa oldin
      if (diffMin >= 28 && diffMin <= 32 && !t.reminded30m) {
        bot.telegram.sendMessage(
          uid,
          `⏰ *30 daqiqadan keyin:*\n\n${emoji} *${t.title}*\n🕐 ${fmtTime(t.datetime)}` +
          (t.note ? `\n📎 _${t.note}_` : ''),
          {
            parse_mode: 'Markdown',
            ...Markup.inlineKeyboard([[Markup.button.callback('✅ Bajarildi', `done_${t.id}`)]]),
          }
        ).catch(() => {});
        t.reminded30m = true;
      }

      // Aynan vaqtida
      if (diffMin >= -2 && diffMin <= 2 && !t.remindedNow) {
        bot.telegram.sendMessage(
          uid,
          `🔔 *Hozir vaqt keldi!*\n\n${emoji} *${t.title}*\n🕐 ${fmtTime(t.datetime)}` +
          (t.note ? `\n📎 _${t.note}_` : ''),
          {
            parse_mode: 'Markdown',
            ...Markup.inlineKeyboard([[
              Markup.button.callback('✅ Bajarildi', `done_${t.id}`),
              Markup.button.callback('⏰ Kechikdi', `late_${t.id}`),
            ]]),
          }
        ).catch(() => {});
        t.remindedNow = true;
      }
    }
  }

  saveDB(db);
}, 60000);

// ── Ertalabki reja (07:30 Tashkent) ──────────────────────────────────────────
setInterval(() => {
  const now = nowTZ();
  if (now.getHours() === 7 && now.getMinutes() === 30) {
    const db = loadDB();
    for (const uid of Object.keys(db)) {
      sendDailyPlan(uid, null);
    }
  }
}, 60000);

// ── Start ─────────────────────────────────────────────────────────────────────
bot.launch();
console.log('✅ Bot ishga tushdi!');

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
