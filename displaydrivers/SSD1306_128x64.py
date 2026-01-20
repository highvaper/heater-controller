# SSD1306 128x64 display driver
# Override show_screen_* methods here to customize for this display

class SSD1306_128x64_Driver:
    """Driver mixin for SSD1306 128x64 display.
    
    Override any show_screen_* method here to customize for this display.
    Example: Can show more lines on home screen due to taller display.
    """
    width = 128
    height = 64

