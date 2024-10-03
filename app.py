# app.py

from flask import Flask, render_template_string, request, redirect, url_for
import threading
import logging
import os
import asyncio
from flask_httpauth import HTTPBasicAuth

# In-memory log storage
log_messages = []

# Logging configuration to capture logs in memory
class InMemoryLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_messages.append(log_entry)
        # Limit the number of log messages to prevent memory issues
        if len(log_messages) > 1000:
            log_messages.pop(0)

# Set up logging before importing bot to ensure bot uses the same logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all messages
handler = InMemoryLogHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Now import the bot module after setting up logging
from bot import main as bot_main, stop_bot

app = Flask(__name__)

auth = HTTPBasicAuth()

# Set username and password from environment variables
USERNAME = os.environ.get('WEB_USERNAME', 'admin')
PASSWORD = os.environ.get('WEB_PASSWORD', 'password')

@auth.verify_password
def verify_password(username, password):
    if username == USERNAME and password == PASSWORD:
        return username
    return None

# Global variables to control the bot's execution
bot_thread = None
bot_running = False

@app.route('/')
@auth.login_required
def index():
    global bot_running
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Bot Control Panel</title>
            <meta http-equiv="refresh" content="5"> <!-- Refresh every 5 seconds -->
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                h1 { color: #333; }
                button { padding: 10px 20px; margin: 5px; }
                .logs { white-space: pre-wrap; border: 1px solid #ccc; padding: 10px; height: 400px; overflow-y: scroll; background-color: #f9f9f9; }
            </style>
        </head>
        <body>
            <h1>Trading Bot Control Panel</h1>
            <form action="{{ url_for('start_bot') }}" method="post">
                {% if not bot_running %}
                <button type="submit">Start Bot</button>
                {% else %}
                <button type="submit" disabled>Bot Running</button>
                {% endif %}
            </form>
            <form action="{{ url_for('stop_bot_route') }}" method="post">
                {% if bot_running %}
                <button type="submit">Stop Bot</button>
                {% else %}
                <button type="submit" disabled>Bot Stopped</button>
                {% endif %}
            </form>
            <h2>Logs</h2>
            <div class="logs">
                {% for message in log_messages %}
                    {{ message }}<br>
                {% endfor %}
            </div>
        </body>
        </html>
    ''', bot_running=bot_running, log_messages=log_messages)

@app.route('/start', methods=['POST'])
@auth.login_required
def start_bot():
    global bot_running, bot_thread
    if not bot_running:
        bot_running = True
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logging.info("Bot started via web interface.")
    return redirect(url_for('index'))

@app.route('/stop', methods=['POST'])
@auth.login_required
def stop_bot_route():
    global bot_running
    if bot_running:
        stop_bot()
        bot_running = False
        logging.info("Bot stopped via web interface.")
    return redirect(url_for('index'))

def run_bot():
    asyncio.run(bot_main())

if __name__ == '__main__':
    # Use a production-ready WSGI server like Gunicorn for deployment
    # For local testing, Flask's built-in server is sufficient
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))