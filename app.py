# app.py

from flask import Flask, render_template_string, request, redirect, url_for, flash
import logging
import os
from flask_httpauth import HTTPBasicAuth

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey')  # For flashing messages

# Configure logging
logging.basicConfig(level=logging.INFO)

auth = HTTPBasicAuth()

# Set username and password from environment variables
USERNAME = os.environ.get('WEB_USERNAME', 'admin')
PASSWORD = os.environ.get('WEB_PASSWORD', 'password')

@auth.verify_password
def verify_password(username, password):
    if username == USERNAME and password == PASSWORD:
        return username
    return None

# Shared configuration dictionary
config = {
    'ENTRY_THRESHOLD': 60000  # Default value
}

# In-memory log storage (for simplicity)
log_messages = []

@app.route('/')
@auth.login_required
def index():
    # Since the bot is running separately, we'll need to get the bot's state via a shared resource.
    # For now, we'll display placeholder data.

    state = {
        'status': 'Unknown',          # Placeholder status
        'latest_price': 'N/A',        # Placeholder latest price
        'account_balance': 'N/A',     # Placeholder account balance
        'position': None,             # No position data
        'pnl': 'N/A'                  # Placeholder P/L
    }

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
                .actions {
                    margin-top: 20px;
                }
                .actions button {
                    padding: 8px 16px;
                    font-size: 16px;
                    margin-right: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Trading Bot Control Panel</h1>
                </div>
                {% with messages = get_flashed_messages() %}
                  {% if messages %}
                    {% for message in messages %}
                      <div class="flash">{{ message }}</div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                <div class="status">
                    <h2>Bot Status: {{ state['status'] }}</h2>
                    <p>Latest Price: ${{ state['latest_price'] }}</p>
                    <p>Account Balance: ${{ state['account_balance'] }}</p>
                    {% if state['position'] %}
                        <p>Current Position: {{ state['position']['qty'] }} units at entry price ${{ state['position']['entry_price'] }}</p>
                        <p>Current P/L: ${{ state['pnl'] }}</p>
                    {% else %}
                        <p>No open positions.</p>
                    {% endif %}
                </div>
                <div class="threshold-form">
                    <h2>Configure Entry Threshold</h2>
                    <form action="{{ url_for('update_threshold') }}" method="post">
                        <label for="entry_threshold">Entry Threshold ($): </label>
                        <input type="number" id="entry_threshold" name="entry_threshold" min="0" step="100" value="{{ config['ENTRY_THRESHOLD'] }}" required>
                        <button type="submit">Update Threshold</button>
                    </form>
                </div>
                <div class="actions">
                    <h2>Actions</h2>
                    <form action="{{ url_for('execute_trade') }}" method="post">
                        <button type="submit">Execute Trade Now</button>
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
    ''', log_messages=log_messages, config=config, state=state)

@app.route('/update_threshold', methods=['POST'])
@auth.login_required
def update_threshold():
    new_threshold = request.form.get('entry_threshold')
    if new_threshold:
        try:
            new_threshold = float(new_threshold)
            # Update the config
            config['ENTRY_THRESHOLD'] = new_threshold
            # Here, you would send the updated config to the bot, e.g., via a shared database or message queue
            flash(f"Entry threshold successfully updated to ${new_threshold:.2f}.")
        except ValueError:
            flash("Invalid entry threshold value.")
    else:
        flash("No entry threshold value provided.")
    return redirect(url_for('index'))

@app.route('/execute_trade', methods=['POST'])
@auth.login_required
def execute_trade():
    # Send command to bot to execute trade immediately
    # For now, just flash a message
    flash("Trade execution triggered.")
    # You would implement the actual command sending to the bot here
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False)