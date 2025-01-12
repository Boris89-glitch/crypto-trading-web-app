import math
from binance.client import Client
from binance.enums import *
import logging
import os
import datetime
from dotenv import load_dotenv


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
client.API_URL = "https://testnet.binance.vision/api"

def check_margin_availability(client, asset):
    try:
        margin_details = client.get_max_margin_loan(asset=asset)
        print(f"My Margin details for {asset}: {margin_details}")
        return margin_details
    except Exception as e:
        logging.error(f"Error retrieving margin details for {asset}: {e}")
        return None


def place_margin_short_with_oco(
    client, symbol, quantity, stop_loss_price, target_profit_price
):  
    info = client.get_symbol_info(symbol)
    tick_size = float(
        next(
            item["tickSize"]
            for item in info["filters"]
            if item["filterType"] == "PRICE_FILTER"
        )
    )

    def format_price(price):
        return "{:0.0{}f}".format(price, -int(math.log10(tick_size)))

    adjusted_stop_loss_price = float(format_price(stop_loss_price - 0.01))
    try:
        asset = symbol[:-4]
        # Step 1: Borrow the asset
        borrow_response = client.create_margin_loan(asset=asset, amount=str(quantity))
        logging.info(f"Asset borrowed for shorting: {borrow_response}")

        # Step 2: Place a market sell to open the short position
        market_sell_response = client.create_margin_order(
            symbol=symbol, side="SELL", type="MARKET", quantity=quantity
        )
        logging.info(f"Market sell order placed for short: {market_sell_response}")

        # Step 3: Place the OCO order for taking profit and limiting loss
        oco_response = client.create_margin_oco_order(
            symbol=symbol,
            side="BUY", 
            quantity=quantity,
            price=target_profit_price,  
            stopPrice=stop_loss_price,  
            stopLimitPrice=adjusted_stop_loss_price,
            stopLimitTimeInForce="GTC",
        )
        logging.info(
            f"OCO order placed with target: {target_profit_price}, stop: {stop_loss_price}. Full response: {oco_response}"
        )

        return oco_response
    except Exception as e:
        logging.error(f"Failed to place margin short with OCO for {symbol}: {e}")
        return None


def check_usdt_balance(client, asset="USDT"):
    try:
        account_info = client.get_margin_account()
        balances = account_info["userAssets"]
        asset_balance = 0
        # convert total btc liability
        btc_price = get_current_price(client, "BTCUSDT")
        total_debt = btc_price * float(account_info["totalLiabilityOfBtc"])
        total_balance = float(account_info["totalCollateralValueInUSDT"])
        print(f"btc price {btc_price}, total debt: {total_debt}, total balance {total_balance}")

        for balance in balances:
            curr_asset = balance["asset"]
            free = balance["free"]
            if curr_asset == asset:
                asset_balance = total_balance - total_debt
                if asset_balance > 0:
                    print(f"Balance for {asset}: {asset_balance}")
        if asset_balance > 0:
            print(f"Balance for {asset}: {asset_balance}")
        else:
            print(f"No balance available for {asset}.")
        return asset_balance

    except Exception as e:
        print(f"Error retrieving balances: {e}")
        return 0


def place_long_with_stop_loss(
    client,
    symbol,
    quantity,
    stop_loss_price
):
    try:
        print(f"Placing long oco order for {quantity} of {symbol}.")
        borrow_response = client.create_margin_loan(
            asset="USDT", amount=str(quantity)
        )
        logging.info(
            f"USDT borrowed for long amount: {quantity}, response: {borrow_response}"
        )

        market_buy_response = client.create_margin_order(
            symbol=symbol, side="BUY", type="MARKET", quantity=quantity
        )
        logging.info(f"Market buy order placed for long: {market_buy_response}")

        print(
            f"Placing stop-loss order for {quantity} of {symbol} at {stop_loss_price}"
        )

        # Ensure to adjust the price to meet the precision requirement
        # formatted_stop_loss_price = "{:.8f}".format(stop_loss_price)

        stop_loss_response = client.create_margin_order(
            symbol=symbol,
            side="SELL",
            type="STOP_LOSS_LIMIT",
            quantity=quantity,
            price=stop_loss_price,  
            stopPrice=stop_loss_price + 0.01,
            timeInForce="GTC",
        )

        logging.info(
            f"Stop-loss order placed: {stop_loss_response}")
        print(f"OCO Order placed.")

    except Exception as e:
        print(f"Failed to place order: {e}")


def check_margin_level_and_allow_trading(client, threshold=1.7):
    """
    Checks the margin level and determines if trading should be allowed.

    :param client: Binance API client
    :param threshold: float, the minimum margin level required to allow trading
    :return: bool, True if trading is allowed, False otherwise
    """
    try:
        margin_details = client.get_margin_account()

        margin_level = float(margin_details.get("totalAssetOfBtc", 0)) / float(
            margin_details.get("totalLiabilityOfBtc", 1)
        )

        if margin_level > threshold:
            logging.info(f"Margin level is healthy: {margin_level}. Trading is allowed.")
            return True
        else:
            logging.info(f"Margin level is low: {margin_level}. Trading is restricted.")
            return False

    except Exception as e:
        logging.info(f"Failed to retrieve or calculate margin level: {e}")
        return False



