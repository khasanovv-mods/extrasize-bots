#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ConversationHandler, ContextTypes
)
from telegram.constants import ParseMode

from database import (
    init_db, create_ticket, get_ticket, get_ticket_status,
    get_old_pending_tickets, take_ticket, update_status,
    close_stale_chats,
    create_chat_request, accept_chat as db_accept_chat, close_chat,
    get_chat, get_active_chat_partner, has_active_chat,
    get_open_chat_by_user,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        from config import BOT_TOKEN as LOCAL_TOKEN
        BOT_TOKEN = LOCAL_TOKEN
    except ImportError:
        pass
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")

ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]
if not ADMIN_IDS:
    try:
        from config import ADMIN_IDS as LOCAL_ADMINS
        ADMIN_IDS = LOCAL_ADMINS
    except ImportError:
        pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_QUESTION, WAITING_REPLY = range(2)

PRICE_LIST_IMAGE = "https://i.ibb.co/jZ1WtWRL/photo-2026-04-06-03-21-49-2.jpg"

PRICE_LIST_TEXT = """
💰 <b>ПРАЙС-ЛИСТ</b>

━━━━━━━━━━━━━━━━━━━━━

 Private skins - 50₽
 Private models (инта | здание) - 50₽
 Private sborka - 150-300₽

━━━━━━━━━━━━━━━━━━━━━

<b>PRIVATE BLOCK</b>

1 месяц - 99₽
3 месяца - 199₽
6 месяцев - 359₽
Навсегда - 699₽

━━━━━━━━━━━━━━━━━━━━━

📞 <b>КАК ЗАКАЗАТЬ?</b>
Нажмите «📞 Связь с администрацией» и напишите, что хотите приобрести.

💳 <b>ОПЛАТА</b>
• Перевод на карту / ЮMoney / ТГ звезды

━━━━━━━━━━━━━━━━━━━━━

<i>Цены актуальны на май 2026 г.</i>
"""

user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Задать вопрос")],
        [KeyboardButton(text="💰 Прайс-лист")],
        [KeyboardButton(text="📞 Связь с администрацией")],
    ],
    resize_keyboard=True
)


# ==================== /start ====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, <b>{user.full_name}</b>!\n\n"
        f"Это бот технической поддержки.\n\n"
        f"Выберите действие на клавиатуре ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=user_keyboard
    )


# ==================== ПРАЙС ====================
async def show_price_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_photo(
            photo=PRICE_LIST_IMAGE,
            caption=PRICE_LIST_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=user_keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка отправки фото прайса: {e}")
        await update.message.reply_text(
            PRICE_LIST_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=user_keyboard,
            disable_web_page_preview=True
        )


# ==================== ТИКЕТЫ (Задать вопрос) ====================
async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Новый вопрос</b>\n\n"
        "Опишите свой вопрос/проблему ниже.\n"
        "При необходимости прикрепите фото, видео или файл.\n\n"
        "Просто отправьте сообщение — я создам тикет.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_QUESTION


def build_admin_kb(ticket_id, ticket_type):
    if ticket_type == "idea":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{ticket_id}"),
                InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{ticket_id}"),
            ],
            [InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{ticket_id}")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{ticket_id}")],
        [InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{ticket_id}")],
    ])


