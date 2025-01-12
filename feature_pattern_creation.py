import pandas as pd
import numpy as np
import ta
from scipy.signal import argrelextrema
from sklearn.linear_model import LinearRegression


def read_data(file_path):
    return pd.read_csv(file_path)

def add_technical_indicators(data):
    data["Open Time"] = pd.to_datetime(data["Open Time"])
    data["RSI"] = ta.momentum.rsi(data["Close"], window=14, fillna=True)
    data["MA_22"] = data["Close"].rolling(window=22).mean()
    data["MA_50"] = data["Close"].rolling(window=50).mean()
    data["ATR"] = ta.volatility.average_true_range(
        data["High"], data["Low"], data["Close"], window=14, fillna=True
    )
    data["Mean ATR"] = data["ATR"].rolling(window=12).mean()
   # data['Volume SMA'] = data['Volume'].rolling(window=12).mean() 

    return data


def detect_divergences(data, window_sizes=[15, 30]):
    price_max_idx, price_min_idx = find_extrema(data["Close"])
    data["bullish_divergence"] = 0
    data["bearish_divergence"] = 0
    for i in range(len(data)):
        for window_size in window_sizes:
            if i in price_max_idx:
                window = data.iloc[max(i - window_size, 0) : i + 1]
                if (
                    calculate_slope(window["Close"]) > 0
                    and calculate_slope(window["RSI"]) < 0
                ):
                    data.at[i, "bearish_divergence"] = 1
            elif i in price_min_idx:
                window = data.iloc[max(i - window_size, 0) : i + 1]
                if (
                    calculate_slope(window["Close"]) < 0
                    and calculate_slope(window["RSI"]) > 0
                ):
                    data.at[i, "bullish_divergence"] = 1
                    
   # filtered_df = data[(data['bullish_divergence'] == 1) | (data['bearish_divergence'] == 1)]
   # print(filtered_df['Open Time'])
    return data

def find_extrema(series, window=9): 
    max_idx = argrelextrema(series.values, np.greater, order=window)[0]
    min_idx = argrelextrema(series.values, np.less, order=window)[0]
    return max_idx, min_idx


def calculate_slope(y_values):
    if len(y_values) < 2:
        return 0 
    x_values = np.arange(len(y_values)).reshape(-1, 1)
    model = LinearRegression().fit(x_values, y_values)
    return model.coef_[0]


def detect_consolidation(data, window_size=12, std_dev_threshold=0.003):
    data["consolidated"] = 0

    for i in range(len(data)):
        start_idx = max(i - window_size + 1, 0)
        end_idx = i + 1
        window = data.iloc[start_idx:end_idx]

        # Calculate standard deviation of close prices within the window
        std_dev = window["Close"].std()
        mean_price = window["Close"].mean()

        # Check if the standard deviation is small relative to the price
        if std_dev / mean_price <= std_dev_threshold:
            data.loc[start_idx:end_idx, "consolidated"] = 1

    return data


# later make this 1% based, TODO
def is_near_round_number(x):
    remainder = x % 1000
    return int(remainder <= 50 or remainder >= 950)


def round_number(data):
    data["round_number"] = data[["High", "Low", "Open", "Close"]].apply(
        lambda x: max(
            is_near_round_number(x["High"]),
            is_near_round_number(x["Low"]),
            is_near_round_number(x["Open"]),
            is_near_round_number(x["Close"]),
        ),
        axis=1,
    )
    return data


def mark_extrema(data):
    order = 5
    maxima_indices = argrelextrema(data["Close"].values, np.greater, order=order)[0]
    minima_indices = argrelextrema(data["Close"].values, np.less, order=order)[0]
    data["extrema"] = 0
    data.loc[maxima_indices, "extrema"] = "high"
    data.loc[minima_indices, "extrema"] = "low"
    return data


def mark_medium_extrema(data):
    order = 30
    maxima_indices = argrelextrema(data["Close"].values, np.greater, order=order)[0]
    minima_indices = argrelextrema(data["Close"].values, np.less, order=order)[0]
    data["medium_extrema"] = 0
    data.loc[maxima_indices, "medium_extrema"] = "medium_high"
    data.loc[minima_indices, "medium_extrema"] = "medium_low"
    return data


def mark_big_extrema(data):
    order = 50
    maxima_indices = argrelextrema(data["Close"].values, np.greater, order=order)[0]
    minima_indices = argrelextrema(data["Close"].values, np.less, order=order)[0]
    data["big_extrema"] = 0
    data.loc[maxima_indices, "big_extrema"] = "big_high"
    data.loc[minima_indices, "big_extrema"] = "big_low"
    return data


def process_data(file_path):
    data = read_data(file_path)
    data = add_technical_indicators(data)
    data = detect_divergences(data)
    # data = round_number(data)
    data = mark_extrema(data)
    data = mark_big_extrema(data)
    data = mark_medium_extrema(data)
    data = detect_consolidation(data)

    feature_columns = [
        "Open Time",
        "Volume",
        "Open",
        #  "High",
        # "Low",
        "Close",
        "ATR",
        "RSI",
        "MA_22",
        "MA_50",
        #  "round_number",
        "bullish_divergence",
        "bearish_divergence",
        "extrema",
        "big_extrema",
        "medium_extrema",
        "Mean ATR",
        #     "Volume SMA",
        "consolidated",
    ]
    data[feature_columns].to_csv(file_path + "_for_processing.csv", index=False)

if __name__ == "__main__":
    process_data("BTCUSDT_4h_data.csv")
