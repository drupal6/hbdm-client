from alpha.platforms.delivery.huobi_delivery_api import HuobiDeliveryRestAPI
import asyncio


if __name__ == '__main__':
    request = HuobiDeliveryRestAPI("https://api.btcgateway.pro", "", "")

    async def get_data():
        success, error = await request.get_position(symbol="BCH")
        print(success)
        print(error)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_data())
    loop.close()






