
class AutoSessionTemperatureProfile:
    """
    Manages temperature profiles with time-based waypoints.
    Format: "0:100,5:100,15:150,30:50"
    Time is in seconds, temperature in Celsius.
    Interpolates linearly between waypoints.
    """
    
    def __init__(self, profile_string):
        """
        Initialize profile from string format.
        Args:
            profile_string: "time_seconds:temp_celsius,time_seconds:temp_celsius,..." format
        """
        self.waypoints = []  # List of (time_ms, temperature) tuples
        self.parse(profile_string)
    
    def parse(self, profile_string):
        """Parse profile string into waypoints."""
        self.waypoints = []
        if not profile_string or not profile_string.strip():
            return
        
        try:
            pairs = profile_string.split(',')
            for pair in pairs:
                time_sec, temp = pair.split(':')
                time_sec = int(time_sec.strip())
                temp = int(temp.strip())
                time_ms = time_sec * 1000  # Convert seconds to milliseconds
                self.waypoints.append((time_ms, temp))
            
            # Sort by time to ensure chronological order
            self.waypoints.sort(key=lambda x: x[0])
        except Exception as e:
            print(f"Error parsing temperature profile: {e}")
            self.waypoints = []
    
    def get_setpoint_at_elapsed_time(self, elapsed_ms):
        """
        Get interpolated setpoint at given elapsed time.
        Args:
            elapsed_ms: Elapsed time in milliseconds since profile start
        Returns:
            Interpolated temperature value, or None if profile is invalid/expired
        """
        if not self.waypoints:
            print(f"DEBUG: No waypoints in profile")
            return None
        
        # Before first waypoint, use first temperature
        if elapsed_ms <= self.waypoints[0][0]:
            print(f"DEBUG: Before first waypoint - elapsed={elapsed_ms}, first_waypoint={self.waypoints[0]}, returning temp={self.waypoints[0][1]}")
            return self.waypoints[0][1]
        
        # After last waypoint, return None (profile finished)
        if elapsed_ms > self.waypoints[-1][0]:
            print(f"DEBUG: After last waypoint - elapsed={elapsed_ms}, last_waypoint={self.waypoints[-1]}")
            return None
        
        # Find surrounding waypoints for interpolation
        for i in range(len(self.waypoints) - 1):
            time1, temp1 = self.waypoints[i]
            time2, temp2 = self.waypoints[i + 1]
            
            if time1 <= elapsed_ms <= time2:
                # Linear interpolation between waypoints
                if time2 == time1:  # Avoid division by zero
                    print(f"DEBUG: Zero time delta - returning temp1={temp1}")
                    return temp1
                
                fraction = (elapsed_ms - time1) / (time2 - time1)
                interpolated = temp1 + (temp2 - temp1) * fraction
                print(f"DEBUG: Interpolating - elapsed={elapsed_ms}, between {time1}ms({temp1}C) and {time2}ms({temp2}C), fraction={fraction}, result={interpolated}C")
                return interpolated
        
        # Shouldn't reach here if logic is correct
        print(f"DEBUG: Reached end - returning last waypoint temp={self.waypoints[-1][1]}")
        return self.waypoints[-1][1]
    
    def get_duration_ms(self):
        """Get total duration of profile in milliseconds."""
        if not self.waypoints:
            return 0
        return self.waypoints[-1][0]
    
    def is_valid(self):
        """Check if profile has valid waypoints."""
        return len(self.waypoints) > 0
    
    def __str__(self):
        """String representation for debugging."""
        waypoint_strs = [f"{time_ms//1000}sec:{temp}C" for time_ms, temp in self.waypoints]
        return f"TemperatureProfile({', '.join(waypoint_strs)})"

