import curses


class Display():
    def __init__(self):
        stdscr = curses.initscr()

        curses.curs_set(False)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)

        stdscr.clear()
        stdscr.nodelay(True)

        begin_x = 0
        begin_y = 0
        height = 17
        width = 60
        win_raw = curses.newwin(height, width, begin_y, begin_x)

        begin_x = 60
        begin_y = 0
        height = 17
        width = 60
        win_state = curses.newwin(height, width, begin_y, begin_x)

        self.stdscr = stdscr
        self.win_raw = win_raw
        self.win_state = win_state

    def quit(self):
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    def print_raw(self, line):
        self.win_raw.move(1, 2)
        self.win_raw.insertln()
        self.win_raw.addstr(1, 2, line)

    def add_stat(self, r, txt):
        self.win_state.addstr(r, 2, txt)

    def disp_packet(self, packet):
        line = ''
        for c in packet[:-1]:
            line += f'{c:02X} '
        c = packet[-1]
        line += f'{c:02X}'
        self.print_raw(line)

    def on_rx_packet(self, packet, ac):
        self.disp_packet(packet)

        if ac.params:
            line = 'Params: '
            for c in ac.params:
                line += f' {c:02X}'
            self.add_stat(3, line)

    def disp_state_machine(self, ac):
        line = 'State:   '
        line += str(ac.state).capitalize()
        self.add_stat(15, f'{line:36s}')

    def key_check(self, ac):
        c = self.getch()
        if c == ord('q'):
            self.quit()
            return True
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
            ac.set_power('1')
        elif c == ord('2'):
            ac.set_power('0')
        elif c == ord('3'):
            ac.set_save('S')
        elif c == ord('4'):
            ac.set_save('R')
        elif c == ord('5'):
            ac.set_humid('1')
        elif c == ord('6'):
            ac.set_humid('0')
        # elif c == ord('0'):
        #     ac.reset_filter()
        elif c == ord('e'):
            temp = ac.temp1
            if temp > ac.MIN_TMP:
                temp -= 1
                ac.set_temp(temp)
        elif c == ord('r'):
            temp = ac.temp1
            if temp < ac.MAX_TMP:
                temp += 1
                ac.set_temp(temp)
        return False

    def disp_sensors(self, ac):
        y = 4
        line = 'Sensors: '
        line += str({k: ac.sensor[k] for k in [0x02, 0x03, 0x04, 0x65, 0x6a]})
        self.add_stat(y, f'{line:55s}')
        y += 1
        line = 'Sensors: '
        line += str({k: ac.sensor[k] for k in [0x60, 0x61, 0x62, 0x63]})
        self.add_stat(y, f'{line:55s}')
        y += 1
        line = 'PwrLv:   '
        line += f'{ac.pwr_lv1:02d}, {ac.pwr_lv2:03d}'
        self.add_stat(y, f'{line:30s}')
        y += 1
        line = 'Filter:  '
        line += '{:04d} H'.format(ac.filter_time)
        self.add_stat(y, f'{line:30s}')

    def disp_status(self, ac):
        line = 'State1: '
        for c in ac.state1:
            line += f' {c:02X}'
        self.add_stat(1, line)
        line = 'State2: '
        if ac.state2:
            for c in ac.state2:
                line += f' {c:02X}'
        self.add_stat(2, line)

        y = 8
        self.add_stat(
            y, f"Power:   {ac.bits_to_text('power', ac.power).title():3s}"
        )
        y += 1
        self.add_stat(
            y, f"Mode:    {ac.bits_to_text('mode', ac.mode).title():9s}"
        )
        y += 1
        self.add_stat(
            y, f"FanLv:   {ac.bits_to_text('fan', ac.fan_lv).title():4s}"
        )
        y += 1
        self.add_stat(y, f'SetTemp: {ac.temp1:2d}')
        y += 1
        self.add_stat(y, f'Temp:    {ac.temp2:2d}')
        y += 1
        self.add_stat(
            y, f"Save:    {ac.bits_to_text('save', ac.save).title():3s}"
        )

        txt = 'Ventilation' if ac.vent else ''
        self.win_state.addstr(9, 47, f'{txt:11s}')
        txt = 'Humidifier' if ac.humid else ''
        self.win_state.addstr(10, 47, f'{txt:10s}')
        txt = 'Filter' if ac.filter else ''
        self.win_state.addstr(11, 47, f'{txt:6s}')
        txt = 'Cleaning' if ac.clean else ''
        self.win_state.addstr(12, 47, f'{txt:8s}')

    def send_status(self, p, status):
        if status == 0:
            line = 'Sent:    '
        else:
            line = 'Failed:  '
        for a in p:
            line += f'{a:02X} '
        self.add_stat(14, f'{line:55s}')

    def loop(self, ac):
        self.disp_state_machine(ac)

        self.win_raw.border()
        self.win_state.border()

        self.win_raw.noutrefresh()
        self.win_state.noutrefresh()

        curses.doupdate()

        return self.key_check(ac)

    def getch(self):
        c = self.stdscr.getch()
        return c
