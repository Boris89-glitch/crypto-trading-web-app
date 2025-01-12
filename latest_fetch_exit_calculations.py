import pandas as pd
import numpy as np
import requests
import ta
from scipy.signal import argrelextrema
from sklearn.linear_model import LinearRegression

def fetch_latest_candle():
    url = "https://api.binance.com/api/v3/klines"
    params = {
        'symbol': 'BTCUSDT',
        'interval': '4h',
        'limit': 1
    }
    response = requests.get(url, params=params)
    columns = ['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 
               'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 
               'Taker Buy Quote Asset Volume', 'Ignore']
    data = pd.DataFrame(response.json(), columns=columns)
    data['Open'] = pd.to_numeric(data['Open'])
    data['High'] = pd.to_numeric(data['High'])
    data['Low'] = pd.to_numeric(data['Low'])
    data['Close'] = pd.to_numeric(data['Close'])
    data['Open Time'] = pd.to_datetime(data['Open Time'], unit='ms')
    data['Volume'] = pd.to_numeric(data['Volume'])
    return data

data = pd.read_csv('data_for_model.csv')

new_candle = fetch_latest_candle()
new_data = pd.DataFrame(new_candle)

# Only calculate new metrics for the new data
new_data['RSI'] = ta.momentum.rsi(pd.concat([data['Close'].iloc[-15:], new_data['Close']]), window=14, fillna=True).iloc[-1]
new_data['MA_22'] = data['Close'].rolling(window=22).mean().iloc[-1]
new_data['MA_50'] = data['Close'].rolling(window=50).mean().iloc[-1]
new_data['ATR'] = ta.volatility.average_true_range(pd.concat([data['High'].iloc[-15:], new_data['High']]),
                                                   pd.concat([data['Low'].iloc[-15:], new_data['Low']]),
                                                   pd.concat([data['Close'].iloc[-15:], new_data['Close']]), window=14, fillna=True).iloc[-1]


all_price_levels = pd.concat([data['Low'], data['High'], new_data['Low'], new_data['High']]).apply(lambda x: np.arange(np.floor(x), np.ceil(x) + 1))
flat_price_levels = [level for sublist in all_price_levels for level in sublist]
price_counts = pd.Series(flat_price_levels).value_counts()
strong_threshold = 95
bin_size = 100
strong_levels = price_counts[price_counts >= strong_threshold].index

def check_strong_levels(row, levels, bin_size):
    return any((row['Open'] >= level - bin_size and row['Open'] <= level + bin_size) or
               (row['High'] >= level - bin_size and row['High'] <= level + bin_size) or
               (row['Low'] >= level - bin_size and row['Low'] <= level + bin_size) or
               (row['Close'] >= level - bin_size and row['Close'] <= level + bin_size)
               for level in levels)
new_data['is_strong_level'] = new_data.apply(check_strong_levels, args=(strong_levels, bin_size,), axis=1).astype(int)

def is_near_round_number(x):
    remainder = x % 1000
    return int(remainder <= 50 or remainder >= 950)

new_data['round_number'] = new_data[['High', 'Low', 'Open', 'Close']].apply(lambda x: max(is_near_round_number(x['High']), 
                                                                                      is_near_round_number(x['Low']),
                                                                                      is_near_round_number(x['Open']),
                                                                                      is_near_round_number(x['Close'])), axis=1)

combined_data = pd.concat([data, new_data], ignore_index=True)
combined_data['bullish_divergence'] = 0
combined_data['bearish_divergence'] = 0

def calculate_slope(y_values):
    x_values = np.arange(len(y_values)).reshape(-1, 1)
    model = LinearRegression().fit(x_values, y_values)
    return model.coef_[0]

def find_extrema(series, window=10):
    max_idx = argrelextrema(series.values, np.greater, order=window)[0]
    min_idx = argrelextrema(series.values, np.less, order=window)[0]
    return max_idx, min_idx

price_max_idx, price_min_idx = find_extrema(combined_data['Close']) 

for i in range(len(combined_data)):
    for window_size in [15, 30]:
        if i in price_max_idx:
            window = combined_data.iloc[max(i-window_size, 0):i+1]
            price_slope = calculate_slope(window['Close'])
            rsi_slope = calculate_slope(window['RSI'])
            if price_slope >= 0 and rsi_slope <= 0:
                combined_data.at[i, 'bearish_divergence'] = 1

        elif i in price_min_idx:
            window = combined_data.iloc[max(i-window_size, 0):i+1]
            price_slope = calculate_slope(window['Close'])
            rsi_slope = calculate_slope(window['RSI'])
            if price_slope <= 0 and rsi_slope >= 0:
                combined_data.at[i, 'bullish_divergence'] = 1
                
combined_data.drop(['Ignore', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume',], axis=1, inplace=True)
combined_data.to_csv('updated_data.csv', index=False)
