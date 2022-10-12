"""
This is a test program using toshiba-aircon-mqtt-bridge.
Tested with NTS-F1403Y1 released 2004.
"""
import random
import ssl
import json
import argparse
from paho.mqtt import client as mqtt_client
import time

from toshiba import Aircon
from credentials import *

import json
from logging import getLogger, config

TOPIC = "aircon/#"
client_id = f'python-mqtt-{random.randint(0, 1000)}'

parser = argparse.ArgumentParser(
    description='packet processing server for Toshiba air conditioner'
)
parser.add_argument(
    "-i", "--interactive", action='store_true',
    help="Enable interactive mode"
)
parser.add_argument(
    "-p", "--packetlog", action='store_true',
    help="Enable packet logging to database"
)
parser.add_argument(
    "-s", "--statuslog", action='store_true',
    help="Enable status logging to database"
)
parser.add_argument(
    "-v", "--verbose", action='store_true',
    help="Set logger to DEBUG"
)

args = parser.parse_args()

with open('log_config.json', 'r') as f:
    log_conf = json.load(f)

loggers = log_conf['loggers']
for logger in loggers:
    handler = loggers[logger]['handlers']
    if not args.interactive:
        if not 'consoleHandler' in handler:
            handler.append('consoleHandler')
        #if 'fileHandler' in handler:
        #    handler.remove('fileHandler')
    else:
        if 'consoleHandler' in handler:
            handler.remove('consoleHandler')
        if not 'fileHandler' in handler:
            handler.append('fileHandler')

handlers = log_conf['handlers']
for handler in handlers:
    if args.verbose:
        handlers[handler]['level'] = 'DEBUG'

config.dictConfig(log_conf)
logger = getLogger(__name__)

ac = Aircon(0x42)
if args.interactive:
    from display import Display
    disp = Display()
else:
    disp = None

if args.packetlog or args.statuslog:
    from database import DB
    db = DB()

def connect_mqtt():
    def on_connect(_client, _userdata, _flags, rc):
        logger.info("Connected to MQTT broker with status %d", rc)
        client.subscribe(TOPIC)

    def on_disconnect(_client, _userdata, _rc):
        logger.warning("MQTT desconnected")
        while True:
            logger.debug("Trying to reconnect")
            try:
                client.reconnect()
                logger.info("MQTT reconnected")
                break
            except Exception as e:
                logger.debug(e)
                time.sleep(5)

    # Set Connecting Client ID
    client = mqtt_client.Client(client_id)
    client.username_pw_set(username, password)
    #client.tls_set(cert_reqs=ssl.CERT_NONE)
    #client.tls_insecure_set(True)
    ca_certs = "certs/ca.crt"
    certfile = "certs/client.crt"
    keyfile = "certs/client.key"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(ca_certs)
    context.load_cert_chain(certfile, keyfile)

    client.tls_set_context(context)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(_client, _userdata, msg):
        if msg.topic == 'aircon/packet/rx':
            packet = msg.payload
            logger.debug('aircon/packet/rx: %s', bytes(packet).hex())
            ac.parse(packet)
            if args.packetlog:
                db.write_packet('RX', packet)
            if disp:
                disp.on_rx_packet(packet, ac)
        elif msg.topic == 'aircon/packet/tx':
            packet = msg.payload
            logger.debug('aircon/packet/tx: %s', bytes(packet).hex())
            if args.packetlog:
                db.write_packet('TX', packet)
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            logger.info('aircon/packet/error: %s', status)
            if args.packetlog:
                db.write_packet(status)
        elif msg.topic == 'aircon/control':
            ctrl = json.loads(msg.payload)
            logger.info('aircon/control: %s', ctrl)
            if 'set_power' in ctrl:
                ac.set_power(ctrl['set_power'])
            if 'set_temp' in ctrl:
                ac.set_temp(ctrl['set_temp'])
            if 'set_fan' in ctrl:
                ac.set_fan(ctrl['set_fan'])
            if 'set_mode' in ctrl:
                ac.set_mode(ctrl['set_mode'])
            if 'set_save' in ctrl:
                ac.set_save(ctrl['set_save'])
            if 'set_humid' in ctrl:
                ac.set_humid(ctrl['set_humid'])
        elif msg.topic == 'aircon/update':
            logger.debug('aircon/update: %s', msg.payload)
        elif msg.topic == 'aircon/status':
            logger.debug('aircon/status: %s', msg.payload)

    client.on_message = on_message

