import df_price as dfp

def conditions():
    latest_quote = dfp.get_latest_crypto_quote("BTC/USD")
    print(latest_quote)
    if latest_quote['bid_price'].iloc[0] < 60000:
        print("Buy condition met")
        return "Buy condition met"
    elif latest_quote['ask_price'].iloc[0] > 70000:
        return "Sell condition met"
    else:
        print("No condition met")
