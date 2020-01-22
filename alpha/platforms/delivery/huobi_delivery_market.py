# -*— coding:utf-8 -*-

"""
Huobi Swap Market Server.

Author: Qiaoxiaofeng
Date:   2020/01/10
Email:  andyjoe318@gmail.com
"""

import gzip
import json
import time
import copy
from collections import deque

from alpha.utils import logger
from alpha.utils.websocket import Websocket
from alpha.utils.decorator import async_method_locker
from alpha.const import MARKET_TYPE_KLINE
from alpha.order import ORDER_ACTION_BUY, ORDER_ACTION_SELL
from alpha.tasks import SingleTask
from alpha.orderbook import Orderbook
from alpha.markettrade import Trade
from alpha.kline import Kline
from alpha.error import Error


class HuobiDeliveryMarket(Websocket):

    def __init__(self, **kwargs):
        self._platform = kwargs["platform"]
        self._wss = kwargs.get("wss", "wss://www.hbdm.com")
        self._symbol = kwargs.get("symbol")
        self._contract_type = kwargs.get("contract_type")
        self._channels = kwargs.get("channels")
        self._orderbook_length = kwargs.get("orderbook_length", 10)
        self._orderbook_step = kwargs.get("orderbook_step", "step6")
        self._orderbooks_length = kwargs.get("orderbooks_length", 100)
        self._klines_length = kwargs.get("klines_length", 100)
        self._klines_period = kwargs.get("klines_period", "1min")
        self._trades_length = kwargs.get("trades_length", 100)
        self._orderbook_update_callback = kwargs.get("orderbook_update_callback")
        self._kline_update_callback = kwargs.get("kline_update_callback")
        self._trade_update_callback = kwargs.get("trade_update_callback")
        self._rest_api = kwargs.get("rest_api")

        self._c_to_s = {}  # {"channel": "symbol"}
        self._orderbooks = deque(maxlen=self._orderbooks_length) 
        self._klines = deque(maxlen=self._klines_length)
        self._trades = deque(maxlen=self._trades_length)
        self._klines_init = False

        url = self._wss + "/ws"
        super(HuobiDeliveryMarket, self).__init__(url, send_hb_interval=5)
        self.initialize()

    @property
    def orderbooks(self):
        return copy.copy(self._orderbooks)

    @property
    def klines(self):
        return copy.copy(self._klines)

    @property
    def trades(self):
        return copy.copy(self._trades)

    @property
    def rest_api(self):
        return self._rest_api

    def init_data(self):
        return self._klines_init

    async def _reconnect(self):
        self._klines_init = False
        self._c_to_s = {}
        self._orderbooks.clear()
        self._klines.clear()
        self._trades.clear()
        super(HuobiDeliveryMarket, self)._reconnect()

    async def _send_heartbeat_msg(self, *args, **kwargs):
        """ 发送心跳给服务器
        """
        if not self.ws:
            logger.warn("websocket connection not connected yet!", caller=self)
            return
        data = {"pong": int(time.time()*1000)}
        await self.ws.send_json(data)

    async def connected_callback(self):
        """
        链接成功初始数据和加监听
        :return:
        """
        self._init_data()
        SingleTask.run(self._add_sub)


    def _init_data(self):
        """
        初始必要数据
        :return:
        """
        async def init_history_Klines():
            success, error = await self._rest_api.get_klines(contract_type=self._contract_type,
                                                             period=self._klines_period,
                                                             size=self._klines_length)
            self._init_history_kline_callback(success, error)
        SingleTask.run(init_history_Klines)

    async def _add_sub(self):
        """
        加监听
        :return:
        """
        for ch in self._channels:
            if ch == "kline":
                channel = self._symbol_to_channel(self._contract_type, "kline")
                if not channel:
                    continue
                kline = {
                    "sub": channel
                }
                await self.ws.send_json(kline)
            elif ch == "orderbook":
                channel = self._symbol_to_channel(self._contract_type, "depth")
                if not channel:
                    continue
                data = {
                    "sub": channel
                }
                await self.ws.send_json(data)
            elif ch == "trade":
                channel = self._symbol_to_channel(self._contract_type, "trade")
                if not channel:
                    continue
                data = {
                    "sub": channel
                }
                await self.ws.send_json(data)
            else:
                logger.error("channel error! channel:", ch, caller=self)

    def _symbol_to_channel(self, contract_type, channel_type):
        if channel_type == "kline":
            channel = "market.{s}.kline.{p}".format(s=contract_type.upper(), p=self._klines_period)
        elif channel_type == "depth":
            channel = "market.{s}.depth.{d}".format(s=contract_type.upper(), d=self._orderbook_step)
        elif channel_type == "trade":
            channel = "market.{s}.trade.detail".format(s=contract_type.upper())
        else:
            logger.error("channel type error! channel type:", channel_type, caller=self)
            return None
        self._c_to_s[channel] = contract_type
        return channel

    async def process_binary(self, msg):
        """ Process binary message that received from Websocket connection.
        """
        data = json.loads(gzip.decompress(msg).decode())
        logger.debug("data:", json.dumps(data), caller=self)
        channel = data.get("ch")
        if not channel:
            if data.get("ping"):
                hb_msg = {"pong": data.get("ping")}
                await self.ws.send_json(hb_msg)
            return

        if channel.find("kline") != -1:
            await self.process_kline(data)

        elif channel.find("depth") != -1:
            await self.process_orderbook(data)
        
        elif channel.find("trade") != -1:
            await self.process_trade(data)
        else:
            logger.error("event error! msg:", msg, caller=self)

    def _init_history_kline_callback(self, success, error):
        if error:
            logger.error("init history_kline error:", error, caller=self)
            return
        history_klines = success.get("data")
        # print("_get_history_kline_callback")
        # print(history_klines)
        ts = int(success.get("ts"))
        for k in history_klines:
            info = {
                "platform": self._platform,
                "id": int(k["id"]),
                "symbol": self._symbol,
                "open": "%.8f" % k["open"],
                "high": "%.8f" % k["high"],
                "low": "%.8f" % k["low"],
                "close": "%.8f" % k["close"],
                "volume": int(k["vol"]),
                "amount": "%.8f" % k["amount"],
                "timestamp": ts,
                "kline_type": MARKET_TYPE_KLINE
            }
            kline = Kline(**info)
            self._klines.append(kline)
        self._klines_init = True

    async def process_kline(self, data):
        """ process kline data
        """
        if not self._klines_init:
            logger.info("klines not init. current:", len(self.klines), caller=self)
            return
        channel = data.get("ch")
        symbol = self._c_to_s[channel]
        d = data.get("tick")
        # print("process_kline", symbol)
        # print(d)
        info = {
            "platform": self._platform,
            "id": int(d["id"]),
            "symbol": symbol,
            "open": "%.8f" % d["open"],
            "high": "%.8f" % d["high"],
            "low": "%.8f" % d["low"],
            "close": "%.8f" % d["close"],
            "volume": int(d["vol"]),
            "amount": "%.8f" % d["amount"],
            "timestamp": int(data.get("ts")),
            "kline_type": MARKET_TYPE_KLINE
        }
        kline = Kline(**info)
        if kline.id == self._klines[-1].id:
            self._klines.pop()
        self._klines.append(kline)
        SingleTask.run(self._kline_update_callback, copy.copy(kline))
        # logger.debug("symbol:", symbol, "kline:", kline, caller=self)

    async def process_orderbook(self, data):
        """ process orderbook data
        """
        channel = data.get("ch")
        symbol = self._c_to_s[channel]
        d = data.get("tick")
        # print("process_orderbook", symbol)
        # print(d)
        asks, bids = [], []
        if d.get("asks"):
            for item in d.get("asks")[:self._orderbook_length]:
                price = "%.8f" % item[0]
                quantity = "%.8f" % item[1]
                asks.append([price, quantity])
        if d.get("bids"):
            for item in d.get("bids")[:self._orderbook_length]:
                price = "%.8f" % item[0]
                quantity = "%.8f" % item[1]
                bids.append([price, quantity])
        info = {
            "platform": self._platform,
            "symbol": symbol,
            "asks": asks,
            "bids": bids,
            "timestamp": d.get("ts")
        }
        orderbook = Orderbook(**info)
        self._orderbooks.append(orderbook)
        SingleTask.run(self._orderbook_update_callback, copy.copy(orderbook))
        logger.debug("symbol:", symbol, "orderbook:", orderbook, caller=self)
    
    async def process_trade(self, data):
        """ process trade
        """
        channel = data.get("ch")
        symbol = self._c_to_s[channel]
        ticks = data.get("tick")
        # print("process_trade", symbol)
        # print(ticks)
        for tick in ticks["data"]:
            direction = tick.get("direction")
            price = tick.get("price")
            quantity = tick.get("amount")
            info = {
                "platform": self._platform,
                "symbol": symbol,
                "action": ORDER_ACTION_BUY if direction == "buy" else ORDER_ACTION_SELL,
                "price": "%.8f" % price,
                "quantity": "%.8f" % quantity,
                "timestamp": tick.get("ts")
            }
            trade = Trade(**info)
            self._trades.append(trade)
            SingleTask.run(self._trade_update_callback, copy.copy(trade))
            logger.debug("symbol:", symbol, "trade:", trade, caller=self)
        



