# SSD1306 128x32 display driver
# Override show_screen_* methods here to customize for this display

class SSD1306_128x32_Driver:
    """Driver mixin for SSD1306 128x32 display.
    
    Override any show_screen_* method here to customize for this display.
    Leave empty to use all defaults from DisplayManager.
    """
    width = 128
    height = 32
