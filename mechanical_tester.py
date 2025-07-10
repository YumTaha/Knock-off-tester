#!/usr/bin/env python3
"""
Integrated mechanical tester: combines actuator control with strain measurement.
Performs continuous descent while logging strain vs position data.
"""
import asyncio
import signal
import logging
import csv
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from enum import Enum

# Actuator imports
import revpimodio2
from simple_pid import PID
from calibration import load_calibration, analog_to_mm

# Strain gauge imports
import pymodbus.client as modbusClient

# Actuator constants
STROKE_MM = 146.0
PWM_DEADBAND = 10
SOFT_MARGIN_MM = 0
HOME_POSITION_MM = 50
TEST_SPEED_PWM = 200  # Slow, controlled speed for testing
MAX_TEST_POSITION_MM = 100  # Stop test if no tooth found by this position

# Strain gauge constants
MODBUS_PORT = "/dev/ttyRS485"
BAUDRATE = 9600
SLAVE_ADDRESS = 240
SCALE_FACTOR = 100
STRAIN_DETECTION_THRESHOLD = 5.0  # Minimum strain change to detect tooth contact
STRAIN_ZERO_THRESHOLD = 0.5  # Consider strain "zero" below this value
BASELINE_SAMPLES = 10  # Number of samples to establish baseline

# Modbus registers
RESET_REG = 1025
PROCESS_REG = 1000
PEAK_REG = 1004

# File prefixes
CSV_PREFIX = "mechanical_test_"
PLOT_PREFIX = "/home/pi/Documents/knockoff/test_plot_"

# Test states
class TestState(Enum):
    IDLE = "idle"
    MOVING_TO_HOME = "moving_to_home"
    DESCENDING = "descending"
    RETURNING_HOME = "returning_home"
    RESETTING = "resetting"

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Suppress noisy third-party loggers
logging.getLogger('pymodbus').setLevel(logging.WARNING)
logging.getLogger('matplotlib').setLevel(logging.WARNING)

