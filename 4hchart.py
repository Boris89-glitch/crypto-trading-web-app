import datetime
import os
import logging
import time
from flask import Flask
import requests
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
import feature_pattern_creation
import testclient_and_orders
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

app = Flask(__name__)


def setup_logging():
    orders_dir = "orders"
    if not os.path.exists(orders_dir):
        os.makedirs(orders_dir)
    logging.basicConfig(
        filename=os.path.join(orders_dir, "order_logs.log"),
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


setup_logging()
logging.basicConfig()

load_dotenv("keyz.env")

api_key = os.getenv("BINANCE_TEST_API_KEY")
secret_key = os.getenv("BINANCE_TEST_SECRET_KEY")

client = Client(api_key, secret_key, testnet=True)


def fetch_data(symbol, interval, limit=700):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data


def scheduled_fetch(interval):
    symbols = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "SHIBUSDT",
        "AVAXUSDT",
        "WBTCUSDT",
        "TRXUSDT",
        "LINKUSDT",
    ]
    for symbol in symbols:
        try:
            logging.info(f"Running scheduled data fetch for {symbol}...")
            data = fetch_data(symbol, interval="1h")

            df = pd.DataFrame(
                data,
                columns=[
                    "Open Time",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                    "Close Time",
                    "Quote Asset Volume",
                    "Number of Trades",
                    "Taker Buy Base Asset Volume",
                    "Taker Buy Quote Asset Volume",
                    "Ignore",
                ],
            )

            df["Open Time"] = pd.to_datetime(df["Open Time"], unit="ms")
            df["Open Time"] = df["Open Time"] + pd.Timedelta(hours=2)
            dir = f"C:\\Users\\Boris\\Desktop\\trading web app\\{symbol}"

            if not os.path.exists(dir):
                os.makedirs(dir)

            filename = f"{dir}\\{symbol}_{interval}_data.csv"
            df.to_csv(filename, index=False)

            find_trend(symbol, interval="1h")
            feature_pattern_creation.process_data(filename)

            check_divergences(symbol, interval)
            check_rsi(symbol, interval)

        except Exception as e:
            logging.exception(f"Error during the scheduled fetch for {symbol}.")


def find_trend(symbol, interval):
    dir = f"C:\\Users\\Boris\\Desktop\\trading web app\\{symbol}"
    filename = f"{dir}\\{symbol}_{interval}_data.csv"
    df = pd.read_csv(filename + "_for_processing.csv")
    if df.empty:
        print(f"No data in {filename}.")
        return

    flag = None
    prev_high_value = prev_low_value = 0
    trend = None

    last_row = df.iloc[-1]
    current_price = last_row["Close"]
    previous_row = df.iloc[-2]
    previous_close = previous_row["Close"]
    atr = last_row["ATR"]
    non_consolidated_df = df[df["consolidated"] == 0]

    if last_row["consolidated"] == 1:
        if not non_consolidated_df.empty:
            last_non_consolidated_row = non_consolidated_df.iloc[-1]
            last_non_consolidated_price = last_non_consolidated_row["Close"]
        else:
            logging.info(
                f"No non-consolidated rows found in {filename}. Unable to determine flag."
            )

        if (
            last_non_consolidated_price is not None
            and previous_close > last_non_consolidated_price
        ):
            flag = "bull_flag"
        elif (
            last_non_consolidated_price is not None
            and previous_close < last_non_consolidated_price
        ):
            flag = "bear_flag"

    for index, row in df.iterrows():
        row_close = row["Close"]

        if row["extrema"] == "high":
            prev_high_value = row_close
        if row["extrema"] == "low":
            prev_low_value = row_close

    if previous_close > prev_high_value:
        trend = "uptrend"
    elif previous_close < prev_high_value and previous_close > prev_low_value:
        trend = "equilibrium?"

    if previous_close < prev_low_value:
        trend = "downtrend"
    elif previous_close > prev_low_value and previous_close < prev_high_value:
        trend = "equilibrium?"

    if flag == "bull_flag":
        buy(symbol, interval, current_price, atr, reason=flag)

    elif flag == "bear_flag":
        sell(symbol, interval, current_price, atr, reason=flag)

    logging.info(
        f"At {row['Open Time']} {interval} {symbol} trend is {trend}  Flag: {flag}, price: {current_price}, prev high value: {prev_high_value}, prev low value: {prev_low_value} "
    )

    return df, trend


def sell(symbol, interval, current_price, atr, reason):
    stop_loss_price = current_price + (1.8 * atr)
    logging.info(
        f"Reason for short: {reason}, price at {current_price}, stop at: {stop_loss_price}, interval: {interval}. "
    )
    position_size = sizing(symbol, current_price)
    testclient_and_orders.log_trade_action(
        symbol, "short", position_size, current_price, reason
    )
    status = testclient_and_orders.check_margin_short_position(client, symbol)
    logging.info(f"SHORT Status for {symbol}: {status}")
    if status == (
        False,
        0.0,
    ) and testclient_and_orders.check_margin_level_and_allow_trading(client):

        stop = testclient_and_orders.adjust_price_to_filter(
            client, symbol, stop_loss_price
        )

        if interval == "5m":
            target_profit_price = current_price - (atr * 1.5)  

        target = testclient_and_orders.adjust_price_to_filter(
            client, symbol, target_profit_price
        )


