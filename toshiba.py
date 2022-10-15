"""
Packet processor for Toshiba air conditioner
with wired remote controller connected to AB bus.
Tested with NTS-F1403Y1 indoor unit (residential central AC).

!!! SOME MODIFICATIONS MAY BE REQUIRED        !!!
!!! FOR USE WITH OTHER TYPES OF INDOOR UNITS. !!!

"""
from enum import IntEnum
from collections import namedtuple
import time
import struct
from logging import getLogger
#from transitions import Machine
from transitions.extensions import GraphMachine as Machine
from transitions.extensions.states import add_state_features, Timeout

RETRY_WAIT = 1.0 # timeout in seconds for command or query reply
QUERY_INTERVAL = 60.0

logger = getLogger(__name__)

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
class CustomMachine(Machine):
    pass

states = [
    State.START,
    State.IDLE,
    {
        'name': State.CMD, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.QUERY1, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.QUERY2, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.SSAVE, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.FILTER, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.HUMID, 'timeout': RETRY_WAIT,
        'on_timeout': 'hmd_timeout', 'on_exit': 'hmd_exit'
    },
    {
        'name': State.HMDTGL, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
]

class StateMachine(object):

    def __init__(self, ac):
        self.ac = ac
        self.callback = None
        self.hmd = None

        self.machine = CustomMachine(
            model=self, states=states, initial=State.START,
            auto_transitions=False, send_event=True
        )
        self.machine.add_transition(
            trigger='idle',
            source=[
                State.START, State.CMD, State.QUERY1, State.QUERY2,
                State.SSAVE, State.FILTER, State.HUMID
            ],
            dest=State.IDLE,
        )
        self.machine.add_transition(
            trigger='cmd', source=State.IDLE, dest=State.CMD,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='query1', source=State.IDLE, dest=State.QUERY1,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='query2', source=State.IDLE, dest=State.QUERY2,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='ssave', source=State.IDLE, dest=State.SSAVE,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='filter', source=State.IDLE, dest=State.FILTER,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='humid',
            source=[State.IDLE, State.HMDTGL], dest=State.HUMID,
            after='set_humid', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='hmdtgl', source=State.HUMID, dest=State.HMDTGL,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='self',
            source=[
                State.CMD, State.QUERY1, State.QUERY2,
                State.SSAVE, State.FILTER, State.HMDTGL
            ],
            dest='=',
        )

    def rx_only(self, _event):
        return self.ac.transmit is None

    def send_packet(self, event):
        logger.debug('send_packet')
        self.callback = event.kwargs.get('callback')
        func, args = self.callback
        func(*args)

    def send_timeout(self, _event):
        logger.warning('send_timeout')
        func, args = self.callback
        func(*args)
        # pylint: disable=no-member
        self.self()

    def send_exit(self, event):
        if event.transition.dest != event.transition.source:
            self.callback = None

    def set_humid(self, event):
        hmd = event.kwargs.get('value')
        if hmd is not None:
            if self.ac.humid == hmd:
                # pylint: disable=no-member
                self.idle()
            else:
                self.hmd = hmd
                self.ac.toggle_humid()

    def hmd_timeout(self, _event):
        self.ac.toggle_humid()

    def hmd_exit(self, event):
        if event.transition.dest == State.IDLE.name:
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
        self.queue = []
        self.tx_packet = None
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
        # pylint: disable=no-member
        return self.machine.state

    def loop(self):
        if self.state == State.IDLE:
            if self.queue:
                func, kwargs = self.queue.pop(0)
                func(**kwargs)
            elif self.update:
                if self.update_cb is not None:
                    # pylint: disable=not-callable
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
            p0 = self.tx_packet
            if (p0[7] >> 4) & 0b11 == self.save:
                # pylint: disable=no-member
                self.machine.idle()
        elif self.state == State.FILTER:
            if self.filter == 0:
                # pylint: disable=no-member
                self.machine.idle()
        elif self.state == State.HUMID:
            if self.humid == self.machine.hmd:
                # pylint: disable=no-member
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
                # pylint: disable=no-member
                self.machine.idle()
            ext = True
        elif p[2] == 0x1c:
            payload = p[6:12]
            self.state2 = payload
            ext = False
        if p[2] == 0x58 or p[2] == 0x1c:
            self.power = payload[0] & 0b1
            self.mode = (payload[0] >> 5) & 0b111
            self.save = (payload[0] >> 3) & 0b11
            self.clean = (payload[1] >> 2) & 0b1
            self.fan_lv = (payload[1] >> 5) & 0b111
            self.filter = (payload[2] >> 7) & 0b1
            self.vent = (payload[2] >> 2) & 0b1
            self.humid = (payload[2] >> 1) & 0b1
            self.temp1 = (payload[4] >> 1) - 35
            if self.status_cb:
                # pylint: disable=not-callable
                self.status_cb(ext)

    def parse_params(self, p):
        if p[2] == 0x11:
            self.params = p[6:8]
    
    def parse_reply(self, p):
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xa1:
            if self.state == State.CMD:
                # pylint: disable=no-member
                self.machine.idle()
            elif self.state == State.HMDTGL:
                # pylint: disable=no-member
                self.machine.humid()
        if p[2] == 0x1a and p[4] == 0x80 and p[5] == 0xef:
            if self.state == State.QUERY1:
                p0 = self.tx_packet
                if p[8] == 0x2c:
                    self.sensor[p0[11]] = struct.unpack('>h', bytes(p[9:11]))[0]
                else:
                    self.sensor[p0[11]] = None
                # pylint: disable=no-member
                self.machine.idle()
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xe8:
            if self.state == State.QUERY2:
                p0 = self.tx_packet
                self.extra[p0[9]] = p[6:11]
                if p0[9] == 0x94:
                    self.pwr_lv1 = p[9]
                    self.pwr_lv2 = p[10]
                elif p0[9] == 0x9e:
                    self.filter_time = (p[9] << 8) + p[10]
                # pylint: disable=no-member
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
        logger.info('set_power: %s', cmd)
        kwargs = {'callback': (self.set_power_, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def set_power_(self, cmd):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x41]
        byte = 0x02 | self.cmd_to_bits('power', cmd)
        payload.append(byte)
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def set_mode(self, cmd):
        logger.info('set_mode: %s', cmd)
        kwargs = {'callback': (self.set_mode_, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def set_mode_(self, cmd):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x42]
        byte = self.cmd_to_bits('mode', cmd)
        payload.append(byte)
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

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
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def set_temp(self, temp):
        logger.info('set_temp: %s', temp)
        kwargs = {'callback': (self.set_temp_, (temp,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def set_temp_(self, temp):
        assert self.state != State.START
        modes = ['heat', 'dry', 'cool', 'auto heat', 'auto cool']
        if self.bits_to_text('mode', self.mode) not in modes:
            # pylint: disable=no-member
            self.machine.idle()
            return
        self.set_cmd(0b01, self.mode, self.fan_lv, temp)

    def set_fan(self, cmd):
        logger.info('set_fan: %s', cmd)
        kwargs = {'callback': (self.set_fan_, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def set_fan_(self, cmd):
        assert self.state != State.START
        fan_lv = self.cmd_to_bits('fan', cmd)
        self.set_cmd(0b10, self.mode, fan_lv, self.temp1)

    def sensor_query(self, qid):
        logger.debug('sendor_query: %s', qid)
        self.sensor[qid] = 0
        kwargs = {'callback': (self.sensor_query_, (qid,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.query1, kwargs))

    def sensor_query_(self, qid):
        assert qid < 0xff
        header = [self.addr, 0x00, 0x17]
        payload = [0x08, 0x80]
        payload += [0xef, 0x00, 0x2c, 0x08, 0x00]
        payload.append(qid)
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def extra_query(self, qid):
        logger.debug('extra_query: %s', qid)
        self.extra[qid] = 0
        kwargs = {'callback': (self.extra_query_, (qid,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.query2, kwargs))

    def extra_query_(self, qid):
        assert qid in [0x94, 0x9e]
        header = [self.addr, 0x00, 0x15]
        payload = [0x08, 0xe8]
        payload += [0x00, 0x01, 0x00]
        payload.append(qid)
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def power_query(self):
        self.extra_query(0x94)

    def filter_query(self):
        self.extra_query(0x9e)

    def set_save(self, cmd):
        logger.info('set_save: %s', cmd)
        kwargs = {'callback': (self.set_save_, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.ssave, kwargs))

    def set_save_(self, cmd):
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
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def reset_filter(self):
        logger.info('reset_filter')
        kwargs = {'callback': (self.reset_filter_, ())}
        # pylint: disable=no-member
        self.queue.append((self.machine.filter, kwargs))

    def reset_filter_(self):
        header = [self.addr, 0xfe, 0x10]
        payload = [0x00, 0x4b]
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def toggle_humid(self):
        logger.info('toggle_humid')
        modes = ['heat', 'auto heat']
        if self.bits_to_text('mode', self.mode) not in modes:
            # pylint: disable=no-member
            self.machine.idle()
            return
        if self.bits_to_text('power', self.power) == 'off':
            # pylint: disable=no-member
            self.machine.idle()
            return
        kwargs = {'callback': (self.toggle_humid_, ())}
        # pylint: disable=no-member
        self.machine.hmdtgl(**kwargs)

    def toggle_humid_(self):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x52, 0x01]
        p = self.gen_pkt(header, payload)
        self.tx_packet = p
        # pylint: disable=not-callable
        self.transmit(p)

    def set_humid(self, cmd):
        logger.info('set_humid: %s', cmd)
        kwargs = {'cmd': cmd}
        self.queue.append((self.set_humid_, kwargs))

    def set_humid_(self, cmd):
        assert self.state != State.START
        value = self.cmd_to_bits('humid', cmd)
        # pylint: disable=no-member
        self.machine.humid(value=value)
