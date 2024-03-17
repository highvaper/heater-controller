from machine import Timer

class CustomTimer:
    # Need to extend existing Timer function to know if its running or not
    # Stops timer being started multiple times in case of some recusion or help catch other bugs 
    def __init__(self, period, mode, callback):
        self.timer = Timer(-1)
        self.is_running = False
        self.period = period
        self.mode = mode
        self.callback = callback

    def start(self):
        if not self.is_running:
            self.timer.init(period=self.period, mode=self.mode, callback=self.callback)
            self.is_running = True
            #print(f"{self.callback.__name__} timer started.")
        else:
            raise RuntimeError(f"{self.callback.__name__} timer is already running. Cannot start again without stopping first.")

    def stop(self):
        if self.is_running:
            self.timer.deinit()
            self.is_running = False
            #print(f"{self.callback.__name__} timer stopped.")
        else:
            raise RuntimeError(f"{self.callback.__name__} timer is not running. Cannot stop without starting first.")

    def is_timer_running(self):
        return self.is_running
