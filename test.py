"""
This is a test program using toshiba-aircon-mqtt-bridge.
Tested with NTS-F1403Y1 released 2004.
"""
import random
import ssl
#import time
import json

from paho.mqtt import client as mqtt_client

from toshiba import Aircon
from display import Display
from credentials import *
from database import DB

TOPIC = "aircon/#"
client_id = f'python-mqtt-{random.randint(0, 1000)}'

ac = Aircon(0x42)
disp = Display()
db = DB()

def connect_mqtt():
    def on_connect(_client, _userdata, _flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
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
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(_client, _userdata, msg):
        if msg.topic == 'aircon/packet/rx':
            packet = msg.payload
            ac.parse(packet)
            db.write_packet('RX', packet)
            if disp:
                disp.on_message(packet, ac)
        elif msg.topic == 'aircon/packet/tx':
            packet = msg.payload
            db.write_packet('TX', packet)
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            db.write_packet(status)
        elif msg.topic == 'aircon/control':
            ctrl = json.loads(msg.payload)
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

    client.subscribe(TOPIC)
    client.on_message = on_message

def run():
    client = connect_mqtt()
    subscribe(client)

    def transmit(p):
        result = client.publish('aircon/packet/tx', bytearray(p))
        # result: [0, 1]
        status = result[0]
        if disp:
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
        }
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
        #update = {'update': data}
        #result = client.publish('aircon/update', json.dumps(update))
        result = client.publish('aircon/update', json.dumps(data))

    def update_status():
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
        }
        #update = {'status': data}
        #result = client.publish('aircon/status', json.dumps(update))
        result = client.publish('aircon/status', json.dumps(data))

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