async def notify_admins_new_ticket(context, ticket_id, user, ticket_type, content, media_type, media_file_id):
    header = "❓ <b>НОВЫЙ ВОПРОС</b>" if ticket_type == "question" else "💡 <b>НОВАЯ ИДЕЯ</b>"
    username = user.username or user.full_name

    text = (
        f"{header} <b>#{ticket_id}</b>\n\n"
        f"👤 От: @{username} (ID: <code>{user.id}</code>)\n\n"
        f"📄 <b>Содержание:</b>\n{content or '(без текста)'}"
    )

    kb = build_admin_kb(ticket_id, ticket_type)

    for admin_id in ADMIN_IDS:
        try:
            if media_type == "photo":
                await context.bot.send_photo(admin_id, media_file_id, caption=text,
                                             reply_markup=kb, parse_mode=ParseMode.HTML)
            elif media_type == "video":
                await context.bot.send_video(admin_id, media_file_id, caption=text,
                                             reply_markup=kb, parse_mode=ParseMode.HTML)
            elif media_type == "document":
                await context.bot.send_document(admin_id, media_file_id, caption=text,
                                                reply_markup=kb, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(admin_id, text,
                                               reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Не удалось отправить тикет админу {admin_id}: {e}")


async def _create_ticket_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user

    content = msg.text or msg.caption or ""
    media_type = None
    media_file_id = None

    if msg.photo:
        media_type, media_file_id = "photo", msg.photo[-1].file_id
    elif msg.video:
        media_type, media_file_id = "video", msg.video.file_id
    elif msg.document:
        media_type, media_file_id = "document", msg.document.file_id

    ticket_id = await create_ticket(
        user_id=user.id,
        username=user.username or user.full_name,
        ticket_type="question",
        content=content,
        media_type=media_type,
        media_file_id=media_file_id,
    )

    await notify_admins_new_ticket(
        context, ticket_id, user, "question", content, media_type, media_file_id
    )

    await msg.reply_text(
        f"✅ Ваш вопрос отправлен!\n"
        f"📌 Номер тикета: <b>#{ticket_id}</b>\n\n"
        f"Ожидайте ответа от администратора.",
        parse_mode=ParseMode.HTML,
        reply_markup=user_keyboard
    )
    return ConversationHandler.END


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _create_ticket_from_message(update, context)


# ==================== ТИКЕТЫ: ответ админа ====================
async def _try_take(query, ticket_id, action_name):
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer("⛔ Нет прав", show_alert=True)
        return None

    ticket = await get_ticket(ticket_id)
    if not ticket:
        await query.answer("❌ Тикет не найден", show_alert=True)
        return None

    if ticket["status"] != "pending":
        if ticket["taken_by_username"] and ticket["taken_by"] != admin.id:
            await query.answer(
                f"⛔ Тикет #{ticket_id} уже обработал администратор @{ticket['taken_by_username']}",
                show_alert=True
            )
        else:
            statuses = {
                "taken": "взят другим админом",
                "approved": "уже одобрен",
                "rejected": "уже отклонён",
                "answered": "уже отвечен",
            }
            await query.answer(
                f"⛔ Тикет #{ticket_id} {statuses.get(ticket['status'], ticket['status'])}",
                show_alert=True
            )
        return None

    ok = await take_ticket(ticket_id, admin.id, admin.username or admin.full_name)
    if not ok:
        await query.answer(
            f"⛔ Тикет #{ticket_id} только что обработал другой администратор",
            show_alert=True
        )
        return None

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    for aid in ADMIN_IDS:
        if aid == admin.id:
            continue
        try:
            await query.bot.send_message(
                aid,
                f"ℹ️ Администратор @{admin.username or admin.full_name} обработал тикет <b>#{ticket_id}</b> ({action_name}).",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    return ticket


async def reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[1])
    ticket = await _try_take(query, ticket_id, "ответ")
    if not ticket:
        return ConversationHandler.END

    context.user_data["reply_ticket_id"] = ticket_id

    await query.message.reply_text(
        f"✏️ Напишите ответ пользователю по тикету <b>#{ticket_id}</b>.\n"
        f"Можно отправить текст, фото, видео или файл.",
        parse_mode=ParseMode.HTML
    )
    return WAITING_REPLY


async def _send_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END

    ticket_id = context.user_data.get("reply_ticket_id")
    if not ticket_id:
        await update.message.reply_text("❌ Тикет не найден в контексте.")
        return ConversationHandler.END

    ticket = await get_ticket(ticket_id)
    if not ticket:
        await update.message.reply_text("❌ Тикет не найден.")
        return ConversationHandler.END

    msg = update.message
    admin_name = update.effective_user.username or update.effective_user.full_name
    caption_text = msg.text or msg.caption or ""
    header = (
        f"📬 <b>Ответ от администрации по тикету #{ticket_id}</b>\n\n"
        f"👤 <b>Администратор:</b> @{admin_name}\n"
        f"📝 <b>Ответ:</b>\n{caption_text}"
    )

    try:
        if msg.photo:
            await context.bot.send_photo(ticket["user_id"], msg.photo[-1].file_id,
                                         caption=header, parse_mode=ParseMode.HTML)
        elif msg.video:
            await context.bot.send_video(ticket["user_id"], msg.video.file_id,
                                         caption=header, parse_mode=ParseMode.HTML)
        elif msg.document:
            await context.bot.send_document(ticket["user_id"], msg.document.file_id,
                                            caption=header, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(ticket["user_id"], header,
                                           parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки: {e}")
        return ConversationHandler.END

    await update_status(ticket_id, "answered")
    await update.message.reply_text(f"✅ Ответ по тикету #{ticket_id} отправлен.")

    for aid in ADMIN_IDS:
        if aid == update.effective_user.id:
            continue
        try:
            await context.bot.send_message(
                aid,
                f"💬 Администратор @{admin_name} ответил на тикет <b>#{ticket_id}</b>.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    return ConversationHandler.END


async def approve_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[1])
    ticket = await _try_take(query, ticket_id, "одобрение")
    if not ticket:
        return

    admin_name = query.from_user.username or query.from_user.full_name

    try:
        await context.bot.send_message(
            ticket["user_id"],
            f"🎉 <b>Отличные новости!</b>\n\n"
            f"Ваш тикет <b>#{ticket_id}</b> был <b>ОДОБРЕН</b>!\n\n"
            f"👤 Администратор: @{admin_name}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить юзера: {e}")

    await update_status(ticket_id, "approved")

    for aid in ADMIN_IDS:
        if aid == query.from_user.id:
            continue
        try:
            await context.bot.send_message(
                aid,
                f"🎉 Администратор @{admin_name} <b>одобрил</b> тикет <b>#{ticket_id}</b>.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass


async def reject_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[1])
    ticket = await _try_take(query, ticket_id, "отказ")
    if not ticket:
        return

    admin_name = query.from_user.username or query.from_user.full_name

    try:
        await context.bot.send_message(
            ticket["user_id"],
            f"📋 <b>Статус тикета #{ticket_id}</b>\n\n"
            f"К сожалению, ваш запрос был отклонён.\n\n"
            f"👤 Администратор: @{admin_name}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить юзера: {e}")

    await update_status(ticket_id, "rejected")

    for aid in ADMIN_IDS:
        if aid == query.from_user.id:
            continue
        try:
            await context.bot.send_message(
                aid,
                f"📋 Администратор @{admin_name} <b>отклонил</b> тикет <b>#{ticket_id}</b>.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("reply_ticket_id", None)
    await update.message.reply_text("❌ Действие отменено.", reply_markup=user_keyboard)
    return ConversationHandler.END


# ==================== ЖИВОЙ ЧАТ: запрос ====================
async def request_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # уже есть активный чат?
    partner = await get_active_chat_partner(user.id)
    if partner:
        await update.message.reply_text(
            "⏳ У вас уже есть активный чат с администрацией.\n"
            "Пишите сообщения — они уйдут администратору.\n"
            "Чтобы закончить — /stopchat",
            reply_markup=user_keyboard
        )
        return

    chat_id = await create_chat_request(user.id, user.username or user.full_name)

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"chat_accept_{chat_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"chat_decline_{chat_id}"),
        ]
    ])

    username = user.username or user.full_name

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"📞 <b>Запрос на связь (чат)</b>\n\n"
                f"👤 @{username} (ID: <code>{user.id}</code>)\n\n"
                f"Хочет связаться с администрацией.",
                reply_markup=admin_kb,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Не удалось отправить заявку админу {admin_id}: {e}")

    await update.message.reply_text(
        "✅ Ваш запрос отправлен администрации.\n"
        "⏳ Ожидайте — как только кто-то примет, сможете общаться.\n\n"
        "<i>Как только чат откроется, просто пишите сюда сообщения "
        "(текст, фото, видео, файлы) — они уйдут администратору.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=user_keyboard
    )


async def chat_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer("⛔ Нет прав", show_alert=True)
        return

    chat_id = int(query.data.split("_")[2])
    chat = await get_chat(chat_id)
    if not chat:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    if chat["active"]:
        await query.answer(
            f"⛔ Заявку уже принял @{chat['admin_username']}",
            show_alert=True
        )
        return

    ok = await db_accept_chat(chat_id, admin.id, admin.username or admin.full_name)
    if not ok:
        await query.answer("⛔ Не удалось принять (уже принята)", show_alert=True)
        return

    await query.answer("✅ Вы приняли запрос")

    # уведомим других админов, что заявка ушла
    for aid in ADMIN_IDS:
        if aid == admin.id:
            continue
        try:
            await context.bot.send_message(
                aid,
                f"ℹ️ Администратор @{admin.username or admin.full_name} принял "
                f"запрос на связь от @{chat['username']}.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    # обновим сообщение у админа
    try:
        await query.edit_message_text(
            f"✅ Вы приняли запрос от @{chat['username']} (ID: <code>{chat['user_id']}</code>).\n\n"
            f"💬 Пишите сообщения — они уйдут пользователю.\n"
            f"📌 Чтобы закончить — /stopchat",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    # уведомим юзера
    try:
        await context.bot.send_message(
            chat["user_id"],
            "🎉 <b>Администратор подключился!</b>\n\n"
            "💬 Пишите свои сообщения — они будут переданы администратору.\n"
            "📌 Чтобы закончить — /stopchat",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить юзера {chat['user_id']}: {e}")


async def chat_decline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer("⛔ Нет прав", show_alert=True)
        return

    chat_id = int(query.data.split("_")[2])
    chat = await get_chat(chat_id)
    if not chat:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    if chat["active"]:
        await query.answer("⛔ Заявку уже принял другой администратор", show_alert=True)
        return

    await close_chat(chat_id)

    try:
        await query.edit_message_text(
            f"❌ Вы отклонили запрос от @{chat['username']}.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat["user_id"],
            "❌ К сожалению, администрация сейчас не может ответить.\n"
            "Попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить юзера: {e}")


# ==================== ЖИВОЙ ЧАТ: пересылка сообщений ====================
async def chat_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит любое сообщение (текст/фото/видео/документ) и пересылает партнёру, если есть активный чат."""
    user_id = update.effective_user.id
    msg = update.message
    if not msg:
        return

    # не перехватываем команды и кнопки меню
    if msg.text and (msg.text.startswith("/") or msg.text in (
        "❓ Задать вопрос", "💰 Прайс-лист", "📞 Связь с администрацией"
    )):
        return

    partner_id = await get_active_chat_partner(user_id)
    if not partner_id:
        return

    # добавляем подпись кто пишет
    is_admin = user_id in ADMIN_IDS
    sender_name = update.effective_user.username or update.effective_user.full_name
    prefix = f"👨‍💼 <b>Администратор @{sender_name}:</b>" if is_admin else f"👤 <b>@{sender_name}:</b>"

    try:
        if msg.photo:
            await context.bot.send_photo(
                partner_id, msg.photo[-1].file_id,
                caption=(msg.caption and f"{prefix}\n{msg.caption}") or prefix,
                parse_mode=ParseMode.HTML
            )
        elif msg.video:
            await context.bot.send_video(
                partner_id, msg.video.file_id,
                caption=(msg.caption and f"{prefix}\n{msg.caption}") or prefix,
                parse_mode=ParseMode.HTML
            )
        elif msg.document:
            await context.bot.send_document(
                partner_id, msg.document.file_id,
                caption=(msg.caption and f"{prefix}\n{msg.caption}") or prefix,
                parse_mode=ParseMode.HTML
            )
        elif msg.text:
            await context.bot.send_message(
                partner_id,
                f"{prefix}\n{msg.text}",
                parse_mode=ParseMode.HTML
            )
        else:
            # прочие типы (голосовые, стикеры и т.п.) — просто копируем
            await msg.copy(chat_id=partner_id)
    except Exception as e:
        logger.error(f"Ошибка пересылки сообщения {user_id} -> {partner_id}: {e}")
        await msg.reply_text("❌ Не удалось доставить сообщение администратору.")


# ==================== ЖИВОЙ ЧАТ: /stopchat ====================
async def stop_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = await get_active_chat_partner(user_id)

    if not partner_id:
        await update.message.reply_text(
            "❌ У вас нет активного чата.",
            reply_markup=user_keyboard
        )
        return

    # находим chat_id
    chat = await get_open_chat_by_user(user_id if user_id not in ADMIN_IDS else partner_id)
    if chat:
        await close_chat(chat["id"])

    await update.message.reply_text("🔴 Чат завершён.", reply_markup=user_keyboard)

    try:
        await context.bot.send_message(
            partner_id,
            "🔴 <b>Собеседник завершил чат.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=user_keyboard if partner_id not in ADMIN_IDS else None
        )
    except Exception:
        pass


# ==================== /pending и напоминания ====================
async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет прав")
        return

    hours = int(context.args[0]) if context.args else 0
    tickets = await get_old_pending_tickets(hours=hours)

    if not tickets:
        await update.message.reply_text(f"✅ Нет ожидающих тикетов (> {hours} ч).")
        return

    text = f"📋 <b>Ожидают ответа</b>"
    if hours:
        text += f" (более {hours} ч)"
    text += ":\n\n"

    for t in tickets[:20]:
        try:
            created = datetime.fromisoformat(t["created_at"])
            hours_ago = int((datetime.now() - created).total_seconds() / 3600)
        except Exception:
            hours_ago = "?"
        text += f"• #{t['id']} ({t['type']}) — {hours_ago} ч. назад\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def check_pending_tickets(context: ContextTypes.DEFAULT_TYPE):
    tickets = await get_old_pending_tickets(hours=24)
    if not tickets:
        return

    text = f"⚠️ <b>{len(tickets)}</b> тикетов ждут ответа >24ч:\n\n"
    for t in tickets[:10]:
        text += f"• #{t['id']} ({t['type']})\n"

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            pass


# ==================== STARTUP ====================
async def post_init(app: Application):
    await init_db()
    await close_stale_chats()
    logger.info("✅ БД инициализирована")


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    question_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^❓ Задать вопрос$"), contact_admin),
        ],
        states={
            WAITING_QUESTION: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                    & ~filters.COMMAND,
                    receive_question
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reply_button, pattern=r"^reply_\d+$")],
        states={
            WAITING_REPLY: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                    & ~filters.COMMAND,
                    _send_admin_reply
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # порядок важен: сначала ConversationHandler'ы, потом общий перехватчик чата
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CommandHandler("stopchat", stop_chat_command))

    application.add_handler(MessageHandler(filters.Regex("^💰 Прайс-лист$"), show_price_list))
    application.add_handler(MessageHandler(filters.Regex("^📞 Связь с администрацией$"), request_chat))

    application.add_handler(question_conv)
    application.add_handler(reply_conv)

    application.add_handler(CallbackQueryHandler(chat_accept_callback, pattern=r"^chat_accept_\d+$"))
    application.add_handler(CallbackQueryHandler(chat_decline_callback, pattern=r"^chat_decline_\d+$"))

    application.add_handler(CallbackQueryHandler(approve_button, pattern=r"^approve_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_button, pattern=r"^reject_\d+$"))

    # ловим всё подряд — но отфильтруем внутри чат-хендлера
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
            & ~filters.COMMAND,
            chat_message_handler
        ),
        group=1  # другая группа, чтобы не конфликтовать с ConversationHandler
    )

    if application.job_queue:
        application.job_queue.run_repeating(check_pending_tickets, interval=3600, first=60)
        logger.info("✅ Напоминания настроены")

    logger.info("✅ Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
