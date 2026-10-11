"""
Premium purchase via Telegram Stars (native payments, currency XTR — no
external payment gateway). Also handles coupon redemption.
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)

from config import PREMIUM_PLANS
from storage import repositories as repo

log = logging.getLogger("spark_baby.payment")
router = Router(name="payment")


def _plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PREMIUM_PLANS.items():
        rows.append([InlineKeyboardButton(
            text=f"{plan['label']} — {plan['stars']} ⭐",
            callback_data=f"buyplan:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("premium"))
async def premium_cmd(message: Message):
    is_premium = await repo.is_premium(message.from_user.id)
    prefix = "🌟 **Tumhara premium already active hai!** Extend karna hai?\n\n" if is_premium else ""
    await message.answer(
        f"{prefix}**Spark Baby Premium**\n\n"
        "✅ Unlimited text + image questions (DM aur groups dono me)\n"
        "✅ Detailed / step-by-step answer mode\n\n"
        "Plan choose karo — payment Telegram Stars se hota hai, seedha Telegram ke andar:",
        reply_markup=_plans_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("buyplan:"))
async def buy_plan_cb(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    plan = PREMIUM_PLANS.get(key)
    if plan is None:
        return await callback.answer("Ye plan available nahi hai.", show_alert=True)

    await callback.answer()
    await callback.message.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Spark Baby Premium — {plan['label']}",
        description=f"{plan['label']} ke liye unlimited AI access + detailed mode.",
        payload=f"premium:{key}:{callback.from_user.id}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=plan["label"], amount=plan["stars"])],
        provider_token="",  # empty for Telegram Stars
    )


@router.pre_checkout_query()
async def pre_checkout_handler(pcq: PreCheckoutQuery):
    # No stock/inventory to validate — plans are always "available".
    await pcq.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    try:
        _, plan_key, _ = payment.invoice_payload.split(":")
    except ValueError:
        log.error(f"[payment] malformed invoice payload: {payment.invoice_payload}")
        return await message.answer("⚠️ Payment mila par plan identify nahi ho paya. Owner ko contact karo.")

    plan = PREMIUM_PLANS.get(plan_key)
    if plan is None:
        log.error(f"[payment] unknown plan_key in payload: {plan_key}")
        return await message.answer("⚠️ Payment mila par plan invalid tha. Owner ko contact karo.")

    await repo.record_payment(
        payment.telegram_payment_charge_id, message.from_user.id, plan_key,
        payment.total_amount, plan["days"],
    )
    new_until = await repo.grant_premium_days(message.from_user.id, plan["days"])

    import time
    days_left = max(0, (new_until - int(time.time())) // 86400)
    await message.answer(
        f"🎉 **Payment successful! Premium activated.**\n"
        f"Plan: {plan['label']} ({plan['stars']} ⭐)\n"
        f"Total validity ab: ~{days_left} din.",
        parse_mode="Markdown",
    )


@router.message(Command("redeem"))
async def redeem_cmd(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Usage: `/redeem <code>`", parse_mode="Markdown")

    code = args[1].strip()
    ok, reason, days = await repo.redeem_coupon(code, message.from_user.id)

    if not ok:
        reasons = {
            "not_found": "❌ Ye coupon code exist nahi karta.",
            "expired": "❌ Ye coupon expire ho gaya hai.",
            "exhausted": "❌ Ye coupon ki saari uses khatam ho gayi hain.",
            "already_used": "❌ Tum already ye coupon redeem kar chuke ho.",
        }
        return await message.answer(reasons.get(reason, "❌ Coupon redeem nahi ho paya."))

    new_until = await repo.grant_premium_days(message.from_user.id, days)
    import time
    days_left = max(0, (new_until - int(time.time())) // 86400)
    await message.answer(
        f"🎉 **Coupon redeemed!** {days} din ka premium mil gaya.\n"
        f"Total validity ab: ~{days_left} din.",
        parse_mode="Markdown",
    )
