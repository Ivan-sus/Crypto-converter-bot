import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# 1. Веб-сервер для удержания порта Render в активном состоянии
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# 2. Твой актуальный рабочий токен от BotFather
TOKEN = "9117035806:AAEAevrS2Ue8hNBoGgv-oftHOzJDyzfhGRw"

# 3. Логирование и инициализация бота
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

class ConverterState(StatesGroup):
    waiting_for_amount = State()
    active_converter = State()  # Состояние постоянной работы

# 4. Функция получения курсов (фиат + Binance для крипты)
async def get_all_rates():
    rates = {}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://open.er-api.com/v6/latest/USD") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates.update(data.get("rates", {}))

            async with session.get("https://api.binance.com/api/v3/ticker/price") as resp:
                if resp.status == 200:
                    prices = await resp.json()
                    binance_prices = {item['symbol']: float(item['price']) for item in prices}
                    
                    rates["BTC_USD"] = binance_prices.get("BTCUSDT")
                    rates["ETH_USD"] = binance_prices.get("ETHUSDT")
                    rates["TON_USD"] = binance_prices.get("TONUSDT")
                    rates["USDT_USD"] = 1.0  # USDT к USD всегда 1
        except Exception as e:
            logging.error(f"Ошибка получения курсов: {e}")
    return rates

def get_currency_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="🇺🇸 USD", callback_data="curr_USD"), InlineKeyboardButton(text="🇪🇺 EUR", callback_data="curr_EUR")],
        [InlineKeyboardButton(text="🇷🇺 RUB", callback_data="curr_RUB"), InlineKeyboardButton(text="🇦🇲 AMD", callback_data="curr_AMD")],
        [InlineKeyboardButton(text="🪙 USDT", callback_data="curr_USDT"), InlineKeyboardButton(text="₿ BTC", callback_data="curr_BTC")],
        [InlineKeyboardButton(text="Ξ ETH", callback_data="curr_ETH"), InlineKeyboardButton(text="💎 TON", callback_data="curr_TON")],
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="change_amount")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Привет! Я крипто-фиатный конвертер.\n\nВведите сумму, которую хотите конвертировать (например: `100` или `50.5`):"
    )
    await state.set_state(ConverterState.waiting_for_amount)

@dp.message(ConverterState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (например: 100).")
        return

    await state.update_data(amount=amount)
    await state.set_state(ConverterState.active_converter)
    
    # Показываем базовое сообщение со списком валют
    await message.answer(
        f"💵 Сумма установлена: **{amount}**\n\nВыберите валюту, **из которой** переводим:",
        reply_markup=get_currency_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "change_amount")
async def change_amount_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ConverterState.waiting_for_amount)
    await callback.message.answer("Введите новую сумму для конвертации:")
    await callback.answer()

@dp.callback_query(F.data.startswith("curr_"))
async def process_currency_choice(callback: types.CallbackQuery, state: FSMContext):
    from_curr = callback.data.split("_")[1]
    data = await state.get_data()
    amount = data.get("amount")

    if not amount:
        await callback.message.answer("Сумма не найдена. Пожалуйста, отправьте /start")
        return

    rates = await get_all_rates()

    usd_value = amount
    if from_curr != "USD":
        if from_curr in ["EUR", "RUB", "AMD"]:
            rate = rates.get(from_curr)
            if rate:
                usd_value = amount / rate
        else:
            crypto_key_map = {"BTC": "BTC_USD", "ETH": "ETH_USD", "USDT": "USDT_USD", "TON": "TON_USD"}
            c_key = crypto_key_map.get(from_curr)
            c_price = rates.get(c_key)
            if c_price:
                usd_value = amount * c_price

    res_usd = usd_value
    res_eur = usd_value * rates.get("EUR", 1)
    res_rub = usd_value * rates.get("RUB", 1)
    res_amd = usd_value * rates.get("AMD", 1)

    btc_price = rates.get("BTC_USD")
    eth_price = rates.get("ETH_USD")
    usdt_price = rates.get("USDT_USD")
    ton_price = rates.get("TON_USD")

    res_usdt = usd_value / usdt_price if usdt_price else 0
    res_btc = usd_value / btc_price if btc_price else 0
    res_eth = usd_value / eth_price if eth_price else 0
    res_ton = usd_value / ton_price if ton_price else 0

    result_text = (
        f"💱 База: **{amount} {from_curr}**\n\n"
        f"Фиат:\n"
        f"🇺🇸 USD: {res_usd:.2f}\n"
        f"🇪🇺 EUR: {res_eur:.2f}\n"
        f"🇷🇺 RUB: {res_rub:.2f}\n"
        f"🇦🇲 AMD: {res_amd:.2f}\n\n"
        f"Криптовалюта:\n"
        f"🟡 USDT: {res_usdt:.2f}\n"
        f"₿ BTC: {res_btc:.6f}\n"
        f"Ξ ETH: {res_eth:.5f}\n"
        f"💎 TON: {res_ton:.2f}\n\n"
        f"👇 Нажмите другую валюту для пересчета или измените сумму:"
    )

    # Редактируем существующее сообщение, чтобы не плодить новые
    try:
        await callback.message.edit_text(result_text, reply_markup=get_currency_keyboard(), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
