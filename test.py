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

#ac = Aircon(0x42)
ac = Aircon(0x40)
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

def publish(client):
    msg_count = 0
    while True:
        time.sleep(1)
        msg = f"messages: {msg_count}"
        result = client.publish(topic, msg)
        # result: [0, 1]
        status = result[0]
        if status == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")
        msg_count += 1

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

            line = 'State1:'
            if ac.state1:
                for c in ac.state1:
                    line += f' {c:02X}'
                disp.add_stat(6, 'Power:   {:1b}'.format(ac.power))
                #disp.add_stat(7, 'Mode:  {:03b}'.format(ac.mode))
                disp.add_stat(7, 'Mode:    {:s}'.format(ac.mode_text(ac.mode)))
                disp.add_stat(8, 'Fan:     {:1b}'.format(ac.fan))
                #disp.add_stat(9, 'FanLV: {:03b}'.format(ac.fan_lv))
                disp.add_stat(9, 'FanLV:   {:s}'.format(ac.fan_text(ac.fan_lv)))
                disp.add_stat(10,'SetTemp: {:2d}'.format(ac.temp1))
                disp.add_stat(11,'Temp:    {:2d}'.format(ac.temp2))
                disp.add_stat(12,'Save:    {:1b}'.format(ac.save))
            disp.add_stat(1, line)
            line = 'State2:'
            if ac.state2:
                for c in ac.state2:
                    line += f' {c:02X}'
            disp.add_stat(2, line)
            line = 'params:'
            if ac.params:
                for c in ac.params:
                    line += f' {c:02X}'
            disp.add_stat(3, line)
            line = 'pong:  '
            if ac.pong:
                for c in ac.pong:
                    line += f' {c:02X}'
            disp.add_stat(4, line)
            line = 'rep_94:'
            if ac.reply_94:
                for c in ac.reply_94:
                    line += f' {c:02X}'
            disp.add_stat(5, line)
            disp.disp_stat()
        elif msg.topic == 'aircon/packet/error':
            status = msg.payload
            db.write_packet(status)

    client.subscribe(topic)
    client.on_message = on_message

def run():
    client = connect_mqtt()
    subscribe(client)
    #client.loop_forever()
    while True:
        client.loop()
        c = disp.getch()
        line = 'Sent: '
        p = None
        if c == ord('q'):
            break
        elif c == ord('z'):
            p = ac.set_mode('A')
        elif c == ord('x'):
            p = ac.set_mode('H')
        elif c == ord('c'):
            p = ac.set_mode('D')
        elif c == ord('v'):
            p = ac.set_mode('C')
        elif c == ord('b'):
            p = ac.set_mode('F')
        elif c == ord('a'):
            p = ac.set_fan('L')
        elif c == ord('s'):
            p = ac.set_fan('M')
        elif c == ord('d'):
            p = ac.set_fan('H')
        elif c == ord('f'):
            p = ac.set_fan('A')
        elif c == ord('e'):
            temp = ac.temp1
            if temp > ac.__class__.MIN_TMP:
                temp -= 1
            p = ac.set_temp(temp)
        elif c == ord('r'):
            temp = ac.temp1
            if temp < ac.__class__.MAX_TMP:
                temp += 1
            p = ac.set_temp(temp)
        if p is not None:
            for a in p:
                line += f'{a:02X} '
            result = client.publish('aircon/packet/tx', bytearray(p))
            # result: [0, 1]
            #status = result[0]
            #if status == 0:
            #    print(f"Send `{msg}` to topic `{topic}`")
            #else:
            #    print(f"Failed to send message to topic {topic}")
            disp.add_stat(14, f'{line:36s}')
            disp.disp_stat()

run()
