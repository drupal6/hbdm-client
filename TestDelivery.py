from alpha.platforms.delivery.huobi_delivery_api import HuobiDeliveryRestAPI
import asyncio


if __name__ == '__main__':
    request = HuobiDeliveryRestAPI("https://api.btcgateway.pro", "xxxx", "xxxx")

    async def get_data():
        success, error = await request.create_order(symbol="BCH", contract_type="this_week", contract_code="",
                                                    volume=1, direction="buy", offset="open", lever_rate=10,
                                                    order_price_type="limit", price=300)
        print(success)
        print(error)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_data())
    loop.close()






