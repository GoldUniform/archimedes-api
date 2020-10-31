import backtrader as bt
import alpaca_trade_api as tradeapi
import alpaca_backtrader_api
import pandas as pd
from datetime import datetime

from prettyprinter import pprint

alpaca_api_url = 'https://paper-api.alpaca.markets'
alpaca_key_id = 'PKBXQFOUVL2X50GQTK8G'
alpaca_secret_key = 'jhtBFWOZwyKpZwz94AqsuLsoVRj9Gj79qCkyM9Wi'

# Params to be picked up from the SQS Queue
backtest_guid = '234234231234-23423423432-234234'
symbol = 'DDOG'
dt_start = '2020-09-01'
dt_end = '2020-09-10'
period = 21
rsi_low = 30
rsi_high = 70
startcash = 25000

class rsi(bt.Strategy):
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
        'strike_rate': (analyzer.won.total / analyzer.total.closed) * 100
    }
    return analysis


if __name__ == '__main__':

    #Create an instance of cerebro
    cerebro = bt.Cerebro(maxcpus=1, optreturn=False)

    #Add a trade analyzer to give us simple trade stats
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")

    #Add our strategy
    cerebro.addstrategy(rsi, period=period, )

    #What is the stake we want
    cerebro.addsizer(bt.sizers.SizerFix, stake=3)

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

    # Set our desired cash start
    cerebro.broker.setcash(startcash)

    # Run over everything
    strategies = cerebro.run()

    # The object we are going to return, containing all the strategy data and trades
    full_analysis = {
        'symbol': symbol,
        'start': dt_start,
        'end': dt_end,
        'type': 'RSI',
        'params': {
            'period': period,
            'low': rsi_low,
            'high': rsi_high,
        },
        'trade_analysis': analyzeTrades(strategies[0].analyzers.ta.get_analysis()),
        'trades': strategies[0].trades,
    }

    pprint(full_analysis)