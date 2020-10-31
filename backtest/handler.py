import json
import boto3
from decimal import *

import alpaca_trade_api as tradeapi
import backtrader as bt
import alpaca_backtrader_api
import pandas as pd

ssmClient = boto3.client('ssm')

def safe_div(x,y):
    if x == 0:
        return 0
    if y == 0:
        return 0
    return x / y

def get_secret(key):

	resp = ssmClient.get_parameter(
		Name=key,
		WithDecryption=False
	)

	return resp['Parameter']['Value']

alpaca_api_url = get_secret('/archimedes/alpaca_api_url')
alpaca_key_id = get_secret('/archimedes/alpaca_key_id')
alpaca_secret_key = get_secret('/archimedes/alpaca_secret_key')

class RSI(bt.Strategy):
    params = (
        ('period',21),
        ('low',30),
        ('high',70),
    )

    def __init__(self):
        self.trades = []
        self.startcash = self.broker.getvalue()
        self.rsi = bt.indicators.RSI_SMA(self.data.close, period=self.params.period)

    def notify_trade(self, trade): # Notify the strategy of a trade and track it
        if trade.justopened:
            trade = {
                'size': trade.size,
                'value': trade.value,
                'status': 'OPEN', 
                'pnl': '0.00',
                'pnlcomm': '0.00',
            }
            self.trades.append(trade)
        elif trade.isclosed:
            self.trades[-1]['status'] = 'CLOSED'
            self.trades[-1]['pnl'] = round(trade.pnl,2)
            self.trades[-1]['pnlcomm'] = round(trade.pnlcomm,2)
        else:
            return

    def next(self): # Evaluated on every bar
        if not self.position:
            if self.rsi < self.params.low:
                self.buy(size=100)
        else:
            if self.rsi > self.params.high:
                self.sell(size=100)

def analyzeTrades(analyzer):
    analysis = {
        'total_open': analyzer.total.open,
        'total_closed': analyzer.total.closed,
        'total_won': analyzer.won.total,
        'total_lost': analyzer.lost.total,
        'win_streak': analyzer.streak.won.longest,
        'lose_streak': analyzer.streak.lost.longest,
        'pnl_net': round(analyzer.pnl.net.total,2),
        'strike_rate': round((safe_div(analyzer.won.total, analyzer.total.closed) * 100), 2)
    }
    return analysis

def scoreBacktest(trade_analysis):
    _score = 0
    _strike = trade_analysis['strike_rate']
    _pnl = trade_analysis['pnl_net']
    _wins = trade_analysis['total_won']
    _losses = trade_analysis['total_lost']
    _wstreak = trade_analysis['win_streak']
    _lstreak = trade_analysis['lose_streak']

    # assign most points based on profit
    if _pnl > 0:
        _score += 50

    # assign points based on the ideal strike rate
    if _strike > 50 and _strike <= 65:
        _score += 20
    elif _strike > 65 and _strike >= 75:
        _score += 10
    else:
        _score += 5

    # assign points based on more wins than losses
    if _wins > _losses:
        _score += 10

    # assign points based on longer win streak than loss streak
    if _wstreak > _lstreak:
        _score += 10

    # assign a few points for having wins
    if _wins > 0:
        _score += 5
        
    # assign some points for having no losses
    if _losses == 0:
        _score += 5

    return _score


def backtest(event, context, dynamodb=None):

    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    ## Get the Optimizer record from dynamodb by GUID
    table = dynamodb.Table('archimedes-optimizations')

    for record in event['Records']:
        payload = json.loads(record["body"], parse_float=Decimal)
 
        #optimizer_guid = payload["optimizer_guid"]
        backtest_guid = payload["guid"]
        
        #optimizer = table.get_item(Key={'guid': optimizer_guid})

        # Params to be picked up from the SQS Queue
        symbol = payload["symbol"]
        dt_start = payload["dt_start"]
        dt_end = payload["dt_end"]
        #interval = payload["interval"]
        startcash = payload["startcash"]
        period = payload["period"]
        rsi_low = payload["rsi_low"]
        rsi_high = payload["rsi_high"]

        # init cerebro
        cerebro = bt.Cerebro(optreturn=False)
        # add trades analyzer
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")
        # add the strategy and parameters
        cerebro.addstrategy(RSI, period=period, low=rsi_low, high=rsi_high)
        # Get Backtest Data from Alpaca API
        store = alpaca_backtrader_api.AlpacaStore(
            key_id=alpaca_key_id,
            secret_key=alpaca_secret_key,
            paper="TRUE"
        )
        DataFactory = store.getdata
        bars = DataFactory(
            dataname=symbol,
            timeframe=bt.TimeFrame.TFrame("Minutes"),
            fromdate=pd.Timestamp(dt_start),
            todate=pd.Timestamp(dt_end),
            historical=True)

        # Add Alpaca data to Cerebro
        cerebro.adddata(bars)
        # Set the initial account cash value
        cerebro.broker.setcash(startcash)
        # Add the order sizer to the strategy, 5% of available equity
        cerebro.addsizer(bt.sizers.PercentSizer, percents=5)
        # Here is how to do it with a fixed stake // cerebro.addsizer(bt.sizers.SizerFix, stake=20)
        # Run the backtest
        strat = cerebro.run()

        # table = dynamodb.Table('archimedes-analysis')

        trade_analysis = analyzeTrades(strat[0].analyzers.ta.get_analysis())


        



        ## add to analysis table
        row = {
            'guid': backtest_guid,
            'symbol': symbol,
            'start': dt_start,
            'end': dt_end,
            'params': {
                'period': period,
                'low': rsi_low,
                'high': rsi_high,
            },
            'trade_analysis': trade_analysis,
            'score': scoreBacktest(trade_analysis),
            'trades': strat[0].trades
        }
        clean_row = json.loads(json.dumps(row), parse_float=Decimal)
        
        # table.put_item(
        #     Item=clean_row
        # )
        ## end analysis