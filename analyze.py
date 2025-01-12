import pandas as pd


def analyze_trades(file_path):
    data = pd.read_csv(file_path)

    buy_data = data[data["Action"] == "buy"]
    sell_data = data[data["Action"] == "sell"]

    average_buy_price = buy_data["Price"].mean() if not buy_data.empty else None
    average_sell_price = sell_data["Price"].mean() if not sell_data.empty else None

    latest_buy_price = buy_data["Price"].iloc[-1] if not buy_data.empty else None
    latest_sell_price = sell_data["Price"].iloc[-1] if not sell_data.empty else None

    if latest_sell_price and average_buy_price:
        in_profit = latest_sell_price > average_buy_price
    else:
        in_profit = None  # Profitability cannot be determined

    return {
        "average_buy_price": average_buy_price,
        "average_sell_price": average_sell_price,
        "latest_buy_price": latest_buy_price,
        "latest_sell_price": latest_sell_price,
        "in_profit": in_profit,
    }
