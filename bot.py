import asyncio
import logging
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.live import CryptoDataStream

# Access environment variables for API keys
API_KEY = os.environ.get('API_KEY')
SECRET_KEY = os.environ.get('SECRET_KEY')

# Initialize the trading client
client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# Global variables
latest_price = None
position = None

# Set your trading parameters
SYMBOL = 'BTC/USD'         # Use 'BTC/USD' for the data stream
ENTRY_THRESHOLD = 60000    # Example entry price threshold
PROFIT_TARGET = 5          # Profit target in percentage
STOP_LOSS = -2             # Stop loss in percentage

# Bot control flag
bot_running = False

# Use the root logger
logger = logging.getLogger()

async def place_order(symbol, qty, side):
    """
    Places a market order and logs the order details.
    """
    global latest_price
    try:
        order_details = MarketOrderRequest(
            symbol=symbol.replace('/', ''),  # Remove '/' for trading API
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC
        )
        # Run the blocking submit_order in a separate thread
        order = await asyncio.to_thread(client.submit_order, order_details)
        price = latest_price
        side_str = "Buy" if side == OrderSide.BUY else "Sell"
        logger.info(f"{side_str} order placed: {qty} {symbol} at ${price:.2f}")
        return order
    except Exception as e:
        logger.error(f"Error placing {side_str.lower()} order: {e}")
        return None

async def on_quote(data):
    """
    Callback function to handle price updates from the WebSocket.
    """
    global latest_price, position, bot_running
    if not bot_running:
        logger.info("Bot is stopped. Exiting on_quote.")
        return

    latest_price = float(data.bid_price)
    logger.debug(f"Received price update: {SYMBOL} at ${latest_price:.2f}")
    try:
        if position is None:
            if latest_price <= ENTRY_THRESHOLD:
                logger.info(f"Price ${latest_price:.2f} <= entry threshold ${ENTRY_THRESHOLD}. Evaluating buy opportunity.")
                account = await asyncio.to_thread(client.get_account)
                buying_power = float(account.buying_power) / 3
                qty = buying_power / latest_price
                order = await place_order(SYMBOL, qty, OrderSide.BUY)
                if order:
                    position = {
                        'entry_price': latest_price,
                        'qty': qty
                    }
                    logger.info(f"Entered position: Bought {qty} {SYMBOL} at ${latest_price:.2f}")
        else:
            entry_price = position['entry_price']
            profit_percentage = ((latest_price - entry_price) / entry_price) * 100
            logger.info(f"Current profit: {profit_percentage:.2f}%")
            if profit_percentage >= PROFIT_TARGET:
                logger.info(f"Profit target reached ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logger.info(f"Exited position: Sold {qty} {SYMBOL} at ${latest_price:.2f}")
            elif profit_percentage <= STOP_LOSS:
                logger.info(f"Stop-loss triggered ({profit_percentage:.2f}%). Placing sell order.")
                qty = position['qty']
                order = await place_order(SYMBOL, qty, OrderSide.SELL)
                if order:
                    position = None
                    logger.info(f"Exited position: Sold {qty} {SYMBOL} at ${latest_price:.2f} due to stop-loss")
                else:
                    logger.error("Sell order failed.")
            else:
                logger.debug("No action taken. Holding position.")
    except Exception as e:
        logger.error(f"Error in trading logic: {e}")

async def start_price_stream():
    """
    Starts the WebSocket stream to receive real-time price updates.
    """
    crypto_stream = CryptoDataStream(API_KEY, SECRET_KEY)
    crypto_stream.subscribe_quotes(on_quote, SYMBOL)
    try:
        logger.info("Starting price stream...")
        await crypto_stream._run_forever()
    except Exception as e:
        logger.error(f"Error in price stream: {e}")
    finally:
        await crypto_stream.close()

async def update_position_state():
    """
    Initializes the position state based on current holdings.
    """
    global position
    try:
        positions = await asyncio.to_thread(client.get_all_positions)
        for pos in positions:
            if pos.symbol == SYMBOL.replace('/', ''):
                position = {
                    'entry_price': float(pos.avg_entry_price),
                    'qty': float(pos.qty)
                }
                logger.info(f"Existing position detected: {position}")
                break
    except Exception as e:
        logger.error(f"Error updating position state: {e}")

async def main():
    global bot_running
    bot_running = True

    # Initialize position state
    await update_position_state()

    # Start the price stream
    await start_price_stream()

def stop_bot():
    global bot_running
    bot_running = False
    logger.info("Bot has been stopped.")