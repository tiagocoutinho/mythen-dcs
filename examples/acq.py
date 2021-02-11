import curses

import typer
from sparklines import sparklines

from mythendcs.core import mythen_for_url, gen_acquisition


class Plot:

    def __init__(self, x0, y0, width, height, attrs=0):
        self.wnd = curses.newwin(height, width, y0, x0)
        self.attrs = attrs

    def set_curve(self, frame, attrs=None):
        attrs = self.attrs if attrs is None else attrs
        n = len(frame)
        height, width = self.wnd.getmaxyx()
        while n % width:
            width -= 1
        data = frame.reshape((width, -1))
        data = data.mean(1)
        graph = sparklines(
            data, num_lines=height, minimum=data.min(), maximum=data.max()
        )
        self.wnd.addstr(0, 0, "\n".join(graph))
        self.wnd.refresh()


class Label:

    def __init__(self, x0, y0, width, height=1, attrs=0):
        self.wnd = curses.newwin(height, width, y0, x0)
        self.attrs = attrs

    def set_text(self, text, attrs=None):
        attrs = self.attrs if attrs is None else attrs
        self.wnd.erase()
        self.wnd.addstr(0, 0, text, attrs)
        self.wnd.refresh()


class Toolbar(Label):

    def __init__(self, text="", attrs=curses.A_REVERSE):
        super().__init__(0, curses.LINES - 1, curses.COLS, attrs=attrs)
        self.set_text(text)

    def set_text(self, text, attrs=None):
        _, width = self.wnd.getmaxyx()
        super().set_text(text.ljust(width-1), attrs=attrs)


def run(stdscr, url, nb_frames, exposure_time):
    stdscr.clear()
    width, height = curses.COLS, curses.LINES
    label = Label(0, 0, width, 3)
    plot = Plot(0, 3, width, height - 4)
    toolbar = Toolbar("Preparing...", curses.A_REVERSE | curses.A_DIM)
    mythen = mythen_for_url(url)
    lf = len(str(nb_frames))
    template = "  min = {{}}\n  max = {{}}\nframe = {{:{}d}}/{}".format(lf, nb_frames)
    toolbar.set_text("Running!")
    try:
        for i, frame in enumerate(gen_acquisition(mythen, nb_frames, exposure_time)):
            dmin, dmax = frame.min(), frame.max()
            plot.set_curve(frame)
            msg = template.format(dmin, dmax, i+1)
            label.set_text(msg)
    finally:
        mythen.stop()

    toolbar.set_text('Finished! Press any key to exit')
    toolbar.wnd.getkey()


def main(url: str, nb_frames: int = 1, exposure_time: float = 1):
    curses.wrapper(run, url, nb_frames, exposure_time)


if __name__ == "__main__":
    typer.run(main)
