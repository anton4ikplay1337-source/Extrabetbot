import os
import telebot
from telebot import types
import sqlite3
import random
from datetime import datetime, timedelta
import string
import time
import re

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('TOKEN', '8965196111:AAFsNCnmRTVsAUsSIKkZiIDCCzB6HSe_-OQ')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '5706071030'))

bot = telebot.TeleBot(TOKEN)

# ========== ВРЕМЕННЫЕ ХРАНИЛИЩА ==========
user_match_creation = {}
user_bet_amount = {}

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  balance INTEGER DEFAULT 1000,
                  freebets INTEGER DEFAULT 0,
                  total_bets INTEGER DEFAULT 0,
                  wins INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS matches
                 (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team1 TEXT,
                  team2 TEXT,
                  match_date TEXT,
                  coefficient1 REAL DEFAULT 2.5,
                  coefficient2 REAL DEFAULT 2.5,
                  coefficient_draw REAL DEFAULT 3.5,
                  status TEXT DEFAULT 'upcoming',
                  winner TEXT,
                  score TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bets
                 (bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  match_id INTEGER,
                  team TEXT,
                  amount INTEGER,
                  bet_type TEXT DEFAULT 'money',
                  coefficient REAL DEFAULT 2.0,
                  status TEXT DEFAULT 'pending')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes
                 (promo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE,
                  freebet_amount INTEGER,
                  max_uses INTEGER,
                  used_count INTEGER DEFAULT 0,
                  is_active INTEGER DEFAULT 1,
                  created_by INTEGER,
                  created_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS used_promos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  promo_code TEXT,
                  used_date TEXT)''')
    
    # НОВАЯ ТАБЛИЦА ДЛЯ ФОТОГРАФИЙ
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  photo_type TEXT,
                  file_id TEXT,
                  added_date TEXT)''')
    
    conn.commit()
    conn.close()

# ========== ГЕНЕРАЦИЯ КОДА ==========
def generate_promo_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ========== БЕЗОПАСНЫЕ ФУНКЦИИ ОТПРАВКИ ==========
def safe_send_message(chat_id, text, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        print(f"Ошибка отправки в {chat_id}: {e}")
        time.sleep(1)
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup)
        except:
            return None

def safe_edit_message(text, chat_id, message_id, reply_markup=None):
    try:
        return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception as e:
        print(f"Ошибка редактирования: {e}")
        return None

# ========== ФУНКЦИЯ ПОЛУЧЕНИЯ ФОТО ==========
def get_photo(photo_type):
    """Получает ID фотографии из базы данных"""
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT file_id FROM photos WHERE photo_type=? ORDER BY photo_id DESC LIMIT 1", (photo_type,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# ========== ФУНКЦИЯ УВЕДОМЛЕНИЯ О РЕЗУЛЬТАТЕ С ФОТО ==========
def notify_user(user_id, match_info, team, amount, coefficient, bet_type, status, winnings=0):
    """Отправляет пользователю уведомление о выигрыше/проигрыше с фото"""
    
    if status == "won":
        if bet_type in ('freebet', 'freebet_active'):
            message = (
                f"🎉 ФРИБЕТ ВЫИГРАЛ!\n\n"
                f"Матч: {match_info}\n"
                f"Ваш прогноз: {team}\n"
                f"💰 Выигрыш: {amount} монет\n"
                f"Спасибо за игру!"
            )
        else:
            message = (
                f"🎉 СТАВКА ВЫИГРАЛА!\n\n"
                f"Матч: {match_info}\n"
                f"Ваш прогноз: {team}\n"
                f"Сумма ставки: {amount}\n"
                f"Коэффициент: {coefficient}\n"
                f"💰 Выигрыш: {winnings} монет\n"
                f"Поздравляем!"
            )
        
        # Отправляем сообщение
        safe_send_message(user_id, message)
        
        # Отправляем фото победы
        win_photo = get_photo('win')
        if win_photo:
            try:
                bot.send_photo(user_id, win_photo, caption="🏆 ПОБЕДА!")
            except:
                pass
    
    else:
        if bet_type in ('freebet', 'freebet_active'):
            message = (
                f"😞 ФРИБЕТ ПРОИГРАЛ\n\n"
                f"Матч: {match_info}\n"
                f"Ваш прогноз: {team}\n"
                f"К сожалению, удача не на вашей стороне."
            )
        else:
            message = (
                f"😞 СТАВКА ПРОИГРАЛА\n\n"
                f"Матч: {match_info}\n"
                f"Ваш прогноз: {team}\n"
                f"Сумма ставки: {amount}\n"
                f"Не расстраивайтесь, повезёт в следующий раз!"
            )
        
        # Отправляем сообщение
        safe_send_message(user_id, message)
        
        # Отправляем фото поражения
        lose_photo = get_photo('lose')
        if lose_photo:
            try:
                bot.send_photo(user_id, lose_photo, caption="💔 Поражение")
            except:
                pass

