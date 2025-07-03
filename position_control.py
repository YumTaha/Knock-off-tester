"""
RevPiModIO2 closed-loop control for a DC-screw linear actuator
==============================================================

This new control system allows you to update speed/position while the motor is running.

"""

import time, signal, revpimodio2
from simple_pid import PID
import calibration

# ───────────────────────────────── Calibration ──────────────────────────────
STROKE_MM        = 300.0   # Full mechanical stroke in millimetres
RAW_MIN, RAW_MAX =  8200, 56800    # ADC at 0 mm and 300 mm (find experimentally)

analogs_mv, positions_mm = calibration.load_calibration()
def raw_to_mm(raw: int) -> float:
    return calibration.analog_to_mm(raw, analogs_mv, positions_mm)

# ───────────────────────────────── PID gains (start conservatively) ─────────
POS_KP, POS_KI, POS_KD = 20, 0.00, .5   # position loop → desired speed (mm/s)
# SPD_KP, SPD_KI, SPD_KD = 0.4, 3.0, 0.0    # speed    loop → PWM duty (%)

# MAX_SPEED_MM_S  = 40.0    # safety clamp
PWM_DEADBAND    = 10      # % below which duty is forced to zero
SOFT_MARGIN_MM  = 0.0     # change to keep clear of end-stops if needed

# ───────────────────────────────── RevPi I/O ────────────────────────────────
rpi = revpimodio2.RevPiModIO(autorefresh=True)  # ~10 ms default

IO_PWM        = rpi.io.PwmDutycycle_2
IO_DIR        = rpi.io.DigitalOutput_1
IO_POT_RAW    = rpi.io.AnalogInput_1

# ───────────────────────────────── PID objects ──────────────────────────────
pos_pid = PID(POS_KP, POS_KI, POS_KD, setpoint=0.0, sample_time=None)
pos_pid.output_limits = (-500, 500)

# ───────────────────────────────── Helpers ──────────────────────────────────
def clamp_mm(v):          # soft stroke limits
    return max(0.0 + SOFT_MARGIN_MM, min(v, STROKE_MM - SOFT_MARGIN_MM))

def move_to(target_mm):
    target_mm = clamp_mm(target_mm)
    pos_pid.setpoint      = target_mm

def set_max_pwm(max_pwm: int):
    """Set the maximum PWM duty cycle (0-1000) and ramp down to setpoint at 100/s."""
    if not (0 <= max_pwm <= 1000):
        raise ValueError("max_pwm must be between 0 and 1000")
    current_limit = abs(pos_pid.output_limits[1])
    if max_pwm < current_limit:
        # Ramp down in steps of 100 per second
        step = 100
        for pwm in range(current_limit, max_pwm, -step):
            pos_pid.output_limits = (-pwm, pwm)
            time.sleep(0.1)
    pos_pid.output_limits = (-max_pwm, max_pwm)
    print(f"[system] Max PWM set to {max_pwm} (0-1000)")

def stop():
    IO_PWM.value = 0
    IO_DIR.value = 0


# ───────────────────────────────── Main control loop ────────────────────────
LOOP_DT = rpi.cycletime  # ≈0.01 s
print(f"[system] Loop time: {LOOP_DT:.3f} ms")

_prev_pos = raw_to_mm(IO_POT_RAW.value)
_debug_counter = 0  # For periodic debug output

def controller(ct):
    LOOP_DT = rpi.cycletime
    global _prev_pos, _debug_counter

    # Read current position
    raw_value = IO_POT_RAW.value
    pos_mm = raw_to_mm(raw_value)
    
    # Calculate PID output
    signed_pwm = pos_pid(pos_mm)           # mm/s
    
    # Calculate velocity (for debugging)
    velocity_mm_s = (pos_mm - _prev_pos) / LOOP_DT if LOOP_DT > 0 else 0
    _prev_pos = pos_mm

    # Dead-band
    original_pwm = signed_pwm
    if abs(signed_pwm) < PWM_DEADBAND:
        signed_pwm = 0.0

    # Direction + magnitude
    direction = 0 if signed_pwm >= 0 else 1
    pwm_magnitude = int(abs(signed_pwm))
    
    IO_DIR.value = direction
    IO_PWM.value = pwm_magnitude
    
    # Debug output (every 5 cycles ≈ 1 second)
    _debug_counter += 1
    if pwm_magnitude > 0:
        _debug_counter = 0
        error_mm = pos_pid.setpoint - pos_mm
        print(f"[debug] Pos:{pos_mm:6.2f}mm | Target:{pos_pid.setpoint:6.1f}mm | "
              f"Error:{error_mm:+6.1f}mm | Vel:{velocity_mm_s:+6.1f}mm/s | "
              f"PID:{original_pwm:+6.1f} | PWM:{pwm_magnitude:3d}% | "
              f"Dir:{'RET' if direction else 'EXT'} | Raw:{raw_value:5d}")

def get_position():
    """Get the current position in mm."""
    raw_value = IO_POT_RAW.value
    return raw_to_mm(raw_value)
# ───────────────────────────────── Clean shutdown ───────────────────────────
_shutdown_flag = False

def shutdown(*_):
    global _shutdown_flag
    print("\n[system] Shutting down, actuator stopped.")
    _shutdown_flag = True
    stop()
    rpi.exit()

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, shutdown)

# ───────────────────────────────── Demo / entry point ───────────────────────
if __name__ == "__main__":
    try:
        print("[system] Starting control loop …")
        # Initialize PID setpoint to current position
        current_position = get_position()
        pos_pid.setpoint = current_position
        rpi.cycleloop(controller, blocking=False)
        move_to(40)
        while abs(40-get_position()) >0.5:
            time.sleep(0.01)  # Allow time for the actuator to move
        move_to(100)
        while get_position()<50:
            time.sleep(0.01)  # Allow time for the actuator to move
        set_max_pwm(200)

        # while not _shutdown_flag:
        #     time.sleep(0.1)
        #     # Allow the user to input a new target position
        #     try:
        #         target = input(f"Enter target position (0-{STROKE_MM} mm): ")
        #         if _shutdown_flag:  # Check flag after input
        #             break
        #         if target.strip().lower() in ('exit', 'quit'):
        #             break
        #         target_mm = float(target)
        #         move_to(target_mm)
        #     except ValueError:
        #         print("Invalid input, please enter a number or 'exit' to quit.")
        #     except (EOFError, KeyboardInterrupt):
        #         # Handle Ctrl+C or EOF during input
        #         break
    except KeyboardInterrupt:
        print("\n[system] Stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"\n[system] Error: {e}")
    finally:
        shutdown()
