from enum import IntEnum
from collections import namedtuple
import time
import struct

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
        return text

CmdSetItem = namedtuple('CmdSetItem', 'bits cmd text')
CommandSets = namedtuple('CommandSets', 'power mode fan save')
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
        self.state = State.START
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

        self.c_time = None
        self.q1_time = None
        self.q2_time = None
        self.sv_time = None
        self.flt_time = None

    def send_cmd(self, p):
        if self.transmit is None:
            return
        self.c_queue.append(p)
        if self.state == State.IDLE:
            self.state = State.CMD
            self.transmit(self.c_queue[0])
            self.c_time = time.time()

    def send_query1(self, p):
        if self.transmit is None:
            self.sensor[p[11]] = 0
            return
        self.q1_queue.append(p)
        if self.state == State.IDLE:
            self.state = State.QUERY1
            self.transmit(self.q1_queue[0])
            self.q1_time = time.time()

    def send_query2(self, p):
        if self.transmit is None:
            return
        self.q2_queue.append(p)
        if self.state == State.IDLE:
            self.state = State.QUERY2
            self.transmit(self.q2_queue[0])
            self.q2_time = time.time()

    def send_sv(self, p):
        if self.transmit is None:
            return
        self.sv_queue.append(p)
        if self.state == State.IDLE:
            self.state = State.SSAVE
            self.transmit(self.sv_queue[0])
            self.sv_time = time.time()

    def send_flt(self, p):
        if self.transmit is None:
            return
        self.flt_queue.append(p)
        if self.state == State.IDLE:
            self.state = State.FILTER
            self.transmit(self.flt_queue[0])
            self.flt_time = time.time()

    def loop(self):
        if self.state == State.IDLE:
            if self.c_queue:
                self.state = State.CMD
                self.transmit(self.c_queue[0])
                self.c_time = time.time()
            elif self.sv_queue:
                self.state = State.SSAVE
                self.transmit(self.sv_queue[0])
                self.sv_time = time.time()
            elif self.flt_queue:
                self.state = State.FILTER
                self.transmit(self.flt_queue[0])
                self.flt_time = time.time()
            elif self.q1_queue:
                self.state = State.QUERY1
                self.transmit(self.q1_queue[0])
                self.q1_time = time.time()
            elif self.q2_queue:
                self.state = State.QUERY2
                self.transmit(self.q2_queue[0])
                self.q2_time = time.time()
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
        elif self.state == State.CMD:
            if time.time() - self.c_time > RETRY_WAIT:
                # no ack, retry
                self.transmit(self.c_queue[0])
                self.c_time = time.time()
        elif self.state == State.SSAVE:
            if (self.sv_queue[0][7] >> 4) & 0b11 == self.save:
                self.sv_queue.pop(0)
                self.state = State.IDLE
            elif time.time() - self.sv_time > RETRY_WAIT:
                # save mode not set, retry
                self.transmit(self.sv_queue[0])
                self.sv_time = time.time()
        elif self.state == State.FILTER:
            if self.filter == 0:
                self.flt_queue.pop(0)
                self.state = State.IDLE
            elif time.time() - self.flt_time > RETRY_WAIT:
                # filter not reset, retry
                self.transmit(self.flt_queue[0])
                self.flt_time = time.time()
        elif self.state == State.QUERY1:
            if time.time() - self.q1_time > RETRY_WAIT:
                # no reply, retry
                self.transmit(self.q1_queue[0])
                self.q1_time = time.time()
        elif self.state == State.QUERY2:
            if time.time() - self.q2_time > RETRY_WAIT:
                # no reply, retry
                self.transmit(self.q2_queue[0])
                self.q2_time = time.time()

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
                self.state = State.IDLE
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
                self.c_queue.pop(0)
                self.state = State.IDLE
        if p[2] == 0x1a and p[4] == 0x80 and p[5] == 0xef:
            if self.state == State.QUERY1:
                p0 = self.q1_queue.pop(0)
                if p[8] == 0x2c:
                    self.sensor[p0[11]] = struct.unpack('>h', bytes(p[9:11]))[0]
                else:
                    self.sensor[p0[11]] = None
                self.state = State.IDLE
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xe8:
            if self.state == State.QUERY2:
                p0 = self.q2_queue.pop(0)
                self.extra[p0[9]] = p[6:11]
                if p0[9] == 0x94:
                    self.pwr_lv1 = p[9]
                    self.pwr_lv2 = p[10]
                elif p0[9] == 0x9e:
                    self.filter_time = (p[9] << 8) + p[10]
                self.state = State.IDLE

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
