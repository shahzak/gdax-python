# gdax/WebsocketClient.py
# original author: Daniel Paquin
# mongo "support" added by Drew Rice
#
#
# Template object to receive messages from the gdax Websocket Feed

from __future__ import print_function
import json
import base64
import hmac
import hashlib
import time
import logging
from threading import Thread
from websocket import create_connection, WebSocketConnectionClosedException
from pymongo import MongoClient
from gdax.gdax_auth import get_auth_headers


class WebsocketClient(object):
    def __init__(self, url="wss://ws-feed.gdax.com", products=None, message_type="subscribe", mongo_collection=None,
                 should_print=True, auth=False, api_key="", api_secret="", api_passphrase="", channels=None, reconnect_attempts_max=50):
        self.url = url
        self.products = products
        self.channels = channels
        self.type = message_type
        self.stop = False
        self.error = None
        self.ws = None
        self.thread = None
        self.auth = auth
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.should_print = should_print
        self.mongo_collection = mongo_collection
        self.reconnect_attempts_max = reconnect_attempts_max
        self.reconnect_attempts = 0

    def start(self):
        def _go():
            self._connect()
            self._listen()
            self._disconnect()

        self.stop = False
        self.on_open()
        self.thread = Thread(target=_go)
        self.thread.start()

    def _connect(self):
        if self.products is None:
            self.products = ["BTC-USD"]
        elif not isinstance(self.products, list):
            self.products = [self.products]

        if self.url[-1] == "/":
            self.url = self.url[:-1]

        if self.channels is None:
            sub_params = {'type': 'subscribe', 'product_ids': self.products}
        else:
            sub_params = {'type': 'subscribe', 'product_ids': self.products, 'channels': self.channels}

        if self.auth:
            timestamp = str(time.time())
            message = timestamp + 'GET' + '/users/self/verify'
            message = message.encode('ascii')
            hmac_key = base64.b64decode(self.api_secret)
            signature = hmac.new(hmac_key, message, hashlib.sha256)
            signature_b64 = base64.b64encode(signature.digest()).decode('utf-8').rstrip('\n')
            sub_params['signature'] = signature_b64
            sub_params['key'] = self.api_key
            sub_params['passphrase'] = self.api_passphrase
            sub_params['timestamp'] = timestamp

        self.ws = create_connection(self.url)

        self.ws.send(json.dumps(sub_params))

    def keepalive(self, interval=30):
        while not self.stop:
            if self.ws:
                self.ws.ping("keepalive")
                time.sleep(interval)

    # create a thread before the while loop in the _listen method
    def _listen(self):
        Thread(target=self.keepalive).start()
        while not self.stop:
            try:
                data = self.ws.recv()
                msg = json.loads(data)
            except ValueError as e:
                self.on_error(e, data)
            except Exception as e:
                self.on_error(e, data)
            else:
                self.on_message(msg)

    def _disconnect(self, closeClient=True):
        try:
            if self.ws:
                self.ws.close()
        except WebSocketConnectionClosedException as e:
            pass

        if closeClient:
            self.on_close()

    def close(self):
        self.stop = True
        self.thread.join()

    def on_open(self):
        if self.should_print:
            logging.info("-- Subscribed! --\n")

    def on_close(self):
        if self.should_print:
            logging.info("\n-- Socket Closed --")

    def on_message(self, msg):
        if self.should_print:
            print(msg)
        if self.mongo_collection:  # dump JSON to given mongo collection
            self.mongo_collection.insert_one(msg)

    def on_error(self, e, data=None):
        self.error = e
        logging.error('Error on Recieve {} - data: {}'.format(e, data))
        if self.reconnect_attempts < self.reconnect_attempts_max
            self.stop = False
            logging.error('Trying to reconnect')
            self._disconnect(False) #disconnect but don't close this client
           # time.sleep(1) #wait a sec before trying to reconnect
            self._connect()
            self.reconnect_attempts += 1
        else
            self.stop = True
            logging.error('Reached maximum reconnect attempts. Closing')


if __name__ == "__main__":
    import sys
    import gdax
    import time


    class MyWebsocketClient(gdax.WebsocketClient):
        def on_open(self):
            self.url = "wss://ws-feed.gdax.com/"
            self.products = ["BTC-USD", "ETH-USD"]
            self.message_count = 0
            logging.info("Let's count the messages!")

        def on_message(self, msg):
            print(json.dumps(msg, indent=4, sort_keys=True))
            self.message_count += 1

        def on_close(self):
            logging.info("-- Goodbye! --")


    wsClient = MyWebsocketClient()
    wsClient.start()
    print(wsClient.url, wsClient.products)
    try:
        while True:
            print("\nMessageCount =", "%i \n" % wsClient.message_count)
            time.sleep(1)
    except KeyboardInterrupt:
        wsClient.close()

    if wsClient.error:
        sys.exit(1)
    else:
        sys.exit(0)