def buy(symbol, interval, current_price, atr, reason):
    stop_loss_price = current_price - (1.8 * atr)
    logging.info(
        f"Reason for long: {reason}, price at {current_price}, stop at: {stop_loss_price}, interval: {interval}."
    )
    position_size = sizing(symbol, current_price)
    testclient_and_orders.log_trade_action(
        symbol, "buy", position_size, current_price, reason
    )
    status = testclient_and_orders.long_status(client, symbol)
    if status == False and testclient_and_orders.check_margin_level_and_allow_trading(
        client
    ):

        stop = testclient_and_orders.adjust_price_to_filter(
            client, symbol, stop_loss_price
        )

        if interval == "5m":
            target_profit_price = current_price + (atr * 2)

        target = testclient_and_orders.adjust_price_to_filter(
            client, symbol, target_profit_price
        )

    #   testclient_and_orders.place_long_with_stop_loss(client, symbol, position_size, stop, target)


def sizing(symbol, current_price):
    percentage = 0.05
    capital = testclient_and_orders.check_usdt_balance(client, asset="USDT")
    if symbol in ["SHIBUSDT", "PEPEUSDT", "BONKUSDT", "FLOKIUSDT"]:
        formatted_price = "{:.8f}".format(current_price)
        current_price = float(formatted_price) if float(formatted_price) > 0 else 1e-8

    qty = (capital * percentage) / current_price
    position_size = testclient_and_orders.adjust_quantity_to_minimum(
        client, symbol, qty
    )
    print(f"qty: {qty} , price: {current_price}, final size: {position_size}")
    logging.info(f"qty: {qty} , price: {current_price}, final size: {position_size}")

    return position_size


def check_divergences(symbol, interval):
    dir = f"C:\\Users\\Boris\\Desktop\\trading web app\\{symbol}"
    filename = f"{dir}\\{symbol}_{interval}_data.csv"
    try:
        df = pd.read_csv(filename + "_for_processing.csv")
        if df.empty:
            print(f"No data in {filename}.")
            return
        last_row = df.iloc[-1]
        current_price = last_row["Close"]
        before_last_row = df.iloc[-2]
        rsi = float(last_row["RSI"])
        atr = last_row["ATR"]

        print(f"Checking  {filename} for {interval} divergences.")

        if (
            before_last_row["bullish_divergence"] == 1
            or before_last_row["bearish_divergence"] == 1
        ):
            if interval == "15m":
                if rsi > 75 or rsi < 25:
                    if rsi > 75:
                        logging.info(
                            f"Opening short because of divergence in {symbol} {interval} at {current_price}"
                        )
                        sell(symbol, interval, current_price, atr, "bearish divergence")
                    else:
                        logging.info(
                            f"Opening long because of divergence in {symbol} {interval} at {current_price}"
                        )
                        buy(symbol, interval, current_price, atr, "bullish divergence")
            else:
                if rsi > 70:
                    logging.info(
                        f"Opening short because of divergence in {symbol} {interval} at {current_price}"
                    )
                    sell(symbol, interval, current_price, atr, "bearish divergence")
                elif rsi < 30:
                    logging.info(
                        f"Opening long because of divergence in {symbol} {interval} at {current_price}"
                    )
                    buy(symbol, interval, current_price, atr, "bearish divergence")
    except FileNotFoundError:
        print(f"File {filename} not found")
    except Exception as e:
        print(f"Error processing file {filename}: {e}")


def check_rsi(symbol, interval):
    dir = f"C:\\Users\\Boris\\Desktop\\trading web app\\{symbol}"

    filename = f"{dir}\\{symbol}_{interval}_data.csv"
    try:
        df = pd.read_csv(filename + "_for_processing.csv")
        if df.empty:
            print(f"No data in {filename}.")
            return
        if symbol != "BTCUSDT" and symbol != "WBTCUSDT":
            last_row = df.iloc[-1]
            rsi = float(last_row["RSI"])
            current_price = last_row["Close"]
            open_time = last_row["Open Time"]
            atr = last_row["ATR"]

            if rsi > 85:
                sell(symbol, interval, current_price, atr, rsi)
                print(f" In {filename} at {open_time}. ")

            if rsi < 15:
                buy(symbol, interval, current_price, atr, rsi)
    except FileNotFoundError:
        print(f"File {filename} not found")
    except Exception as e:
        print(f"Error processing file {filename}: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(
    func=lambda: scheduled_fetch("5m"),
    trigger="interval",
    minutes=5,
    max_instances=2,
    next_run_time=datetime.datetime.now(),
),
scheduler.add_job(
    func=lambda: scheduled_fetch("1h"),
    trigger="interval",
    minutes=31,
    max_instances=2,
    next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=2),
)
""" scheduler.add_job(
    func=lambda: scheduled_fetch("4h"),
    trigger="interval",
    minutes=120,
    max_instances=2,
    next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=7),
) """
scheduler.start()

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("Stopping scheduler...")
    scheduler.shutdown()


@app.route("/")
def home():
    return "Data fetching and processing service is running."


if __name__ == "__main__":
    app.run(use_reloader=False)
