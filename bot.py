import logging
import psycopg2
from psycopg2 import pool
import locales as locale_data
from locales import get_text
import datetime
import asyncio
import os
import threading
import random  
import time  
import httpx
from game_data import GAME_DATA
from flask import Flask
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, 
    Update, error
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, 
    CallbackQueryHandler, MessageHandler, filters, MessageReactionHandler
)
from telegram.request import HTTPXRequest
from ghost_engine import GhostEngine

# ==============================================================================
# 🔐 SECURITY & CONFIGURATION
# ==============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
admin_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in admin_env.split(",") if x.strip().isdigit()]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==============================================================================
# 🚀 HIGH-PERFORMANCE ENGINE (RAM Cache & Connection Pool)
# ==============================================================================
# Replace these strings with real file_ids later from your Render Logs!
DEFAULT_MALE = "AgACAgUAAxkBAAIDbWnFVLX6LjG374-RxzYj_EdXsCjrAAJyDWsbQK0xVsZVFy9b3aYnAQADAgADeAADOgQ"
DEFAULT_FEMALE = "AgACAgUAAxkBAAIDdWnFXghImuyxdLW8-iIJEp1kwHAdAAKNDWsbQK0xVuqb4eiaOzUOAQADAgADeAADOgQ"
DEFAULT_OTHER = "AgACAgUAAxkBAAIDemnFXpBYUU0YQkeTclrszyDczqUoAAKODWsbQK0xVhTsjry1NYnTAQADAgADeAADOgQ"

ACTIVE_CHATS = {} 
MESSAGE_MAP = {}
GAME_STATES = {}       
GAME_COOLDOWNS = {}    
USER_LANGS = {}
TRANSLATE_ENABLED = set()

DB_POOL = None
GHOST = None 

def init_db_pool():
    global DB_POOL
    if not DATABASE_URL: return
    try:
        DB_POOL = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DATABASE_URL)
        print("✅ CONNECTION POOL STARTED.")
    except Exception as e:
        print(f"❌ Pool Error: {e}")

def get_conn():
    if DB_POOL: return DB_POOL.getconn()
    return None

def release_conn(conn):
    if DB_POOL and conn: DB_POOL.putconn(conn)

async def get_lang(user_id):
    # 1. Instant RAM check (Fastest)
    if user_id in USER_LANGS: return USER_LANGS[user_id]
    
    # 2. Database check with a 2-attempt Auto-Retry loop
    for attempt in range(2): 
        conn = get_conn()
        if not conn: return "English"
        
        try:
            cur = conn.cursor()
            cur.execute("SELECT language FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
            release_conn(conn) # Put healthy connection back in pool
            
            lang = row[0] if row else "English"
            USER_LANGS[user_id] = lang
            return lang
            
        except psycopg2.OperationalError as e:
            # 🚨 STALE CONNECTION DETECTED!
            print(f"⚠️ Stale connection caught (Attempt {attempt+1}). Reconnecting...")
            if conn:
                try: 
                    # 🗑️ Throw away the dead connection permanently
                    DB_POOL.putconn(conn, close=True) 
                except: pass
                
        except Exception as e:
            # Catch other random database errors safely
            print(f"❌ DB Error: {e}")
            if conn: release_conn(conn)
            return "English"

    # 3. Ultimate Failsafe if the database is completely down
    return "English"
async def translate_text(text, target_lang):
    if not GROQ_API_KEY: return text
    prompt = f"Translate this internet slang/chat text to {target_lang}. Reply ONLY with the translation, absolutely nothing else. Text: '{text}'"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "llama3-8b-8192", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=4.0)
            return resp.json()["choices"][0]["message"]["content"].strip()
    except: return text
# ==============================================================================
# ❤️ THE HEARTBEAT
# ==============================================================================
app_flask = Flask(__name__)

@app_flask.route('/')
def health_check():
    return "Bot is Alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)

