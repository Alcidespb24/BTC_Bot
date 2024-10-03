import asyncio
import logging
import os
import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.live import CryptoDataStream
import config as cg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Initialize the trading client
client = TradingClient(cg.api_key, cg.secret_key, paper=True)

# Global variables to hold the latest price and position state
latest_price = None
position = None

# Set your trading parameters
SYMBOL = 'BTC/USD'  # Use 'BTC/USD' for the data stream
ENTRY_THRESHOLD = 60000  # Example entry price threshold
PROFIT_TARGET = 5        # Profit target in percentage
STOP_LOSS = -2           # Stop loss in percentage

# Slack webhook URL for notifications
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

def send_slack_message(message):
    if SLACK_WEBHOOK_URL:
        payload = {'text': message}
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if response.status_code != 200:
            logging.error(f"Failed to send Slack message: {response.text}")
    else:
        logging.warning("SLACK_WEBHOOK_URL not set. Cannot send Slack message.")

async def place_order(symbol, qty, side):
    global latest_price
    try:
        order_details = MarketOrderRequest(
            symbol=symbol.replace('/', ''),
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC
        )
        order = await asyncio.to_thread(client.submit_order, order_details)
        price = latest_price
        side_str = "Buy" if side == OrderSide.BUY else "Sell"
        logging.info(f"{side_str} order placed: {qty} {symbol} at ${price:.2f}")
        send_slack_message(f"{side_str} order placed: {qty} {symbol} at ${price:.2f}")
        return order
    except Exception as e:
        logging.error(f"Error placing {side_str.lower()} order: {e}")
        return None

async def on_quote(data):
    global latest_price, position
    latest_price = float(data.bid_price)
    logging.debug(f"Received price update: {SYMBOL} at ${latest_price:.2f}")
    try:
        if position is None:
            if latest_price <= ENTRY_THRESHOLD:
                logging.info(f"Price ${latest_price:.2f} <= entry threshold ${ENTRY_THRESHOLD}. Evaluating buy opportunity.")
                account = await asyncio.to_thread(client.get_account)
                buying_power = float(account.buying_power) / 3
                qty = buying_power / latest_price
                order = await place_order(SYMBOL, qty, OrderSide.BUY)
                if order:
                    position = {
                        'entry_price': latest_price,
                        'qty': qty
                    }
                    logging.info(f"Entered position: Bought {qty} {SYMBOL} at ${latest_price:.2f}")
        else:
            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            logging.info(f"Current profit: {profit_percentage:.2f}%")
            if profit_percentage >= PROFIT_TARGET:
                logging.info(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logging.info(f"Exited position: Sold {qty} {SYMBOL} at ${latest_price:.2f}")
            elif profit_percentage <= STOP_LOSS:
                logging.info(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logging.info(f"Exited position: Sold {qty} {SYMBOL} at ${latest_price:.2f} due to stop-loss")
                else:
                    logging.error("Sell order failed.")
            else:
                logging.debug("No action taken. Holding position.")
    except Exception as e:
        logging.error(f"Error in trading logic: {e}")

async def start_price_stream():
    crypto_stream = CryptoDataStream(cg.api_key, cg.secret_key)
    crypto_stream.subscribe_quotes(on_quote, SYMBOL)
    try:
        logging.info("Starting price stream...")
        await crypto_stream._run_forever()
    except Exception as e:
        logging.error(f"Error in price stream: {e}")
    finally:
        await crypto_stream.close()

async def update_position_state():
    global position
    try:
        positions = await asyncio.to_thread(client.get_all_positions)
        for pos in positions:
            if pos.symbol == SYMBOL.replace('/', ''):
                position = {
                    'entry_price': float(pos.avg_entry_price),
                    'qty': float(pos.qty)
                }
                logging.info(f"Existing position detected: {position}")
                break
    except Exception as e:
        logging.error(f"Error updating position state: {e}")

async def heartbeat():
    while True:
        logging.info("Heartbeat: Trading bot is running.")
        await asyncio.sleep(3600)  # Adjust interval as needed

async def main():
    # Start the heartbeat task
    asyncio.create_task(heartbeat())

    # Initialize position state
    await update_position_state()

    # Start the price stream
    await start_price_stream()

if __name__ == "__main__":
    logging.info("Trading bot started.")
    asyncio.run(main())