def cancel_orders(client, symbol):
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        for order in open_orders:
            canceled_order = client.cancel_order(
                symbol=symbol, orderId=order["orderId"]
            )
            print(f"Canceled order ID: {canceled_order['orderId']}")
    except Exception as e:
        print(f"Failed to cancel orders: {e}")


def close_order(symbol, order_type, quantity):
    try:
        print(f"Closing {order_type} order for {quantity} of {symbol}.")
        order = client.order_market(
            symbol=symbol,
            side=SIDE_SELL if order_type == "long" else SIDE_BUY,
            quantity=quantity,
        )
        print(f"Order closed: {order}")
        logging.info(f"Order closed: {order}")
    except Exception as e:
        print(f"Failed to close order: {e}")


def get_current_price(client, symbol):
    """Get the current price of a specific symbol"""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker["price"])
        return current_price
    except Exception as e:
        print(f"Error retrieving current price: {e}")
        logging.info(f"Error retrieving current price: {e}")
        return None


def calculate_quantity(capital, price):
    quantity = capital / price
    return quantity


def adjust_price_to_filter(client, symbol, price):
    try:
        info = client.get_symbol_info(symbol)
        # Extract the minimum price and tick size from symbol filters
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                min_price = float(f["minPrice"])
                tick_size = float(f["tickSize"])
                break

        decimal_places = int(-math.log10(tick_size))

        price = math.floor(price / tick_size) * tick_size

        price = round(price, decimal_places)

        price = max(min_price, price)

        return price
    except Exception as e:
        logging.error("Failed to adjust price: " + str(e))
        return None  # Or handle error appropriately


def adjust_quantity_to_minimum(client, symbol, quantity):
    try:
        info = client.get_symbol_info(symbol)
        min_qty = float(info["filters"][1]["minQty"])
        step_size = float(info["filters"][1]["stepSize"])
        decimal_places = int(-math.log10(step_size))

        quantity = math.floor(quantity / step_size) * step_size

        quantity = round(quantity, decimal_places)

        quantity = max(min_qty, quantity)

        return quantity
    except Exception as e:
        print(f"Error adjusting quantity: {e}")
        return None


def long_status(client, symbol):
    try:
        margin_account = client.get_margin_account()
        asset = symbol[:-4]  # Assuming 'BTCUSDT', asset would be 'BTC'

        # Extract the net asset balance (free + locked - borrowed)
        asset_balance = next(
            (bal for bal in margin_account["userAssets"] if bal["asset"] == asset), None
        )
        if asset_balance:
            free_balance = float(asset_balance["free"])
            locked_balance = float(asset_balance["locked"])
            borrowed = float(asset_balance["borrowed"])
            net_balance = free_balance + locked_balance - borrowed

            print(
                f"Margin Balance for {asset}: Net: {net_balance}, Free: {free_balance}, Locked: {locked_balance}, Borrowed: {borrowed}"
            )
        else:
            print(f"No balance information found for {asset}.")
            net_balance = 0

        # Check for open margin orders
        open_orders = client.get_open_margin_orders(symbol=symbol)
        has_pending_sell = any(
            order["side"] == "SELL" and order["status"] == "NEW"
            for order in open_orders
        )

        # Determine if in a long position by checking net balance and pending sells
        is_long = net_balance > 0 and has_pending_sell

        print(f"Is long: {is_long}, Pending sell orders: {has_pending_sell}")
        return is_long
    except Exception as e:
        print(f"Failed to check margin long status for {symbol}: {e}")
        return False


def get_total_asset_balance(client, asset):
    try:
        account_info = client.get_account()
        balance = next(
            (item for item in account_info["balances"] if item["asset"] == asset), None
        )

        free_balance = float(balance["free"]) if balance else 0.0
        locked_balance = float(balance["locked"]) if balance else 0.0
        total_balance = free_balance + locked_balance

        logging.info(
            f"Asset: {asset}, Free: {free_balance}, Locked: {locked_balance}, Total: {total_balance}"
        )
        print(
            f"Asset: {asset}, Free: {free_balance}, Locked: {locked_balance}, Total: {total_balance}"
        )

        return total_balance

    except Exception as e:
        logging.error(f"Failed to fetch balance for {asset}: {e}")
        print(f"Failed to fetch balance for {asset}: {e}")
        return 0.0


def check_margin_short_position(client, symbol):
    try:
        account_details = client.get_margin_account()
        asset = symbol[:-4]

        for asset_detail in account_details["userAssets"]:
            if asset_detail["asset"] == asset:
                borrowed = float(asset_detail["borrowed"])
                free = float(asset_detail["free"])
                if borrowed > 0:
                    # Assuming a short if there's a borrowed amount not yet repaid
                    logging.info(f"Borrowed amount for {asset}: {borrowed}")
                    return True, borrowed
                break
        logging.info(f"No borrowed amount for {asset}. No active short position.")
        return False, 0.0
    except Exception as e:
        logging.error(f"Failed to check short position for {symbol}: {e}")
        return False, 0.0


