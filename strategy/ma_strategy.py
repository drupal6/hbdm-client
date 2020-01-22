# -*- coding:utf-8 -*-
"""
简单卖平策略，仅做演示使用

Author: Qiaoxiaofeng
Date:   2020/01/10
Email: andyjoe318@gmail.com
"""
# 策略实现
import time
from alpha import const
from alpha.utils import tools
from alpha.utils import logger
from alpha.config import config
from alpha.market import Market
from alpha.trade import Trade
from alpha.const import HUOBI_SWAP, HUOBI_DELIVERY
from alpha.order import Order
from alpha.orderbook import Orderbook
from alpha.kline import Kline
from alpha.markettrade import Trade as MarketTrade
from alpha.asset import Asset
from alpha.position import Position
from alpha.error import Error
from alpha.tasks import LoopRunTask
from alpha.utils.klineutils import interval_handler
from alpha.order import ORDER_ACTION_SELL, ORDER_ACTION_BUY, ORDER_STATUS_FAILED, ORDER_STATUS_CANCELED, ORDER_STATUS_FILLED,\
    ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET


class MaStrategy:

    def __init__(self):
        """ 初始化
        """
        print(config)
        self.strategy = config.strategy
        self.platform = config.accounts[0]["platform"]
        self.account = config.accounts[0]["account"]
        self.access_key = config.accounts[0]["access_key"]
        self.secret_key = config.accounts[0]["secret_key"]
        self.host = config.accounts[0]["host"]
        self.wss = config.accounts[0]["wss"]
        self.symbol = config.symbol
        self.lever_rate = config.lever_rate
        self.place_num = config.place_num
        self.contract_type = config.contract_type
        self.channels = config.markets[0]["channels"]
        self.orderbook_length = config.markets[0]["orderbook_length"]
        self.orderbook_step = config.markets[0]["orderbook_step"]
        self.orderbooks_length = config.markets[0]["orderbooks_length"]
        self.klines_length = config.markets[0]["klines_length"]
        self.klines_period = config.markets[0]["klines_period"]
        self.trades_length = config.markets[0]["trades_length"]
        self.market_wss = config.markets[0]["wss"]

        self.orderbook_invalid_seconds = 0.5

        self.last_bid_price = 0  # 上次的买入价格
        self.last_ask_price = 0  # 上次的卖出价格
        self.last_orderbook_timestamp = 0  # 上次的orderbook时间戳
        self.last_open_order_time = 0  #上次开单时间

        self.raw_symbol = self.symbol.split('-')[0]

        self.ask1_price = 0
        self.bid1_price = 0
        self.ask1_volume = 0
        self.bid1_volume = 0

        self.periods = [5, 10]

        self.trade_init_result = False

        # rest api
        if self.platform == HUOBI_SWAP:
            from alpha.platforms.swap.huobi_swap_api import HuobiSwapRestAPI
            self._rest_api = HuobiSwapRestAPI(self.host, self.access_key, self.secret_key)
        elif self.platform == HUOBI_DELIVERY:
            from alpha.platforms.delivery.huobi_delivery_api import HuobiDeliveryRestAPI
            self._rest_api = HuobiDeliveryRestAPI(self.host, self.access_key, self.secret_key)

        # 交易模块
        cc = {
            "strategy": self.strategy,
            "platform": self.platform,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "account": self.account,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
            "host": self.host,
            "wss": self.wss,
            "rest_api": self._rest_api,
            "order_update_callback": self.on_event_order_update,
            "asset_update_callback": self.on_event_asset_update,
            "position_update_callback": self.on_event_position_update,
            "init_success_callback": self.on_event_init_trade_success_callback,
        }
        self.trader = Trade(**cc)

        # 行情模块
        cc = {
            "platform": self.platform,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "channels": self.channels,
            "orderbook_length": self.orderbook_length,
            "orderbook_step": self.orderbook_step,
            "orderbooks_length": self.orderbooks_length,
            "klines_length": self.klines_length,
            "klines_period": self.klines_period,
            "trades_length": self.trades_length,
            "wss": self.market_wss,
            "rest_api": self._rest_api,
            "orderbook_update_callback": self.on_event_orderbook_update,
            "kline_update_callback": self.on_event_kline_update,
            "trade_update_callback": self.on_event_trade_update,
        }
        self.market = Market(**cc)
        
        # 1秒执行1次
        LoopRunTask.register(self.on_ticker, 5)

    async def on_ticker(self, *args, **kwargs):
        if not self.trade_init_result:
            logger.error("trade not init.", caller=self)
            return
        if not self.market.init_data():
            logger.error("not init market data.", caller=self)
            return
        if not self.trader.init_data():
            logger.error("not init trader data.", caller=self)
            return
        klines = self.market.klines
        if klines[-1].id == self.last_open_order_time:
            logger.info("haved order. ordertime:", self.last_open_order_time, caller=self)
            return
        ma_point = interval_handler(values=klines, periods=self.periods, vtype="close")
        if ma_point[self.periods[0]][1] < ma_point[self.periods[1]][1]:
            if ma_point[self.periods[0]][0] >= ma_point[self.periods[1]][0]:
                print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), "开多平空")
        elif ma_point[self.periods[0]][1] > ma_point[self.periods[1]][1]:
            if ma_point[self.periods[0]][0] <= ma_point[self.periods[1]][0]:
                print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), "开空平多")
        # await self.cancel_orders()
        # await self.place_orders()

    async def cancel_orders(self):
        """  取消订单
        """
        order_nos = [orderno for orderno in self.trader.orders ]
        if order_nos and self.last_ask_price != self.ask1_price:
            _, errors = await self.trader.revoke_order(*order_nos)
            if errors:
                logger.error(self.strategy, "cancel future order error! error:", errors, caller=self)
            else:
                logger.info(self.strategy, "cancel future order:", order_nos, caller=self)
    
    async def place_orders(self):
        """ 下单
        """
        orders_data = []
        if self.trader.position and self.trader.position.short_quantity:
            # 平空单
            price = self.ask1_price - 0.1
            quantity = -self.trader.position.short_quantity
            action = ORDER_ACTION_BUY
            new_price = str(price)  # 将价格转换为字符串，保持精度
            if quantity:
                orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT, "lever_rate": self.lever_rate})
                self.last_ask_price = self.ask1_price
        if self.trader.assets and self.trader.assets.assets.get(self.raw_symbol):
            # 开空单
            price = self.bid1_price + 0.1
            volume = float(self.trader.assets.assets.get(self.raw_symbol).get("free")) * price // 100 
            if volume >= 1:
                quantity = - volume #  空1张
                action = ORDER_ACTION_SELL
                new_price = str(price)  # 将价格转换为字符串，保持精度
                if quantity:
                    orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT, "lever_rate": self.lever_rate})
                    self.last_bid_price = self.bid1_price

        if orders_data:
            order_nos, error = await self.trader.create_orders(orders_data)
            if error:
                logger.error(self.strategy, "create future order error! error:", error, caller=self)
            logger.info(self.strategy, "create future orders success:", order_nos, caller=self)

    async def on_event_orderbook_update(self, orderbook: Orderbook):
        """  orderbook更新
            self.market.orderbooks 是最新的orderbook组成的队列，记录的是历史N次orderbook的数据。
            本回调所传的orderbook是最新的单次orderbook。
        """
        logger.debug("orderbook:", orderbook, caller=self)
        if orderbook.asks:
            self.ask1_price = float(orderbook.asks[0][0])  # 卖一价格
            self.ask1_volume = float(orderbook.asks[0][1])  # 卖一数量
        if orderbook.bids:
            self.bid1_price = float(orderbook.bids[0][0])  # 买一价格
            self.bid1_volume = float(orderbook.bids[0][1])  # 买一数量
        self.last_orderbook_timestamp = orderbook.timestamp

    async def on_event_order_update(self, order: Order):
        """ 订单状态更新
        """
        print("on_event_order_update")
        print(order.__str__())

    async def on_event_asset_update(self, asset: Asset):
        """ 资产更新
        """
        print("on_event_asset_update")
        print(asset.__str__())

    async def on_event_position_update(self, position: Position):
        """ 仓位更新
        """
        print("on_event_position_update")
        print(position.__str__())
    
    async def on_event_kline_update(self, kline: Kline):
        """ kline更新
            self.market.klines 是最新的kline组成的队列，记录的是历史N次kline的数据。
            本回调所传的kline是最新的单次kline。
        """
        print("on_event_kline_update")
        print(kline.__str__())
    
    async def on_event_trade_update(self, trade: MarketTrade):
        """ market trade更新
            self.market.trades 是最新的逐笔成交组成的队列，记录的是历史N次trade的数据。
            本回调所传的trade是最新的单次trade。
        """
        print("on_event_trade_update")
        print(trade.__str__())
    
    async def on_event_init_trade_success_callback(self, success: bool, error: Error, **kwargs):
        """ init success callback
        """
        if not success:
            logger.error("init trade error callback update:", success, error, kwargs, caller=self)
        else:
            self.trade_init_result = True


