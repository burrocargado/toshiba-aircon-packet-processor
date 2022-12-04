"""
Packet processing server for Toshiba air conditioner
with wired remote controller connected to AB bus.
This program is for use with toshiba-aircon-mqtt-bridge.
"""
import random
import ssl
import json
import argparse
import time
import sys
from logging import getLogger, config
from paho.mqtt import client as mqtt_client
from toshiba import Aircon
import credentials

logger = getLogger(__name__)


class Server():
    # pylint: disable=too-many-arguments
    def __init__(
            self, disp=None, db=None, statuslog=False,
            packetlog=False, receive_only=True, tls=True,
            address=0x42):
        self.bridge_alive = False
        self.ac = Aircon(address)
        self.disp = disp
        self.db = db
        self.tls = tls
        if db is not None:
            self.statuslog = statuslog
            self.packetlog = packetlog
        else:
            self.statuslog = False
            self.packetlog = False

        if not receive_only:
            self.ac.transmit = self.transmit
        self.ac.start_cb = self.send_start
        self.ac.ready_cb = self.send_ready
        self.ac.update_cb = self.update_sensors
        self.ac.status_cb = self.update_status

        self.client_id = f'python-mqtt-{random.randint(0, 1000)}'
        self.client = self.connect_mqtt()

    def send_start(self):
        payload = json.dumps({'state': 'start'})
        self.client.publish(
            "aircon/client/processor",
            payload=payload, qos=1, retain=True
        )

    def send_ready(self):
        payload = json.dumps({'state': 'ready'})
        self.client.publish(
            "aircon/client/processor",
            payload=payload, qos=1, retain=True
        )

    def on_connect(self, _client, _userdata, _flags, rc):
        logger.info("Connected to MQTT broker with status %d", rc)
        if rc == 0:
            self.client.subscribe('aircon/#', qos=1)
        else:
            logger.error('MQTT connection failed, abort')
            sys.exit(1)

    def on_disconnect(self, _client, _userdata, _rc):
        logger.warning("MQTT disconnected")
        while True:
            logger.debug("Trying to reconnect")
            try:
                self.client.reconnect()
                break
            except Exception as e:
                logger.debug(e)
                time.sleep(5)

    def on_message(self, _client, _userdata, msg):
        ac = self.ac
        # pylint: disable=too-many-branches
        if msg.topic == 'aircon/packet/rx':
            packet = msg.payload
            logger.debug('aircon/packet/rx: %s', bytes(packet).hex())
            ac.parse(packet)
            if self.packetlog:
                self.db.write_packet('RX', packet)
            if self.disp:
                self.disp.on_rx_packet(packet, ac)
        elif msg.topic == 'aircon/packet/tx':
            packet = msg.payload
            logger.debug('aircon/packet/tx: %s', bytes(packet).hex())
            if self.packetlog:
                self.db.write_packet('TX', packet)
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            logger.info('aircon/packet/error: %s', status)
            if self.packetlog:
                self.db.write_packet(status)
        elif msg.topic == 'aircon/control':
            if not self.bridge_alive:
                return
            try:
                ctrl = json.loads(msg.payload)
            except Exception as e:
                logger.error('control message is not in json format: %s', e)
            else:
                logger.info('aircon/control: %s', ctrl)
                if 'set_power' in ctrl:
                    ac.set_power(ctrl['set_power'])
                if 'set_mode' in ctrl:
                    ac.set_mode(ctrl['set_mode'])
                if 'set_fan' in ctrl:
                    ac.set_fan(ctrl['set_fan'])
                if 'set_temp' in ctrl:
                    ac.set_temp(ctrl['set_temp'])
                if 'set_save' in ctrl:
                    ac.set_save(ctrl['set_save'])
                if 'set_humid' in ctrl:
                    ac.set_humid(ctrl['set_humid'])
        elif msg.topic == 'aircon/client/bridge':
            try:
                data = json.loads(msg.payload)
            except Exception as e:
                logger.error('client message is not in json format: %s', e)
            else:
                logger.info('aircon/client/bridge: %s', data)
                connection = data.get('connection')
                if connection == 'dead':
                    ac.reset()
                    self.bridge_alive = False
                elif connection == 'alive':
                    ac.reset()
                    self.bridge_alive = True

        elif msg.topic == 'aircon/update':
            logger.debug('aircon/update: %s', msg.payload)
        elif msg.topic == 'aircon/status':
            logger.debug('aircon/status: %s', msg.payload)

    def connect_mqtt(self):
        client = mqtt_client.Client(self.client_id, clean_session=True)
        username = getattr(credentials, 'username', None)
        password = getattr(credentials, 'password', None)
        if username is not None and password is not None:
            client.username_pw_set(username, password)
        if self.tls:
            logger.info('Use TLS for MQTT connection')
            ca_cert = getattr(credentials, 'ca_cert', None)
            certfile = getattr(credentials, 'certfile', None)
            keyfile = getattr(credentials, 'keyfile', None)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if ca_cert is not None:
                context.load_verify_locations(ca_cert)
            else:
                logger.warning('Insecure mode: disable TLS server check')
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            if certfile is not None and keyfile is not None:
                context.load_cert_chain(certfile, keyfile)

            client.tls_set_context(context)

        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        payload = json.dumps({'state': 'offline'})
        client.will_set("aircon/client/processor", payload=payload, qos=1, retain=True)
        client.connect(credentials.broker, credentials.port)

        return client

    def transmit(self, p):
        result = self.client.publish('aircon/packet/tx', bytearray(p))
        logger.debug('packet sent: %s', result)
        status = result[0]
        if self.disp:
            self.disp.disp_packet(p)
            self.disp.send_status(p, status)

    def update_sensors(self):
        ac = self.ac
        if self.disp:
            self.disp.disp_sensors(ac)
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
        if self.statuslog:
            self.db.write_status(update)
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
        result = self.client.publish('aircon/update', json.dumps(data))
        logger.debug('update sent: %s', result)

    def update_status(self, ext):
        ac = self.ac
        if self.disp:
            self.disp.disp_status(ac)
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
        result = self.client.publish('aircon/status', json.dumps(data))

        if not ext:
            logger.info('status change: %s', data)
        logger.debug('status sent: %s, result:%s', data, result)

    def run(self):
        while True:
            self.client.loop(timeout=0.01)
            self.ac.loop()
            if self.disp:
                if self.disp.loop(self.ac):
                    break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='packet processing server for Toshiba air conditioner'
    )
    parser.add_argument(
        "-i", "--interactive", action='store_true',
        help="enable interactive mode"
    )
    parser.add_argument(
        "-p", "--packetlog", action='store_true',
        help="enable packet logging to database"
    )
    parser.add_argument(
        "-s", "--statuslog", action='store_true',
        help="enable status logging to database"
    )
    parser.add_argument(
        "-r", "--receive-only", action='store_true',
        help="disable packet transmission"
    )
    parser.add_argument(
        "-v", "--verbose", action='store_true',
        help="set logging level to DEBUG"
    )
    args = parser.parse_args()

    with open('log_config.json', 'r', encoding='utf-8') as f:
        log_conf = json.load(f)

    loggers = log_conf['loggers']
    for logger_ in loggers:
        handler = loggers[logger_]['handlers']
        if not args.interactive:
            if 'consoleHandler' not in handler:
                handler.append('consoleHandler')
            # if 'fileHandler' in handler:
            #    handler.remove('fileHandler')
        else:
            if 'consoleHandler' in handler:
                handler.remove('consoleHandler')
            if 'fileHandler' not in handler:
                handler.append('fileHandler')

    handlers = log_conf['handlers']
    for handler in handlers:
        if args.verbose:
            handlers[handler]['level'] = 'DEBUG'

    config.dictConfig(log_conf)

    if args.interactive:
        from display import Display
        _disp = Display()
    else:
        _disp = None

    if args.packetlog or args.statuslog:
        from database import DB
        _db = DB()
    else:
        _db = None

    server = Server(
        _disp, _db, args.statuslog, args.packetlog, args.receive_only
    )
    server.run()
