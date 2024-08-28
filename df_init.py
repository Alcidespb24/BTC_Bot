import os
import pandas as pd
from alpaca.trading.client import TradingClient
import config as cg

def get_account_info():
    # Initialize the trading client with API keys from the config
    client = TradingClient(cg.api_key, cg.secret_key, paper=True)

    # Retrieve account information as a dictionary
    account = dict(client.get_account())

    # Convert the account information to a DataFrame
    df = pd.DataFrame(account, index=[0])

    # Select relevant columns
    df = df[['buying_power', 'status', 'cash']]

    # Return the DataFrame
    return df