import configparser

from utils.utils import bool_from_str


conf = configparser.ConfigParser()
conf.read('settings.ini')

client = "bitflyer"

oanda_account_id = conf['oanda']['account_id']
oanda_access_token = conf['oanda']['access_token']
oanda_product_code = conf['oanda']['product_code']

bitflyer_access_key = conf['bitflyer']['api_key']
bitflyer_secret_key = conf['bitflyer']['api_secret']
bitflyer_product_code = conf['bitflyer']['product_code']

if client.lower() == "oanda":
    product_code = oanda_product_code
elif client.lower() == "bitflyer":
    product_code = bitflyer_product_code

db_name = conf['db']['name']
db_driver = conf['db']['driver']

web_port = int(conf['web']['port'])

trade_duration = conf['pytrading']['trade_duration'].lower()
back_test = bool_from_str(conf['pytrading']['back_test'])
live_practice = conf['pytrading']['live_practice']
use_percent = float(conf['pytrading']['use_percent'])
past_period = int(conf['pytrading']['past_period'])
stop_limit_percent = float(conf['pytrading']['stop_limit_percent'])
num_ranking = int(conf['pytrading']['num_ranking'])
