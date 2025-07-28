#!/usr/bin/env python3
"""
Minimal asyncio actuator control: move to position (cancellable) and set speed limit.
"""
import asyncio
import signal
import revpimodio2
from simple_pid import PID
from calibration import load_calibration, analog_to_mm

STROKE_MM = 146.0
PWM_DEADBAND = 10
SOFT_MARGIN_MM = 0.0

class ActuatorController:
    def __init__(self):
        analogs_mv, positions_mm = load_calibration()
        self.raw_to_mm = lambda raw: analog_to_mm(raw, analogs_mv, positions_mm)
        self.stop = lambda: (setattr(self.IO_PWM, "value", 0), 
                             setattr(self.IO_DIR, "value", 0), 
                             setattr(self.pos_pid, "output_limits", (0, 0)))
        self.rpi = revpimodio2.RevPiModIO(autorefresh=True)
        self.IO_PWM = self.rpi.io.PwmDutycycle_2
        self.IO_DIR = self.rpi.io.DigitalOutput_1
        self.IO_POT_RAW = self.rpi.io.AnalogInput_1
        self.pos_pid = PID(Kp=20, Ki=0, Kd=0.5)
        self.pos_pid.output_limits = (-500, 500)
        self._shutdown = False
        self._move_task = None
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        print(f"[system] Ready (Loop: {self.rpi.cycletime:.3f} ms)")

    async def start(self):
        self.pos_pid.setpoint = self.get_position()
        asyncio.create_task(self._control_loop())

    async def _control_loop(self):
        while not self._shutdown:
            pos = self.get_position()
            if abs(self.pos_pid.setpoint - pos) < 0.5:  # Position deadband
                pwm_signed = 0
            else:
                pwm_signed = self.pos_pid(pos)
            if abs(pwm_signed) < PWM_DEADBAND:
                pwm_signed = 0
            self.IO_DIR.value = 0 if pwm_signed >= 0 else 1
            self.IO_PWM.value = int(abs(pwm_signed))
            await asyncio.sleep(0.01)

    get_position = lambda self: self.raw_to_mm(self.IO_POT_RAW.value)

    def move(self, target_mm):
        if self.pos_pid.output_limits == (0, 0):  # Restore speed before moving
            self.pos_pid.output_limits = self._saved_limits
        safe_target = max(SOFT_MARGIN_MM, min(target_mm, STROKE_MM - SOFT_MARGIN_MM))
        self.pos_pid.setpoint = safe_target
        print(f"[move] Target: {safe_target:.1f} mm")

    def cancel_move(self):
        current_pos = self.get_position()
        self.pos_pid.setpoint = current_pos
        self._saved_limits = self.pos_pid.output_limits # saves previous speed
        self.pos_pid.output_limits = (0, 0)  # Full stop
        print(f"[move] Cancelled at {current_pos:.2f} mm")

    async def set_speed_limit(self, pwm_limit):
        if not 0 <= pwm_limit <= 1000:
            print("[speed] Invalid limit")
            return
        current = abs(self.pos_pid.output_limits[1])
        if pwm_limit < current:
            for pwm in range(current, pwm_limit, -100):
                self.pos_pid.output_limits = (-pwm, pwm)
                await asyncio.sleep(0.1)
        self.pos_pid.output_limits = (-pwm_limit, pwm_limit)
        print(f"[speed] Limit set to {pwm_limit}")

    def _shutdown_handler(self, *_):
        self._shutdown = True
        self.stop()
        self.rpi.exit()
        print("[system] Shutdown")

async def get_user_input():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, "> ")

async def main():
    ctrl = ActuatorController()
    await ctrl.start()
    print("Commands: <pos>, speed <val>, cancel, pos, quit")
    while not ctrl._shutdown:
        try:
            cmd = (await get_user_input()).strip().lower()
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd.startswith("speed "):
                try:
                    val = int(cmd.split()[1])
                    await ctrl.set_speed_limit(val)
                except Exception:
                    print("[speed] Usage: speed <0-1000>")
            elif cmd == "cancel":
                ctrl.cancel_move()
            elif cmd == "pos":
                print(f"[pos] {ctrl.get_position():.2f} mm")
            else:
                try:
                    pos = float(cmd)
                    ctrl.move(pos)
                except Exception:
                    print("[cmd] Invalid. Use <pos>, speed <val>, cancel, pos, quit")
        except (EOFError, KeyboardInterrupt):
            break
    ctrl._shutdown_handler()

if __name__ == "__main__":
    asyncio.run(main())
