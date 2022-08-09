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

        begin_x = 0; begin_y = 0
        height = 17; width = 60
        win_raw = curses.newwin(height, width, begin_y, begin_x)

        begin_x = 60; begin_y = 0
        height = 17; width = 60
        win_state = curses.newwin(height, width, begin_y, begin_x)

        self.stdscr = stdscr
        self.win_raw = win_raw
        self.win_state = win_state

        self.ctr = 0
    
    def quit(self):
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    def print_raw(self, line):
        self.win_raw.move(1,2)
        self.win_raw.insertln()
        self.win_raw.addstr(1, 2, line)
    
    def add_stat(self, r, txt):
        self.win_state.addstr(r, 2, txt)
    
    def loop(self):
        self.win_raw.border()
        self.win_state.border()
        
        self.win_raw.noutrefresh()
        self.win_state.noutrefresh()
        
        # avoid cursor displayed at random position
        self.stdscr.move(16, 120)
        if self.ctr & 1 == 0:
            self.stdscr.addch('.')
        else:
            self.stdscr.addch(' ')
        curses.doupdate()
        self.ctr += 1
    
    def getch(self):
        c = self.stdscr.getch()
        return c