def log_trade_action(symbol, action, quantity, price, reason):
    directory = "trade_logs"
    if not os.path.exists(directory):
        os.makedirs(directory)

    filename = os.path.join(directory, f"{symbol}_trades.csv")
    file_exists = os.path.isfile(filename)

    with open(filename, "a") as file:
        if not file_exists:
            header = "Time,Action,Quantity,Price,Reason\n"
            file.write(header)

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"{current_time},{action},{quantity},{price},{reason}\n"

        file.write(entry)

    logging.info(
        f"Logged {action} for {symbol}: {quantity} at {price} Reason: {reason} "
    )


def cancel_all_orders(client, symbol):
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        print(f"Found {len(open_orders)} open orders for {symbol}.")

        for order in open_orders:
            if "orderListId" in order:  # This indicates an OCO order
                # OCO orders have a list of orders within them
                for oco_order in order["orders"]:
                    orderId = oco_order["orderId"]
                    print(f"Oco order id: {orderId}")
                    canceled_order = client.cancel_order(
                        symbol=symbol, orderId=orderId
                    )
                    print(f"Canceled OCO sub-order: {canceled_order['orderId']}")

            else:
                orderId = order["orderId"]
                canceled_order = client.cancel_order(symbol=symbol, orderId=orderId)
                print(f"Canceled regular order: {canceled_order['orderId']}")
                logging.info(f"Canceled regular order: {canceled_order['orderId']}")

    except Exception as e:
        print(f"Failed to cancel orders: {e}")
        logging.error(f"Failed to cancel orders: {e}")


def cancel_all_oco_orders(client, symbol):
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        print(f"Total open orders fetched: {len(open_orders)}")

        oco_orders = [order for order in open_orders if "orderListId" in order]

        print(f"Found {len(oco_orders)} OCO orders for {symbol}.")

        for order in oco_orders:
            try:
                # Assuming 'orders' key contains sub-orders directly with 'orderId'
                for sub_order in order["orders"]:
                    print(f"sub order within oco_orders: {sub_order}")
                    orderId = sub_order["orderId"]
                    canceled_order = client.cancel_order(
                        symbol=symbol, orderId=orderId
                    )
                    print(f"Canceled OCO sub-order ID: {canceled_order['orderId']}")
            except KeyError as e:
                print(
                    f"Failed to cancel a sub-order in OCO order {order['orderListId']} due to missing key: {e}"
                )
            except Exception as e:
                print(f"Error while cancelling sub-order: {e}")

    except Exception as e:
        print(f"Failed to fetch or cancel OCO orders: {e}")
        logging.error(f"Failed to fetch or cancel OCO orders: {e}")

### needs real api key ###
# check_usdt_balance(client)
# check_margin_short_position(client, symbol)
# check_orders(client, symbol)
# close_order(symbol, "long", 0.01)
# place_order(symbol, "short", quantity, )
"""
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
    #  "WBTCUSDT",
    #   "TRXUSDT",
    "LINKUSDT",
    # "NOTUSDT",
    #   "STRKUSDT",
    #   "BCHUSDT",
    #     "DOTUSDT",
    #      "UNIUSDT",
    "NEARUSDT",
    "MATICUSDT",
    "LTCUSDT",
    #   "ICPUSDT",
    "PEPEUSDT",
    "FETUSDT",
    #  "ETCUSDT",
    #     "APTUSDT",
    "RNDRUSDT",
    #      "HBARUSDT",
    #      "FILUSDT",
    #      "STXUSDT",
    "ATOMUSDT",
    "XLMUSDT",
    #      "IMXUSDT",
    "INJUSDT",
    "ARBUSDT",
    "ARUSDT",
    "WIFUSDT",
    #     "SUIUSDT",
    "FLOKIUSDT",
    #     "GRTUSDT",
    #     "OPUSDT",
    #    "TAOUSDT",
    "VETUSDT",
    #  "MKRUSDT",
    #    "THETAUSDT",
    "FTMUSDT",
    "BONKUSDT",
    "JASMYUSDT",
    "RUNEUSDT",
    #     "TIAUSDT",
    #      "LDOUSDT",
    #     "EOSUSDT",
    "PYTHUSDT",
    "SEIUSDT",
    "ALGOUSDT",
    "AAVEUSDT",
    #    "GALAUSDT",
    "JUPUSDT",
    "QNTUSDT",
    #    "ENAUSDT",
    #    "ORDIUSDT",
    #    "FLOWUSDT",
    #   "CHZUSDT",
    "DYDXUSDT",
    "EGLDUSDT",
]
for symbol in symbols:
    current_price = get_current_price(client, symbol) 
    asset = symbol[:-4]
    amount = get_total_asset_balance(client, asset)
    print("amount: ", amount)"""
# cancel_all_oco_orders(client, symbol)
#   get_total_asset_balance(client, asset)
#   long_status(client, symbol)
# cancel_all_orders(client, symbol)
# close_order(symbol, "long", amount)
