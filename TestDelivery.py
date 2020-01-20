from alpha.platforms.delivery.huobi_delivery_api import HuobiDeliveryRestAPI
import asyncio


if __name__ == '__main__':
    request = HuobiDeliveryRestAPI("https://api.btcgateway.pro", "a1e398fb-b2f29381-hrf5gdfghe-b5c30", "38a0ca03-78410e05-c7b44632-bd3b3")

    async def get_data():
        success, error = await request.get_position(symbol="BCH")
        print(success)
        print(error)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_data())
    loop.close()






