#!/usr/bin/env python3
import time, signal, revpimodio2
from simple_pid import PID
from calibration import load_calibration, analog_to_mm

# ── choose demo here ─────────────────────────────────────────
DEMO_MODE = 2      # 1 = auto-move demo, 2 = interactive CLI

# ── constants ───────────────────────────────────────────────
STROKE_MM      = 146.0
PWM_DEADBAND   = 10
SOFT_MARGIN_MM = 0.0          # set >0 if you want software end-stops

# ── calibration ─────────────────────────────────────────────
analogs_mv, positions_mm = load_calibration()
raw_to_mm = lambda raw: analog_to_mm(raw, analogs_mv, positions_mm)

# ── I/O ─────────────────────────────────────────────────────
rpi            = revpimodio2.RevPiModIO(autorefresh=True)
IO_PWM         = rpi.io.PwmDutycycle_2
IO_DIR         = rpi.io.DigitalOutput_1
IO_POT_RAW     = rpi.io.AnalogInput_1

# ── position PID (mm → signed PWM %) ────────────────────────
pos_pid = PID(Kp=20, Ki=0, Kd=0.5)
pos_pid.output_limits = (-500, 500)

# ── helpers ─────────────────────────────────────────────────
clamp      = lambda v: max(SOFT_MARGIN_MM, min(v, STROKE_MM - SOFT_MARGIN_MM))
move_to    = lambda mm: pos_pid.__setattr__("setpoint", clamp(mm))
stop       = lambda: (setattr(IO_PWM, "value", 0), setattr(IO_DIR, "value", 0), setattr(pos_pid, "output_limits", (0, 0)))
get_pos    = lambda: raw_to_mm(IO_POT_RAW.value)

def set_max_pwm(limit: int):
    if not 0 <= limit <= 1000:
        raise ValueError("0 ≤ max_pwm ≤ 1000")
    cur = abs(pos_pid.output_limits[1])
    if limit < cur:                             # gentle ramp-down
        for pwm in range(cur, limit, -100):
            pos_pid.output_limits = (-pwm, pwm)
            time.sleep(0.1)
    pos_pid.output_limits = (-limit, limit)
    print(f"[system] Max PWM set to {limit}")

print(f"[system] Loop time: {rpi.cycletime:.3f} ms")

def controller(_ct):
    pos = raw_to_mm(IO_POT_RAW.value)
    pwm_signed = pos_pid(pos)                   # mm/s → signed PWM %
    if abs(pwm_signed) < PWM_DEADBAND:
        pwm_signed = 0
    IO_DIR.value = 0 if pwm_signed >= 0 else 1
    pwm = int(abs(pwm_signed))
    IO_PWM.value = pwm

    if pwm:                                     # debug print
        err = pos_pid.setpoint - pos
        print(f"[debug] Pos:{pos:6.2f}mm | Target:{pos_pid.setpoint:6.1f}mm | "
              f"Error:{err:+6.1f}mm | PID:{pwm_signed:+6.1f} | "
              f"PWM:{pwm:3d}% | Dir:{'RET' if IO_DIR.value else 'EXT'} | "
              f"Raw:{IO_POT_RAW.value:5d}")

# ── clean shutdown ──────────────────────────────────────────
_shutdown = False
def shutdown(*_):
    global _shutdown
    print("\n[system] Shutting down, actuator stopped.")
    _shutdown = True
    stop()
    rpi.exit(full=True)

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, shutdown)

# ───────────────────────── Demo / entry point ───────────────
if __name__ == "__main__":
    try:
        print("[system] Starting control loop …")
        pos_pid.setpoint = get_pos()           # start where we are
        rpi.cycleloop(controller, blocking=False)

        if DEMO_MODE == 1:
            # Demo 1: automatic sequence
            move_to(40)
            while abs(40 - get_pos()) > 0.5: time.sleep(0.01)
            move_to(100)
            while get_pos() < 50: time.sleep(0.01)
            set_max_pwm(200)

            while not _shutdown: time.sleep(0.1)

        else:  # DEMO_MODE == 2
            while not _shutdown:
                time.sleep(0.1)
                try:
                    target = input(f"Target (30-{STROKE_MM} mm): ").strip()
                    if not (30.3 <= float(target) <= STROKE_MM):
                        print(f"Value must be between 30 and {STROKE_MM} mm.")
                        continue
                    move_to(float(target))
                except ValueError:
                    print("Invalid number.")
                except (EOFError, KeyboardInterrupt):
                    break

    except KeyboardInterrupt:
        print("\n[system] Stopped by user (Ctrl-C)")
    except Exception as e:
        print(f"\n[system] Error: {e}")
    finally:
        shutdown()
