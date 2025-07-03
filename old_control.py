"""
Minimal RevPi Control System with Calibration
=============================================

Simple control system:
1. Read analog input and convert to mm using calibration
2. Get user target (in mm)
3. Move to target with PID control
4. Stop when within 0.5mm of target

Author: Minimal control system with calibration
"""

import revpimodio2
from simple_pid import PID 
from calibration import load_calibration, analog_to_mm

def main():
    # Load calibration data
    analogs_mv, positions_mm = load_calibration()
    min_pos, max_pos = positions_mm.min(), positions_mm.max()
    
    # Connect to RevPi
    rpi = revpimodio2.RevPiModIO(autorefresh=True)
    print("Connected to RevPi")
    print(f"Position range: {min_pos:.1f} - {max_pos:.1f} mm")

    pid = PID(Kp=100, Ki=0.01, Kd=0.02, sample_time=0.02)

    try:
        while True:
            # Get target from user
            target_mm = float(input(f"Enter target ({min_pos:.1f}-{max_pos:.1f} mm): "))
            print(f"Moving to {target_mm:.1f} mm...")
            
            pid.setpoint = target_mm
            pid.output_limits = (-500, 500)
            
            while True:
                # Read current position
                current_mv = rpi.io.AnalogInput_1.value
                current_mm = analog_to_mm(current_mv, analogs_mv, positions_mm)

                # Update PID controller
                output = pid(current_mm)
                if abs(current_mm - target_mm) < 0.05:  # Within 0.05mm
                    # Stop - brake
                    rpi.io.PwmDutycycle_2.value = 0
                    print(f"Reached target: {current_mv} mV -> {current_mm:.2f} mm")
                    break
                
                if output > 0:
                    # Move forward
                    rpi.io.DigitalOutput_1.value = 0  # DIR Low = forward
                    rpi.io.PwmDutycycle_2.value = int(output)
                else:
                    # Move backward
                    rpi.io.DigitalOutput_1.value = 1  # DIR High = backward
                    rpi.io.PwmDutycycle_2.value = int(abs(output))
                
                # Show status
                print(f"Command: {output:.1f}, Current: {current_mm:.2f} mm, Target: {target_mm:.1f} mm")

            
    except KeyboardInterrupt:
        print("\n\nStopped by user (Ctrl+C)")
            
if __name__ == "__main__":
    main()
