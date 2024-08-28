import os
from datetime import datetime

def write_order_summary(order_type, symbol, qty, price, side):
    summary = (
        f"Order Type: {order_type}\n"
        f"Symbol: {symbol}\n"
        f"Quantity: {qty}\n"
        f"Price: {price}\n"
        f"Side: {side}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "-------------------------------\n"
    )

    # Define the summary file path
    summary_file = "order_summary.txt"

    # Write to the file (append mode)
    with open(summary_file, "a") as file:
        file.write(summary)

    print(f"Order summary written to {summary_file}")
