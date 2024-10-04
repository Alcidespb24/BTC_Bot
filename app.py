# app.py

from flask import Flask, render_template_string, request, redirect, url_for, flash
import threading
import logging
import os
import asyncio
from flask_httpauth import HTTPBasicAuth

# In-memory log storage
log_messages = []

# Shared configuration dictionary
config = {
    'ENTRY_THRESHOLD': 60000  # Default value
}

# Logging configuration to capture logs from 'bot' logger
class InMemoryLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_messages.append(log_entry)
        # Limit the number of log messages to prevent memory issues
        if len(log_messages) > 1000:
            log_messages.pop(0)

# Set up logging before importing bot to ensure bot uses the same logger
bot_logger = logging.getLogger('bot')  # Listen to 'bot' logger
bot_logger.setLevel(logging.INFO)       # Set to INFO to capture relevant messages
handler = InMemoryLogHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
handler.setFormatter(formatter)
bot_logger.addHandler(handler)

# Now import the bot module after setting up logging
from bot import main as bot_main, stop_bot

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey')  # For flashing messages

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
config_lock = threading.Lock()  # To ensure thread-safe access to config

@app.route('/')
@auth.login_required
def index():
    global bot_running, config
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Bot Control Panel</title>
            <meta http-equiv="refresh" content="5"> <!-- Refresh every 5 seconds -->
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 20px; 
                    background-color: #f0f2f5;
                }
                h1 { 
                    color: #333; 
                }
                button { 
                    padding: 10px 20px; 
                    margin: 5px; 
                    font-size: 16px;
                    cursor: pointer;
                    border: none;
                    border-radius: 5px;
                    transition: background-color 0.3s;
                }
                button:disabled {
                    background-color: #ccc;
                    cursor: not-allowed;
                }
                .start-btn {
                    background-color: #28a745; /* Green */
                    color: white;
                }
                .start-btn:hover:not(:disabled) {
                    background-color: #218838;
                }
                .stop-btn {
                    background-color: #dc3545; /* Red */
                    color: white;
                }
                .stop-btn:hover:not(:disabled) {
                    background-color: #c82333;
                }
                .logs { 
                    white-space: pre-wrap; 
                    border: 1px solid #ccc; 
                    padding: 10px; 
                    height: 400px; 
                    overflow-y: scroll; 
                    background-color: #fff;
                    border-radius: 5px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                }
                .container {
                    max-width: 900px;
                    margin: auto;
                }
                .controls {
                    margin-bottom: 20px;
                }
                .controls form {
                    display: inline-block;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .header div {
                    display: flex;
                    align-items: center;
                }
                .header h1 {
                    margin: 0;
                }
                .status {
                    font-size: 18px;
                    color: #28a745;
                    font-weight: bold;
                }
                .status.stopped {
                    color: #dc3545;
                }
                .threshold-form {
                    margin-top: 20px;
                }
                .threshold-form input {
                    padding: 8px;
                    font-size: 16px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    width: 150px;
                }
                .threshold-form button {
                    padding: 8px 16px;
                    font-size: 16px;
                    margin-left: 10px;
                }
                .flash {
                    padding: 10px;
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                    border-radius: 4px;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Trading Bot Control Panel</h1>
                    <div class="status {% if not bot_running %}stopped{% endif %}">
                        {% if bot_running %}
                            Status: Running
                        {% else %}
                            Status: Stopped
                        {% endif %}
                    </div>
                </div>
                {% with messages = get_flashed_messages() %}
                  {% if messages %}
                    {% for message in messages %}
                      <div class="flash">{{ message }}</div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                <div class="controls">
                    <form action="{{ url_for('start_bot') }}" method="post">
                        {% if not bot_running %}
                        <button type="submit" class="start-btn">Start Bot</button>
                        {% else %}
                        <button type="submit" class="start-btn" disabled>Bot Running</button>
                        {% endif %}
                    </form>
                    <form action="{{ url_for('stop_bot_route') }}" method="post">
                        {% if bot_running %}
                        <button type="submit" class="stop-btn">Stop Bot</button>
                        {% else %}
                        <button type="submit" class="stop-btn" disabled>Bot Stopped</button>
                        {% endif %}
                    </form>
                </div>
                <div class="threshold-form">
                    <h2>Configure Entry Threshold</h2>
                    <form action="{{ url_for('update_threshold') }}" method="post">
                        <label for="entry_threshold">Entry Threshold ($): </label>
                        <input type="number" id="entry_threshold" name="entry_threshold" min="0" step="100" value="{{ config['ENTRY_THRESHOLD'] }}" required>
                        <button type="submit">Update Threshold</button>
                    </form>
                </div>
                <h2>Logs</h2>
                <div class="logs" id="logContainer">
                    {% for message in log_messages %}
                        {% if 'ERROR' in message %}
                            <span style="color: red;">{{ message }}</span><br>
                        {% elif 'WARNING' in message %}
                            <span style="color: orange;">{{ message }}</span><br>
                        {% elif 'INFO' in message %}
                            <span style="color: green;">{{ message }}</span><br>
                        {% else %}
                            {{ message }}<br>
                        {% endif %}
                    {% endfor %}
                </div>
            </div>
            <script>
                // Auto-scroll to the bottom of the logs div
                var logContainer = document.getElementById("logContainer");
                logContainer.scrollTop = logContainer.scrollHeight;
            </script>
        </body>
        </html>
    ''', bot_running=bot_running, log_messages=log_messages, config=config)

@app.route('/start', methods=['POST'])
@auth.login_required
def start_bot():
    global bot_running, bot_thread, config
    if not bot_running:
        bot_running = True
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        bot_logger.info("Bot started via web interface.")
        flash("Bot has been started.")
    else:
        flash("Bot is already running.")
    return redirect(url_for('index'))

@app.route('/stop', methods=['POST'])
@auth.login_required
def stop_bot_route():
    global bot_running
    if bot_running:
        stop_bot()
        bot_running = False
        bot_logger.info("Bot stopped via web interface.")
        flash("Bot has been stopped.")
    else:
        flash("Bot is not running.")
    return redirect(url_for('index'))

@app.route('/update_threshold', methods=['POST'])
@auth.login_required
def update_threshold():
    global config
    new_threshold = request.form.get('entry_threshold')
    if new_threshold:
        try:
            new_threshold = float(new_threshold)
            with config_lock:
                config['ENTRY_THRESHOLD'] = new_threshold
            bot_logger.info(f"Entry threshold updated to ${new_threshold:.2f} via web interface.")
            flash(f"Entry threshold successfully updated to ${new_threshold:.2f}.")
        except ValueError:
            flash("Invalid entry threshold value.")
    else:
        flash("No entry threshold value provided.")
    return redirect(url_for('index'))

def run_bot():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot_main(config, config_lock))
    except Exception as e:
        bot_logger.error(f"Bot encountered an exception: {e}")
    finally:
        loop.close()

if __name__ == '__main__':
    # For local testing, use Flask's built-in server
    # For production, Gunicorn handles running the app
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))