def run():
    client = connect_mqtt()
    subscribe(client)

    def transmit(p):
        result = client.publish('aircon/packet/tx', bytearray(p))
        # result: [0, 1]
        logger.debug('packet sent: %s', result)
        status = result[0]
        if disp:
            disp.disp_packet(p)
            disp.send_status(p, status)

    def update_sensors():
        if disp:
            disp.disp_sensors(ac)

        update = {
            'power': ac.bits_to_text('power', ac.power),
            'mode': ac.bits_to_text('mode', ac.mode),
            'clean': 'ON' if ac.clean == 1 else 'OFF',
            'fanlv': ac.bits_to_text('fan', ac.fan_lv),
            'settmp': ac.temp1,
            'temp': ac.temp2,
            'pwrlv1': ac.pwr_lv1,
            'pwrlv2': ac.pwr_lv2,
            'sens_ta': ac.sensor[0x02],
            'sens_tcj': ac.sensor[0x03],
            'sens_tc': ac.sensor[0x04],
            'sens_te': ac.sensor[0x60],
            'sens_to': ac.sensor[0x61],
            'sens_td': ac.sensor[0x62],
            'sens_ts': ac.sensor[0x63],
            'sens_ths': ac.sensor[0x65],
            'sens_current': ac.sensor[0x6a],
            'filter_time': ac.filter_time,
            'filter': 'ON' if ac.filter == 1 else 'OFF',
            'vent': 'ON' if ac.vent == 1 else 'OFF',
            'humid': ac.bits_to_text('humid', ac.humid),
        }
        if args.statuslog:
            db.write_status(update)
        data = {
            'pwrlv1': ac.pwr_lv1,
            'pwrlv2': ac.pwr_lv2,
            'filter_time': ac.filter_time,
            'sens_ta': ac.sensor[0x02],
            'sens_tcj': ac.sensor[0x03],
            'sens_tc': ac.sensor[0x04],
            'sens_te': ac.sensor[0x60],
            'sens_to': ac.sensor[0x61],
            'sens_td': ac.sensor[0x62],
            'sens_ts': ac.sensor[0x63],
            'sens_ths': ac.sensor[0x65],
            'sens_current': ac.sensor[0x6a],
        }
        result = client.publish('aircon/update', json.dumps(data))
        logger.debug('update sent: %s', result)

    def update_status(ext):
        if disp:
            disp.disp_status(ac)

        data = {
            'power': ac.bits_to_text('power', ac.power),
            'mode': ac.bits_to_text('mode', ac.mode),
            'clean': 'on' if ac.clean == 1 else 'off',
            'fanlv': ac.bits_to_text('fan', ac.fan_lv),
            'settmp': ac.temp1,
            'temp': ac.temp2,
            'filter': 'on' if ac.filter == 1 else 'off',
            'vent': 'on' if ac.vent == 1 else 'off',
            'save': ac.bits_to_text('save', ac.save),
            'humid': ac.bits_to_text('humid', ac.humid),
        }
        result = client.publish('aircon/status', json.dumps(data))
        if not ext:
            logger.info('status change: %s', data)
        logger.debug('status sent: %s, result:%s', data, result)

    ac.transmit = transmit
    ac.update_cb = update_sensors
    ac.status_cb = update_status

    while True:
        client.loop(timeout=0.01)
        ac.loop()
        if disp:
            if disp.loop(ac):
                break

run()
