from enum import IntEnum
from collections import namedtuple
import time
import struct
from transitions import Machine
from transitions.extensions import GraphMachine
from transitions.extensions.states import add_state_features, Timeout

HEAD_TMP = 0b01
HEAD_FAN = 0b10
RETRY_WAIT = 1.0 # timeout in seconds for command or query reply
QUERY_INTERVAL = 60.0

class State(IntEnum):
    START = 0
    IDLE = 1
    CMD = 2
    QUERY1 = 3
    QUERY2 = 4
    SSAVE = 5
    FILTER = 6
    HUMID = 7
    HMDTGL = 8

    def __str__(self):
        if self.value == 0:
            text = 'starting up'
        elif self.value == 1:
            text = 'idle'
        elif self.value == 2:
            text = 'command sent'
        elif self.value == 3:
            text = 'sensor query'
        elif self.value == 4:
            text = 'extra query'
        elif self.value == 5:
            text = 'setting save mode'
        elif self.value == 6:
            text = 'resetting filter'
        elif self.value == 7:
            text = 'setting humidifier'
        elif self.value == 8:
            text = 'toggling humidifier'
        return text

@add_state_features(Timeout)
class CustomMachine(GraphMachine):
    pass

states = [
    State.START,
    State.IDLE,
    {'name': State.CMD, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
    {'name': State.QUERY1, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
    {'name': State.QUERY2, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
    {'name': State.SSAVE, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
    {'name': State.FILTER, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
    {'name': State.HUMID, 'timeout': RETRY_WAIT, 'on_timeout': 'hmd_timeout'},
    {'name': State.HMDTGL, 'timeout': RETRY_WAIT, 'on_timeout': 'ack_timeout'},
]

class StateMachine(object):

    def __init__(self, ac):
        self.ac = ac
        self.packet = None
        self.hmd = None

        self.machine = CustomMachine(model=self, states=states, initial=State.START, auto_transitions=False, send_event=True)
        self.machine.add_transition(
            trigger='idle',
            source=[State.START, State.CMD, State.QUERY1, State.QUERY2, State.SSAVE, State.FILTER, State.HUMID],
            dest=State.IDLE,
            before='before_idle',
        )
        self.machine.add_transition(trigger='cmd', source=State.IDLE, dest=State.CMD, after='send_packet')
        self.machine.add_transition(trigger='query1', source=State.IDLE, dest=State.QUERY1, after='send_packet')
        self.machine.add_transition(trigger='query2', source=State.IDLE, dest=State.QUERY2, after='send_packet')
        self.machine.add_transition(trigger='ssave', source=State.IDLE, dest=State.SSAVE, after='send_packet')
        self.machine.add_transition(trigger='filter', source=State.IDLE, dest=State.FILTER, after='send_packet')
        self.machine.add_transition(trigger='humid', source=[State.IDLE, State.HMDTGL], dest=State.HUMID, after='set_humid')
        self.machine.add_transition(trigger='hmdtgl', source=State.HUMID, dest=State.HMDTGL, after='send_packet')
        self.machine.add_transition(
            trigger='self',
            source=[State.CMD, State.QUERY1, State.QUERY2, State.SSAVE, State.FILTER, State.HMDTGL],
            dest='=',
        )

    def ack_timeout(self, event):
        #print(f'timeout: {self.state}')
        if self.ac.transmit:
            self.ac.transmit(self.packet)
            self.self()
    
    def send_packet(self, event):
        self.packet = event.kwargs.get('packet')
        if self.ac.transmit:
            self.ac.transmit(self.packet)

    def set_humid(self, event):
        hmd = event.kwargs.get('value')
        if hmd is not None:
            if self.ac.humid == hmd:
                self.idle()
            else:
                self.hmd = hmd
                self.ac.toggle_humid()

    def hmd_timeout(self, event):
        self.ac.toggle_humid()
    
    def before_idle(self, event):
        self.packet = None
        if self.state == State.HUMID:
            self.hmd = None

CmdSetItem = namedtuple('CmdSetItem', 'bits cmd text')
CommandSets = namedtuple('CommandSets', 'power mode fan save humid')
CMDSETS = CommandSets(
    # power
    (
        CmdSetItem(0b1, '1', 'on'),
        CmdSetItem(0b0, '0', 'off')
    ),
    # mode
    (
        CmdSetItem(0b001, 'H', 'heat'),
        CmdSetItem(0b010, 'C', 'cool'),
        CmdSetItem(0b011, 'F', 'fan'),
        CmdSetItem(0b100, 'D', 'dry'),
        CmdSetItem(0b101, 'A', 'auto heat'),
        CmdSetItem(0b110, '', 'auto cool')
    ),
    # fan
    (
        CmdSetItem(0b101, 'L', 'low'),
        CmdSetItem(0b100, 'M', 'med'),
        CmdSetItem(0b011, 'H', 'high'),
        CmdSetItem(0b010, 'A', 'auto')
    ),
    # save mode
    (
        CmdSetItem(0b11, 'R', 'off'),
        CmdSetItem(0b00, 'S', 'on')
    ),
    # humidifier
    (
        CmdSetItem(0b1, '1', 'on'),
        CmdSetItem(0b0, '0', 'off')
    )
)


class Aircon():

    MAX_TMP = 29
    MIN_TMP = 18

    def __init__(self, addr):
        self.transmit = None
        self.update_cb = None
        self.status_cb = None
        self.update = False
        self.c_queue = [] # command packet queue
        self.q1_queue = [] # sensor query packet queue
        self.q2_queue = [] # extra query packet queue
        self.sv_queue = [] # seve mode setting packet queue
        self.flt_queue = [] # filter resetting packet queue
        self.hmd_queue = [] # humidifier setting value queue
        self.machine = StateMachine(self)
        self.addr = addr

        self.state1 = None
        self.state2 = None
        self.params = None
        self.power = None
        self.mode = None
        self.save1 = None
        self.clean = None
        self.fan_lv = None
        self.temp1 = None
        self.temp2 = None
        self.save = None
        self.filter = None
        self.vent = None
        self.humid = None
        self.pwr_lv1 = 0
        self.pwr_lv2 = 0
        self.filter_time = 0
        self.sensor = {}
        self.extra = {}
        self.q_time = 0.0

    @property
    def state(self):
        return self.machine.state

    def send_cmd(self, p):
        if self.transmit is None:
            return
        self.c_queue.append(p)
        if self.state == State.IDLE:
            self.machine.cmd(packet=self.c_queue.pop(0))

    def send_hmd(self, p):
        if self.transmit is None:
            return
        assert self.state == State.HUMID
        self.machine.hmdtgl(packet=p)

    def send_query1(self, p):
        if self.transmit is None:
            self.sensor[p[11]] = 0
            return
        self.q1_queue.append(p)
        if self.state == State.IDLE:
            self.machine.query1(packet=self.q1_queue.pop(0))

    def send_query2(self, p):
        if self.transmit is None:
            return
        self.q2_queue.append(p)
        if self.state == State.IDLE:
            self.machine.query2(packet=self.q2_queue.pop(0))

    def send_sv(self, p):
        if self.transmit is None:
            return
        self.sv_queue.append(p)
        if self.state == State.IDLE:
            self.machine.ssave(packet=self.sv_queue.pop(0))

    def send_flt(self, p):
        if self.transmit is None:
            return
        self.flt_queue.append(p)
        if self.state == State.IDLE:
            self.machine.filter(packet=self.flt_queue.pop(0))

    def loop(self):
        if self.state == State.IDLE:
            if self.c_queue:
                self.machine.cmd(packet=self.c_queue.pop(0))
            elif self.sv_queue:
                self.machine.ssave(packet=self.sv_queue.pop(0))
            elif self.hmd_queue:
                self.machine.humid(value=self.hmd_queue.pop(0))
            elif self.flt_queue:
                self.machine.filter(packet=self.flt_queue.pop(0))
            elif self.q1_queue:
                self.machine.query1(packet=self.q1_queue.pop(0))
            elif self.q2_queue:
                self.machine.query2(packet=self.q2_queue.pop(0))
            elif self.update_cb is not None and self.update:
                self.update_cb()
                self.update = False
            elif time.time() - self.q_time > QUERY_INTERVAL:
                self.power_query()
                self.filter_query()
                self.sensor_query(0x02)
                self.sensor_query(0x03)
                self.sensor_query(0x04)
                self.sensor_query(0x60)
                self.sensor_query(0x61)
                self.sensor_query(0x62)
                self.sensor_query(0x63)
                self.sensor_query(0x65)
                self.sensor_query(0x6a)
                self.q_time = time.time()
                self.update = True
        elif self.state == State.SSAVE:
            if (self.machine.packet[0][7] >> 4) & 0b11 == self.save:
                self.machine.idle()
        elif self.state == State.FILTER:
            if self.filter == 0:
                self.machine.idle()
        elif self.state == State.HUMID:
            if self.humid == self.machine.hmd:
                self.machine.idle()

    def parse(self, p):
        if p[0] == 0x00:
            if p[1] == 0xfe:
                self.parse_broadcast(p)
            elif p[1] == 0x52:
                self.parse_params(p)
            elif p[1] == self.addr:
                self.parse_reply(p)

    def parse_broadcast(self, p):
        if p[2] == 0x58:
            payload = p[6:14]
            self.state1 = payload
            self.temp2 = (payload[5] >> 1) - 35
            self.save1 = payload[7] & 0b1
            if self.state == State.START:
                self.machine.idle()
        elif p[2] == 0x1c:
            payload = p[6:12]
            self.state2 = payload
        if p[2] == 0x58 or p[2] == 0x1c:
            self.power = payload[0] & 0b1
            self.mode = (payload[0] >> 5) & 0b111
            self.save = (payload[0] >> 3) & 0b11
            self.clean = (payload[1] >> 2) & 0b1
            self.fan_lv = (payload[1] >> 5) & 0b111
            self.filter = (payload[2] >> 7) & 0b1
            self.vent = (payload[2] >> 2) & 0b1 # this might be incorrect
            self.humid = (payload[2] >> 1) & 0b1
            self.temp1 = (payload[4] >> 1) - 35
            if self.status_cb:
                self.status_cb()

    def parse_params(self, p):
        if p[2] == 0x11:
            self.params = p[6:8]
    
    def parse_reply(self, p):
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xa1:
            if self.state == State.CMD:
                self.machine.idle()
            elif self.state == State.HMDTGL:
                self.machine.humid()
        if p[2] == 0x1a and p[4] == 0x80 and p[5] == 0xef:
            if self.state == State.QUERY1:
                p0 = self.machine.packet
                if p[8] == 0x2c:
                    self.sensor[p0[11]] = struct.unpack('>h', bytes(p[9:11]))[0]
                else:
                    self.sensor[p0[11]] = None
                self.machine.idle()
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xe8:
            if self.state == State.QUERY2:
                p0 = self.machine.packet
                self.extra[p0[9]] = p[6:11]
                if p0[9] == 0x94:
                    self.pwr_lv1 = p[9]
                    self.pwr_lv2 = p[10]
                elif p0[9] == 0x9e:
                    self.filter_time = (p[9] << 8) + p[10]
                self.machine.idle()

    def bits_to_text(self, cmdtype, bits):
        text = f'{bits:b}'
        for csi in getattr(CMDSETS, cmdtype):
            if csi.bits == bits:
                text = csi.text
                break
        return text

    def cmd_to_bits(self, cmdtype, cmd):
        assert cmd != ''
        bits = None
        for csi in getattr(CMDSETS, cmdtype):
            if csi.cmd == cmd:
                bits = csi.bits
                break
        assert bits is not None
        return bits

    def gen_pkt(self, header, payload):
        assert len(header) == 3
        p = []
        p += header
        p.append(len(payload))
        p += payload
        ck = 0x0
        for c in p:
            ck ^= c
        p.append(ck)
        return p

    def set_power(self, cmd):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x41]
        byte = 0x02 | self.cmd_to_bits('power', cmd)
        payload.append(byte)
        p = self.gen_pkt(header, payload)
        self.send_cmd(p)

    def set_mode(self, cmd):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x42]
        byte = self.cmd_to_bits('mode', cmd)
        payload.append(byte)
        p = self.gen_pkt(header, payload)
        self.send_cmd(p)

    def set_cmd(self, head, mode, fan_lv, temp):
        assert mode is not None
        assert fan_lv is not None
        assert temp >= self.MIN_TMP
        assert temp <= self.MAX_TMP
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x4c]
        mode = mode & 0b111
        byte = head << 3 | mode
        payload.append(byte)
        fan_lv = fan_lv & 0b111
        byte = 0b111000 | fan_lv
        payload.append(byte)
        temp = (temp + 35) << 1
        payload.append(temp)
        p = self.gen_pkt(header, payload)
        self.send_cmd(p)

    def set_temp(self, temp):
        assert self.state != State.START
        self.set_cmd(HEAD_TMP, self.mode, self.fan_lv, temp)

    def set_fan(self, cmd):
        assert self.state != State.START
        fan_lv = self.cmd_to_bits('fan', cmd)
        self.set_cmd(HEAD_FAN, self.mode, fan_lv, self.temp1)

    def sensor_query(self, id):
        assert id < 0xff
        header = [self.addr, 0x00, 0x17]
        payload = [0x08, 0x80]
        payload += [0xef, 0x00, 0x2c, 0x08, 0x00]
        payload.append(id)
        p = self.gen_pkt(header, payload)
        self.send_query1(p)

    def extra_query(self, id):
        assert id in [0x94, 0x9e]
        header = [self.addr, 0x00, 0x15]
        payload = [0x08, 0xe8]
        payload += [0x00, 0x01, 0x00]
        payload.append(id)
        p = self.gen_pkt(header, payload)
        self.send_query2(p)

    def power_query(self):
        self.extra_query(0x94)

    def filter_query(self):
        self.extra_query(0x9e)

    def set_save(self, cmd):
        assert self.state != State.START
        bits = self.cmd_to_bits('save', cmd)
        header = [self.addr, 0xfe, 0x10]
        payload = [0x00, 0x4c]
        a = 0b100000 | self.mode
        payload.append(a)
        a = bits << 4 | 0b1000 | self.fan_lv
        payload.append(a)
        a = (self.temp1 + 35) << 1
        payload.append(a)
        p = self.gen_pkt(header, payload)
        self.send_sv(p)

    def reset_filter(self):
        header = [self.addr, 0xfe, 0x10]
        payload = [0x00, 0x4b]
        p = self.gen_pkt(header, payload)
        self.send_flt(p)

    def toggle_humid(self):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x52, 0x01]
        p = self.gen_pkt(header, payload)
        self.send_hmd(p)

    def set_humid(self, cmd):
        if self.mode not in [0b001, 0b101]:
            return
        value = self.cmd_to_bits('humid', cmd)
        self.hmd_queue.append(value)
        if self.state == State.IDLE:
            self.machine.humid(value=self.hmd_queue.pop(0))