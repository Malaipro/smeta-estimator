"""Telegram adapter for the preliminary foundation demo."""

from __future__ import annotations

from io import BytesIO
import logging
import time

from telegram import InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from smeta_estimator.excel import build_foundation_workbook, foundation_workbook_filename
from smeta_estimator.foundation import FoundationValidationError

from .config import BotConfig
from .service import (
    EDIT_FIELDS,
    FoundationDraft,
    calculate_draft,
    draft_summary,
    parse_decimal,
    parse_percent,
)


LOGGER = logging.getLogger(__name__)
OBJECT, OUTER_LENGTH, INNER_LENGTH, CONFIRM, EDIT = range(5)

CONFIRM_KEYBOARD = ReplyKeyboardMarkup(
    [["Рассчитать"], ["Изменить параметры"], ["Отмена"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def _is_allowed(update: Update, config: BotConfig) -> bool:
    return bool(update.effective_user and update.effective_user.id in config.allowed_user_ids)


async def _require_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config: BotConfig = context.application.bot_data["config"]
    if _is_allowed(update, config):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Доступ к демо закрыт. Обратитесь к владельцу бота.")
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_access(update, context):
        return
    await update.effective_message.reply_text(
        "Демо рассчитывает предварительные объёмы свайно-ростверкового фундамента "
        "и формирует Excel. Начать расчёт: /new\n\n"
        "Стоимость пока не подставляется: база цен ещё не подключена."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_access(update, context):
        return
    await update.effective_message.reply_text(
        "/new — новый расчёт\n/cancel — отменить текущий расчёт\n/help — помощь\n\n"
        "Вводите размеры в метрах. Допустимы точка и запятая."
    )


async def new_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["draft"] = FoundationDraft()
    await update.effective_message.reply_text(
        "Введите условное название объекта без адреса и ФИО.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return OBJECT


async def receive_object(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    name = (update.effective_message.text or "").strip()
    if not name or len(name) > 80:
        await update.effective_message.reply_text("Введите название длиной от 1 до 80 символов.")
        return OBJECT
    draft: FoundationDraft = context.user_data["draft"]
    draft.object_name = name
    await update.effective_message.reply_text("Введите периметр наружных несущих стен, м. Например: 40")
    return OUTER_LENGTH


async def receive_outer_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    try:
        value = parse_decimal(update.effective_message.text or "")
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return OUTER_LENGTH
    draft: FoundationDraft = context.user_data["draft"]
    draft.outer_wall_length_m = value
    await update.effective_message.reply_text(
        "Введите суммарную длину внутренних несущих стен, м. Если их нет — 0."
    )
    return INNER_LENGTH


async def receive_inner_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    try:
        value = parse_decimal(update.effective_message.text or "", allow_zero=True)
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return INNER_LENGTH
    draft: FoundationDraft = context.user_data["draft"]
    draft.inner_wall_length_m = value
    await update.effective_message.reply_text(draft_summary(draft), reply_markup=CONFIRM_KEYBOARD)
    return CONFIRM


async def confirm_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    action = (update.effective_message.text or "").strip().lower()
    if action == "рассчитать":
        return await _send_result(update, context)
    if action == "изменить параметры":
        context.user_data["edit_index"] = 0
        await _ask_edit_field(update, context)
        return EDIT
    if action == "отмена":
        return await cancel(update, context)
    await update.effective_message.reply_text(
        "Выберите «Рассчитать», «Изменить параметры» или «Отмена».",
        reply_markup=CONFIRM_KEYBOARD,
    )
    return CONFIRM


async def _ask_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    index: int = context.user_data["edit_index"]
    field = EDIT_FIELDS[index]
    draft: FoundationDraft = context.user_data["draft"]
    current = getattr(draft, field.name)
    if field.kind == "percent":
        current *= 100
    await update.effective_message.reply_text(
        f"{field.label}, {field.unit}. Сейчас: {current}. Введите новое значение или «-», чтобы оставить.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def receive_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    index: int = context.user_data["edit_index"]
    field = EDIT_FIELDS[index]
    text = (update.effective_message.text or "").strip()
    if text != "-":
        try:
            value = parse_percent(text) if field.kind == "percent" else parse_decimal(text)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return EDIT
        draft: FoundationDraft = context.user_data["draft"]
        setattr(draft, field.name, value)

    index += 1
    context.user_data["edit_index"] = index
    if index < len(EDIT_FIELDS):
        await _ask_edit_field(update, context)
        return EDIT

    draft: FoundationDraft = context.user_data["draft"]
    await update.effective_message.reply_text(draft_summary(draft), reply_markup=CONFIRM_KEYBOARD)
    return CONFIRM


async def _send_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft: FoundationDraft = context.user_data["draft"]
    try:
        data, result, lines = calculate_draft(draft)
        content = build_foundation_workbook(
            object_name=draft.object_name,
            data=data,
            result=result,
            lines=lines,
        )
    except FoundationValidationError as exc:
        details = "\n".join(f"• {issue.field}: {issue.message}" for issue in exc.issues)
        await update.effective_message.reply_text(
            f"Расчёт не выполнен. Проверьте параметры:\n{details}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END
    except Exception:
        LOGGER.exception("Failed to create foundation estimate")
        await update.effective_message.reply_text(
            "Не удалось сформировать файл. Ошибка записана в журнал без исходных данных пользователя.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        f"Готово. Свай: {result.pile_count_effective} шт. Бетон к заказу: "
        f"{result.concrete_calculated_m3} м³. Стоимость появится после подключения базы цен."
    )
    stream = BytesIO(content)
    filename = foundation_workbook_filename(draft.object_name)
    await update.effective_message.reply_document(
        document=InputFile(stream, filename=filename),
        caption="Предварительная смета фундамента",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    context.user_data.clear()
    await update.effective_message.reply_text("Текущий расчёт отменён.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def build_application(config: BotConfig) -> Application:
    application = Application.builder().token(config.token).concurrent_updates(False).build()
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("new", new_estimate)],
            states={
                OBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_object)],
                OUTER_LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_outer_length)],
                INNER_LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_inner_length)],
                CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_action)],
                EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("new", new_estimate)],
            allow_reentry=True,
        )
    )
    application.add_handler(CommandHandler("cancel", cancel))
    return application


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTP client request URLs can contain the Telegram bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    config = BotConfig.from_env()
    if config.startup_delay_seconds:
        LOGGER.info("Waiting %.1f seconds before Telegram polling", config.startup_delay_seconds)
        time.sleep(config.startup_delay_seconds)
    application = build_application(config)
    LOGGER.info("Starting Telegram polling for %d allowed user(s)", len(config.allowed_user_ids))
    application.run_polling(drop_pending_updates=True)
