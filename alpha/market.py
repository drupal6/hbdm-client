import copy

from alpha import const
from alpha.utils import logger
from alpha.error import Error
from alpha.tasks import SingleTask


class Market:
    def __init__(self, platform=None, symbol=None, contract_type=None, channels=None, orderbook_length=None,
                 orderbook_step=None, orderbooks_length=None, klines_length=None, klines_period=None,
                 trades_length=None, wss=None, orderbook_update_callback=None, kline_update_callback=None,
                 trade_update_callback=None, rest_api=None, **kwargs):
        """initialize trade object."""
        kwargs["platform"] = platform
        kwargs["symbol"] = symbol
        kwargs["channels"] = channels
        kwargs["orderbook_length"] = orderbook_length
        kwargs["orderbook_step"] = orderbook_step
        kwargs["orderbook_length"] = orderbook_length
        kwargs["orderbooks_length"] = orderbooks_length
        kwargs["klines_length"] = klines_length
        kwargs["klines_period"] = klines_period
        kwargs["trades_length"] = trades_length
        kwargs["wss"] = wss
        kwargs["orderbook_update_callback"] = orderbook_update_callback
        kwargs["kline_update_callback"] = kline_update_callback
        kwargs["trade_update_callback"] = trade_update_callback
        kwargs["rest_api"] = rest_api

        if contract_type == "this_week":
            kwargs["contract_type"] = symbol + "_CW"
        elif contract_type == "next_week":
            kwargs["contract_type"] = symbol + "_NW"
        elif contract_type == "quarter":
            kwargs["contract_type"] = symbol + "_CQ"
        else:
            logger.error("is deliverd. symbol:", symbol, "contract_type:", contract_type, caller=self)
            return

        self._raw_params = copy.copy(kwargs)
        self._on_orderbook_update_callback = orderbook_update_callback
        self._on_kline_update_callback = kline_update_callback
        self._on_trade_update_callback = trade_update_callback
        self._rest_api = rest_api

        if platform == const.HUOBI_SWAP:
            from alpha.platforms.swap.huobi_swap_market import HuobiSwapMarket as M
        if platform == const.HUOBI_DELIVERY:
            from alpha.platforms.delivery.huobi_delivery_market import HuobiDeliveryMarket as M
        else:
            logger.error("platform error:", platform, caller=self)
            return
        self._m = M(**kwargs)

    @property
    def orderbooks(self):
        return self._m.orderbooks

    @property
    def klines(self):
        return self._m.klines

    @property
    def trades(self):
        return self._m.trades

    @property
    def rest_api(self):
        return self._rest_api

    def init_data(self):
        return self._m.init_data()
