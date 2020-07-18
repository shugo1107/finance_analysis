DURATION_5S = '5s'
DURATION_1M = '1m'
DURATION_5M = '5m'
DURATION_15M = '15m'
DURATION_30M = '30m'
DURATION_1H = '1h'
DURATION_1D = '1d'
DURATIONS = [DURATION_5S, DURATION_1M, DURATION_5M, DURATION_15M,
             DURATION_30M, DURATION_1H, DURATION_1D]

GRANULARITY_5S = 'S5'
GRANULARITY_1M = 'M1'
GRANULARITY_5M = 'M5'
GRANULARITY_15M = 'M15'
GRANULARITY_30M = 'M30'
GRANULARITY_1H = 'H1'
GRANULARITY_1D = 'D1'

TRADE_MAP = {
    DURATION_5S: {
        'duration': DURATION_5S,
        'granularity': GRANULARITY_5S,
    },
    DURATION_1M: {
        'duration': DURATION_1M,
        'granularity': GRANULARITY_1M,
    },
    DURATION_5M: {
        'duration': DURATION_5M,
        'granularity': GRANULARITY_5M,
    },
    DURATION_15M: {
        'duration': DURATION_15M,
        'granularity': GRANULARITY_15M,
    },
    DURATION_30M: {
        'duration': DURATION_30M,
        'granularity': GRANULARITY_30M,
    },
    DURATION_1H: {
        'duration': DURATION_1H,
        'granularity': GRANULARITY_1H,
    },
    DURATION_1D: {
        'duration': DURATION_1D,
        'granularity': GRANULARITY_1D,
    }
}

BUY = 'BUY'
SELL = 'SELL'

PRODUCT_CODE_USD_JPY = 'USD_JPY'
PRODUCT_CODE_EUR_JPY = 'EUR_JPY'
PRODUCT_CODE_EUR_USD = 'EUR_USD'
PRODUCT_CODE_GBP_USD = 'GBP_USD'
PRODUCT_CODE_GBP_JPY = 'GBP_JPY'
PRODUCT_CODE_AUD_JPY = 'AUD_JPY'

