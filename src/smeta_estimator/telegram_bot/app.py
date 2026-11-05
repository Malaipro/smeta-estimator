"""Telegram adapter for the preliminary foundation demo."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import logging
import re
import time

from telegram import InputFile, ReplyKeyboardMarkup, Update
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

(
    OBJECT,
    SHAPE,
    HOUSE_LENGTH,
    HOUSE_WIDTH,
    OUTER_LENGTH,
    AREA,
    INNER_LENGTH,
    STOREYS,
    WALL_MATERIAL,
    SOIL,
    PARAMETERS_MODE,
    CUSTOM_PARAMETERS,
    CONFIRM,
    EDIT,
) = range(14)

BUTTON_NEW = "🧮 Новый расчёт"
BUTTON_INFO = "ℹ️ Что рассчитывает бот"
BUTTON_HELP = "❓ Помощь"
BUTTON_BACK = "⬅️ Назад"
BUTTON_CANCEL = "❌ Отменить"
BUTTON_REPEAT = "🔁 Повторить с изменениями"
BUTTON_EXPLAIN = "ℹ️ Пояснения к смете"
BUTTON_CALCULATE = "✅ Рассчитать"
BUTTON_EDIT = "✏️ Изменить параметры"

SHAPE_RECTANGULAR = "Прямоугольный дом"
SHAPE_COMPLEX = "Сложная форма"
NO_INNER_WALLS = "Нет внутренних несущих стен"
DEMO_PARAMETERS = "Использовать демо-параметры"
MANUAL_PARAMETERS = "Ввести параметры вручную"

STOREY_OPTIONS = {"1 этаж": 1, "2 этажа": 2}
WALL_OPTIONS = ("Кирпич", "Porotherm")
SOIL_OPTIONS = (
    "Неизвестен",
    "Условно нормальный",
    "Слабый",
    "Пучинистый",
    "Высокие грунтовые воды",
)
CUSTOM_FIELDS = EDIT_FIELDS[:7]


def _keyboard(rows: list[list[str]], *, include_navigation: bool = True) -> ReplyKeyboardMarkup:
    values = list(rows)
    if include_navigation:
        values.append([BUTTON_BACK, BUTTON_CANCEL])
    return ReplyKeyboardMarkup(values, resize_keyboard=True, one_time_keyboard=True)


MAIN_KEYBOARD = _keyboard(
    [[BUTTON_NEW], [BUTTON_INFO, BUTTON_HELP]],
    include_navigation=False,
)
POST_RESULT_KEYBOARD = _keyboard(
    [[BUTTON_NEW], [BUTTON_REPEAT], [BUTTON_EXPLAIN]],
    include_navigation=False,
)
CONFIRM_KEYBOARD = _keyboard(
    [[BUTTON_CALCULATE], [BUTTON_EDIT], [BUTTON_BACK, BUTTON_CANCEL]],
    include_navigation=False,
)


def _exact_button(value: str):
    return filters.Regex(rf"^{re.escape(value)}$")


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    context.user_data["current_state"] = state
    return state


def _draft(context: ContextTypes.DEFAULT_TYPE) -> FoundationDraft:
    return context.user_data["draft"]


def _is_allowed(update: Update, config: BotConfig) -> bool:
    return bool(
        update.effective_user
        and (
            not config.allowed_user_ids
            or update.effective_user.id in config.allowed_user_ids
        )
    )


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
        "и формирует Excel.\n\n"
        "Цены тестовые. Этажность, материал стен и грунт сохраняются в исходных "
        "данных, но пока не меняют формулу.",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_access(update, context):
        return
    await update.effective_message.reply_text(
        "/new — новый расчёт\n/cancel — отменить текущий расчёт\n/help — помощь\n\n"
        "Размеры вводятся в метрах. Допустимы точка и запятая.",
        reply_markup=MAIN_KEYBOARD,
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_access(update, context):
        return
    await update.effective_message.reply_text(
        "В формуле используются периметр, длина внутренних несущих стен, размеры "
        "ростверка, шаг, диаметр и длина свай. Площадь, этажность, материал стен и "
        "условие по грунту пока выводятся как справочные исходные данные.\n\n"
        "Расчёт предварительный и не заменяет проект конструктора или геологию.",
        reply_markup=MAIN_KEYBOARD,
    )


async def explain_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_access(update, context):
        return
    await update.effective_message.reply_text(
        "Excel содержит 4 листа: сводку, исходные данные, смету и источники цен. "
        "Полный итог не показывается, если у строки нет подтверждённого объёма или цены. "
        "Жёлтым отмечены значения, которые требуют проверки.",
        reply_markup=POST_RESULT_KEYBOARD,
    )


async def _prompt_object(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите условное название объекта без адреса и ФИО.",
        reply_markup=_keyboard([[BUTTON_CANCEL]], include_navigation=False),
    )
    return _set_state(context, OBJECT)


async def _prompt_shape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выберите форму дома.",
        reply_markup=_keyboard([[SHAPE_RECTANGULAR], [SHAPE_COMPLEX]]),
    )
    return _set_state(context, SHAPE)


async def _prompt_house_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите длину дома, м. Например: 10",
        reply_markup=_keyboard([]),
    )
    return _set_state(context, HOUSE_LENGTH)


async def _prompt_house_width(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите ширину дома, м. Например: 12",
        reply_markup=_keyboard([]),
    )
    return _set_state(context, HOUSE_WIDTH)


async def _prompt_outer_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите наружный периметр несущих стен, м. Например: 44",
        reply_markup=_keyboard([]),
    )
    return _set_state(context, OUTER_LENGTH)


async def _prompt_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите ориентировочную площадь дома, м². Она сохраняется в Excel, но пока не меняет формулу.",
        reply_markup=_keyboard([]),
    )
    return _set_state(context, AREA)


async def _prompt_inner_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Введите суммарную длину внутренних несущих стен, м, или выберите, что их нет.",
        reply_markup=_keyboard([[NO_INNER_WALLS]]),
    )
    return _set_state(context, INNER_LENGTH)


async def _prompt_storeys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выберите этажность. Пока она не меняет формулу фундамента.",
        reply_markup=_keyboard([["1 этаж", "2 этажа"]]),
    )
    return _set_state(context, STOREYS)


async def _prompt_wall_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выберите материал стен. Пока он сохраняется справочно.",
        reply_markup=_keyboard([["Кирпич", "Porotherm"]]),
    )
    return _set_state(context, WALL_MATERIAL)


async def _prompt_soil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выберите известное условие по грунту. Это не заменяет геологию.",
        reply_markup=_keyboard([[SOIL_OPTIONS[0], SOIL_OPTIONS[1]], [SOIL_OPTIONS[2], SOIL_OPTIONS[3]], [SOIL_OPTIONS[4]]]),
    )
    return _set_state(context, SOIL)


async def _prompt_parameters_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выберите параметры фундамента. Демо-набор: наружный ростверк 500×600 мм, "
        "внутренний 400×600 мм, сваи Ø350 мм длиной 2 м с шагом 1,5 м. "
        "Это не инженерная рекомендация.",
        reply_markup=_keyboard([[DEMO_PARAMETERS], [MANUAL_PARAMETERS]]),
    )
    return _set_state(context, PARAMETERS_MODE)


async def _prompt_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        draft_summary(_draft(context)),
        reply_markup=CONFIRM_KEYBOARD,
    )
    return _set_state(context, CONFIRM)


async def new_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["draft"] = FoundationDraft()
    return await _prompt_object(update, context)


async def repeat_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    last_draft = context.user_data.get("last_draft")
    if not isinstance(last_draft, FoundationDraft):
        return await new_estimate(update, context)
    context.user_data["draft"] = deepcopy(last_draft)
    return await _prompt_confirmation(update, context)


async def receive_object(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.effective_message.text or "").strip()
    if not name or len(name) > 80:
        await update.effective_message.reply_text("Введите название длиной от 1 до 80 символов.")
        return OBJECT
    _draft(context).object_name = name
    return await _prompt_shape(update, context)


async def receive_shape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = (update.effective_message.text or "").strip()
    if value == SHAPE_RECTANGULAR:
        _draft(context).shape = value
        return await _prompt_house_length(update, context)
    if value == SHAPE_COMPLEX:
        draft = _draft(context)
        draft.shape = value
        draft.house_length_m = None
        draft.house_width_m = None
        return await _prompt_outer_length(update, context)
    await update.effective_message.reply_text("Выберите форму кнопкой.")
    return SHAPE


async def receive_house_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        _draft(context).house_length_m = parse_decimal(update.effective_message.text or "")
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return HOUSE_LENGTH
    return await _prompt_house_width(update, context)


async def receive_house_width(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        width = parse_decimal(update.effective_message.text or "")
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return HOUSE_WIDTH
    draft = _draft(context)
    if draft.house_length_m is None:
        return await _prompt_house_length(update, context)
    draft.set_rectangular_geometry(draft.house_length_m, width)
    return await _prompt_inner_length(update, context)


async def receive_outer_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        _draft(context).outer_wall_length_m = parse_decimal(update.effective_message.text or "")
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return OUTER_LENGTH
    return await _prompt_area(update, context)


async def receive_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        _draft(context).area_m2 = parse_decimal(update.effective_message.text or "")
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return AREA
    return await _prompt_inner_length(update, context)


async def receive_inner_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text == NO_INNER_WALLS:
        value = 0
    else:
        try:
            value = parse_decimal(text, allow_zero=True)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return INNER_LENGTH
    _draft(context).inner_wall_length_m = value
    return await _prompt_storeys(update, context)


async def receive_storeys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text not in STOREY_OPTIONS:
        await update.effective_message.reply_text("Выберите этажность кнопкой.")
        return STOREYS
    _draft(context).storeys = STOREY_OPTIONS[text]
    return await _prompt_wall_material(update, context)


async def receive_wall_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text not in WALL_OPTIONS:
        await update.effective_message.reply_text("Выберите материал кнопкой.")
        return WALL_MATERIAL
    _draft(context).wall_material = text
    return await _prompt_soil(update, context)


async def receive_soil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text not in SOIL_OPTIONS:
        await update.effective_message.reply_text("Выберите вариант грунта кнопкой.")
        return SOIL
    _draft(context).soil_condition = text
    return await _prompt_parameters_mode(update, context)


async def _ask_parameter_field(update: Update, context: ContextTypes.DEFAULT_TYPE, fields) -> None:
    index: int = context.user_data["edit_index"]
    field = fields[index]
    current = getattr(_draft(context), field.name)
    if field.kind == "percent":
        current *= 100
    await update.effective_message.reply_text(
        f"{field.label}, {field.unit}. Сейчас: {current}. Введите новое значение или «-», чтобы оставить.",
        reply_markup=_keyboard([]),
    )


async def receive_parameters_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    draft = _draft(context)
    if text == DEMO_PARAMETERS:
        draft.parameters_source = "Демонстрационные значения"
        return await _prompt_confirmation(update, context)
    if text == MANUAL_PARAMETERS:
        draft.parameters_source = "Ручной ввод"
        context.user_data["edit_index"] = 0
        await _ask_parameter_field(update, context, CUSTOM_FIELDS)
        return _set_state(context, CUSTOM_PARAMETERS)
    await update.effective_message.reply_text("Выберите режим параметров кнопкой.")
    return PARAMETERS_MODE


async def receive_custom_parameter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    index: int = context.user_data["edit_index"]
    field = CUSTOM_FIELDS[index]
    text = (update.effective_message.text or "").strip()
    if text != "-":
        try:
            value = parse_decimal(text)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return CUSTOM_PARAMETERS
        setattr(_draft(context), field.name, value)
    index += 1
    context.user_data["edit_index"] = index
    if index < len(CUSTOM_FIELDS):
        await _ask_parameter_field(update, context, CUSTOM_FIELDS)
        return CUSTOM_PARAMETERS
    return await _prompt_confirmation(update, context)


async def confirm_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    action = (update.effective_message.text or "").strip()
    if action == BUTTON_CALCULATE:
        return await _send_result(update, context)
    if action == BUTTON_EDIT:
        _draft(context).parameters_source = "Ручной ввод"
        context.user_data["edit_index"] = 0
        await _ask_parameter_field(update, context, EDIT_FIELDS)
        return _set_state(context, EDIT)
    await update.effective_message.reply_text("Выберите действие кнопкой.", reply_markup=CONFIRM_KEYBOARD)
    return CONFIRM


async def receive_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    index: int = context.user_data["edit_index"]
    field = EDIT_FIELDS[index]
    text = (update.effective_message.text or "").strip()
    if text != "-":
        try:
            value = parse_percent(text) if field.kind == "percent" else parse_decimal(text)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return EDIT
        setattr(_draft(context), field.name, value)
    index += 1
    context.user_data["edit_index"] = index
    if index < len(EDIT_FIELDS):
        await _ask_parameter_field(update, context, EDIT_FIELDS)
        return EDIT
    return await _prompt_confirmation(update, context)


async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get("current_state")
    if state == SHAPE:
        return await _prompt_object(update, context)
    if state == HOUSE_LENGTH:
        return await _prompt_shape(update, context)
    if state == HOUSE_WIDTH:
        return await _prompt_house_length(update, context)
    if state == OUTER_LENGTH:
        return await _prompt_shape(update, context)
    if state == AREA:
        return await _prompt_outer_length(update, context)
    if state == INNER_LENGTH:
        if _draft(context).shape == SHAPE_RECTANGULAR:
            return await _prompt_house_width(update, context)
        return await _prompt_area(update, context)
    if state == STOREYS:
        return await _prompt_inner_length(update, context)
    if state == WALL_MATERIAL:
        return await _prompt_storeys(update, context)
    if state == SOIL:
        return await _prompt_wall_material(update, context)
    if state == PARAMETERS_MODE:
        return await _prompt_soil(update, context)
    if state in (CUSTOM_PARAMETERS, EDIT):
        fields = CUSTOM_FIELDS if state == CUSTOM_PARAMETERS else EDIT_FIELDS
        index = context.user_data.get("edit_index", 0)
        if index > 0:
            context.user_data["edit_index"] = index - 1
            await _ask_parameter_field(update, context, fields)
            return state
        return await _prompt_parameters_mode(update, context)
    if state == CONFIRM:
        return await _prompt_parameters_mode(update, context)
    return await cancel(update, context)


async def _send_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _draft(context)
    try:
        calculation = calculate_draft(draft)
        content = build_foundation_workbook(
            object_name=draft.object_name,
            project_info=draft.to_project_info(),
            data=calculation.data,
            result=calculation.result,
            lines=calculation.lines,
            demo_summary=calculation.demo_summary,
            price_candidates=calculation.price_candidates,
        )
    except FoundationValidationError as exc:
        details = "\n".join(f"• {issue.field}: {issue.message}" for issue in exc.issues)
        await update.effective_message.reply_text(
            f"Расчёт не выполнен. Проверьте параметры:\n{details}",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END
    except Exception:
        LOGGER.exception("Failed to create foundation estimate")
        await update.effective_message.reply_text(
            "Не удалось сформировать файл. Ошибка записана в журнал без исходных данных пользователя.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    extra_warning = ""
    if draft.soil_condition != "Условно нормальный":
        extra_warning = "\nУсловие по грунту требует геологии и проверки конструктора."
    await update.effective_message.reply_text(
        f"Готово. Свай: {calculation.result.pile_count_effective} шт. "
        f"Бетон к заказу: {calculation.result.concrete_calculated_m3} м³.\n"
        f"Стоимость рассчитанных позиций: "
        f"{format(calculation.demo_summary.known_subtotal, ',.0f').replace(',', ' ')} ₽. "
        "Полный итог пока недоступен: для части строк нет объёма или цены."
        f"{extra_warning}"
    )
    stream = BytesIO(content)
    filename = foundation_workbook_filename(draft.object_name)
    await update.effective_message.reply_document(
        document=InputFile(stream, filename=filename),
        caption=(
            "Предварительная смета фундамента. Цены тестовые, "
            "актуальность и регион не подтверждены."
        ),
        reply_markup=POST_RESULT_KEYBOARD,
    )
    last_draft = deepcopy(draft)
    context.user_data.clear()
    context.user_data["last_draft"] = last_draft
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_access(update, context):
        return ConversationHandler.END
    context.user_data.clear()
    await update.effective_message.reply_text("Текущий расчёт отменён.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


def _state_handlers(handler) -> list:
    return [
        MessageHandler(_exact_button(BUTTON_BACK), go_back),
        MessageHandler(_exact_button(BUTTON_CANCEL), cancel),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handler),
    ]


def build_application(config: BotConfig) -> Application:
    application = Application.builder().token(config.token).concurrent_updates(False).build()
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler("new", new_estimate),
                MessageHandler(_exact_button(BUTTON_NEW), new_estimate),
                MessageHandler(_exact_button(BUTTON_REPEAT), repeat_estimate),
            ],
            states={
                OBJECT: _state_handlers(receive_object),
                SHAPE: _state_handlers(receive_shape),
                HOUSE_LENGTH: _state_handlers(receive_house_length),
                HOUSE_WIDTH: _state_handlers(receive_house_width),
                OUTER_LENGTH: _state_handlers(receive_outer_length),
                AREA: _state_handlers(receive_area),
                INNER_LENGTH: _state_handlers(receive_inner_length),
                STOREYS: _state_handlers(receive_storeys),
                WALL_MATERIAL: _state_handlers(receive_wall_material),
                SOIL: _state_handlers(receive_soil),
                PARAMETERS_MODE: _state_handlers(receive_parameters_mode),
                CUSTOM_PARAMETERS: _state_handlers(receive_custom_parameter),
                CONFIRM: _state_handlers(confirm_action),
                EDIT: _state_handlers(receive_edit),
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("new", new_estimate),
                MessageHandler(_exact_button(BUTTON_CANCEL), cancel),
            ],
            allow_reentry=True,
        )
    )
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(_exact_button(BUTTON_INFO), info_command))
    application.add_handler(MessageHandler(_exact_button(BUTTON_HELP), help_command))
    application.add_handler(MessageHandler(_exact_button(BUTTON_EXPLAIN), explain_estimate))
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
    if config.allowed_user_ids:
        LOGGER.info("Starting Telegram polling for %d allowed user(s)", len(config.allowed_user_ids))
    else:
        LOGGER.info("Starting Telegram polling in public access mode")
    application.run_polling(drop_pending_updates=True)