def init_db():
    init_db_pool() 
    conn = get_conn()
    if not conn: return
    cur = conn.cursor()
    
    tables = [
        """CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
            language TEXT DEFAULT 'English', gender TEXT DEFAULT 'Hidden',
            age_range TEXT DEFAULT 'Hidden', region TEXT DEFAULT 'Hidden',
            interests TEXT DEFAULT '', mood TEXT DEFAULT 'Neutral',
            karma_score INTEGER DEFAULT 100, status TEXT DEFAULT 'idle',
            partner_id BIGINT DEFAULT 0, report_count INTEGER DEFAULT 0,
            banned_until TIMESTAMP, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            nickname TEXT DEFAULT 'Anon', avatar_id TEXT
        );""",
        """CREATE TABLE IF NOT EXISTS chat_logs (
            id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_id BIGINT,
            message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY, reporter_id BIGINT, reported_id BIGINT,
            reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS user_interactions (
            id SERIAL PRIMARY KEY, rater_id BIGINT, target_id BIGINT,
            score INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY, user_id BIGINT, message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    ]
    for t in tables: cur.execute(t)
    
    # Migration checks for new columns
    try:
        cols = ["username TEXT", "first_name TEXT", "report_count INTEGER DEFAULT 0", 
                "banned_until TIMESTAMP", "gender TEXT DEFAULT 'Hidden'", 
                "age_range TEXT DEFAULT 'Hidden'", "region TEXT DEFAULT 'Hidden'",
                "nickname TEXT DEFAULT 'Anon'", "avatar_id TEXT"]
        for c in cols: cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {c};")
    except: pass
    
    conn.commit(); cur.close(); release_conn(conn)
    global GHOST
    GHOST = GhostEngine(DB_POOL)

# ==============================================================================
# ⌨️ KEYBOARD LAYOUTS
# ==============================================================================
def get_keyboard_lobby(lang="English"):
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_text(lang, "START_BTN"))],
        [KeyboardButton(get_text(lang, "CHANGE_INTERESTS")), KeyboardButton(get_text(lang, "SETTINGS"))],
        [KeyboardButton(get_text(lang, "MY_ID")), KeyboardButton(get_text(lang, "HELP"))]
    ], resize_keyboard=True)

def get_keyboard_searching(lang="English"):
    return ReplyKeyboardMarkup([[KeyboardButton(get_text(lang, "STOP_SEARCH"))]], resize_keyboard=True)

def get_keyboard_chat(lang="English", is_translating=False):
    trans_btn = KeyboardButton(get_text(lang, "BTN_TRANS_OFF")) if is_translating else KeyboardButton(get_text(lang, "BTN_TRANS_ON"))
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_text(lang, "BTN_GAMES")), trans_btn],
        [KeyboardButton(get_text(lang, "BTN_STOP")), KeyboardButton(get_text(lang, "BTN_NEXT"))]
    ], resize_keyboard=True)

def get_keyboard_game(lang="English", is_spicy=False):
    spicy_btn = KeyboardButton(get_text(lang, "BTN_NORMAL_MODE")) if is_spicy else KeyboardButton(get_text(lang, "BTN_SPICY_MODE"))
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_text(lang, "BTN_STOP_CHAT")), KeyboardButton(get_text(lang, "BTN_STOP_GAME"))],
        [spicy_btn]
    ], resize_keyboard=True)

# ==============================================================================
# 🧠 MATCHMAKING ENGINE
# ==============================================================================
def find_match(user_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language, interests, age_range, mood FROM users WHERE user_id = %s", (user_id,))
    me = cur.fetchone()
    if not me: release_conn(conn); return None, [], "Neutral", "English", "Anon", None, 100, "Hidden"
    my_lang, my_interests, my_age, my_mood = me
    my_tags = [t.strip().lower() for t in my_interests.split(',')] if my_interests else []

    cur.execute("SELECT target_id FROM user_interactions WHERE rater_id = %s AND score = -1", (user_id,))
    disliked_ids = {row[0] for row in cur.fetchall()}

    cur.execute("""
        SELECT user_id, language, interests, age_range, mood, nickname, avatar_id, karma_score, gender 
        FROM users 
        WHERE status = 'searching' AND user_id != %s AND (banned_until IS NULL OR banned_until < NOW())
    """, (user_id,))
    candidates = cur.fetchall()
    
    best_match, best_score, common_interests = None, -999999, []
    p_mood, p_lang, p_nick, p_ava, p_karma, p_gen = "Neutral", "English", "Anon", None, 100, "Hidden"

    for cand in candidates:
        cand_id, cand_lang, cand_interests, cand_age, cand_mood, cand_nick, cand_ava, cand_karma, cand_gen = cand
        cand_tags = [t.strip().lower() for t in cand_interests.split(',')] if cand_interests else []
        score = 0
        if cand_id in disliked_ids: score -= 1000
        matched_tags = list(set(my_tags) & set(cand_tags))
        if matched_tags: score += 40
        if cand_lang == my_lang: score += 20
        if cand_age == my_age and cand_age != 'Hidden': score += 10
            
        if score > best_score:
            best_score = score
            best_match = cand_id
            common_interests = matched_tags
            p_mood = cand_mood
            p_lang = cand_lang
            p_nick = cand_nick
            p_ava = cand_ava
            p_karma = cand_karma
            p_gen = cand_gen

    cur.close(); release_conn(conn)
    return best_match, common_interests, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen

# ==============================================================================
# 🎮 GAME ENGINE LOGIC
# ==============================================================================
async def offer_game(update, context, user_id, game_name):
    partner_id = ACTIVE_CHATS.get(user_id)
    if not partner_id: return
    
    l1 = await get_lang(user_id)
    if isinstance(partner_id, str) and partner_id.startswith("AI_"):
        accept, reply_text = GHOST.decide_game_offer(game_name)
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        await asyncio.sleep(2)
        await context.bot.send_message(user_id, reply_text)
        if accept:
            await asyncio.sleep(1)
            if "Truth" in game_name: await context.bot.send_message(user_id, "🎲 **Game On!**\nSince I can't click buttons, just type your Question or Dare here in the chat!", parse_mode='Markdown')
            elif "Rock" in game_name: await context.bot.send_message(user_id, "✂️ **Rock Paper Scissors**\n\nType your move: *Rock, Paper, or Scissors*", parse_mode='Markdown')
        return

    last = GAME_COOLDOWNS.get(user_id, 0)
    if time.time() - last < 60:
        await context.bot.send_message(user_id, get_text(l1, "WAIT_60S").format(seconds=int(60 - (time.time() - last))))
        return
    GAME_COOLDOWNS[user_id] = time.time()

    l2 = await get_lang(partner_id)
    game_base = game_name.split("|")[0]
    r_key = "RULE_TOD" if "Truth" in game_base else ("RULE_WYR" if "Would" in game_base else "RULE_RPS")
    
    kb = [[InlineKeyboardButton(get_text(l2, "GAME_ACCEPTED"), callback_data=f"game_accept_{game_name}"), InlineKeyboardButton(get_text(l2, "GAME_REJECTED"), callback_data="game_reject")]]
    await context.bot.send_message(user_id, get_text(l1, "OFFERED").format(game=game_name), parse_mode='Markdown')
    await context.bot.send_message(partner_id, get_text(l2, "GAME_REQ").format(game=game_name, rules=get_text(l2, r_key)), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def start_game_session(update, context, game_raw, p1, p2):
    rounds = 1
    game_name = game_raw
    if "|" in game_raw:
        game_name = "Rock Paper Scissors"
        rounds = int(game_raw.split("|")[1])

    state = {"game": game_name, "turn": p2, "partner": p2, "status": "playing", "moves": {}, "max_r": rounds, "cur_r": 1, "s1": 0, "s2": 0, "streak": 0, "explained": [], "used_q": [], "spicy": False}
    GAME_STATES[p1] = GAME_STATES[p2] = state
    
    l1 = await get_lang(p1); l2 = await get_lang(p2)
    await context.bot.send_message(p1, get_text(l1, "GAME_STARTED").format(game=game_name), reply_markup=get_keyboard_game(l1), parse_mode='Markdown')
    await context.bot.send_message(p2, get_text(l2, "GAME_STARTED").format(game=game_name), reply_markup=get_keyboard_game(l2), parse_mode='Markdown')
    
    if game_name == "Truth or Dare": await send_tod_turn(context, p2)
    elif game_name == "Would You Rather": await send_wyr_round(context, p1, p2)
    elif game_name == "Rock Paper Scissors": await send_rps_round(context, p1, p2)

async def send_tod_turn(context, turn_id):
    l = await get_lang(turn_id)
    kb = [[InlineKeyboardButton(get_text(l, "PICK_TRUTH"), callback_data="tod_pick_truth"), InlineKeyboardButton(get_text(l, "PICK_DARE"), callback_data="tod_pick_dare")]]
    await context.bot.send_message(turn_id, get_text(l, "YOUR_TURN"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def send_tod_options(context, target_id, mode):
    l = await get_lang(target_id)
    is_spicy = GAME_STATES.get(target_id, {}).get("spicy", False)
    list_key = f"tod_{mode}_spicy" if is_spicy else f"tod_{mode}"
    options = random.sample(GAME_DATA[list_key], 5)
    
    icon = "🔥 " if is_spicy else "🎭 "
    msg_text = icon + get_text(l, "PICK_A").format(mode=mode.upper()).replace("🎭 ", "")
    for i, opt in enumerate(options): msg_text += f"**{i+1}.** {opt}\n"
    
    kb = [[InlineKeyboardButton("1️⃣", callback_data="tod_send_0"), InlineKeyboardButton("2️⃣", callback_data="tod_send_1"), InlineKeyboardButton("3️⃣", callback_data="tod_send_2")],
          [InlineKeyboardButton("4️⃣", callback_data="tod_send_3"), InlineKeyboardButton("5️⃣", callback_data="tod_send_4")],
          [InlineKeyboardButton(get_text(l, "ASK_OWN"), callback_data="tod_manual")]]
    
    if target_id not in GAME_STATES: GAME_STATES[target_id] = {}
    GAME_STATES[target_id]["options"] = options
    await context.bot.send_message(target_id, msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def send_wyr_round(context, p1, p2):
    gd = GAME_STATES.get(p1)
    if not gd: return

    is_spicy = gd.get("spicy", False)
    list_key = "wyr_spicy" if is_spicy else "wyr"
    
    total_options = len(GAME_DATA[list_key])
    used_key = "used_q_spicy" if is_spicy else "used_q"
    used_indices = gd.get(used_key, [])

    if len(used_indices) >= total_options:
        used_indices = []
    
    available = [i for i in range(total_options) if i not in used_indices]
    selected_index = random.choice(available)
    gd[used_key] = used_indices + [selected_index]
    
    q = GAME_DATA[list_key][selected_index]
    
    l1 = await get_lang(p1)
    l2 = await get_lang(p2)
    
    msg1 = get_text(l1, "WYR_Q").format(q1=q[0], q2=q[1])
    msg2 = get_text(l2, "WYR_Q").format(q1=q[0], q2=q[1])
    
    kb = [
        [InlineKeyboardButton("🅰️ A", callback_data="wyr_a")],
        [InlineKeyboardButton("🅱️ B", callback_data="wyr_b")]
    ]
    
    await context.bot.send_message(p1, msg1, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    await context.bot.send_message(p2, msg2, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def send_rps_round(context, p1, p2):
    kb = [[InlineKeyboardButton("🪨", callback_data="rps_rock"), InlineKeyboardButton("📄", callback_data="rps_paper"), InlineKeyboardButton("✂️", callback_data="rps_scissors")]]
    l1 = await get_lang(p1); l2 = await get_lang(p2)
    await context.bot.send_message(p1, get_text(l1, "SHOOT"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    await context.bot.send_message(p2, get_text(l2, "SHOOT"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# ==============================================================================
# 👮 ADMIN SYSTEM 
# ==============================================================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    conn = get_conn(); cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE status != 'idle'")
    online = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE report_count > 0")
    flagged = cur.fetchone()[0]
    
    cur.execute("SELECT gender, COUNT(*) FROM users GROUP BY gender")
    g_stats = " | ".join([f"{r[0]}:{r[1]}" for r in cur.fetchall()])

    def get_stat(col):
        cur.execute(f"SELECT {col}, COUNT(*) FROM users GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 3")
        return " | ".join([f"{r[0]}:{r[1]}" for r in cur.fetchall()])

    msg = (f"👮 **CONTROL ROOM**\n"
           f"👥 Total: `{total}` | 🟢 Online: `{online}`\n"
           f"⚠️ Flagged: `{flagged}`\n"
           f"🚻 **Gender:** {g_stats}\n"
           f"🌍 {get_stat('region')}\n\n"
           f"🛠️ **COMMANDS:**\n"
           f"• `/ban ID HOURS`\n"
           f"• `/warn ID REASON`\n"
           f"• `/broadcast MESSAGE`\n"
           f"• `/unban ID`")
    
    kb = [[InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_info"), InlineKeyboardButton("📜 Recent Users", callback_data="admin_users")],
          [InlineKeyboardButton("⚠️ Reports", callback_data="admin_reports"), InlineKeyboardButton("📨 Feedbacks", callback_data="admin_feedbacks")],
          [InlineKeyboardButton("🚫 Bans", callback_data="admin_banlist")]]
    
    try:
        if update.callback_query: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except error.BadRequest: pass
    cur.close(); release_conn(conn)

async def admin_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        target = int(context.args[0])
        hours = int(context.args[1])
        conn = get_conn(); cur = conn.cursor()
        ban_until = datetime.datetime.now() + datetime.timedelta(hours=hours)
        cur.execute("UPDATE users SET banned_until = %s WHERE user_id = %s", (ban_until, target))
        conn.commit(); cur.close(); release_conn(conn)
        await update.message.reply_text(f"🔨 Banned {target} for {hours}h.")
        if target in ACTIVE_CHATS: del ACTIVE_CHATS[target]
        try: await context.bot.send_message(target, f"🚫 You are banned for {hours} hours.")
        except: pass
    except: await update.message.reply_text("Usage: /ban ID HOURS")

async def admin_warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        target = int(context.args[0])
        reason = " ".join(context.args[1:])
        await context.bot.send_message(target, f"⚠️ **OFFICIAL WARNING**\n\n{reason}", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Warned {target}.")
    except: await update.message.reply_text("Usage: /warn ID REASON")

async def admin_broadcast_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    msg = " ".join(context.args)
    if not msg: return await update.message.reply_text("Usage: /broadcast MSG")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall(); cur.close(); release_conn(conn)
    await update.message.reply_text(f"📢 Sending to {len(users)} users...")
    for u in users:
        try: 
            await context.bot.send_message(u[0], f"📢 **ANNOUNCEMENT:**\n\n{msg}", parse_mode='Markdown')
            await asyncio.sleep(0.05) # 🛡️ RATE LIMIT PROTECTION
        except: pass
    await update.message.reply_text("✅ Broadcast done.")

async def handle_feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    feedback_text = update.message.text.replace("/feedback", "").strip()
    if not feedback_text: await update.message.reply_text("❌ Usage: `/feedback message`", parse_mode='Markdown'); return
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO feedback (user_id, message) VALUES (%s, %s)", (user_id, feedback_text))
    conn.commit(); cur.close(); release_conn(conn)
    await update.message.reply_text("✅ **Feedback Sent!**", parse_mode='Markdown')

# ==============================================================================
# 📝 ONBOARDING (UPDATED WITH AVATAR & NICKNAME)
# ==============================================================================
async def send_onboarding_step(update, step):
    kb, msg = [], ""
    
    if step == 1:
        msg = "1️⃣ **What's your gender?**"
        kb = [[InlineKeyboardButton("👨 Male", callback_data="set_gen_Male"), InlineKeyboardButton("👩 Female", callback_data="set_gen_Female")], 
              [InlineKeyboardButton("🌈 Other", callback_data="set_gen_Other"), InlineKeyboardButton("⏭️ Skip", callback_data="set_gen_Hidden")]]
    elif step == 2:
        msg = "2️⃣ **Age Group?**"
        kb = [[InlineKeyboardButton("👦 ~18", callback_data="set_age_~18"), InlineKeyboardButton("🧢 20-25", callback_data="set_age_20-25")], 
              [InlineKeyboardButton("💼 25-30", callback_data="set_age_25-30"), InlineKeyboardButton("☕ 30+", callback_data="set_age_30+")],
              [InlineKeyboardButton("⏭️ Skip", callback_data="set_age_Hidden")]]
    elif step == 3:
        msg = "3️⃣ **Primary Language?**"
        kb = [[InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_English"), InlineKeyboardButton("🇮🇳 Hindi", callback_data="set_lang_Hindi")],
              [InlineKeyboardButton("🇮🇩 Indo", callback_data="set_lang_Indo"), InlineKeyboardButton("🇪🇸 Spanish", callback_data="set_lang_Spanish")],
              [InlineKeyboardButton("🇫🇷 French", callback_data="set_lang_French"), InlineKeyboardButton("🇯🇵 Japanese", callback_data="set_lang_Japanese")],
              [InlineKeyboardButton("🌍 Other", callback_data="set_lang_Other"), InlineKeyboardButton("⏭️ Skip", callback_data="set_lang_English")]]
    elif step == 4:
        msg = "4️⃣ **Region?**"
        kb = [[InlineKeyboardButton("🌏 Asia 🗻", callback_data="set_reg_Asia"), InlineKeyboardButton("🌍 Europe 🍷", callback_data="set_reg_Europe")],
              [InlineKeyboardButton("🌎 America 🗽", callback_data="set_reg_America"), InlineKeyboardButton("🌍 Africa 🌴", callback_data="set_reg_Africa")],
              [InlineKeyboardButton("⏭️ Skip", callback_data="set_reg_Hidden")]]
    elif step == 5:
        msg = "5️⃣ **Current Mood?**"
        kb = [[InlineKeyboardButton("😃 Happy", callback_data="set_mood_Happy"), InlineKeyboardButton("😔 Sad", callback_data="set_mood_Sad")],
              [InlineKeyboardButton("😴 Bored", callback_data="set_mood_Bored"), InlineKeyboardButton("🤔 Don't Know", callback_data="set_mood_Confused")],
              [InlineKeyboardButton("🥀 Lonely", callback_data="set_mood_Lonely"), InlineKeyboardButton("😰 Anxious", callback_data="set_mood_Anxious")],
              [InlineKeyboardButton("⏭️ Skip", callback_data="set_mood_Neutral")]]
    elif step == 6:
        msg = "6️⃣ **Interests**\n\nType keywords (e.g., *Music, Movies,kdrama..*) or click Skip."
        kb = [[InlineKeyboardButton("⏭️ Skip to Name", callback_data="onboarding_step_7")]]
    elif step == 7:
        msg = "7️⃣ **What's your Nickname?**\n\nType a cool nickname (onii-chan, kotone) for your profile."
        kb = [[InlineKeyboardButton("⏭️ Skip (Use 'Anon')", callback_data="onboarding_step_8")]]
    elif step == 8:
        msg = "8️⃣ **Final Step! Vibe Avatar** 📸\n\nSend a cool animated image (your Ghibli, Anime,cartoon Avatar) to represent you. \n\n⚠️ *Do Not Post Real Faces or NSFW! Violators will be permanently banned.*"
        kb = [[InlineKeyboardButton("⏭️ Skip (Use Default)", callback_data="onboarding_done")]]

    try:
        if update.callback_query: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: pass

# ==============================================================================
# 📱 MAIN CONTROLLER
# ==============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 🛡️ CHECKPOINT: Prevent overwriting the chat keyboard
    if user.id in ACTIVE_CHATS:
        l = await get_lang(user.id)
        await update.message.reply_text(get_text(l, "CMD_IN_CHAT"), reply_markup=get_keyboard_chat(l), parse_mode='Markdown')
        return

    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT banned_until, gender FROM users WHERE user_id = %s", (user.id,))
    data = cur.fetchone()
    if data and data[0] and data[0] > datetime.datetime.now():
        await update.message.reply_text(f"🚫 Banned until {data[0]}."); cur.close(); release_conn(conn); return
    
    cur.execute("""INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) 
                   ON CONFLICT (user_id) DO UPDATE SET username = %s, first_name = %s""", 
                   (user.id, user.username, user.first_name, user.username, user.first_name))
    conn.commit(); cur.close(); release_conn(conn)

    welcome_msg = "👋 **Welcome to OmeTV Chatbot🤖**\n\nConnect with strangers worldwide 🌍\nNo names. No login. End to End encrypted\n\n*Let's vibe check.* 👇"
    if not data or data[1] == 'Hidden':
        await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        await send_onboarding_step(update, 1)
    else:
        msg = await update.message.reply_text("🔄 Loading...", reply_markup=ReplyKeyboardRemove())
        try: await context.bot.delete_message(chat_id=user.id, message_id=msg.message_id)
        except: pass
        await show_main_menu(update)

# ==============================================================================
# 🔌 FAST CONNECTION LOGIC (Trading Card UI)
# ==============================================================================
async def execute_ghost_search(context, user_id, u_gender, u_region):
    await asyncio.sleep(15)  
    conn = get_conn()
    if not conn: return
    cur = conn.cursor()
    cur.execute("SELECT status FROM users WHERE user_id = %s", (user_id,))
    status = cur.fetchone(); cur.close(); release_conn(conn)
    
    if status and status[0] == 'searching':
        persona = GHOST.pick_random_persona() 
        user_ctx = {'gender': u_gender, 'country': u_region}
        success = await GHOST.start_chat(user_id, persona, "Hidden", user_ctx)
        
        if success:
            ACTIVE_CHATS[user_id] = f"AI_{persona}"
            l = await get_lang(user_id)
            
            card = (f"🪪 **OFFICIAL ANON ID**\n━━━━━━━━━━━━━━━\n"
                    f"👤 **Name:** Anon\n👑 **Status:** 🌟 Trusted Veteran\n🎭 **Vibe:** Random\n\n"
                    f"📊 **STATS:**\n🔗 **Common:** Random\n\n⚠️ *Say Hi to start chatting!*")
            try: 
                await context.bot.send_message(user_id, f"🖼️ [Ghost Avatar]\n\n{card}", parse_mode='Markdown')
                await context.bot.send_message(user_id, "🎮 Menu unlocked below.", reply_markup=get_keyboard_chat(l))
            except: pass

async def connect_users(context, user_id, partner_id, common, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen):
    for uid in [user_id, partner_id]:
        if isinstance(ACTIVE_CHATS.get(uid), str):
            if uid in GAME_STATES: del GAME_STATES[uid]
            
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET status='chatting', partner_id=%s WHERE user_id=%s", (partner_id, user_id))
    cur.execute("UPDATE users SET status='chatting', partner_id=%s WHERE user_id=%s", (user_id, partner_id))
    
    cur.execute("SELECT nickname, avatar_id, karma_score, gender, mood FROM users WHERE user_id=%s", (user_id,))
    u1 = cur.fetchone()
    conn.commit(); cur.close(); release_conn(conn)
    
    u1_nick = u1[0] if u1 else "Anon"
    u1_ava = u1[1] if u1 else None
    u1_karma = u1[2] if u1 else 100
    u1_gen = u1[3] if u1 else "Hidden"
    u1_mood = u1[4] if u1 else "Neutral"
    
    ACTIVE_CHATS[user_id] = partner_id; ACTIVE_CHATS[partner_id] = user_id
    common_str = ", ".join(common).title() if common else "Random"
    l1 = await get_lang(user_id); l2 = await get_lang(partner_id)
    
    def get_title(k): return "🌟 Trusted Veteran" if k >= 150 else ("⚠️ Suspect" if k <= 50 else "🌱 Rookie")
    def get_def(g): return DEFAULT_MALE if g == "Male" else (DEFAULT_FEMALE if g == "Female" else DEFAULT_OTHER)

    c1 = f"🪪 **OFFICIAL ANON ID**\n━━━━━━━━━━━━━━━\n👤 **Name:** {p_nick}\n👑 **Status:** {get_title(p_karma)}\n🎭 **Vibe:** {p_mood}\n\n📊 **STATS:**\n🔗 **Common:** {common_str}\n\n⚠️ *Say Hi to start chatting!*"
    a1 = p_ava if p_ava else get_def(p_gen)
    kb1 = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 Report Profile", callback_data=f"report_profile_{partner_id}")]])
    
    c2 = f"🪪 **OFFICIAL ANON ID**\n━━━━━━━━━━━━━━━\n👤 **Name:** {u1_nick}\n👑 **Status:** {get_title(u1_karma)}\n🎭 **Vibe:** {u1_mood}\n\n📊 **STATS:**\n🔗 **Common:** {common_str}\n\n⚠️ *Say Hi to start chatting!*"
    a2 = u1_ava if u1_ava else get_def(u1_gen)
    kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 Report Profile", callback_data=f"report_profile_{user_id}")]])
    
    for target, av, cap, kb, lang in [(user_id, a1, c1, kb1, l1), (partner_id, a2, c2, kb2, l2)]:
        try:
            if av and av != "MALE_FILE_ID_HERE" and av != "FEMALE_FILE_ID_HERE" and av != "OTHER_FILE_ID_HERE": 
                await context.bot.send_photo(target, photo=av, caption=cap, reply_markup=kb, parse_mode='Markdown')
            else: 
                await context.bot.send_message(target, f"🖼️ [No Avatar Set]\n\n{cap}", reply_markup=kb, parse_mode='Markdown')
            await context.bot.send_message(target, "🎮 Menu unlocked below.", reply_markup=get_keyboard_chat(lang))
        except Exception as e: 
            print("Card Error:", e)

async def stop_search_process(update, context):
    user_id = update.effective_user.id
    l = await get_lang(user_id)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET status = 'idle' WHERE user_id = %s", (user_id,))
    conn.commit(); cur.close(); release_conn(conn)
    try:
        if update.callback_query: await update.callback_query.message.reply_text(get_text(l, "STOPPED_SEARCH"), reply_markup=get_keyboard_lobby(l), parse_mode='Markdown')
        else: await update.message.reply_text(get_text(l, "STOPPED_SEARCH"), reply_markup=get_keyboard_lobby(l), parse_mode='Markdown')
    except: pass

async def start_search(update, context):
    user_id = update.effective_user.id
    l = await get_lang(user_id)
    if user_id in ACTIVE_CHATS: await update.message.reply_text(get_text(l, "ALREADY_IN_CHAT"), parse_mode='Markdown'); return
    
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET status = 'searching' WHERE user_id = %s", (user_id,))
    cur.execute("SELECT gender, region, interests FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone(); u_gender = row[0] if row else "Hidden"; u_region = row[1] if row else "Unknown"; tags = row[2] or "Any"
    conn.commit(); cur.close(); release_conn(conn)
    
    await update.message.reply_text(get_text(l, "SEARCHING_MSG").format(tags=tags), parse_mode='Markdown', reply_markup=get_keyboard_searching(l))
    partner_id, common, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen = find_match(user_id)
    
    if partner_id:
        partner_chat_state = ACTIVE_CHATS.get(partner_id)
        if isinstance(partner_chat_state, str) and partner_chat_state.startswith("AI_"):
            del ACTIVE_CHATS[partner_id]
            conn = get_conn(); cur = conn.cursor()
            cur.execute("UPDATE users SET status='idle' WHERE user_id = %s", (partner_id,))
            conn.commit(); cur.close(); release_conn(conn)
            p_l = await get_lang(partner_id)
            kb_feedback = [[InlineKeyboardButton("👍", callback_data="rate_like_AI"), InlineKeyboardButton("👎", callback_data="rate_dislike_AI")], [InlineKeyboardButton("⚠️ Report", callback_data="rate_report_AI")]]
            try:
                await context.bot.send_message(partner_id, get_text(p_l, "DISCONNECTED"), reply_markup=get_keyboard_lobby(p_l), parse_mode='Markdown')
                await context.bot.send_message(partner_id, get_text(p_l, "RATE_STRANGER"), reply_markup=InlineKeyboardMarkup(kb_feedback))
            except: pass
        else:
            await connect_users(context, user_id, partner_id, common, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen)
            return 
    asyncio.create_task(execute_ghost_search(context, user_id, u_gender, u_region))

async def perform_match(update, context, user_id):
    partner_id, common, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen = find_match(user_id)
    if partner_id: await connect_users(context, user_id, partner_id, common, p_mood, p_lang, p_nick, p_ava, p_karma, p_gen)

async def stop_chat(update, context, is_next=False):
    user_id = update.effective_user.id
    l = await get_lang(user_id)
    partner_id = ACTIVE_CHATS.pop(user_id, 0)
    
    if user_id in TRANSLATE_ENABLED: TRANSLATE_ENABLED.remove(user_id)
    if partner_id in TRANSLATE_ENABLED: TRANSLATE_ENABLED.remove(partner_id)
    
    keys_to_remove = [k for k in MESSAGE_MAP if k[0] in (user_id, partner_id)]
    for k in keys_to_remove: del MESSAGE_MAP[k]
    if user_id in GAME_STATES: del GAME_STATES[user_id]

    if isinstance(partner_id, int) and partner_id > 0:
        if partner_id in ACTIVE_CHATS: del ACTIVE_CHATS[partner_id]
        if partner_id in GAME_STATES: del GAME_STATES[partner_id]
        
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE users SET status='idle', partner_id=0 WHERE user_id IN (%s, %s)", (user_id, partner_id))
        conn.commit(); cur.close(); release_conn(conn)
        
        p_lang = await get_lang(partner_id)
        k_partner = [[InlineKeyboardButton("👍", callback_data=f"rate_like_{user_id}"), InlineKeyboardButton("👎", callback_data=f"rate_dislike_{user_id}")], [InlineKeyboardButton("⚠️ Report", callback_data=f"rate_report_{user_id}")]]
        try: 
            await context.bot.send_message(partner_id, get_text(p_lang, "DISCONNECTED"), reply_markup=get_keyboard_lobby(p_lang), parse_mode='Markdown')
            await context.bot.send_message(partner_id, get_text(p_lang, "RATE_STRANGER"), reply_markup=InlineKeyboardMarkup(k_partner))
        except: pass

    elif isinstance(partner_id, str):
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE users SET status='idle' WHERE user_id = %s", (user_id,))
        conn.commit(); cur.close(); release_conn(conn)

    target_id = partner_id if isinstance(partner_id, int) else "AI"
    k_me = [[InlineKeyboardButton("👍", callback_data=f"rate_like_{target_id}"), InlineKeyboardButton("👎", callback_data=f"rate_dislike_{target_id}")], [InlineKeyboardButton("⚠️ Report", callback_data=f"rate_report_{target_id}")]]
    
    if is_next:
        await update.message.reply_text(get_text(l, "SKIPPING"), reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        await update.message.reply_text(get_text(l, "RATE_PREV"), reply_markup=InlineKeyboardMarkup(k_me))
        await start_search(update, context)
    else:
        await update.message.reply_text(get_text(l, "DISCONNECTED"), reply_markup=get_keyboard_lobby(l), parse_mode='Markdown')
        await update.message.reply_text(get_text(l, "RATE_STRANGER"), reply_markup=InlineKeyboardMarkup(k_me))

# ==============================================================================
# 🗣️ MESSAGE RELAY & TEXT HANDLERS
# ==============================================================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🆘 **USER GUIDE**\n\n"
        "**1. How to Chat?**\nClick '🚀 Start Matching'. You will be connected to a random stranger.\n\n"
        "**2. The Games**\nClick '🎮 Games' inside a chat to challenge your partner.\n\n"
        "**3. Safety First**\n• End to End Encrypted.\n• To leave: Click '🛑 Stop'.\n• Behave Respectful to avoid Permanent **BAN**.\n\n"
        "**4. Commands**\n/start - Restart Bot\n/feedback [msg] - Send your feedback"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message_reaction: return
    user_id = update.effective_user.id
    partner_id = ACTIVE_CHATS.get(user_id)
    if not partner_id or isinstance(partner_id, str): return 
    
    target_msg_id = None
    for (rec_id, rec_msg_id), snd_msg_id in MESSAGE_MAP.items():
        if rec_id == user_id and rec_msg_id == update.message_reaction.message_id:
            target_msg_id = snd_msg_id
            break
    
    if target_msg_id:
        try: await context.bot.set_message_reaction(chat_id=partner_id, message_id=target_msg_id, reaction=update.message_reaction.new_reaction)
        except: pass

async def relay_message(update, context):
    user_id = update.effective_user.id
    
# --- INTERCEPT AVATAR UPLOADS ---
    if context.user_data.get("state") == "ONBOARDING_AVATAR" and update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update_user(user_id, "avatar_id", file_id)
        context.user_data["state"] = None
        await update.message.reply_text(f"✅ **Profile Complete!**\n\nYOUR ID IS:\n`{file_id}`", reply_markup=get_keyboard_lobby(await get_lang(user_id)), parse_mode='Markdown')
        return

    l = await get_lang(user_id)
    partner_id = ACTIVE_CHATS.get(user_id)
    if not partner_id: return 

    # --- PARTNER IS AI ---
    if isinstance(partner_id, str) and partner_id.startswith("AI_"):
        msg_text = update.message.text
        if msg_text and msg_text.lower() in ['rock', 'paper', 'scissors']:
            ai_move = random.choice(['rock', 'paper', 'scissors'])
            user_move = msg_text.lower()
            result = get_text(l, "DRAW")
            if (user_move == 'rock' and ai_move == 'scissors') or (user_move == 'paper' and ai_move == 'rock') or (user_move == 'scissors' and ai_move == 'paper'):
                result = get_text(l, "WON_MATCH")
            elif user_move != ai_move:
                result = get_text(l, "LOST_MATCH")
            await asyncio.sleep(1)
            await update.message.reply_text(f"I picked **{ai_move.title()}**.\n\n{result}", parse_mode='Markdown')
            return

        if msg_text:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            result = await GHOST.process_message(user_id, msg_text)
            if result in ["TRIGGER_SKIP", "TRIGGER_INDIAN_MALE_BEG"]:
                await stop_chat(update, context)
                return
            if isinstance(result, dict) and result.get("type") == "text":
                reply_text = result['content']
                triggers = ["bye", "skip", "stop", "boring", "bsdk", "hat", "leave", "gtg"]
                is_leaving = any(f" {t} " in f" {reply_text.lower()} " for t in triggers)
                is_ghosting = random.random() < 0.05
                if is_leaving or is_ghosting:
                    if not is_ghosting:
                        await asyncio.sleep(result['delay'])
                        await update.message.reply_text(reply_text)
                    await asyncio.sleep(1) 
                    await stop_chat(update, context)
                    return
                await asyncio.sleep(result['delay'])
                await update.message.reply_text(reply_text)
        return

    # --- PARTNER IS HUMAN ---
    if partner_id:
        p_lang = await get_lang(partner_id)
        if user_id in GAME_STATES and GAME_STATES[user_id].get("status") == "discussing":
            gd = GAME_STATES[user_id]
            try:
                await update.message.copy(chat_id=partner_id, caption=get_text(p_lang, "BECAUSE"))
                await update.message.reply_text(get_text(l, "EXPLANATION_SENT"))
                if "explained" not in gd: gd["explained"] = []
                if user_id not in gd["explained"]: gd["explained"].append(user_id)
                if len(gd["explained"]) >= 2:
                    await context.bot.send_message(user_id, get_text(l, "NEXT_ROUND"))
                    await context.bot.send_message(partner_id, get_text(p_lang, "NEXT_ROUND"))
                    gd["status"] = "playing"; gd["explained"] = []
                    await asyncio.sleep(1.5)
                    await send_wyr_round(context, user_id, partner_id)
            except Exception as e: print(f"WYR Error: {e}")
            return

        if user_id in GAME_STATES and GAME_STATES[user_id].get("status") == "answering" and GAME_STATES[user_id].get("turn") == user_id:
            try: 
                if update.message.photo or update.message.video or update.message.video_note or update.message.voice:
                    duration = update.message.video.duration if update.message.video else (update.message.voice.duration if update.message.voice else (update.message.video_note.duration if update.message.video_note else 0))
                    cap = "📸" if update.message.photo else "📹"
                    cb = f"secret_{user_id}_{update.message.message_id}_{duration}"
                    await context.bot.send_message(partner_id, get_text(p_lang, "SECRET_RX").format(cap=cap), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🔓", callback_data=cb)]]), parse_mode='Markdown')
                else:
                    await update.message.copy(chat_id=partner_id, caption=get_text(p_lang, "ANSWER"))
                
                await update.message.reply_text(get_text(l, "ANSWER_SENT"))
                GAME_STATES[user_id]["status"] = "playing"
                if partner_id in GAME_STATES: GAME_STATES[partner_id]["status"] = "playing"
                GAME_STATES[user_id]["turn"] = partner_id; GAME_STATES[partner_id]["turn"] = partner_id
                await send_tod_turn(context, partner_id)
                return 
            except: pass

        if update.message:
            if update.message.photo or update.message.video or update.message.video_note or update.message.voice:
                duration = 0
                caption = "📸"
                if update.message.video: caption = "📹"; duration = update.message.video.duration or 0
                elif update.message.voice: caption = "🗣️"; duration = update.message.voice.duration or 0
                elif update.message.video_note: caption = "⏺"; duration = update.message.video_note.duration or 0
                
                callback_data = f"secret_{user_id}_{update.message.message_id}_{duration}"
                kb = [[InlineKeyboardButton(f"🔓 {caption}", callback_data=callback_data)]]
                await context.bot.send_message(partner_id, get_text(p_lang, "SECRET_RX").format(cap=caption), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                await update.message.reply_text(get_text(l, "SECRET_SENT"), parse_mode='Markdown')
                return 

            if update.message.text:
                conn = get_conn(); cur = conn.cursor()
                cur.execute("INSERT INTO chat_logs (sender_id, receiver_id, message) VALUES (%s, %s, %s)", (user_id, partner_id, update.message.text))
                conn.commit(); cur.close(); release_conn(conn)
            
            try:
                reply_target_id = None
                if update.message.reply_to_message:
                    reply_target_id = MESSAGE_MAP.get((user_id, update.message.reply_to_message.message_id))
                    if not reply_target_id:
                        for (rec_id, rec_msg_id), snd_msg_id in MESSAGE_MAP.items():
                            if rec_id == partner_id and snd_msg_id == update.message.reply_to_message.message_id:
                                reply_target_id = rec_msg_id
                                break
                
                # --- 🔤 TRANSLATION INTERCEPT ---
                if update.message.text and partner_id in TRANSLATE_ENABLED:
                    p_lang = await get_lang(partner_id)
                    translated = await translate_text(update.message.text, p_lang)
                    if translated and translated.lower() != update.message.text.lower():
                        final_text = f"{update.message.text}\n💬 *[{translated}]*"
                    else:
                        final_text = update.message.text
                    sent_msg = await context.bot.send_message(chat_id=partner_id, text=final_text, reply_to_message_id=reply_target_id, parse_mode='Markdown')
                else:
                    sent_msg = await update.message.copy(chat_id=partner_id, reply_to_message_id=reply_target_id)
                
                if sent_msg: MESSAGE_MAP[(partner_id, sent_msg.message_id)] = update.message.message_id
            except: await stop_chat(update, context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    text = update.message.text
    user_id = update.effective_user.id
    l = await get_lang(user_id)

    if context.user_data.get("state") == "GAME_MANUAL":
        partner_id = ACTIVE_CHATS.get(user_id)
        if partner_id:
             p_lang = await get_lang(partner_id)
             await context.bot.send_message(partner_id, get_text(p_lang, "QUESTION").format(q=text), parse_mode='Markdown')
             await update.message.reply_text(get_text(l, "ASKED").format(q=text))
             if partner_id in GAME_STATES:
                 GAME_STATES[partner_id]["status"] = "answering"; GAME_STATES[partner_id]["turn"] = partner_id
        context.user_data["state"] = None
        return

    # --- ONBOARDING & EDITS ---
    state = context.user_data.get("state")
    if state == "ONBOARDING_INTEREST":
        await update_user(user_id, "interests", text)
        context.user_data["state"] = "ONBOARDING_NICKNAME"
        await send_onboarding_step(update, 7); return
    if state == "ONBOARDING_NICKNAME":
        await update_user(user_id, "nickname", text[:20]) 
        context.user_data["state"] = "ONBOARDING_AVATAR"
        await send_onboarding_step(update, 8); return
    if state == "ONBOARDING_AVATAR":
        await update.message.reply_text("⚠️ Please send an **IMAGE**, or click Skip."); return

    if text in [x["START_BTN"] for x in locale_data.TEXTS.values()]: await start_search(update, context); return
    if text in [x["STOP_SEARCH"] for x in locale_data.TEXTS.values()]: await stop_search_process(update, context); return
    
    if text in [x["CHANGE_INTERESTS"] for x in locale_data.TEXTS.values()]: 
        context.user_data["state"] = "ONBOARDING_INTEREST"
        await update.message.reply_text("👇 Type interests:", reply_markup=ReplyKeyboardRemove()); return

    all_settings = [x["SETTINGS"] for x in locale_data.TEXTS.values()]
    if text in all_settings:
        kb = [
            [InlineKeyboardButton("🚻 Gender", callback_data="set_gen_menu"), InlineKeyboardButton("🎂 Age", callback_data="set_age_menu")],
            [InlineKeyboardButton("🗣️ Lang", callback_data="set_lang_menu"), InlineKeyboardButton("🎭 Mood", callback_data="set_mood_menu")],
            [InlineKeyboardButton("📝 Name", callback_data="edit_nickname"), InlineKeyboardButton("📸 Avatar", callback_data="edit_avatar")],
            [InlineKeyboardButton("🔙 Close", callback_data="close_settings")]
        ]
        await update.message.reply_text("⚙️ **Settings:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return

    if text in [x["MY_ID"] for x in locale_data.TEXTS.values()]: await show_profile(update, context); return
    if text in [x["HELP"] for x in locale_data.TEXTS.values()]: await help_command(update, context); return

    all_stops = [x["BTN_STOP"] for x in locale_data.TEXTS.values()] + [x["BTN_STOP_CHAT"] for x in locale_data.TEXTS.values()]
    if text in all_stops or text == "🛑 Stop": await stop_chat(update, context); return
    if text in [x["BTN_NEXT"] for x in locale_data.TEXTS.values()] or text == "⏭️ Next": await stop_chat(update, context, is_next=True); return
    
    # --- TRANSLATE BUTTONS & CATCH-UP LOGIC ---
    all_trans_on = [x.get("BTN_TRANS_ON", "🔤 Translate") for x in locale_data.TEXTS.values()] + ["🔤 Translate"]
    if text in all_trans_on:
        pid = ACTIVE_CHATS.get(user_id)
        if not pid or isinstance(pid, str): return
        TRANSLATE_ENABLED.add(user_id)
        
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT message FROM chat_logs WHERE sender_id = %s AND receiver_id = %s ORDER BY timestamp DESC LIMIT 3", (pid, user_id))
        rows = cur.fetchall(); cur.close(); release_conn(conn)
        
        if rows:
            combined = "\n".join([r[0] for r in reversed(rows)])
            translated = await translate_text(combined, l)
            await update.message.reply_text(get_text(l, "TRANS_CATCHUP").format(text=translated), reply_markup=get_keyboard_chat(l, True), parse_mode='Markdown')
        else:
            await update.message.reply_text("🔄 **Translation ON.**", reply_markup=get_keyboard_chat(l, True), parse_mode='Markdown')
        return

    all_trans_off = [x.get("BTN_TRANS_OFF", "🧊 Stop Translate") for x in locale_data.TEXTS.values()] + ["🧊 Stop Translate"]
    if text in all_trans_off:
        if user_id in TRANSLATE_ENABLED: TRANSLATE_ENABLED.remove(user_id)
        await update.message.reply_text("💧 **Translation OFF.**", reply_markup=get_keyboard_chat(l, False), parse_mode='Markdown')
        return
    
    if text in [x["BTN_GAMES"] for x in locale_data.TEXTS.values()] or text == "🎮 Games":
        kb = [[InlineKeyboardButton("😈 Truth or Dare", callback_data="game_offer_Truth or Dare")],
              [InlineKeyboardButton("🎲 Would You Rather", callback_data="game_offer_Would You Rather")],
              [InlineKeyboardButton("✂️ Rock Paper Scissors", callback_data="rps_mode_select")]]
        await update.message.reply_text(get_text(l, "GAME_CENTER"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return
    
    if text in [x["BTN_STOP_GAME"] for x in locale_data.TEXTS.values()] or text == "🛑 Stop Game":
        pid = ACTIVE_CHATS.get(user_id)
        if user_id in GAME_STATES: del GAME_STATES[user_id]
        if pid and pid in GAME_STATES: del GAME_STATES[pid]
        await update.message.reply_text(get_text(l, "GAME_STOPPED"), reply_markup=get_keyboard_chat(l))
        if pid: 
            p_lang = await get_lang(pid)
            await context.bot.send_message(pid, get_text(p_lang, "PARTNER_STOPPED_GAME"), reply_markup=get_keyboard_chat(p_lang))
        return

    all_spicy = [x["BTN_SPICY_MODE"] for x in locale_data.TEXTS.values()] + ["🌶️ Spicy Mode"]
    if text in all_spicy:
        pid = ACTIVE_CHATS.get(user_id)
        if not pid or isinstance(pid, str): return
        last = GAME_COOLDOWNS.get(f"spicy_{user_id}", 0)
        if time.time() - last < 60:
            await update.message.reply_text(get_text(l, "WAIT_60S").format(seconds=int(60 - (time.time() - last))))
            return
        GAME_COOLDOWNS[f"spicy_{user_id}"] = time.time()
        p_lang = await get_lang(pid)
        kb = [[InlineKeyboardButton(get_text(p_lang, "BTN_SPICY_ACCEPT"), callback_data="spicy_accept"), InlineKeyboardButton(get_text(p_lang, "BTN_SPICY_REJECT"), callback_data="spicy_reject")]]
        await update.message.reply_text("⏳ Request sent to partner...")
        await context.bot.send_message(pid, get_text(p_lang, "SPICY_REQ"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    all_normal = [x["BTN_NORMAL_MODE"] for x in locale_data.TEXTS.values()] + ["🧊 Turn off Spicy Mode"]
    if text in all_normal:
        pid = ACTIVE_CHATS.get(user_id)
        if user_id in GAME_STATES: GAME_STATES[user_id]["spicy"] = False
        if pid and pid in GAME_STATES: GAME_STATES[pid]["spicy"] = False
        await update.message.reply_text(get_text(l, "SPICY_OFF"), reply_markup=get_keyboard_game(l, False), parse_mode='Markdown')
        if pid:
            p_lang = await get_lang(pid)
            await context.bot.send_message(pid, get_text(p_lang, "SPICY_OFF"), reply_markup=get_keyboard_game(p_lang, False), parse_mode='Markdown')
        return

    if text.startswith("/"):
        cmd = text.lower().strip()
        if cmd == "/search":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT status FROM users WHERE user_id = %s", (user_id,))
            status_row = cur.fetchone(); cur.close(); release_conn(conn)
            
            if user_id in ACTIVE_CHATS: await update.message.reply_text(get_text(l, "CMD_IN_CHAT"), parse_mode='Markdown')
            elif status_row and status_row[0] == 'searching': await update.message.reply_text(get_text(l, "CMD_IN_WAIT"), parse_mode='Markdown')
            else: await start_search(update, context)
            return

        if cmd == "/stop": 
            if user_id not in ACTIVE_CHATS: await update.message.reply_text(get_text(l, "CMD_NOT_IN_CHAT_STOP"), parse_mode='Markdown')
            else: await stop_chat(update, context)
            return

        if cmd == "/next": 
            if user_id not in ACTIVE_CHATS: await update.message.reply_text(get_text(l, "CMD_NOT_IN_CHAT_NEXT"), parse_mode='Markdown')
            else: await stop_chat(update, context, is_next=True)
            return
        
        if cmd == "/admin": await admin_panel(update, context); return
        if cmd.startswith("/ban"): await admin_ban_command(update, context); return
        if cmd.startswith("/warn"): await admin_warn_command(update, context); return
        if cmd.startswith("/broadcast"): await admin_broadcast_execute(update, context); return
        if cmd.startswith("/feedback"): await handle_feedback_command(update, context); return

    await relay_message(update, context)

# ==============================================================================
# 🧩 HELPERS & BUTTON HANDLER
# ==============================================================================
async def send_reroll_option(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT status FROM users WHERE user_id = %s", (user_id,))
    status = cur.fetchone(); cur.close(); release_conn(conn)
    
    if status and status[0] == 'searching':
        l = await get_lang(user_id)
        kb = [[InlineKeyboardButton("🔔", callback_data="notify_me")], [InlineKeyboardButton("📡", callback_data="keep_searching")]]
        try: await context.bot.send_message(user_id, get_text(l, "WAIT_NOTIFY"), reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        except: pass

async def show_profile(update, context):
    user_id = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language, interests, karma_score, gender, age_range, region, mood, nickname, avatar_id FROM users WHERE user_id = %s", (user_id,))
    data = cur.fetchone(); cur.close(); release_conn(conn)
    text = f"🪪 **MY ANON ID**\n━━━━━━━━━━━━━━━━\n👤 **Name:** {data[7]}\n🗣️ **Lang:** {data[0]}\n🏷️ **Tags:** {data[1]}\n🚻 **Gen:** {data[3]}\n🎂 **Age:** {data[4]}\n🌍 **Reg:** {data[5]}\n🎭 **Vibe:** {data[6]}\n🛡️ **Karma:** {data[2]}"
    
    try:
        if data[8] and data[8] not in ["MALE_FILE_ID_HERE", "FEMALE_FILE_ID_HERE", "OTHER_FILE_ID_HERE"]:
            await update.message.reply_photo(photo=data[8], caption=text, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🖼️ [No Custom Avatar]\n\n{text}", parse_mode='Markdown')
    except:
        await update.message.reply_text(text, parse_mode='Markdown')

async def show_main_menu(update):
    user = update.effective_user
    l = await get_lang(user.id)
    kb = get_keyboard_lobby(l)
    try: 
        if update.message: await update.message.reply_text("👋", reply_markup=kb, parse_mode='Markdown')
        elif update.callback_query: await update.callback_query.message.reply_text("⏳", reply_markup=kb, parse_mode='Markdown')
    except: pass

async def handle_report(update, context, reporter, reported):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET report_count = report_count + 1 WHERE user_id = %s RETURNING report_count", (reported,))
    cnt = cur.fetchone()[0]
    cur.execute("INSERT INTO reports (reporter_id, reported_id, reason) VALUES (%s, %s, 'Report')", (reporter, reported))
    conn.commit()
    if cnt >= 3:
        cur.execute("SELECT message FROM chat_logs WHERE sender_id = %s ORDER BY timestamp DESC LIMIT 5", (reported,))
        logs = [l[0] for l in cur.fetchall()]
        msg = f"🚨 **REPORT (3+)**\nUser: `{reported}`\nLogs: {logs}"
        kb = [[InlineKeyboardButton(f"🔨 BAN {reported}", callback_data=f"ban_user_{reported}")]]
        for a in ADMIN_IDS:
            try: await context.bot.send_message(a, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: pass
    cur.close(); release_conn(conn)

async def update_user(user_id, col, val):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"UPDATE users SET {col} = %s WHERE user_id = %s", (val, user_id))
    conn.commit(); cur.close(); release_conn(conn)
    if col == "language": USER_LANGS[user_id] = val 

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id
    l = await get_lang(uid)

    if data == "rps_mode_select":
        kb = [[InlineKeyboardButton("Best of 3", callback_data="game_offer_Rock paper Scissors|3"), InlineKeyboardButton("Best of 5", callback_data="game_offer_Rock paper Scissors|5")]]
        await q.edit_message_text("🔢", reply_markup=InlineKeyboardMarkup(kb)); return
    
    if data.startswith("secret_"):
        try:
            _, sender_id, msg_id, duration_str = data.split("_")
            duration = int(duration_str)
            timeout = 15 if duration == 0 else (duration + 30)
            await q.edit_message_text(f"🔓 **{timeout}s...**")
            sent_media = await context.bot.copy_message(chat_id=uid, from_chat_id=int(sender_id), message_id=int(msg_id), protect_content=True, caption=f"⏱️ **{timeout}s...**", parse_mode='Markdown')
            
            # 🛡️ Run the timer in the background so the bot doesn't freeze
            async def delete_secret(chat_id, message_id, wait_time):
                await asyncio.sleep(wait_time)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    await context.bot.send_message(chat_id, "💣")
                except: pass

            asyncio.create_task(delete_secret(uid, sent_media.message_id, timeout))
            
        except Exception:
            try: await q.edit_message_text("❌")
            except: pass
        return
        
    if data == "set_gen_menu": await send_onboarding_step(update, 1); return
    if data == "set_age_menu": await send_onboarding_step(update, 2); return
    if data == "set_lang_menu": await send_onboarding_step(update, 3); return
    if data == "set_mood_menu": await send_onboarding_step(update, 5); return
    if data == "close_settings": await q.delete_message(); return
    
    if data.startswith("set_gen_"): await update_user(uid, "gender", data.split("_")[2]); await send_onboarding_step(update, 2); return
    if data.startswith("set_age_"): await update_user(uid, "age_range", data.split("_")[2]); await send_onboarding_step(update, 3); return
    if data.startswith("set_lang_"): await update_user(uid, "language", data.split("_")[2]); await send_onboarding_step(update, 4); return
    if data.startswith("set_reg_"): await update_user(uid, "region", data.split("_")[2]); await send_onboarding_step(update, 5); return
    if data.startswith("set_mood_"): await update_user(uid, "mood", data.split("_")[2]); context.user_data["state"] = "ONBOARDING_INTEREST"; await send_onboarding_step(update, 6); return
    if data == "onboarding_step_7": context.user_data["state"] = "ONBOARDING_NICKNAME"; await send_onboarding_step(update, 7); return
    if data == "onboarding_step_8": context.user_data["state"] = "ONBOARDING_AVATAR"; await send_onboarding_step(update, 8); return
    if data == "onboarding_done": context.user_data["state"] = None; await show_main_menu(update); return

    if data == "edit_nickname": context.user_data["state"] = "ONBOARDING_NICKNAME"; await q.edit_message_text("👇 Type new nickname:"); return
    if data == "edit_avatar": context.user_data["state"] = "ONBOARDING_AVATAR"; await q.edit_message_text("📸 Send new avatar image:"); return

   # ADMIN: PROFILE REPORTING SYSTEM
    if data.startswith("report_profile_"):
        target_id = data.split("_")[2]
        try: await q.edit_message_caption("🚨 Report sent to admins.")
        except: 
            try: await q.edit_message_text("🚨 Report sent to admins.")
            except: pass
        
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT nickname, avatar_id FROM users WHERE user_id = %s", (int(target_id),))
        t_data = cur.fetchone(); cur.close(); release_conn(conn)
        if t_data:
            akb = [[InlineKeyboardButton("🗑️ Delete Avatar", callback_data=f"admin_del_avatar_{target_id}"), InlineKeyboardButton("🔨 Ban User", callback_data=f"ban_user_{target_id}")],
                   [InlineKeyboardButton("✅ Innocent", callback_data=f"admin_ignore_rep_{target_id}")]]
            for a in ADMIN_IDS:
                try:
                    rep_msg = f"🚨 **PROFILE REPORT**\nID: `{target_id}`\nName: {t_data[0]}"
                    if t_data[1] and t_data[1] not in ["MALE_FILE_ID_HERE", "FEMALE_FILE_ID_HERE", "OTHER_FILE_ID_HERE"]: 
                        await context.bot.send_photo(a, photo=t_data[1], caption=rep_msg, reply_markup=InlineKeyboardMarkup(akb), parse_mode='Markdown')
                    else: 
                        await context.bot.send_message(a, f"[No Avatar]\n{rep_msg}", reply_markup=InlineKeyboardMarkup(akb), parse_mode='Markdown')
                except: pass
        return

    if data.startswith("admin_del_avatar_"):
        if uid not in ADMIN_IDS: return
        target_id = data.split("_")[3]
        await update_user(int(target_id), "avatar_id", None)
        try: await context.bot.send_message(int(target_id), "⚠️ **WARNING:** Your avatar was removed by an admin for violating guidelines.", parse_mode='Markdown')
        except: pass
        try: await q.edit_message_caption("🗑️ Avatar Deleted & User Warned.")
        except: 
            try: await q.edit_message_text("🗑️ Avatar Deleted & User Warned.")
            except: pass
        return

    if data.startswith("admin_ignore_rep_"):
        if uid not in ADMIN_IDS: return
        try: await q.edit_message_caption("✅ Report Dismissed.")
        except: 
            try: await q.edit_message_text("✅ Report Dismissed.")
            except: pass
        return

    if uid in ADMIN_IDS:
        if data == "admin_home": await admin_panel(update, context); return
        if data.startswith("ban_user_"): 
            target_id = int(data.split("_")[2])
            conn = get_conn(); cur = conn.cursor()
            ban_until = datetime.datetime.now() + datetime.timedelta(hours=24) # Instantly bans for 24 hours
            cur.execute("UPDATE users SET banned_until = %s WHERE user_id = %s", (ban_until, target_id))
            conn.commit(); cur.close(); release_conn(conn)
            if target_id in ACTIVE_CHATS: del ACTIVE_CHATS[target_id]
            try: await context.bot.send_message(target_id, "🚫 You have been BANNED by an admin for 24 hours.", reply_markup=ReplyKeyboardRemove())
            except: pass
            try: await q.edit_message_caption(f"🔨 Banned User {target_id} for 24h.")
            except: 
                try: await q.edit_message_text(f"🔨 Banned User {target_id} for 24h.")
                except: pass
            return
# --- 1. BROADCAST INFO ---
        if data == "admin_broadcast_info":
            text = "📢 **How to Broadcast:**\nType `/broadcast Your Message Here` in the chat. It will instantly send your message to ALL registered users."
            kb = [[InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return

        # --- 2. RECENT USERS ---
        if data == "admin_users":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT user_id, nickname, first_name, joined_at FROM users ORDER BY joined_at DESC LIMIT 15")
            rows = cur.fetchall(); cur.close(); release_conn(conn)
            text = "📜 **15 Newest Users:**\n━━━━━━━━━━━━━━━━\n"
            for r in rows: text += f"• `{r[0]}` - {r[1]} ({r[2] or 'NoName'}) - {r[3].strftime('%b %d')}\n"
            kb = [[InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return

        # --- 3. FEEDBACK QUEUE ---
        if data == "admin_feedbacks":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT f.user_id, u.nickname, f.message FROM feedback f JOIN users u ON f.user_id = u.user_id ORDER BY f.timestamp DESC LIMIT 5")
            rows = cur.fetchall(); cur.close(); release_conn(conn)
            text = "📨 **Latest Feedback:**\n━━━━━━━━━━━━━━━━\n"
            if not rows: text += "No feedback right now!\n"
            for r in rows: text += f"• `{r[0]}` ({r[1]}): {r[2]}\n\n"
            kb = [[InlineKeyboardButton("🗑️ Clear Read Feedback", callback_data="admin_clear_feedback")],
                  [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return

        if data == "admin_clear_feedback":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("DELETE FROM feedback")
            conn.commit(); cur.close(); release_conn(conn)
            await q.answer("✅ All feedback cleared!", show_alert=True)
            kb = [[InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text("🗑️ Feedback cleared.", reply_markup=InlineKeyboardMarkup(kb))
            except: 
                try: await q.edit_message_caption(caption="🗑️ Feedback cleared.", reply_markup=InlineKeyboardMarkup(kb))
                except: pass
            return

        # --- 4. REPORT TICKETING SYSTEM ---
        if data == "admin_reports":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT user_id, nickname, first_name, username, report_count FROM users WHERE report_count > 0 ORDER BY report_count DESC LIMIT 1")
            r = cur.fetchone()
            if not r:
                cur.close(); release_conn(conn)
                text = "✅ **Zero Active Reports!**\nYour community is safe."
                kb = [[InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            else:
                user_id, nick, fname, uname, count = r
                cur.execute("SELECT message FROM chat_logs WHERE sender_id = %s ORDER BY timestamp DESC LIMIT 5", (user_id,))
                logs = [row[0] for row in cur.fetchall()]
                cur.close(); release_conn(conn)
                
                text = f"⚠️ **REPORT TICKET**\n━━━━━━━━━━━━━━━━\n👤 **Name:** {nick} ({fname})\n🆔 **ID:** `{user_id}`\n🔗 **User:** @{uname or 'None'}\n🚨 **Reports:** {count}\n\n📜 **Recent Logs:**\n"
                for log in logs: text += f"- \"{log}\"\n"
                
                kb = [
                    [InlineKeyboardButton("🔨 Ban (24h)", callback_data=f"admin_rep_ban_{user_id}"), InlineKeyboardButton("⚠️ Warn", callback_data=f"admin_rep_warn_{user_id}")],
                    [InlineKeyboardButton("✅ Spare (Reset)", callback_data=f"admin_rep_spare_{user_id}")],
                    [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]
                ]
            try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return

        if data.startswith("admin_rep_ban_"):
            target_id = int(data.split("_")[3])
            conn = get_conn(); cur = conn.cursor()
            ban_until = datetime.datetime.now() + datetime.timedelta(hours=24)
            cur.execute("UPDATE users SET banned_until = %s, report_count = 0 WHERE user_id = %s", (ban_until, target_id))
            conn.commit(); cur.close(); release_conn(conn)
            if target_id in ACTIVE_CHATS: del ACTIVE_CHATS[target_id]
            try: await context.bot.send_message(target_id, "🚫 You have been BANNED by an admin for 24 hours.", reply_markup=ReplyKeyboardRemove())
            except: pass
            await q.answer("✅ Banned & cleared report.", show_alert=True)
            kb = [[InlineKeyboardButton("⏭️ Next Report", callback_data="admin_reports")], [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text("🔨 User banned for 24h. Load next?", reply_markup=InlineKeyboardMarkup(kb))
            except: 
                try: await q.edit_message_caption(caption="🔨 User banned for 24h. Load next?", reply_markup=InlineKeyboardMarkup(kb))
                except: pass
            return

        if data.startswith("admin_rep_warn_"):
            target_id = int(data.split("_")[3])
            conn = get_conn(); cur = conn.cursor()
            cur.execute("UPDATE users SET report_count = 0 WHERE user_id = %s", (target_id,))
            conn.commit(); cur.close(); release_conn(conn)
            try: await context.bot.send_message(target_id, "⚠️ **OFFICIAL WARNING**\nYour recent behavior was reported. Please follow the guidelines or face a ban.", parse_mode='Markdown')
            except: pass
            await q.answer("✅ Warned & cleared report.", show_alert=True)
            kb = [[InlineKeyboardButton("⏭️ Next Report", callback_data="admin_reports")], [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text("⚠️ Warning sent! Load next?", reply_markup=InlineKeyboardMarkup(kb))
            except: 
                try: await q.edit_message_caption(caption="⚠️ Warning sent! Load next?", reply_markup=InlineKeyboardMarkup(kb))
                except: pass
            return
            
        if data.startswith("admin_rep_spare_"):
            target_id = int(data.split("_")[3])
            conn = get_conn(); cur = conn.cursor()
            cur.execute("UPDATE users SET report_count = 0 WHERE user_id = %s", (target_id,))
            conn.commit(); cur.close(); release_conn(conn)
            await q.answer("✅ Spared & cleared report.", show_alert=True)
            kb = [[InlineKeyboardButton("⏭️ Next Report", callback_data="admin_reports")], [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text("✅ User spared! Load next?", reply_markup=InlineKeyboardMarkup(kb))
            except: 
                try: await q.edit_message_caption(caption="✅ User spared! Load next?", reply_markup=InlineKeyboardMarkup(kb))
                except: pass
            return

        # --- 5. BAN MANAGEMENT ---
        if data == "admin_banlist":
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT user_id, nickname FROM users WHERE banned_until > NOW() ORDER BY banned_until DESC LIMIT 10")
            rows = cur.fetchall(); cur.close(); release_conn(conn)
            text = "🚫 **Currently Banned:**\n━━━━━━━━━━━━━━━━\n"
            kb = []
            if not rows: text += "No active bans! 😇\n"
            else:
                for r in rows: 
                    text += f"• `{r[0]}` - {r[1]}\n"
                    kb.append([InlineKeyboardButton(f"🔓 Unban {r[1][:10]}", callback_data=f"admin_unban_{r[0]}")])
            kb.append([InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")])
            
            try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return

        if data.startswith("admin_unban_"):
            target_id = int(data.split("_")[2])
            conn = get_conn(); cur = conn.cursor()
            cur.execute("UPDATE users SET banned_until = NULL WHERE user_id = %s", (target_id,))
            conn.commit(); cur.close(); release_conn(conn)
            try: await context.bot.send_message(target_id, "🔓 **YOUR BAN HAS BEEN LIFTED.**\n\nPlease ensure you follow the community guidelines. Any future violations will result in a permanent ban.", parse_mode='Markdown')
            except: pass
            await q.answer("✅ User Unbanned!", show_alert=True)
            kb = [[InlineKeyboardButton("🔄 Refresh Banlist", callback_data="admin_banlist")], [InlineKeyboardButton("🔙 Back to Control Room", callback_data="admin_home")]]
            try: await q.edit_message_text(f"✅ User `{target_id}` unbanned successfully.", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except: 
                try: await q.edit_message_caption(caption=f"✅ User `{target_id}` unbanned successfully.", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except: pass
            return
    # --- GAME ENGINE & NOTIFICATIONS ---
    if data == "notify_me":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'waiting_notify' WHERE user_id = %s", (uid,))
        conn.commit(); cur.close(); release_conn(conn)
        await q.edit_message_text(get_text(l, "WAIT_NOTIFY"), parse_mode='Markdown')
        await show_main_menu(update); return

    if data == "keep_searching": await q.delete_message(); return
        
    if data.startswith("game_offer_"): await offer_game(update, context, uid, data.split("_", 2)[2]); return
    if data.startswith("game_accept_"): pid = ACTIVE_CHATS.get(uid); await start_game_session(update, context, data.split("_", 2)[2], pid, uid) if pid else None; return
    if data == "game_reject": 
        pid = ACTIVE_CHATS.get(uid)
        if pid: 
            p_lang = await get_lang(pid)
            await context.bot.send_message(pid, get_text(p_lang, "DECLINED"))
        await q.edit_message_text(get_text(l, "DECLINED")); return
        
    if data == "spicy_accept":
        pid = ACTIVE_CHATS.get(uid)
        if uid in GAME_STATES: GAME_STATES[uid]["spicy"] = True
        if pid and pid in GAME_STATES: GAME_STATES[pid]["spicy"] = True
        await q.edit_message_text(get_text(l, "SPICY_ON"), parse_mode='Markdown')
        await context.bot.send_message(uid, get_text(l, "SPICY_ON"), reply_markup=get_keyboard_game(l, True), parse_mode='Markdown')
        if pid:
            p_lang = await get_lang(pid)
            await context.bot.send_message(pid, get_text(p_lang, "SPICY_ON"), reply_markup=get_keyboard_game(p_lang, True), parse_mode='Markdown')
        return
        
    if data == "spicy_reject":
        pid = ACTIVE_CHATS.get(uid)
        await q.edit_message_text(get_text(l, "SPICY_DECLINED"), parse_mode='Markdown')
        if pid:
            p_lang = await get_lang(pid)
            await context.bot.send_message(pid, get_text(p_lang, "SPICY_DECLINED"), parse_mode='Markdown')
        return
    
    if data.startswith("tod_pick_"):
        mode = data.split("_")[2] 
        await q.edit_message_text(get_text(l, "YOU_PICKED").format(mode=mode.upper()), parse_mode='Markdown')
        partner_id = ACTIVE_CHATS.get(uid)
        if partner_id: await send_tod_options(context, partner_id, mode)
        return
    
    if data.startswith("tod_send_"): 
        gd = GAME_STATES.get(uid)
        if gd:
            q_text = gd["options"][int(data.split("_")[2])]
            pid = ACTIVE_CHATS.get(uid) 
            if pid:
                p_lang = await get_lang(pid)
                await context.bot.send_message(pid, get_text(p_lang, "QUESTION").format(q=q_text), parse_mode='Markdown')
                await q.edit_message_text(get_text(l, "ASKED").format(q=q_text))
                if pid in GAME_STATES: 
                    GAME_STATES[pid]["status"] = "answering"; GAME_STATES[pid]["turn"] = pid 
        return
        
    if data == "tod_manual": context.user_data["state"] = "GAME_MANUAL"; await q.edit_message_text(get_text(l, "TYPE_Q_NOW")); return

    if data.startswith("rps_"):
        move = data.split("_")[1]
        gd = GAME_STATES.get(uid)
        if not gd: return
        gd["moves"][uid] = move
        await q.edit_message_text(get_text(l, "CHOSE").format(move=move.upper()))
        
        partner_id = ACTIVE_CHATS.get(uid)
        if partner_id and partner_id in gd["moves"]:
            p_move = gd["moves"][partner_id]
            p_lang = await get_lang(partner_id)
            winner = None
            
            if move == p_move: winner = None
            elif (move == "rock" and p_move == "scissors") or (move == "paper" and p_move == "rock") or (move == "scissors" and p_move == "paper"): winner = uid
            else: winner = partner_id

            if winner == uid: gd[f"s_{uid}"] = gd.get(f"s_{uid}", 0) + 1
            elif winner == partner_id: gd[f"s_{partner_id}"] = gd.get(f"s_{partner_id}", 0) + 1
            
            sc_me, sc_pa = gd.get(f"s_{uid}", 0), gd.get(f"s_{partner_id}", 0)
            
            if gd["cur_r"] >= gd["max_r"]:
                is_spicy = gd.get("spicy", False)
                list_key = "tod_dare_spicy" if is_spicy else "tod_dare"
                chosen_dare = random.choice(GAME_DATA.get(list_key, ["Send a voice note howling like a wolf!"]))
                
                final_res = get_text(l, "DRAW_MATCH") + get_text(l, "RPS_DRAW_NO_DARE")
                p_final = get_text(p_lang, "DRAW_MATCH") + get_text(p_lang, "RPS_DRAW_NO_DARE")
                
                if sc_me > sc_pa: 
                    final_res = get_text(l, "WON_MATCH") + get_text(l, "RPS_WIN_DARE").format(dare=chosen_dare)
                    p_final = get_text(p_lang, "LOST_MATCH") + get_text(p_lang, "RPS_LOSE_DARE").format(dare=chosen_dare)
                elif sc_pa > sc_me: 
                    final_res = get_text(l, "LOST_MATCH") + get_text(l, "RPS_LOSE_DARE").format(dare=chosen_dare)
                    p_final = get_text(p_lang, "WON_MATCH") + get_text(p_lang, "RPS_WIN_DARE").format(dare=chosen_dare)
                
                msg = get_text(l, "RPS_FINAL").format(max_r=gd['max_r'], s1=sc_me, s2=sc_pa, res=final_res)
                p_msg = get_text(p_lang, "RPS_FINAL").format(max_r=gd['max_r'], s1=sc_pa, s2=sc_me, res=p_final)
                
                await context.bot.send_message(uid, msg, parse_mode='Markdown', reply_markup=get_keyboard_game(l, is_spicy))
                await context.bot.send_message(partner_id, p_msg, parse_mode='Markdown', reply_markup=get_keyboard_game(p_lang, is_spicy))
                gd["moves"] = {}; del GAME_STATES[uid]; del GAME_STATES[partner_id]
            else:
                r_res = get_text(l, "DRAW"); p_r_res = get_text(p_lang, "DRAW")
                if winner == uid:
                    r_res = get_text(l, "BEAT").format(m1=move.upper(), m2=p_move.upper())
                    p_r_res = get_text(p_lang, "LOST").format(m1=p_move.upper(), m2=move.upper())
                elif winner == partner_id:
                    r_res = get_text(l, "LOST").format(m1=move.upper(), m2=p_move.upper())
                    p_r_res = get_text(p_lang, "BEAT").format(m1=p_move.upper(), m2=move.upper())
                
                msg = get_text(l, "RPS_RES").format(r=gd['cur_r'], res=r_res, s1=sc_me, s2=sc_pa)
                p_msg = get_text(p_lang, "RPS_RES").format(r=gd['cur_r'], res=p_r_res, s1=sc_pa, s2=sc_me)

                await context.bot.send_message(uid, msg, parse_mode='Markdown')
                await context.bot.send_message(partner_id, p_msg, parse_mode='Markdown')
                gd["cur_r"] += 1; gd["moves"] = {}
                await asyncio.sleep(2)
                await send_rps_round(context, uid, partner_id)
        return

    if data.startswith("wyr_") and data != "wyr_skip":
        choice = data.split("_")[1].upper()
        gd = GAME_STATES.get(uid)
        if not gd: return
        gd["moves"][uid] = choice
        await q.edit_message_text(get_text(l, "VOTED").format(choice=choice))
        
        partner_id = ACTIVE_CHATS.get(uid)
        if partner_id and partner_id in gd["moves"]:
            p_choice = gd["moves"][partner_id]
            p_lang = await get_lang(partner_id)
            
            match_text, p_match_text = "", ""
            if choice == p_choice:
                gd["streak"] = gd.get("streak", 0) + 1; s = gd["streak"]
                match_text = get_text(l, "MATCH_100").format(s=s); p_match_text = get_text(p_lang, "MATCH_100").format(s=s)
            else:
                gd["streak"] = 0
                match_text = get_text(l, "MATCH_DIFF"); p_match_text = get_text(p_lang, "MATCH_DIFF")

            msg = get_text(l, "WYR_RESULTS").format(my_choice=choice, p_choice=p_choice, match=match_text)
            p_msg = get_text(p_lang, "WYR_RESULTS").format(my_choice=p_choice, p_choice=choice, match=p_match_text)
            gd["status"] = "discussing"; gd["explained"] = [] 
            
            kb = [[InlineKeyboardButton(get_text(l, "SKIP_DISC"), callback_data="wyr_skip")]]
            p_kb = [[InlineKeyboardButton(get_text(p_lang, "SKIP_DISC"), callback_data="wyr_skip")]]
            
            await context.bot.send_message(uid, msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
            await context.bot.send_message(partner_id, p_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(p_kb))
            gd["moves"] = {}
        return
    
    if data == "wyr_skip":
        gd = GAME_STATES.get(uid); pid = ACTIVE_CHATS.get(uid)
        if gd and gd.get("status") == "discussing":
            if "explained" not in gd: gd["explained"] = []
            if uid not in gd["explained"]:
                gd["explained"].append(uid)
                await q.edit_message_text(get_text(l, "YOU_SKIPPED"))
                if pid: await context.bot.send_message(pid, get_text(await get_lang(pid), "PARTNER_SKIPPED"))
            else:
                await q.answer("⏳", show_alert=True); return

            if len(gd["explained"]) >= 2:
                if pid: await context.bot.send_message(pid, get_text(await get_lang(pid), "NEXT_ROUND"))
                await context.bot.send_message(uid, get_text(l, "NEXT_ROUND"))
                gd["status"] = "playing"
                await asyncio.sleep(1.5)
                if pid: await send_wyr_round(context, uid, pid)
        return
    if data.startswith("rate_"):
        parts = data.split("_"); act = parts[1]; target_str = parts[2]
        if target_str == "AI": await q.edit_message_text("✅"); return
        target = int(target_str)
        if act == "report": 
            await handle_report(update, context, uid, target)
            await q.edit_message_text("⚠️")
        else:
            sc = 1 if act == "like" else -1
            conn = get_conn(); cur = conn.cursor()
            cur.execute("INSERT INTO user_interactions (rater_id, target_id, score) VALUES (%s, %s, %s)", (uid, target, sc))
            conn.commit(); cur.close(); release_conn(conn)
            await q.edit_message_text("✅")

if __name__ == '__main__':
    if not BOT_TOKEN: print("ERROR: Config missing")
    else:
        init_db()
        flask_thread = threading.Thread(target=run_flask); flask_thread.daemon = True; flask_thread.start()
        req = HTTPXRequest(connect_timeout=60, read_timeout=60)
        app = ApplicationBuilder().token(BOT_TOKEN).request(req).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("admin", admin_panel))
        app.add_handler(CommandHandler("ban", admin_ban_command))
        app.add_handler(CommandHandler("warn", admin_warn_command))
        app.add_handler(CommandHandler("broadcast", admin_broadcast_execute))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("feedback", handle_feedback_command))
        
        app.add_handler(MessageHandler(filters.TEXT, handle_text_input))
        
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageReactionHandler(handle_reaction))
        app.add_handler(MessageHandler(filters.ALL, relay_message))
        
        print("🤖 PHASE 24 BOT LIVE - AVATARS & TRADING CARDS")
        app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])
