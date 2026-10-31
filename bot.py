import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Твой токен от BotFather
TOKEN = "9117035806:AAGPv4a8YN1hVSlQ2FPjK-ZutaSwslzK3hc"

# Сброс логов для блокнота
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

class ConverterState(StatesGroup):
    waiting_for_amount = State()

async def get_all_rates():
    rates = {}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://open.er-api.com/v6/latest/USD") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates.update(data.get("rates", {}))

            crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,toncoin&vs_currencies=usd"
            async with session.get(crypto_url) as resp:
                if resp.status == 200:
                    c_data = await resp.json()
                    rates["BTC_USD"] = c_data.get("bitcoin", {}).get("usd", 0)
                    rates["ETH_USD"] = c_data.get("ethereum", {}).get("usd", 0)
                    rates["USDT_USD"] = c_data.get("tether", {}).get("usd", 1)
                    rates["TON_USD"] = c_data.get("toncoin", {}).get("usd", 0)
        except Exception as e:
            logging.error(f"Ошибка получения курсов: {e}")
        return rates

def get_currencies_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 USD", callback_data="curr_USD"),
            InlineKeyboardButton(text="🇪🇺 EUR", callback_data="curr_EUR"),
            InlineKeyboardButton(text="🇷🇺 RUB", callback_data="curr_RUB"),
        ],
        [
            InlineKeyboardButton(text="🇦🇲 AMD", callback_data="curr_AMD"),
            InlineKeyboardButton(text="🪙 USDT", callback_data="curr_USDT"),
        ],
        [
            InlineKeyboardButton(text="₿ BTC", callback_data="curr_BTC"),
            InlineKeyboardButton(text="Ξ ETH", callback_data="curr_ETH"),
            InlineKeyboardButton(text="💎 TON", callback_data="curr_TON"),
        ]
    ])
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я крипто-фиатный бот-конвертер.\n\n"
        "Выбери валюту или криптовалюту, из которой хочешь перевести:",
        reply_markup=get_currencies_keyboard()
    )

@dp.callback_query(F.data.startswith("curr_"))
async def process_currency(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    await state.update_data(base_currency=currency)
    await callback.message.edit_text(
        f"Выбрана единица: {currency}.\n\n"
        "Теперь введи количество цифрами (например: 1 для крипты или 100 для фиата):"
    )
    await state.set_state(ConverterState.waiting_for_amount)
    await callback.answer()

@dp.message(ConverterState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи корректное число (например, 0.05 или 500).")
        return

    data = await state.get_data()
    base_curr = data.get("base_currency")

    rates = await get_all_rates()
    if not rates:
        await message.answer("❌ Не удалось подключиться к серверам курсов. Попробуй позже.")
        await state.clear()
        return

    usd_value = 0
    if base_curr in ["BTC", "ETH", "USDT", "TON"]:
        price_in_usd = rates.get(f"{base_curr}_USD", 0)
        usd_value = amount * price_in_usd
    else:
        rate_to_usd = rates.get(base_curr, 1)
        if rate_to_usd > 0:
            usd_value = amount / rate_to_usd

    res_usd = usd_value
    res_eur = usd_value * rates.get("EUR", 0.9)
    res_rub = usd_value * rates.get("RUB", 90)
    res_amd = usd_value * rates.get("AMD", 400)
    
    usdt_price = rates.get("USDT_USD", 1)
    res_usdt = usd_value / usdt_price if usdt_price > 0 else usd_value
    
    btc_price = rates.get("BTC_USD", 1)
    res_btc = usd_value / btc_price if btc_price > 0 else 0
    
    eth_price = rates.get("ETH_USD", 1)
    res_eth = usd_value / eth_price if eth_price > 0 else 0
    
    ton_price = rates.get("TON_USD", 1)
    res_ton = usd_value / ton_price if ton_price > 0 else 0

    result_text = (
        f"💱 Конвертация: {amount} {base_curr}\n\n"
        f"Фиат:\n"
        f"🇺🇸 USD: {res_usd:.2f}\n"
        f"🇪🇺 EUR: {res_eur:.2f}\n"
        f"🇷🇺 RUB: {res_rub:.2f}\n"
        f"🇦🇲 AMD: {res_amd:.2f}\n\n"
        f"Криптовалюта:\n"
        f"🪙 USDT: {res_usdt:.2f}\n"
        f"₿ BTC: {res_btc:.6f}\n"
        f"Ξ ETH: {res_eth:.5f}\n"
        f"💎 TON: {res_ton:.2f}\n\n"
        f"Хочешь пересчитать еще? Нажми /start"
    )

    await message.answer(result_text)
    await state.clear()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

await main()