# ========== КОМАНДА ДЛЯ УСТАНОВКИ ФОТО ==========
@bot.message_handler(commands=['setphoto'])
def set_photo_start(message):
    """Команда для установки фото (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        safe_send_message(message.chat.id, "⛔ Только админ может менять фото!")
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏆 Фото победы", callback_data="set_photo_win"),
        types.InlineKeyboardButton("💔 Фото поражения", callback_data="set_photo_lose")
    )
    kb.add(types.InlineKeyboardButton("📋 Показать фото", callback_data="show_photos"))
    
    safe_send_message(
        message.chat.id,
        "📸 Управление фотографиями\n\n"
        "Выберите тип фото для замены:\n"
        "Затем отправьте фото в чат",
        kb
    )

# ========== КЛАВИАТУРЫ ==========
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎮 Управление матчами", "🎫 Промокоды")
    kb.add("💰 Выдать фрибет", "📊 Статистика бота")
    kb.add("👥 Пользователи", "🏒 Матчи")
    kb.add("👤 Профиль", "📋 Меню")
    kb.add("📸 Установить фото")
    return kb

def main_keyboard(user_id=None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🏒 Матчи", "👤 Профиль")
    kb.add("💰 Баланс", "📊 Статистика")
    kb.add("🎫 Активировать промокод", "🎁 Мои фрибеты")
    kb.add("🆘 Получить бонус")
    
    if user_id == ADMIN_ID:
        kb.add("🔧 Админ-панель")
    
    return kb

def admin_promo_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Создать промокод", callback_data="admin_create_promo"),
        types.InlineKeyboardButton("📋 Список промокодов", callback_data="admin_list_promos")
    )
    kb.add(
        types.InlineKeyboardButton("🗑 Удалить промокод", callback_data="admin_delete_promo_list"),
        types.InlineKeyboardButton("📊 Статистика промо", callback_data="admin_promo_stats")
    )
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_admin_main"))
    return kb

def admin_matches_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Создать матч", callback_data="admin_create_match"),
        types.InlineKeyboardButton("📋 Все матчи", callback_data="admin_all_matches")
    )
    kb.add(
        types.InlineKeyboardButton("✅ Установить результат", callback_data="admin_set_result"),
        types.InlineKeyboardButton("🗑 Удалить матч", callback_data="admin_delete_match_list")
    )
    kb.add(
        types.InlineKeyboardButton("🎲 Рассчитать все", callback_data="admin_calculate_all"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_admin_main")
    )
    return kb

def matches_keyboard():
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT match_id, team1, team2, match_date, coefficient1, coefficient2, coefficient_draw FROM matches WHERE status='upcoming'")
    matches = c.fetchall()
    conn.close()
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    for match in matches:
        kb.add(types.InlineKeyboardButton(
            f"⚔ {match[1]} (x{match[4]}) vs {match[2]} (x{match[5]}) | Ничья (x{match[6]}) | {match[3]}",
            callback_data=f"match_{match[0]}"
        ))
    kb.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_matches"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return kb

def bet_keyboard(match_id):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT team1, team2, coefficient1, coefficient2, coefficient_draw FROM matches WHERE match_id=?", (match_id,))
    match = c.fetchone()
    conn.close()
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"✅ {match[0]} x{match[2]}", callback_data=f"betsum_{match_id}_{match[0]}"),
        types.InlineKeyboardButton(f"✅ {match[1]} x{match[3]}", callback_data=f"betsum_{match_id}_{match[1]}")
    )
    kb.add(
        types.InlineKeyboardButton(f"🤝 Ничья x{match[4]}", callback_data=f"betsum_{match_id}_Ничья"),
        types.InlineKeyboardButton("🔙 К матчам", callback_data="show_matches")
    )
    return kb

def sum_keyboard(match_id, team):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("100", callback_data=f"bet_{match_id}_{team}_100"),
        types.InlineKeyboardButton("500", callback_data=f"bet_{match_id}_{team}_500"),
        types.InlineKeyboardButton("1000", callback_data=f"bet_{match_id}_{team}_1000")
    )
    kb.add(
        types.InlineKeyboardButton("2500", callback_data=f"bet_{match_id}_{team}_2500"),
        types.InlineKeyboardButton("5000", callback_data=f"bet_{match_id}_{team}_5000"),
        types.InlineKeyboardButton("Своя сумма", callback_data=f"custom_{match_id}_{team}")
    )
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data=f"match_{match_id}"))
    return kb

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()
    
    welcome_text = (
        "🏒 ДОБРО ПОЖАЛОВАТЬ В EXTRABET!\n\n"
        "💰 Ваш стартовый баланс: 1000 монет\n\n"
        "📋 Меню находится снизу"
    )
    
    if user_id == ADMIN_ID:
        safe_send_message(message.chat.id, welcome_text, admin_keyboard())
    else:
        safe_send_message(message.chat.id, welcome_text, main_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == "📸 Установить фото")
def set_photo_button(message):
    set_photo_start(message)

@bot.message_handler(func=lambda m: m.text == "📋 Меню")
def show_menu(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        safe_send_message(message.chat.id, "📋 Меню находится снизу\nВыберите раздел:", admin_keyboard())
    else:
        safe_send_message(message.chat.id, "📋 Меню находится снизу\nВыберите раздел:", main_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == "🔧 Админ-панель")
def admin_panel(message):
    if message.from_user.id == ADMIN_ID:
        safe_send_message(message.chat.id, "👑 Админ-панель управления\n📋 Меню снизу", admin_keyboard())
    else:
        safe_send_message(message.chat.id, "⛔ Доступ запрещен!")

@bot.message_handler(func=lambda m: m.text == "🆘 Получить бонус")
def get_bonus(message):
    user_id = message.from_user.id
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if not user:
        safe_send_message(message.chat.id, "❌ Используйте /start для регистрации")
        conn.close()
        return
    balance = user[0]
    if balance != 0:
        safe_send_message(message.chat.id, f"❌ Бонус недоступен!\nВаш баланс: {balance} монет\nБонус можно получить только при балансе = 0")
    else:
        c.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user_id,))
        conn.commit()
        safe_send_message(message.chat.id, "✅ Бонус получен!\n💰 Начислено: 50 монет\n💵 Новый баланс: 50 монет\n🆘 Можете получать бонус бесконечно (когда баланс снова 0)")
    conn.close()

@bot.message_handler(func=lambda m: m.text == "🎫 Активировать промокод")
def activate_promo_start(message):
    msg = safe_send_message(message.chat.id, "🎫 Активация промокода\nОтправьте промокод для получения фрибетов!")
    bot.register_next_step_handler(msg, process_activate_promo)

def process_activate_promo(message):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT * FROM promocodes WHERE code=? AND is_active=1", (code,))
    promo = c.fetchone()
    if not promo:
        safe_send_message(message.chat.id, "❌ Промокод не найден или неактивен!")
        conn.close()
        return
    if promo[3] <= promo[4]:
        safe_send_message(message.chat.id, "❌ Промокод больше недействителен!")
        conn.close()
        return
    c.execute("SELECT id FROM used_promos WHERE user_id=? AND promo_code=?", (user_id, code))
    if c.fetchone():
        safe_send_message(message.chat.id, "❌ Вы уже использовали этот промокод!")
        conn.close()
        return
    freebet_amount = promo[2]
    c.execute("INSERT INTO used_promos (user_id, promo_code, used_date) VALUES (?, ?, ?)",
             (user_id, code, datetime.now().strftime("%d.%m.%Y %H:%M")))
    c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code=?", (code,))
    c.execute("UPDATE users SET freebets = freebets + 1 WHERE user_id=?", (user_id,))
    c.execute("INSERT INTO bets (user_id, match_id, team, amount, bet_type, coefficient) VALUES (?, 0, 'freebet', ?, 'freebet', 1.0)",
             (user_id, freebet_amount))
    if promo[4] + 1 >= promo[3]:
        c.execute("UPDATE promocodes SET is_active=0 WHERE code=?", (code,))
    conn.commit()
    conn.close()
    safe_send_message(message.chat.id, f"🎁 Фрибет активирован!\nПромокод: {code}\nСумма фрибета: {freebet_amount} монет\nИспользуйте в разделе «Мои фрибеты»")

@bot.message_handler(func=lambda m: m.text == "🎁 Мои фрибеты")
def show_freebets(message):
    user_id = message.from_user.id
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT bet_id, amount FROM bets WHERE user_id=? AND bet_type='freebet' AND status='pending'", (user_id,))
    freebets = c.fetchall()
    conn.close()
    if freebets:
        kb = types.InlineKeyboardMarkup(row_width=1)
        text = "🎁 Ваши фрибеты:\n\n"
        for fb in freebets:
            text += f"🆔 #{fb[0]}: {fb[1]} монет\n"
            kb.add(types.InlineKeyboardButton(f"Использовать фрибет #{fb[0]} ({fb[1]}💰)", callback_data=f"use_freebet_{fb[0]}"))
        text += "\nВыберите фрибет для использования:"
        safe_send_message(message.chat.id, text, kb)
    else:
        safe_send_message(message.chat.id, "🎁 У вас пока нет фрибетов\nАктивируйте промокод для получения!")

@bot.message_handler(func=lambda m: m.text == "🎮 Управление матчами")
def manage_matches(message):
    if message.from_user.id == ADMIN_ID:
        safe_send_message(message.chat.id, "🎮 Управление матчами", admin_matches_keyboard())

@bot.message_handler(func=lambda m: m.text == "💰 Выдать фрибет")
def give_freebet_start(message):
    if message.from_user.id != ADMIN_ID: return
    msg = safe_send_message(message.chat.id, "🎁 Выдача фрибета\nОтправьте ID пользователя и сумму:\nID_пользователя сумма\nПример: 123456789 500")
    bot.register_next_step_handler(msg, process_freebet)

def process_freebet(message):
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = int(parts[1])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("UPDATE users SET freebets = freebets + 1 WHERE user_id=?", (target_id,))
        c.execute("INSERT INTO bets (user_id, match_id, team, amount, bet_type) VALUES (?, 0, 'freebet', ?, 'freebet')", (target_id, amount))
        conn.commit()
        conn.close()
        safe_send_message(message.chat.id, f"✅ Фрибет выдан!\n👤 ID: {target_id}\n💰 Сумма: {amount}")
        try:
            safe_send_message(target_id, f"🎁 Вы получили фрибет!\n💰 Сумма: {amount} монет\nИспользуйте в разделе «Мои фрибеты»")
        except:
            pass
    except:
        safe_send_message(message.chat.id, "❌ Ошибка! Формат: ID сумма")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика бота")
def bot_stats(message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM bets WHERE bet_type='money'")
    total_bets = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM bets WHERE bet_type='money'")
    total_amount = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM matches WHERE status='upcoming'")
    active_matches = c.fetchone()[0]
    conn.close()
    stats = f"📊 Статистика бота\n\n👥 Пользователей: {total_users}\n💰 Общий баланс: {total_balance}\n🏒 Активных матчей: {active_matches}\n📈 Всего ставок: {total_bets}\n💵 Сумма ставок: {total_amount} монет"
    safe_send_message(message.chat.id, stats)

@bot.message_handler(func=lambda m: m.text == "👥 Пользователи")
def users_list(message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, freebets, total_bets FROM users ORDER BY balance DESC LIMIT 20")
    users = c.fetchall()
    conn.close()
    text = "👥 Топ-20 пользователей\n\n"
    for i, user in enumerate(users, 1):
        text += f"{i}. {user[1]} | 💰{user[2]} | 🎁{user[3]}\n"
    safe_send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🏒 Матчи")
def show_matches_handler(message):
    safe_send_message(message.chat.id, "🎯 Доступные матчи:", matches_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_handler(message):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,))
    user = c.fetchone()
    conn.close()
    if user:
        win_rate = (user[5] / user[4] * 100) if user[4] > 0 else 0
        text = f"👤 Профиль\n\n💰 Баланс: {user[2]}\n🎁 Фрибеты: {user[3]}\n📊 Ставок: {user[4]}\n✅ Побед: {user[5]}\n📈 Винрейт: {win_rate:.1f}%"
        safe_send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def balance_handler(message):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT balance, freebets FROM users WHERE user_id=?", (message.from_user.id,))
    data = c.fetchone()
    conn.close()
    safe_send_message(message.chat.id, f"💰 Баланс: {data[0]} монет\n🎁 Фрибеты: {data[1]}")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_handler(message):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("""
        SELECT b.team, b.amount, b.status, m.team1, m.team2 
        FROM bets b JOIN matches m ON b.match_id = m.match_id 
        WHERE b.user_id=? ORDER BY b.bet_id DESC LIMIT 5
    """, (message.from_user.id,))
    bets = c.fetchall()
    conn.close()
    if bets:
        text = "📊 Последние ставки:\n\n"
        for bet in bets:
            emoji = "✅" if bet[2] == "won" else "❌" if bet[2] == "lost" else "⏳"
            text += f"{emoji} {bet[3]} vs {bet[4]}\n   {bet[1]} на {bet[0]}\n\n"
    else:
        text = "У вас пока нет ставок"
    safe_send_message(message.chat.id, text)

# ========== ОБРАБОТЧИК ФОТОГРАФИЙ ==========
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Обрабатывает загрузку фото для побед/поражений"""
    user_id = message.from_user.id
    
    # Проверяем, что это админ
    if user_id != ADMIN_ID:
        return
    
    # Проверяем, что админ выбрал тип фото
    if user_id in user_match_creation and 'photo_type' in user_match_creation[user_id]:
        photo_type = user_match_creation[user_id]['photo_type']
        file_id = message.photo[-1].file_id  # Берем самое большое разрешение
        
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        
        # Удаляем старые фото этого типа
        c.execute("DELETE FROM photos WHERE photo_type=?", (photo_type,))
        
        # Сохраняем новое фото
        c.execute("INSERT INTO photos (photo_type, file_id, added_date) VALUES (?, ?, ?)",
                 (photo_type, file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()
        conn.close()
        
        type_name = "🏆 ПОБЕДЫ" if photo_type == 'win' else "💔 ПОРАЖЕНИЯ"
        safe_send_message(message.chat.id, f"✅ Фото для {type_name} обновлено!")
        
        # Очищаем временные данные
        del user_match_creation[user_id]
    else:
        safe_send_message(message.chat.id, "ℹ️ Сначала выберите тип фото через /setphoto")

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    
    # Установка фото
    if call.data == "set_photo_win":
        if user_id != ADMIN_ID: return
        user_match_creation[user_id] = {'photo_type': 'win'}
        bot.answer_callback_query(call.id, "Отправьте фото для ПОБЕДЫ")
        safe_send_message(call.message.chat.id, "📸 Отправьте фото для 🏆 ПОБЕДЫ\n(просто отправьте картинку в чат)")
    
    elif call.data == "set_photo_lose":
        if user_id != ADMIN_ID: return
        user_match_creation[user_id] = {'photo_type': 'lose'}
        bot.answer_callback_query(call.id, "Отправьте фото для ПОРАЖЕНИЯ")
        safe_send_message(call.message.chat.id, "📸 Отправьте фото для 💔 ПОРАЖЕНИЯ\n(просто отправьте картинку в чат)")
    
    elif call.data == "show_photos":
        if user_id != ADMIN_ID: return
        
        win_photo = get_photo('win')
        lose_photo = get_photo('lose')
        
        if win_photo:
            safe_send_message(call.message.chat.id, "🏆 Текущее фото ПОБЕДЫ:")
            try:
                bot.send_photo(call.message.chat.id, win_photo)
            except:
                safe_send_message(call.message.chat.id, "❌ Ошибка загрузки фото")
        
        if lose_photo:
            safe_send_message(call.message.chat.id, "💔 Текущее фото ПОРАЖЕНИЯ:")
            try:
                bot.send_photo(call.message.chat.id, lose_photo)
            except:
                safe_send_message(call.message.chat.id, "❌ Ошибка загрузки фото")
        
        if not win_photo and not lose_photo:
            bot.answer_callback_query(call.id, "Фото не установлены!")
    
    # АДМИН-ПРОМОКОДЫ
    elif call.data == "admin_create_promo":
        if user_id != ADMIN_ID: return
        msg = safe_send_message(call.message.chat.id, "🎫 Создание промокода\nОтправьте данные:\nСУММА КОЛ-ВО_ИСПОЛЬЗОВАНИЙ\nПример: 500 10\nИли свой код: СУММА КОЛ-ВО КОД")
        bot.register_next_step_handler(msg, admin_create_promo_process)
    
    elif call.data == "admin_list_promos":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT * FROM promocodes ORDER BY created_date DESC LIMIT 20")
        promos = c.fetchall()
        conn.close()
        text = "📋 Список промокодов:\n\n" if promos else "❌ Промокодов пока нет"
        for p in promos:
            status = "🟢" if p[5] else "🔴"
            text += f"{status} {p[1]}\n   💰 {p[2]} монет | {p[4]}/{p[3]} исп.\n\n"
        safe_edit_message(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_delete_promo_list":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT promo_id, code, freebet_amount FROM promocodes WHERE is_active=1")
        promos = c.fetchall()
        conn.close()
        if promos:
            kb = types.InlineKeyboardMarkup(row_width=1)
            for p in promos:
                kb.add(types.InlineKeyboardButton(f"🗑 {p[1]} ({p[2]}💰)", callback_data=f"admin_delete_promo_{p[0]}"))
            kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_admin_promo"))
            safe_edit_message("Выберите промокод для удаления:", call.message.chat.id, call.message.message_id, kb)
        else:
            bot.answer_callback_query(call.id, "Нет активных промокодов")
    
    elif call.data.startswith("admin_delete_promo_"):
        if user_id != ADMIN_ID: return
        promo_id = int(call.data.split("_")[3])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("UPDATE promocodes SET is_active=0 WHERE promo_id=?", (promo_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Промокод деактивирован!")
        safe_edit_message("✅ Промокод деактивирован!", call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_promo_stats":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM promocodes")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM promocodes WHERE is_active=1")
        active = c.fetchone()[0]
        c.execute("SELECT SUM(used_count) FROM promocodes")
        total_used = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(DISTINCT user_id) FROM used_promos")
        unique_users = c.fetchone()[0]
        conn.close()
        text = f"📊 Статистика промокодов:\n\n📝 Всего создано: {total}\n🟢 Активных: {active}\n👥 Использований: {total_used}\n👤 Уникальных пользователей: {unique_users}"
        safe_edit_message(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "back_admin_promo":
        if user_id == ADMIN_ID:
            safe_edit_message("🎫 Управление промокодами:", call.message.chat.id, call.message.message_id, admin_promo_keyboard())
    
    elif call.data == "back_admin_main":
        if user_id == ADMIN_ID:
            safe_edit_message("👑 Админ-панель. Меню снизу:", call.message.chat.id, call.message.message_id)
    
    # АДМИН-МАТЧИ
    elif call.data == "admin_create_match":
        if user_id != ADMIN_ID: return
        msg = safe_send_message(call.message.chat.id, "➕ Создание матча\nОтправьте данные:\nКоманда1 vs Команда2 ДД.ММ.ГГГГ ЧЧ:ММ коэф1 коэф2 коэф_ничьей\nПример: Динамо vs Брест 20.05.2026 19:30 2.5 2.5 3.5")
        bot.register_next_step_handler(msg, admin_create_match)
    
    elif call.data == "admin_all_matches":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT * FROM matches ORDER BY match_date DESC LIMIT 10")
        matches = c.fetchall()
        conn.close()
        text = "📋 Все матчи:\n\n"
        for m in matches:
            status = "🟢" if m[7] == 'upcoming' else "🔴" if m[7] == 'finished' else "⏳"
            text += f"{status} #{m[0]}: {m[1]} vs {m[2]}\n   📅 {m[3]} | КФ: {m[4]}/{m[5]}/{m[6]}\n"
            if m[8]:
                text += f"   🏆 Победитель: {m[8]} | Счет: {m[9]}\n"
            text += "\n"
        safe_edit_message(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_set_result":
        if user_id != ADMIN_ID: return
        msg = safe_send_message(call.message.chat.id, "✅ Установка результата\nОтправьте: ID_матча Победитель Счет\nПример: 1 Динамо 5:3 или 1 Ничья 2:2")
        bot.register_next_step_handler(msg, admin_set_result)
    
    elif call.data == "admin_delete_match_list":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT match_id, team1, team2 FROM matches WHERE status='upcoming'")
        matches = c.fetchall()
        conn.close()
        if matches:
            kb = types.InlineKeyboardMarkup(row_width=1)
            for m in matches:
                kb.add(types.InlineKeyboardButton(f"🗑 #{m[0]} {m[1]} vs {m[2]}", callback_data=f"admin_delete_{m[0]}"))
            kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_admin_main"))
            safe_edit_message("🗑 Выберите матч для удаления:", call.message.chat.id, call.message.message_id, kb)
        else:
            bot.answer_callback_query(call.id, "Нет матчей для удаления")
    
    elif call.data == "admin_calculate_all":
        if user_id != ADMIN_ID: return
        calculate_all_matches()
        bot.answer_callback_query(call.id, "✅ Все матчи рассчитаны!")
        safe_send_message(call.message.chat.id, "✅ Результаты всех матчей определены и ставки рассчитаны!")
    
    elif call.data.startswith("admin_delete_"):
        if user_id != ADMIN_ID: return
        match_id = int(call.data.split("_")[2])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("DELETE FROM matches WHERE match_id=?", (match_id,))
        c.execute("DELETE FROM bets WHERE match_id=?", (match_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Матч #{match_id} удален!")
        safe_edit_message(f"🗑 Матч #{match_id} удален вместе со ставками!", call.message.chat.id, call.message.message_id)
    
    # ОБЫЧНЫЕ CALLBACK'И
    elif call.data == "show_matches":
        safe_edit_message("🎯 Доступные матчи:", call.message.chat.id, call.message.message_id, matches_keyboard())
    
    elif call.data == "refresh_matches":
        safe_edit_message("🔄 Матчи обновлены!", call.message.chat.id, call.message.message_id, matches_keyboard())
    
    elif call.data == "back_main":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        safe_send_message(call.message.chat.id, "📋 Меню находится снизу:", main_keyboard(call.from_user.id))
    
    elif call.data.startswith("match_"):
        match_id = int(call.data.split("_")[1])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT team1, team2, match_date, coefficient1, coefficient2, coefficient_draw FROM matches WHERE match_id=?", (match_id,))
        match = c.fetchone()
        conn.close()
        text = f"⚔ {match[0]} vs {match[1]}\n📅 {match[2]}\n📊 КФ: П1={match[3]} | П2={match[4]} | Ничья={match[5]}\n\nВыберите исход:"
        safe_edit_message(text, call.message.chat.id, call.message.message_id, bet_keyboard(match_id))
    
    elif call.data.startswith("betsum_"):
        data = call.data.split("_", 2)
        if len(data) < 3:
            bot.answer_callback_query(call.id, "Ошибка данных")
            return
        match_id = int(data[1])
        team = data[2]
        safe_edit_message(f"💰 Выберите сумму ставки на {team}:", call.message.chat.id, call.message.message_id, sum_keyboard(match_id, team))
    
    elif call.data.startswith("custom_"):
        data = call.data.split("_", 2)
        if len(data) < 3:
            bot.answer_callback_query(call.id, "Ошибка данных")
            return
        match_id = int(data[1])
        team = data[2]
        msg = safe_send_message(call.message.chat.id, f"💵 Введите сумму ставки на {team}:")
        user_bet_amount[user_id] = {'match_id': match_id, 'team': team}
        bot.register_next_step_handler(msg, process_custom_bet)
    
    elif call.data.startswith("bet_"):
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Ошибка данных")
            return
        match_id = int(parts[1])
        team = "_".join(parts[2:-1])
        amount = int(parts[-1])
        place_bet(call, user_id, match_id, team, amount)
    
    elif call.data.startswith("use_freebet_"):
        bet_id = int(call.data.split("_")[2])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT amount FROM bets WHERE bet_id=? AND bet_type='freebet' AND status='pending'", (bet_id,))
        freebet = c.fetchone()
        conn.close()
        if freebet:
            conn = sqlite3.connect('hockey_bets.db')
            c = conn.cursor()
            c.execute("SELECT match_id, team1, team2, match_date FROM matches WHERE status='upcoming'")
            matches = c.fetchall()
            conn.close()
            if matches:
                kb = types.InlineKeyboardMarkup(row_width=1)
                text = f"🎯 Выберите матч для фрибета\n💰 Номинал: {freebet[0]} монет\n\n"
                for match in matches:
                    kb.add(types.InlineKeyboardButton(f"⚔ {match[1]} vs {match[2]} | {match[3]}", callback_data=f"freebet_match_{bet_id}_{match[0]}"))
                kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="show_freebets_back"))
                safe_edit_message(text, call.message.chat.id, call.message.message_id, kb)
            else:
                bot.answer_callback_query(call.id, "❌ Нет доступных матчей!")
        else:
            bot.answer_callback_query(call.id, "❌ Фрибет недоступен!")
    
    elif call.data.startswith("freebet_match_"):
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Ошибка данных")
            return
        bet_id = int(parts[2])
        match_id = int(parts[3])
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT team1, team2 FROM matches WHERE match_id=?", (match_id,))
        match = c.fetchone()
        conn.close()
        if match:
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(f"✅ {match[0]}", callback_data=f"freebet_team_{bet_id}_{match_id}_{match[0]}"),
                types.InlineKeyboardButton(f"✅ {match[1]}", callback_data=f"freebet_team_{bet_id}_{match_id}_{match[1]}")
            )
            kb.add(
                types.InlineKeyboardButton(f"🤝 Ничья", callback_data=f"freebet_team_{bet_id}_{match_id}_Ничья"),
                types.InlineKeyboardButton("🔙 Назад", callback_data=f"use_freebet_{bet_id}")
            )
            safe_edit_message(f"⚔ {match[0]} vs {match[1]}\n\nВыберите исход для фрибета:", call.message.chat.id, call.message.message_id, kb)
    
    elif call.data.startswith("freebet_team_"):
        parts = call.data.split("_", 4)
        if len(parts) < 5:
            bot.answer_callback_query(call.id, "Ошибка данных")
            return
        bet_id = int(parts[2])
        match_id = int(parts[3])
        team = parts[4]
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT amount FROM bets WHERE bet_id=? AND bet_type='freebet' AND status='pending'", (bet_id,))
        freebet = c.fetchone()
        if freebet:
            c.execute("UPDATE bets SET match_id=?, team=?, bet_type='freebet_active' WHERE bet_id=?", (match_id, team, bet_id))
            c.execute("UPDATE users SET freebets = freebets - 1 WHERE user_id=?", (call.from_user.id,))
            conn.commit()
            safe_edit_message(f"✅ Фрибет использован!\nМатч #{match_id}\nИсход: {team}\n💰 Сумма: {freebet[0]} монет\nЖдите результат матча!", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ Фрибет недоступен!")
        conn.close()

# ========== ФУНКЦИИ СОЗДАНИЯ ПРОМОКОДА ==========
def admin_create_promo_process(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        if len(parts) == 2:
            amount = int(parts[0])
            max_uses = int(parts[1])
            code = generate_promo_code()
        elif len(parts) >= 3:
            amount = int(parts[0])
            max_uses = int(parts[1])
            code = parts[2].upper()
        else:
            raise ValueError
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("SELECT code FROM promocodes WHERE code=?", (code,))
        if c.fetchone():
            safe_send_message(message.chat.id, "❌ Такой промокод уже существует!")
            conn.close()
            return
        c.execute("INSERT INTO promocodes (code, freebet_amount, max_uses, created_by, created_date) VALUES (?, ?, ?, ?, ?)",
                 (code, amount, max_uses, ADMIN_ID, datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()
        conn.close()
        safe_send_message(message.chat.id, f"✅ Промокод создан!\n🎫 Код: {code}\n💰 Сумма фрибета: {amount}\n👥 Использований: {max_uses}\nОтправьте этот код пользователям!")
    except:
        safe_send_message(message.chat.id, "❌ Ошибка!\nФормат: СУММА КОЛ-ВО [КОД]\nПример: 500 10 или 1000 5 HOCKEY")

# ========== ФУНКЦИИ МАТЧЕЙ ==========
def admin_create_match(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        text = message.text
        if ' vs ' not in text: raise ValueError("Нет 'vs'")
        left_part, right_part = text.split(' vs ', 1)
        team1 = left_part.strip()
        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}\s\d{2}:\d{2}', right_part)
        if not date_match: raise ValueError("Не найдена дата")
        date_str = date_match.group()
        date_pos = date_match.start()
        team2 = right_part[:date_pos].strip()
        after_date = right_part[date_pos + len(date_str):].strip()
        coef_parts = after_date.split()
        coef1 = float(coef_parts[0]) if coef_parts else 2.5
        coef2 = float(coef_parts[1]) if len(coef_parts) > 1 else 2.5
        coef_draw = float(coef_parts[2]) if len(coef_parts) > 2 else 3.5
        datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("INSERT INTO matches (team1, team2, match_date, coefficient1, coefficient2, coefficient_draw) VALUES (?, ?, ?, ?, ?, ?)",
                 (team1, team2, date_str, coef1, coef2, coef_draw))
        conn.commit()
        match_id = c.lastrowid
        conn.close()
        safe_send_message(message.chat.id, f"✅ Матч создан!\n🆔: {match_id}\n⚔ {team1} (x{coef1}) vs {team2} (x{coef2})\n🤝 Ничья: x{coef_draw}\n📅 {date_str}")
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ Ошибка: {e}\nПравильный формат:\nКоманда1 vs Команда2 ДД.ММ.ГГГГ ЧЧ:ММ [коэф1 коэф2 коэф_ничьей]")

def admin_set_result(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        match_id = int(parts[0])
        winner = parts[1]
        score = parts[2]
        conn = sqlite3.connect('hockey_bets.db')
        c = conn.cursor()
        c.execute("UPDATE matches SET status='finished', winner=?, score=? WHERE match_id=?", (winner, score, match_id))
        c.execute("SELECT bet_id, user_id, team, amount, bet_type, coefficient FROM bets WHERE match_id=? AND status='pending'", (match_id,))
        bets = c.fetchall()
        for bet in bets:
            bet_id, uid, team, amount, bet_type, coefficient = bet
            if team == winner:
                winnings = amount * coefficient if bet_type not in ('freebet', 'freebet_active') else amount
                c.execute("UPDATE users SET balance = balance + ?, wins = wins + 1 WHERE user_id=?", (int(winnings), uid))
                c.execute("UPDATE bets SET status='won' WHERE bet_id=?", (bet_id,))
                status = "won"
            else:
                c.execute("UPDATE bets SET status='lost' WHERE bet_id=?", (bet_id,))
                status = "lost"
            match_info = f"Матч #{match_id}"
            notify_user(uid, match_info, team, amount, coefficient, bet_type, status, winnings=int(amount*coefficient) if status=='won' and bet_type not in ('freebet','freebet_active') else amount)
        conn.commit()
        conn.close()
        safe_send_message(message.chat.id, f"✅ Результат установлен!\nМатч #{match_id}\n🏆 Победитель: {winner}\n📊 Счет: {score}\n💰 Все ставки рассчитаны!")
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ Ошибка: {e}\nФормат: ID_матча Победитель Счет\nДля ничьей: ID_матча Ничья Счет")

def calculate_all_matches():
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT match_id, team1, team2 FROM matches WHERE status='upcoming'")
    matches = c.fetchall()
    for match in matches:
        outcomes = [match[1], match[2], "Ничья"]
        winner = random.choice(outcomes)
        score = f"{random.randint(1,5)}:{random.randint(1,5)}" if winner == "Ничья" else f"{random.randint(1,7)}:{random.randint(0,6)}"
        c.execute("UPDATE matches SET status='finished', winner=?, score=? WHERE match_id=?", (winner, score, match[0]))
        c.execute("SELECT bet_id, user_id, team, amount, bet_type, coefficient FROM bets WHERE match_id=? AND status='pending'", (match[0],))
        bets = c.fetchall()
        for bet in bets:
            bet_id, uid, team, amount, bet_type, coefficient = bet
            if team == winner:
                winnings = amount * coefficient if bet_type not in ('freebet', 'freebet_active') else amount
                c.execute("UPDATE users SET balance = balance + ?, wins = wins + 1 WHERE user_id=?", (int(winnings), uid))
                c.execute("UPDATE bets SET status='won' WHERE bet_id=?", (bet_id,))
                status = "won"
            else:
                c.execute("UPDATE bets SET status='lost' WHERE bet_id=?", (bet_id,))
                status = "lost"
            match_info = f"Матч #{match[0]} {match[1]} vs {match[2]}"
            notify_user(uid, match_info, team, amount, coefficient, bet_type, status, winnings=int(amount*coefficient) if status=='won' and bet_type not in ('freebet','freebet_active') else amount)
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ СТАВОК ==========
def place_bet(call, user_id, match_id, team, amount):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    balance = c.fetchone()
    c.execute("SELECT team1, coefficient1, coefficient2, coefficient_draw FROM matches WHERE match_id=?", (match_id,))
    match = c.fetchone()
    if not match:
        bot.answer_callback_query(call.id, "❌ Матч не найден!")
        conn.close()
        return
    if team == match[0]: coefficient = match[1]
    elif team == match[2]: coefficient = match[2]
    else: coefficient = match[3]
    if balance and balance[0] >= amount:
        c.execute("UPDATE users SET balance = balance - ?, total_bets = total_bets + 1 WHERE user_id=?", (amount, user_id))
        c.execute("INSERT INTO bets (user_id, match_id, team, amount, coefficient) VALUES (?, ?, ?, ?, ?)", (user_id, match_id, team, amount, coefficient))
        conn.commit()
        new_balance = balance[0] - amount
        bot.answer_callback_query(call.id, "✅ Ставка принята!")
        safe_edit_message(f"✅ Ставка принята!\n🎯 {team}\n💰 {amount} (x{coefficient})\n💵 Баланс: {new_balance}", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
    conn.close()

def process_custom_bet(message):
    user_id = message.from_user.id
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError
        data = user_bet_amount.get(user_id)
        if data:
            conn = sqlite3.connect('hockey_bets.db')
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
            balance = c.fetchone()[0]
            conn.close()
            if balance >= amount:
                place_bet_direct(user_id, data['match_id'], data['team'], amount, message.chat.id)
            else:
                safe_send_message(message.chat.id, "❌ Недостаточно средств!")
        del user_bet_amount[user_id]
    except:
        safe_send_message(message.chat.id, "❌ Введите корректную сумму!")

def place_bet_direct(user_id, match_id, team, amount, chat_id):
    conn = sqlite3.connect('hockey_bets.db')
    c = conn.cursor()
    c.execute("SELECT team1, coefficient1, coefficient2, coefficient_draw FROM matches WHERE match_id=?", (match_id,))
    match = c.fetchone()
    if team == match[0]: coefficient = match[1]
    elif team == match[2]: coefficient = match[2]
    else: coefficient = match[3]
    c.execute("UPDATE users SET balance = balance - ?, total_bets = total_bets + 1 WHERE user_id=?", (amount, user_id))
    c.execute("INSERT INTO bets (user_id, match_id, team, amount, coefficient) VALUES (?, ?, ?, ?, ?)", (user_id, match_id, team, amount, coefficient))
    conn.commit()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    new_balance = c.fetchone()[0]
    conn.close()
    safe_send_message(chat_id, f"✅ Ставка принята!\n💰 {amount} на {team}\n💵 Баланс: {new_balance}")

# ========== ЗАПУСК ДЛЯ RENDER ==========
if __name__ == '__main__':
    print("🏒 EXTRABET запущен на Render!")
    print("👑 Админ-панель активирована")
    print("📸 Система фото уведомлений готова")
    init_db()
    
    # Простой запуск без циклов переподключения
    print("Бот начинает polling...")
    bot.infinity_polling(timeout=30, long_polling_timeout=60)