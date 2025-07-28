#!/usr/bin/env python3
"""
Minimal Modbus data logger: captures process/peak data when threshold crossed.
"""
import asyncio
import logging
import pymodbus.client as modbusClient
from datetime import datetime
import csv
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Constants
PORT = "/dev/ttyRS485"
BAUDRATE = 9600
SLAVE_ADDRESS = 240
THRESHOLD = 3.0
SCALE_FACTOR = 100
SLEEP_INTERVAL = 0.1

# Modbus registers
RESET_REG = 1025
PROCESS_REG = 1000
PEAK_REG = 1004

# File prefixes
CSV_PREFIX = "process_data_"
PLOT_PREFIX = "/home/pi/Documents/knockoff/plot_"

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Our logger can still show debug

# Suppress noisy third-party loggers
logging.getLogger('pymodbus').setLevel(logging.WARNING)
logging.getLogger('matplotlib').setLevel(logging.WARNING)

class ModbusDataLogger:
    def __init__(self, client):
        self.client = client
        self.cycle = 0
        
    async def read_scaled_value(self, register):
        """Read and scale a 32-bit register value"""
        result = await self.client.read_holding_registers(register, count=2, slave=SLAVE_ADDRESS)
        if result.isError():
            return None
        value = self.client.convert_from_registers(result.registers, self.client.DATATYPE.INT32)
        return value / SCALE_FACTOR
    
    async def reset_peaks(self):
        """Reset peak values"""
        result = await self.client.write_register(RESET_REG, 1, slave=SLAVE_ADDRESS)
        if result.isError():
            logger.error(f"Error resetting peaks: {result}")
            return False
        logger.info("Peak values reset")
        return True
    
    async def capture_cycle(self):
        """Capture one complete data cycle"""
        if not await self.reset_peaks():
            return
            
        data = []
        capturing = False
        
        while True:
            # Read process and peak values
            process_val = await self.read_scaled_value(PROCESS_REG)
            peak_val = await self.read_scaled_value(PEAK_REG)
            
            if process_val is None or peak_val is None:
                await asyncio.sleep(SLEEP_INTERVAL)
                continue
                
            timestamp = datetime.now().isoformat()
            data.append([timestamp, process_val, peak_val])
            
            logger.debug(f"Timestamp: {timestamp}, Process Value: {process_val:.2f}, Peak Value: {peak_val:.2f}")
            
            # State machine logic
            if process_val >= THRESHOLD:
                capturing = True
            elif capturing and process_val < THRESHOLD:
                logger.info("Threshold crossed - exporting data")
                await self.export_data(data)
                self.cycle += 1
                break
                
            await asyncio.sleep(SLEEP_INTERVAL)
    
    async def export_data(self, data):
        """Export data to CSV and create plot"""
        csv_file = f"{CSV_PREFIX}{self.cycle}.csv"
        plot_file = f"{PLOT_PREFIX}{self.cycle}.png"
        
        # Export CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Process Value", "Peak Value"])
            writer.writerows(data)
        logger.info(f"Data exported to {csv_file}")
        
        # Create plot
        df = pd.read_csv(csv_file)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        plt.figure(figsize=(10, 6))
        plt.plot(df['Timestamp'], df['Peak Value'], label='Peak Value')
        plt.xlabel('Time')
        plt.ylabel('Peak Value')
        plt.title('Time vs Peak Value')
        plt.xticks(rotation=45)
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()
        logger.info(f"Plot saved to {plot_file}")
    
    async def run(self):
        """Main monitoring loop"""
        logger.info("Starting data logger")
        try:
            while True:
                await self.capture_cycle()
        except asyncio.CancelledError:
            logger.info("Data logger cancelled")
        except Exception as e:
            logger.error(f"Error in data logger: {e}")

async def main():
    """Setup and run the data logger"""
    client = modbusClient.AsyncModbusSerialClient(
        PORT, timeout=1, baudrate=BAUDRATE, 
        stopbits=1, parity="N", bytesize=8
    )
    
    try:
        await client.connect()
        if not client.connected:
            logger.error("Failed to connect to Modbus device")
            return
            
        logger.info("Connected to Modbus device")
        data_logger = ModbusDataLogger(client)
        await data_logger.run()
        
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        client.close()
        logger.info("Connection closed")

if __name__ == "__main__":
    asyncio.run(main())
