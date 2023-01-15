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
import threading
# import random  # for timeout retry test
from logging import getLogger
from transitions import Machine
# from transitions.extensions import GraphMachine as Machine
from transitions.extensions.states import add_state_features, Timeout

RETRY_WAIT = 1.0  # timeout in seconds for command or query reply
WSTAT_WAIT = 2.0
QUERY_INTERVAL = 60.0

logger = getLogger(__name__)
lock = threading.Lock()


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
    WSTAT = 9

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
        elif self.value == 9:
            text = 'waiting status update'
        return text


@add_state_features(Timeout)
class CustomMachine(Machine):
    pass


states = [
    {
        'name': State.START,
        'on_enter': 'start_enter', 'on_exit': 'start_exit'
    },
    State.IDLE,
    {
        'name': State.CMD, 'timeout': RETRY_WAIT,
        'on_timeout': 'send_timeout', 'on_exit': 'send_exit'
    },
    {
        'name': State.WSTAT, 'timeout': WSTAT_WAIT,
        'on_timeout': 'wstat_timeout', 'on_exit': 'wstat_exit'
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
        self.retry = 0

        self.machine = CustomMachine(
            model=self, states=states, initial=State.START,
            auto_transitions=False, send_event=True,
            before_state_change='state_change'
        )
        self.machine.add_transition(
            trigger='reset',
            source='*',
            dest=State.START,
        )
        self.machine.add_transition(
            trigger='idle',
            source=[
                State.START, State.CMD, State.WSTAT, State.QUERY1,
                State.QUERY2, State.SSAVE, State.FILTER, State.HUMID
            ],
            dest=State.IDLE,
        )
        self.machine.add_transition(
            trigger='cmd',
            source=[State.IDLE, State.WSTAT],
            dest=State.CMD,
            after='send_packet', unless='rx_only'
        )
        self.machine.add_transition(
            trigger='wstat', source=State.CMD, dest=State.WSTAT,
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

    def state_change(self, event):
        if callable(self.ac.state_cb):
            self.ac.state_cb(str(event.transition.dest).lower())

    def start_enter(self, _event):
        if callable(self.ac.start_cb):
            self.ac.start_cb()

    def start_exit(self, event):
        if event.transition.dest != event.transition.source:
            if callable(self.ac.ready_cb):
                self.ac.ready_cb()

    def rx_only(self, _event):
        return self.ac.transmit is None

    def send_packet(self, event):
        logger.debug('send_packet')
        self.retry = 0
        callback = event.kwargs.get('callback')
        if callback is not None:
            self.callback = event.kwargs.get('callback')
        func, args = self.callback
        try:
            func(*args)
        except Exception as e:
            logger.error('state machine packet send failed: %s', e)
            # pylint: disable=no-member
            self.idle()

    def send_timeout(self, _event):
        self.retry += 1
        if self.retry < 2:
            logger.debug('send_timeout retry: %d', self.retry)
        elif self.retry < 5:
            logger.warning('send_timeout retry: %d', self.retry)
        else:
            logger.error('send_timeout retry: %d, abort', self.retry)
            # pylint: disable=no-member
            self.idle()
            return
        func, args = self.callback
        func(*args)
        # pylint: disable=no-member
        self.self()

    def send_exit(self, event):
        if (event.transition.dest != event.transition.source
                and event.transition.dest != State.WSTAT.name):
            self.callback = None

    def wstat_timeout(self, _event):
        # pylint: disable=no-member
        self.cmd()

    def wstat_exit(self, event):
        if event.transition.dest != State.CMD.name:
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
        if event.transition.dest != State.HMDTGL.name:
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

CmdSetting = namedtuple('CmdSetting', 'var value')


class Aircon():

    MAX_TMP = 29
    MIN_TMP = 18

    def __init__(self, addr):
        self.transmit = None
        self.start_cb = None
        self.ready_cb = None
        self.state_cb = None
        self.update_cb = None
        self.status_cb = None
        self.update = False
        self.queue = []
        self.tx_waiting_packet = None
        self.tx_packet = None
        self.cmd_setting = None
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
        with lock:
            if self.tx_waiting_packet is not None:
                # if random.random() < 0.8:  # for timeout retry test
                #     self.transmit(self.tx_waiting_packet)
                self.transmit(self.tx_waiting_packet)
                self.tx_waiting_packet = None

        if self.state == State.IDLE:
            if self.queue:
                func, kwargs = self.queue.pop(0)
                try:
                    func(**kwargs)
                except Exception as e:
                    logger.error('executing queue failed: %s', e)
            elif self.update:
                if callable(self.update_cb):
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
        elif self.state == State.WSTAT:
            var = self.cmd_setting.var
            value = getattr(self, var)
            if (var == 'mode'
                    and self.bits_to_text('mode', value).startswith('auto')):
                value = self.cmd_to_bits('mode', 'A')
            if value == self.cmd_setting.value:
                # pylint: disable=no-member
                self.machine.idle()
                self.cmd_setting = None
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

    def _transmit(self, p):
        with lock:
            self.tx_waiting_packet = p

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
            if callable(self.status_cb):
                # pylint: disable=not-callable
                self.status_cb(ext)

    def parse_params(self, p):
        if p[2] == 0x11:
            self.params = p[6:8]

    def parse_reply(self, p):
        if p[2] == 0x18 and p[4] == 0x80 and p[5] == 0xa1:
            if self.state == State.CMD:
                # pylint: disable=no-member
                self.machine.wstat()
            elif self.state == State.HMDTGL:
                # pylint: disable=no-member
                self.machine.humid()
        if p[2] == 0x1a and p[4] == 0x80 and p[5] == 0xef:
            if self.state == State.QUERY1:
                p0 = self.tx_packet
                if p[8] == 0x2c:
                    self.sensor[p0[11]] = (
                        struct.unpack('>h', bytes(p[9:11]))[0]
                    )
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
        if cmd == '':
            raise ValueError(
                f'empty command: type: {cmdtype}'
            )
        bits = None
        for csi in getattr(CMDSETS, cmdtype):
            if csi.cmd == cmd:
                bits = csi.bits
                break
        if bits is None:
            raise ValueError(
                f'invalid command: type: {cmdtype}, value: {cmd}'
            )
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
        self.tx_packet = p
        return p

    def set_power(self, cmd):
        logger.info('set_power: %s', cmd)
        kwargs = {'callback': (self._set_power, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def _set_power(self, cmd):
        value = self.cmd_to_bits('power', cmd)
        self.cmd_setting = CmdSetting('power', value)
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x41]
        byte = 0x02 | value
        payload.append(byte)
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

    def set_mode(self, cmd):
        logger.info('set_mode: %s', cmd)
        kwargs = {'callback': (self._set_mode, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def _set_mode(self, cmd):
        value = self.cmd_to_bits('mode', cmd)
        self.cmd_setting = CmdSetting('mode', value)
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x42]
        payload.append(value)
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

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
        # pylint: disable=not-callable
        self._transmit(p)

    def set_temp(self, temp):
        logger.info('set_temp: %s', temp)
        kwargs = {'callback': (self._set_temp, (temp,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def _set_temp(self, temp):
        assert self.state != State.START
        if not isinstance(temp, int):
            raise TypeError('temp is not integer')
        if temp < self.MIN_TMP or temp > self.MAX_TMP:
            raise ValueError('invalid temp value')
        self.cmd_setting = CmdSetting('temp1', temp)
        modes = ['heat', 'dry', 'cool', 'auto heat', 'auto cool']
        if self.bits_to_text('mode', self.mode) not in modes:
            raise ValueError('set temp in invalid mode')
        self.set_cmd(0b01, self.mode, self.fan_lv, temp)

    def set_fan(self, cmd):
        logger.info('set_fan: %s', cmd)
        kwargs = {'callback': (self._set_fan, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.cmd, kwargs))

    def _set_fan(self, cmd):
        assert self.state != State.START
        value = self.cmd_to_bits('fan', cmd)
        self.cmd_setting = CmdSetting('fan_lv', value)
        self.set_cmd(0b10, self.mode, value, self.temp1)

    def sensor_query(self, qid):
        logger.debug('sendor_query: %s', qid)
        self.sensor[qid] = 0
        kwargs = {'callback': (self._sensor_query, (qid,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.query1, kwargs))

    def _sensor_query(self, qid):
        assert qid < 0xff
        header = [self.addr, 0x00, 0x17]
        payload = [0x08, 0x80]
        payload += [0xef, 0x00, 0x2c, 0x08, 0x00]
        payload.append(qid)
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

    def extra_query(self, qid):
        logger.debug('extra_query: %s', qid)
        self.extra[qid] = 0
        kwargs = {'callback': (self._extra_query, (qid,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.query2, kwargs))

    def _extra_query(self, qid):
        assert qid in [0x94, 0x9e]
        header = [self.addr, 0x00, 0x15]
        payload = [0x08, 0xe8]
        payload += [0x00, 0x01, 0x00]
        payload.append(qid)
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

    def power_query(self):
        self.extra_query(0x94)

    def filter_query(self):
        self.extra_query(0x9e)

    def set_save(self, cmd):
        logger.info('set_save: %s', cmd)
        kwargs = {'callback': (self._set_save, (cmd,))}
        # pylint: disable=no-member
        self.queue.append((self.machine.ssave, kwargs))

    def _set_save(self, cmd):
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
        # pylint: disable=not-callable
        self._transmit(p)

    def reset_filter(self):
        logger.info('reset_filter')
        kwargs = {'callback': (self._reset_filter, ())}
        # pylint: disable=no-member
        self.queue.append((self.machine.filter, kwargs))

    def _reset_filter(self):
        header = [self.addr, 0xfe, 0x10]
        payload = [0x00, 0x4b]
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

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
        kwargs = {'callback': (self._toggle_humid, ())}
        # pylint: disable=no-member
        self.machine.hmdtgl(**kwargs)

    def _toggle_humid(self):
        header = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x52, 0x01]
        p = self.gen_pkt(header, payload)
        # pylint: disable=not-callable
        self._transmit(p)

    def set_humid(self, cmd):
        logger.info('set_humid: %s', cmd)
        kwargs = {'cmd': cmd}
        self.queue.append((self._set_humid, kwargs))

    def _set_humid(self, cmd):
        assert self.state != State.START
        value = self.cmd_to_bits('humid', cmd)
        # pylint: disable=no-member
        self.machine.humid(value=value)

    def reset(self):
        self.queue = []
        self.machine.reset()
        self.tx_packet = None
        self.cmd_setting = None
