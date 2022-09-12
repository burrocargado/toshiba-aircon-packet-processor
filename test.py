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
            line = ''
            for c in packet[:-1]:
                line += f'{c:02X} '
            c = packet[-1]
            line += f'{c:02X}'
            disp.print_raw(line)

            if ac.state1:
                line = 'State1: '
                for c in ac.state1:
                    line += f' {c:02X}'
                disp.add_stat(1, line)
                y = 7
                #disp.add_stat(y, f'Power:   {ac.power:1b}')
                txt = 'ON' if ac.power else 'OFF'
                disp.add_stat(y, f'Power:   {txt:3s}')
                y +=1
                disp.add_stat(y, f'Mode:    {ac.mode_text(ac.mode).title():9s}')
                #y +=1
                #disp.add_stat(y, f'Clean:   {ac.clean:1b}')
                y +=1
                disp.add_stat(y, f'FanLv:   {ac.fan_text(ac.fan_lv).title():4s}')
                y +=1
                disp.add_stat(y, f'SetTemp: {ac.temp1:2d}')
                y +=1
                disp.add_stat(y, f'Temp:    {ac.temp2:2d}')
                y +=1
                disp.add_stat(y, f'Save:    {ac.save_text(ac.save).upper():3s}')

            txt = 'Filter' if ac.filter else ''
            disp.win_state.addstr(2, 52, f'{txt:6s}')
            txt = 'Ventilation' if ac.vent else ''
            disp.win_state.addstr(1, 47, f'{txt:11s}')
            txt = 'Cleaning' if ac.clean else ''
            disp.win_state.addstr(1, 37, f'{txt:8s}')

            if ac.params:
                line = 'params: '
                for c in ac.params:
                    line += f' {c:02X}'
                disp.add_stat(2, line)

        elif msg.topic == 'aircon/packet/tx':
            packet = msg.payload
            db.write_packet('TX', packet)
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            db.write_packet(status)
        elif msg.topic == 'aircon/control':
            ctrl = json.loads(msg.payload)
            if 'set_power' in ctrl:
                v = ctrl['set_power']
                if v == 'on':
                    ac.set_power(True)
                elif v == 'off':
                    ac.set_power(False)
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
        if status == 0:
            line = 'Sent:    '
        else:
            line = 'Failed:  '
        for a in p:
            line += f'{a:02X} '
        disp.add_stat(14, f'{line:55s}')

    def update_sensors():
        y = 3
        line = 'Sensors: '
        line += str({k: ac.sensor[k] for k in [0x02, 0x03, 0x04, 0x65, 0x6a]})
        disp.add_stat(y, f'{line:55s}')
        y +=1
        line = 'Sensors: '
        line += str({k: ac.sensor[k] for k in [0x60, 0x61, 0x62, 0x63]})
        disp.add_stat(y, f'{line:55s}')
        y +=1
        line = 'PwrLv:   '
        line += f'{ac.pwr_lv1:02d}, {ac.pwr_lv2:03d}'
        disp.add_stat(y, f'{line:30s}')
        y +=1
        line = 'Filter:  '
        line += '{:04d} H'.format(ac.filter_time)
        disp.add_stat(y, f'{line:30s}')

        update = {
            'power': 'ON' if ac.power == 1 else 'OFF',
            'mode': ac.mode_text(ac.mode),
            'clean': 'ON' if ac.clean == 1 else 'OFF',
            'fanlv': ac.fan_text(ac.fan_lv),
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
        data = {
            'power': 'on' if ac.power == 1 else 'off',
            'mode': ac.mode_text(ac.mode),
            'clean': 'on' if ac.clean == 1 else 'off',
            'fanlv': ac.fan_text(ac.fan_lv),
            'settmp': ac.temp1,
            'temp': ac.temp2,
            'filter': 'on' if ac.filter == 1 else 'off',
            'vent': 'on' if ac.vent == 1 else 'off',
            'save': ac.save_text(ac.save),
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
        line = 'State:   '
        line += ac.state_text().capitalize()
        disp.add_stat(15, f'{line:36s}')
        disp.loop()
        c = disp.getch()
        if c == ord('q'):
            disp.quit()
            break
        elif c == ord('z'):
            ac.set_mode('A')
        elif c == ord('x'):
            ac.set_mode('H')
        elif c == ord('c'):
            ac.set_mode('D')
        elif c == ord('v'):
            ac.set_mode('C')
        elif c == ord('b'):
            ac.set_mode('F')
        elif c == ord('a'):
            ac.set_fan('L')
        elif c == ord('s'):
            ac.set_fan('M')
        elif c == ord('d'):
            ac.set_fan('H')
        elif c == ord('f'):
            ac.set_fan('A')
        elif c == ord('1'):
            ac.set_power(True)
        elif c == ord('2'):
            ac.set_power(False)
        elif c == ord('3'):
            ac.set_save('S')
        elif c == ord('4'):
            ac.set_save('R')
        #elif c == ord('0'):
        #    ac.reset_filter()
        elif c == ord('e'):
            temp = ac.temp1
            if temp > ac.__class__.MIN_TMP:
                temp -= 1
                ac.set_temp(temp)
        elif c == ord('r'):
            temp = ac.temp1
            if temp < ac.__class__.MAX_TMP:
                temp += 1
                ac.set_temp(temp)

run()
