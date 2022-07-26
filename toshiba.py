from enum import IntEnum

HEAD_TMP = 0b01
HEAD_FAN = 0b10

class State(IntEnum):
    START = 0
    IDLE = 1
    CMD = 2
    SENSOR = 3

class Aircon():
    mode = [
        (0x01, 'H', 'heat'),
        (0x02, 'C', 'cool'),
        (0x03, 'F', 'fan'),
        (0x04, 'D', 'dry'),
        (0x05, 'A', 'auto heat'),
        (0x06, '', 'auto cool')
    ]
    fan = [
        (0b101, 'L', 'low'),
        (0b100, 'M', 'mid'),
        (0b011, 'H', 'high'),
        (0b010, 'A', 'auto')
    ]
    MAX_TMP = 29
    MIN_TMP = 18

    def __init__(self, addr):
        self.state = State.IDLE
        self.addr = addr
        self.state1 = None
        self.state2 = None
        self.params = None
        self.pong = None
        self.e8 = None
        self.power = None
        self.mode = None
        self.fan = None
        self.fan_lv = None
        self.temp1 = None
        self.temp2 = None
        self.save = None

        self.query_e8 = None
        self.reply_9e = None
        self.reply_94 = None
        self.reply = {}

        self.state = State.START

    def parse(self, p):
        if p[0] == 0x00:
            if p[1] == 0xfe:
                self.parse_broadcast(p)
            elif p[1] == 0x52:
                self.parse_params(p)
            elif p[1] == self.addr:
                self.parse_reply(p)
        elif p[0] == self.addr:
            if p[1] == 0x00:
                self.parse_remote(p)
    
    def parse_broadcast(self, p):
        if p[2] == 0x58:
            self.state1 = p[6:14]
            self.power = self.state1[0] & 0b1
            self.mode = (self.state1[0] >> 5) & 0b111
            self.fan = (self.state1[1] >> 2) & 0b1
            self.fan_lv = (self.state1[1] >> 5) & 0b111
            self.temp1 = (self.state1[4] >> 1) - 35
            self.temp2 = (self.state1[5] >> 1) - 35
            self.save = self.state1[7] & 0b1
            if self.state == State.START:
                self.state = State.IDLE
        if p[2] == 0x1c:
            self.state2 = p[6:12]
            self.power = self.state2[0] & 0b1
            self.mode = (self.state2[0] >> 5) & 0b111
            self.fan = (self.state2[1] >> 2) & 0b1
            self.fan_lv = (self.state2[1] >> 5) & 0b111
            self.temp1 = (self.state2[4] >> 1) - 35

    def parse_params(self, p):
        if p[2] == 0x11:
            self.params = p[6:8]
    
    def parse_reply(self, p):
        if self.query_e8 is None:
            return
        if p[2] == 0x18 and p[5] == 0x0c:
            self.pong = p[6:12]
        if p[2] == 0x18 and p[5] == 0xe8:
            self.e8 = p[6:11]
            if self.query_e8[3] == 0x94:
                self.reply_94 = self.e8
            elif self.query_e8[3] == 0x9e:
                self.reply_9e = self.e8
            key = ''
            for c in self.query_e8:
                key += f'{c:02X}'
            self.reply[key] = self.e8
            self.query_e8 = None

    def parse_remote(self, p):
        if p[2] == 0x15 and p[5] == 0xe8:
            self.query_e8 = p[6:10]
    
    def mode_text(self, val):
        text = f'{val:03b}'
        for d, cmd, label in self.__class__.mode:
            if d == val:
                text = label.title()
                break
        return '{:9s}'.format(text)

    def fan_text(self, val):
        text = f'{val:03b}'
        for d, cmd, label in self.__class__.fan:
            if d == val:
                text = label.title()
                break
        return '{:4s}'.format(text)

    def set_mode(self, mode):
        p = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x42]
        byte = None
        for d, cmd, label in self.__class__.mode:
            if cmd == mode:
                byte = d
                break
        assert byte is not None
        payload.append(byte)
        p.append(len(payload))
        p += payload
        ck = 0x0
        for c in p:
            ck ^= c
        p.append(ck)
        return p

    def set_cmd(self, head, mode, fan_lv, temp):
        assert mode is not None
        assert fan_lv is not None
        assert temp >= self.__class__.MIN_TMP#18
        assert temp <= self.__class__.MAX_TMP#29
        p = [self.addr, 0x00, 0x11]
        payload = [0x08, 0x4c]
        mode = mode & 0b111
        byte = head << 3 | mode
        payload.append(byte)
        fan_lv = fan_lv & 0b111
        byte = 0b111000 | fan_lv
        payload.append(byte)
        temp = (temp + 35) << 1
        payload.append(temp)
        p.append(len(payload))
        p += payload
        ck = 0x0
        for c in p:
            ck ^= c
        p.append(ck)
        return p

    def set_temp(self, temp):
        return self.set_cmd(HEAD_TMP, self.mode, self.fan_lv, temp)
    
    def set_fan(self, fan):
        fan_lv = None
        for d, cmd, label in self.__class__.fan:
            if cmd == fan:
                fan_lv = d
                break
        assert fan_lv is not None
        return self.set_cmd(HEAD_FAN, self.mode, fan_lv, self.temp1)

    def sensor_query(self, id):
        p = [self.addr, 0x00, 0x17]
        payload = [0x08, 0x80]
        payload += [0xef, 0x00, 0x2c, 0x08, 0x00]
        payload.append(id)
        p.append(len(payload))
        p += payload
        ck = 0x0
        for c in p:
            ck ^= c
        p.append(ck)
        return p
       