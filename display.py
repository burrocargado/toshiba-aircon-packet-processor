import curses

class Display():
    def __init__(self):
        stdscr = curses.initscr()

        curses.noecho()
        curses.cbreak()
        curses.curs_set(False)
        stdscr.keypad(True)

        stdscr.clear()
        stdscr.border()
        stdscr.refresh()
        stdscr.nodelay(True)

        begin_x = 1; begin_y = 1
        height = 16; width = 70
        win_raw = curses.newwin(height, width, begin_y, begin_x)
        win_raw.border()
        win_raw.refresh()

        begin_x = 71; begin_y = 1
        height = 16; width = 50
        win_state = curses.newwin(height, width, begin_y, begin_x)
        win_state.refresh()
        win_state.border()
        win_state.refresh()

        self.stdscr = stdscr
        self.win_raw = win_raw
        self.win_state = win_state
    
    def print_raw(self, line):
        win_raw = self.win_raw
        win_raw.addstr(1, 2, line)
        win_raw.border()
        win_raw.refresh()
        win_raw.insertln()
    
    def add_stat(self, r, txt):
        self.win_state.addstr(r, 2, txt)
    
    def disp_stat(self):
        self.win_state.border()
        self.win_state.refresh()
    
    def getch(self):
        return self.stdscr.getch()
