from alpaca.data.requests import CryptoLatestQuoteRequest
from alpaca.data.historical import CryptoHistoricalDataClient
import pandas as pd

def get_latest_crypto_quote(symbol):
    # Initialize the data client
    data_client = CryptoHistoricalDataClient()

    # Set the request parameters
    request_params = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)

    # Get the latest quote
    latest_quote = data_client.get_crypto_latest_quote(request_params)

    # Process the data into a DataFrame
    df_price = pd.concat({k: pd.DataFrame(v) for k, v in latest_quote.items()}, axis=0)
    df_price.drop(columns=[0], inplace=True)
    df_price.rename(index={0: 'symbol', 1: 'time', 2: 'ask_price', 3: 'ask_size', 4: 'bid_exchange', 5: 'bid_price', 6: 'bid_size'}, inplace=True)
    df_price = df_price.T
    df_price.columns = df_price.columns.droplevel(0)

    # Return the entire DataFrame
    return df_price
