import curses

class Display():
    def __init__(self):
        stdscr = curses.initscr()

        curses.curs_set(False)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)

        stdscr.clear()
        #stdscr.border()
        #stdscr.refresh()
        stdscr.nodelay(True)

        begin_x = 0; begin_y = 0
        height = 17; width = 60
        win_raw = curses.newwin(height, width, begin_y, begin_x)
        #win_raw = stdscr.subwin(height, width, begin_y, begin_x)
        #win_raw.border()
        #win_raw.noutrefresh()

        #begin_x = 61; begin_y = 0
        begin_x = 60; begin_y = 0
        height = 17; width = 60
        win_state = curses.newwin(height, width, begin_y, begin_x)
        #win_state = stdscr.subwin(height, width, begin_y, begin_x)
        #win_state.refresh()
        #win_state.border()
        #win_state.noutrefresh()
        #win_raw.refresh()
        #win_state.refresh()
        #curses.doupdate()

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
        #self.win_raw.move(1, 1)
        #self.win_raw.addstr(1, 1, ' ')
        #self.win_raw.move(1,1)
        #self.win_raw.border()
        #self.win_raw.noutrefresh()
        #self.win_raw.insertln()
        #win_raw.refresh()
        #win_raw.insertln()
        #curses.curs_set(False)
    
    def add_stat(self, r, txt):
        self.win_state.addstr(r, 2, txt)
        #self.win_raw.move(1, 1)
        #self.win_raw.addstr(1, 1, ' ')
        #self.win_state.move(0,0)
        #self.win_state.move(1,1)
        #self.win_state.border()
        #self.win_state.noutrefresh()
    
    #def disp_stat(self):
    #    self.win_state.border()
    #    self.win_state.refresh()
    #    #curses.curs_set(False)
    
    def loop(self):
        #self.win_raw.move(0,0)
        #self.win_raw.addch(' ')
        #self.win_state.move(0,0)
        #self.win_raw.addch(' ')
        self.win_raw.border()
        self.win_state.border()
        #curses.setsyx(0, 0)
        #self.win_raw.cursyncup()
        #self.win_state.cursyncup()
        
        self.win_raw.noutrefresh()
        self.win_state.noutrefresh()
        
        #self.stdscr.refresh()
        #self.win_raw.refresh()
        #self.win_state.refresh()
        
        #self.stdscr.move(16, 120-3)
        #self.stdscr.addstr(f'{self.ctr%1000:03d}')

        # avoid cursor displayed at random position
        self.stdscr.move(16, 120)
        if self.ctr & 1 == 0:
            self.stdscr.addch('.')
        else:
            self.stdscr.addch(' ')
        #self.stdscr.noutrefresh()
        curses.doupdate()
        self.ctr += 1
    
    def getch(self):
        c = self.stdscr.getch()
        #curses.curs_set(False)
        #self.win_state.addstr(1, 55, "x")
        return c
