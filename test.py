from paho.mqtt import client as mqtt_client
import random
import time
from toshiba import Aircon
from display import Display
import ssl
from credentials import *
from database import DB
import datetime as dt

topic = "aircon/#"
client_id = f'python-mqtt-{random.randint(0, 1000)}'

ac = Aircon(0x42)
#ac = Aircon(0x40)
disp = Display()
#db = DB('sqlite:///log.sqlite3')
timestr = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
db = DB(f"sqlite:///packetlog/log-{timestr}.sqlite3")

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
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
    
    #client.tls_set(ca_certs, certfile, keyfile, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1, ciphers=None)
    #client.tls_set(ca_certs, certfile, keyfile, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    #client.tls_set(ca_certs, certfile, keyfile, cert_reqs=ssl.CERT_REQUIRED, ciphers=None)
    client.tls_set_context(context)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        #print(f"Received `{msg.payload}` from `{msg.topic}` topic")
        if msg.topic == 'aircon/packet/rx':
            packet = msg.payload
            ac.parse(packet)
            db.write_packet('OK', packet)
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
                disp.add_stat(y, 'Power:   {:1b}'.format(ac.power)); y +=1
                #disp.add_stat(7, 'Mode:  {:03b}'.format(ac.mode))
                disp.add_stat(y, 'Mode:    {:9s}'.format(ac.mode_text(ac.mode).title())); y +=1
                disp.add_stat(y, 'Clean:   {:1b}'.format(ac.clean)); y +=1
                #disp.add_stat(9, 'FanLv: {:03b}'.format(ac.fan_lv))
                disp.add_stat(y, 'FanLv:   {:4s}'.format(ac.fan_text(ac.fan_lv).title())); y +=1
                disp.add_stat(y,'SetTemp: {:2d}'.format(ac.temp1)); y +=1
                disp.add_stat(y,'Temp:    {:2d}'.format(ac.temp2)); y +=1
                disp.add_stat(y,'Save:    {:3s}'.format(ac.save_text(ac.save).title()))
            #line = 'State2: '
            #if ac.state2:
            #    for c in ac.state2:
            #        line += f' {c:02X}'
            #disp.add_stat(2, line)
            
            if ac.params:
                line = 'params: '
                for c in ac.params:
                    line += f' {c:02X}'
                disp.add_stat(2, line)
            #line = 'sensors: '
            #if ac.sensor:
            #    line += '{:s}'.format(str(ac.sensor))
            #disp.add_stat(4, f'{line:30s}')
            
            #if 0x94 in ac.extra:
            #    line = 'PwrLV:  '
            #    value = ac.extra[0x94]
            #    #line += '{:s}'.format(str(ac.extra))
            #    for c in value:
            #        line += f' {c:02X}'
            #    disp.add_stat(5, f'{line:30s}')

            #disp.disp_stat()
        
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            db.write_packet(status)

    client.subscribe(topic)
    client.on_message = on_message

def run():
    client = connect_mqtt()
    subscribe(client)
    def transmit(p):
        result = client.publish('aircon/packet/tx', bytearray(p))
        # result: [0, 1]
        #status = result[0]
        #if status == 0:
        #    print(f"Send `{msg}` to topic `{topic}`")
        #else:
        #    print(f"Failed to send message to topic {topic}")
        line = 'Sent:    '
        for a in p:
            line += f'{a:02X} '
        disp.add_stat(14, f'{line:55s}')
        #disp.disp_stat()

    def update_sensors():
        y = 3
        line = 'Sensors: '
        line += '{:s}'.format(str({k: ac.sensor[k] for k in [0x02, 0x03, 0x04, 0x65, 0x6a]}))
        disp.add_stat(y, f'{line:55s}'); y +=1
        line = 'Sensors: '
        line += '{:s}'.format(str({k: ac.sensor[k] for k in [0x60, 0x61, 0x62, 0x63]}))
        disp.add_stat(y, f'{line:55s}'); y +=1
        line = 'PwrLv:   '
        line += '{:02d}, {:03d}'.format(ac.pwr_lv1, ac.pwr_lv2)
        disp.add_stat(y, f'{line:30s}'); y +=1
        line = 'Filter:  '
        line += '{:04d} H'.format(ac.filter_time)
        disp.add_stat(y, f'{line:30s}')
        
        update = {
            'power': 'ON' if ac.power == 1 else 'OFF',
            'mode': ac.mode_text(ac.mode),
            'fan': 'ON' if ac.clean == 1 else 'OFF',
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
        }
        db.write_status(update)

    ac.transmit = transmit
    ac.update_cb = update_sensors
    #client.loop_forever()
    while True:
        client.loop()
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
            ac.set_save('S')
        elif c == ord('2'):
            ac.set_save('R')
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
        #disp.disp_stat()
        #disp.loop()

run()
