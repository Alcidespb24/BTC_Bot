import main as m
import time
import conditions as c

client = m.client
positions = client.get_all_positions()

def submit_order():

    while True:
        positions = client.get_all_positions()

        if not positions:
           if c.conditions() == "Buy condition met":
               m.order_details()
        elif positions:
            if c.conditions() == "Sell condition met":
                m.order_details()