class MechanicalTester:
    def __init__(self):
        # Initialize actuator
        self._init_actuator()
        
        # Initialize strain gauge (will be set in main)
        self.modbus_client = None
        
        # Test state
        self.state = TestState.IDLE
        self.cycle = 0
        self.test_data = []
        self.max_strain_seen = 0.0
        self.baseline_strain = 0.0  # Baseline strain value
        self._shutdown = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        
        logger.info("[system] Mechanical tester initialized")

    def _init_actuator(self):
        """Initialize actuator hardware and PID controller"""
        analogs_mv, positions_mm = load_calibration()
        self.raw_to_mm = lambda raw: analog_to_mm(raw, analogs_mv, positions_mm)
        
        self.rpi = revpimodio2.RevPiModIO(autorefresh=True)
        self.IO_PWM = self.rpi.io.PwmDutycycle_2
        self.IO_DIR = self.rpi.io.DigitalOutput_1
        self.IO_POT_RAW = self.rpi.io.AnalogInput_1
        
        # Initialize PID controller but don't set a setpoint yet
        self.pos_pid = PID(Kp=20, Ki=0, Kd=0.5)
        self.pos_pid.output_limits = (0, 0)  # Start with actuator stopped
        
        # Set initial setpoint to current position to prevent movement
        current_pos = self.get_position()
        self.pos_pid.setpoint = current_pos
        
        logger.info(f"[actuator] Ready (Loop: {self.rpi.cycletime:.3f} ms)")
        logger.info(f"[actuator] Initial position: {current_pos:.2f} mm - actuator held in place")

    get_position = lambda self: self.raw_to_mm(self.IO_POT_RAW.value)
    stop_actuator = lambda self: (setattr(self.IO_PWM, "value", 0), 
                                 setattr(self.IO_DIR, "value", 0), 
                                 setattr(self.pos_pid, "output_limits", (0, 0)))

    async def read_strain_value(self, register):
        """Read and scale a 32-bit register value from strain gauge"""
        if not self.modbus_client:
            return None
            
        result = await self.modbus_client.read_holding_registers(register, count=2, slave=SLAVE_ADDRESS)
        if result.isError():
            return None
        value = self.modbus_client.convert_from_registers(result.registers, self.modbus_client.DATATYPE.INT32)
        return value / SCALE_FACTOR

    async def establish_baseline(self):
        """Establish baseline strain reading"""
        logger.info("[strain] Establishing baseline strain reading...")
        readings = []
        
        for i in range(BASELINE_SAMPLES):
            strain = await self.read_strain_value(PROCESS_REG)
            if strain is not None:
                readings.append(strain)
            await asyncio.sleep(0.1)
        
        if readings:
            self.baseline_strain = sum(readings) / len(readings)
            logger.info(f"[strain] Baseline established: {self.baseline_strain:.2f}")
            return True
        else:
            logger.error("[strain] Failed to establish baseline")
            return False

    get_strain_change = lambda self, current_strain: None if current_strain is None else current_strain - self.baseline_strain

    async def reset_strain_peaks(self):
        """Reset strain gauge peak values"""
        if not self.modbus_client:
            return False
            
        result = await self.modbus_client.write_register(RESET_REG, 1, slave=SLAVE_ADDRESS)
        if result.isError():
            logger.error(f"Error resetting strain peaks: {result}")
            return False
        logger.info("[strain] Peak values reset")
        return True

    async def move_to_position(self, target_mm, speed_pwm=None):
        """Move actuator to target position"""
        if speed_pwm is None:
            speed_pwm = 300  # Default speed
            
        self.pos_pid.output_limits = (-speed_pwm, speed_pwm)
        safe_target = max(SOFT_MARGIN_MM, min(target_mm, STROKE_MM - SOFT_MARGIN_MM))
        self.pos_pid.setpoint = safe_target
        
        logger.info(f"[actuator] Moving to {safe_target:.1f} mm at speed {speed_pwm}")
        
        # Wait until position is reached (within 1mm tolerance)
        while abs(self.get_position() - safe_target) > 1.0 and not self._shutdown:
            await asyncio.sleep(0.1)
        
        logger.info(f"[actuator] Reached position {self.get_position():.1f} mm")

    async def control_loop(self):
        """Main actuator control loop"""
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
            
            await asyncio.sleep(0.01)  # 100Hz control loop

    async def perform_test_cycle(self):
        """Perform one complete mechanical test cycle"""
        logger.info(f"[test] Starting cycle {self.cycle}")
        
        # Reset for new test
        self.test_data = []
        self.max_strain_seen = 0.0
        
        # State 1: Move to home position
        self.state = TestState.MOVING_TO_HOME
        await self.move_to_position(HOME_POSITION_MM)
        
        # State 2: Establish baseline and reset strain peaks
        self.state = TestState.RESETTING
        if not await self.establish_baseline():
            logger.error("[test] Failed to establish baseline, aborting test")
            return
            
        await self.reset_strain_peaks()
        await asyncio.sleep(0.5)  # Let readings stabilize
        
        # State 3: Descending test with data collection
        self.state = TestState.DESCENDING
        logger.info("[test] Starting descent and data collection")
        
        # Start slow descent
        self.pos_pid.output_limits = (-TEST_SPEED_PWM, TEST_SPEED_PWM)
        self.pos_pid.setpoint = STROKE_MM - SOFT_MARGIN_MM  # Go to bottom
        
        # Collect data during descent
        strain_returned_to_zero = False
        no_tooth_detected = False
        tooth_contacted = False
        max_strain_change = 0.0
        
        while not strain_returned_to_zero and not no_tooth_detected and not self._shutdown:
            # Read current data
            position = self.get_position()
            process_strain = await self.read_strain_value(PROCESS_REG)
            peak_strain = await self.read_strain_value(PEAK_REG)
            
            if process_strain is not None and peak_strain is not None:
                # Calculate strain change from baseline
                strain_change = self.get_strain_change(process_strain)
                peak_change = self.get_strain_change(peak_strain)
                
                timestamp = datetime.now().isoformat()
                self.test_data.append([timestamp, position, strain_change, peak_change])
                
                # Track maximum strain change seen
                if strain_change is not None:
                    max_strain_change = max(max_strain_change, strain_change)
                
                logger.debug(f"Position: {position:.2f}mm, Strain Change: {strain_change:.2f}, Peak Change: {peak_change:.2f}")
                
                # Check if we've made contact with tooth
                if strain_change is not None and strain_change > STRAIN_DETECTION_THRESHOLD:
                    if not tooth_contacted:
                        logger.info(f"[test] Tooth contact detected at position {position:.2f}mm")
                        tooth_contacted = True
                
                # Check if strain has returned to baseline after tooth contact
                if tooth_contacted and strain_change is not None and abs(strain_change) < STRAIN_ZERO_THRESHOLD:
                    logger.info(f"[test] Strain returned to baseline, test completed")
                    strain_returned_to_zero = True
                
                # Check if we've reached max test position without finding a tooth
                if position >= MAX_TEST_POSITION_MM and max_strain_change < STRAIN_DETECTION_THRESHOLD:
                    logger.warning(f"[test] No tooth detected by position {MAX_TEST_POSITION_MM}mm, aborting test")
                    no_tooth_detected = True
            
            await asyncio.sleep(0.1)  # 10Hz data collection
        
        # State 4: Return to home
        self.state = TestState.RETURNING_HOME
        await self.move_to_position(HOME_POSITION_MM)
        
        # State 5: Export data (only if we found a tooth)
        if not no_tooth_detected and tooth_contacted:
            await self.export_test_data()
        else:
            if no_tooth_detected:
                logger.info("[test] No data exported - no tooth was detected")
            else:
                logger.info("[test] No data exported - insufficient strain detected")
        
        self.cycle += 1
        self.state = TestState.IDLE
        logger.info(f"[test] Cycle {self.cycle - 1} completed")

    async def export_test_data(self):
        """Export test data to CSV and create plot"""
        if not self.test_data:
            logger.warning("[export] No data to export")
            return
            
        csv_file = f"{CSV_PREFIX}{self.cycle}.csv"
        plot_file = f"{PLOT_PREFIX}{self.cycle}.png"
        
        # Export CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Position_mm", "Strain_Change", "Peak_Strain_Change"])
            writer.writerows(self.test_data)
        logger.info(f"[export] Data exported to {csv_file}")
        
        # Create strain vs position plot
        df = pd.read_csv(csv_file)
        
        # Remove leading zeros in strain data
        first_significant = df[df['Strain_Change'].abs() > STRAIN_ZERO_THRESHOLD].index
        if len(first_significant) > 0:
            df_trimmed = df.iloc[first_significant[0]:]
        else:
            df_trimmed = df
        
        plt.figure(figsize=(12, 6))
        
        # Plot only the process strain change
        plt.plot(df_trimmed['Position_mm'], df_trimmed['Strain_Change'], 'b-', label='Stress', linewidth=2)
        
        # Find and display peak value as text annotation
        peak_value = df_trimmed['Peak_Strain_Change'].max()
        peak_position = df_trimmed.loc[df_trimmed['Peak_Strain_Change'].idxmax(), 'Position_mm']
        
        # Add peak value annotation
        plt.annotate(f'Peak: {peak_value:.2f}', 
                    xy=(peak_position, peak_value), 
                    xytext=(peak_position + 5, peak_value + 1),
                    arrowprops=dict(arrowstyle='->', color='red'),
                    fontsize=12, color='red', fontweight='bold')
        
        plt.xlabel('Strain')
        plt.ylabel('Stress')
        plt.title(f'Mechanical Test Cycle {self.cycle} - Stress vs Strain')
        plt.grid(True)
        plt.legend()
        
        plt.tight_layout()
        plt.savefig(plot_file, dpi=150)
        plt.close()
        logger.info(f"[export] Plot saved to {plot_file}")

    async def run_continuous_testing(self):
        """Run testing based on user commands"""
        logger.info("[system] Mechanical tester ready - waiting for commands")
        logger.info("Commands: 'test' to run a test cycle, 'pos' to show position, 'quit' to exit")
        
        try:
            while not self._shutdown:
                # Get user input
                try:
                    cmd = await self.get_user_input()
                    cmd = cmd.strip().lower()
                    
                    if cmd in ("quit", "exit", "q"):
                        logger.info("[system] User requested shutdown")
                        break
                    elif cmd == "test":
                        logger.info("[system] Starting test cycle...")
                        await self.perform_test_cycle()
                        logger.info("[system] Test cycle completed. Ready for next command.")
                    elif cmd == "pos":
                        current_pos = self.get_position()
                        logger.info(f"[actuator] Current position: {current_pos:.2f} mm")
                    elif cmd == "home":
                        logger.info("[actuator] Moving to home position...")
                        await self.move_to_position(HOME_POSITION_MM)
                        logger.info("[actuator] At home position")
                    elif cmd == "help":
                        logger.info("Available commands:")
                        logger.info("  test  - Run a mechanical test cycle")
                        logger.info("  pos   - Show current actuator position") 
                        logger.info("  home  - Move actuator to home position")
                        logger.info("  help  - Show this help message")
                        logger.info("  quit  - Emergency shutdown")
                    else:
                        logger.warning(f"[system] Unknown command: '{cmd}'. Type 'help' for available commands.")
                        
                except (EOFError, KeyboardInterrupt):
                    logger.info("[system] Interrupt received, shutting down")
                    break
                    
        except asyncio.CancelledError:
            logger.info("[system] Testing cancelled")
        except Exception as e:
            logger.error(f"[system] Error during operation: {e}")
        finally:
            self.stop_actuator()

    async def get_user_input(self):
        """Get user input asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, "> ")

    def _shutdown_handler(self, *_):
        """Handle shutdown signals"""
        logger.info("[system] Shutdown signal received")
        self._shutdown = True
        self.stop_actuator()
        self.rpi.exit()

async def main():
    """Main entry point"""
    # Initialize mechanical tester
    tester = MechanicalTester()
    
    # Initialize Modbus connection
    modbus_client = modbusClient.AsyncModbusSerialClient(
        MODBUS_PORT, timeout=1, baudrate=BAUDRATE, 
        stopbits=1, parity="N", bytesize=8
    )
    
    try:
        # Connect to strain gauge
        await modbus_client.connect()
        if not modbus_client.connected:
            logger.error("[modbus] Failed to connect to strain gauge")
            return
            
        logger.info("[modbus] Connected to strain gauge")
        tester.modbus_client = modbus_client
        
        # Start actuator control loop
        control_task = asyncio.create_task(tester.control_loop())
        
        # Start testing
        await tester.run_continuous_testing()
        
    except Exception as e:
        logger.error(f"[system] Error: {e}")
    finally:
        if modbus_client:
            modbus_client.close()
        logger.info("[system] System shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
