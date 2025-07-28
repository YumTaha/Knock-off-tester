import asyncio
import logging
import pymodbus.client as modbusClient
from datetime import datetime
import csv
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

_logger = logging.getLogger(__file__)
_logger.setLevel("DEBUG")
# Configure logging
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
_logger.addHandler(handler)


# Configure serial port
port = "/dev/ttyRS485"  
baudrate = 9600
slave_address = 240  

CSV_FILENAME_PREFIX = "process_data_"
PLOT_FILENAME_PREFIX = "/home/pi/Documents/knockoff/plot_"

async def read_process_and_peak(client: modbusClient.AsyncModbusSerialClient, data_log: list):
    """Continuously read process and peak values and log them."""
    try:
        cycle_counter = 0  # Initialize a counter for the data cycles

        while True:  # Main loop for continuous monitoring
            # Reset peak values at the start of each cycle
            reset_wr = await client.write_register(1025, 1, slave=slave_address)
            if reset_wr.isError():
                _logger.error(f"Error resetting peak values: {reset_wr}")
                return  # Exit the function if reset fails
            else:
                _logger.info("Peak values reset successfully.")
                data_log.clear()  # Clear previous data log for the new peak capture

            above_threshold = False  # Flag to indicate if process value is above threshold
            temp_data_log = []  # Temporary list to hold data within the threshold range

            while True:  # Inner loop for reading and logging data until process value drops below threshold
                # Read current process value (Modbus addresses 1000 and 1001)
                process_rr = await client.read_holding_registers(1000, count=2, slave=slave_address)
                if process_rr.isError():
                    _logger.error(f"Error reading process value: {process_rr}")
                    await asyncio.sleep(0.1)
                    continue
                process_value = client.convert_from_registers(process_rr.registers, client.DATATYPE.INT32)
                scaled_process_value = process_value / 100  # Assuming a scaling factor of 100

                # Read max peak value (Modbus addresses 1004 and 1005)
                peak_rr = await client.read_holding_registers(1004, count=2, slave=slave_address)
                if peak_rr.isError():
                    _logger.error(f"Error reading peak value: {peak_rr}")
                    await asyncio.sleep(0.1)
                    continue
                peak_value = client.convert_from_registers(peak_rr.registers, client.DATATYPE.INT32)
                scaled_peak_value = peak_value / 100  # Assuming the same scaling factor for peak

                timestamp = datetime.now().isoformat()
                _logger.debug(f"Timestamp: {timestamp}, Process Value: {scaled_process_value}, Peak Value: {scaled_peak_value}")

                if scaled_process_value >= 3:
                    above_threshold = True  # Set flag when process value exceeds threshold
                    temp_data_log.append([timestamp, scaled_process_value, scaled_peak_value])  # Append data to temporary log
                elif above_threshold and scaled_process_value < 3:
                    # If process value drops below threshold after being above it
                    temp_data_log.append([timestamp, scaled_process_value, scaled_peak_value])
                    _logger.info("Process value dropped below threshold. Exporting data and resetting.")

                    # Generate filenames with cycle counter
                    csv_filename = f"{CSV_FILENAME_PREFIX}{cycle_counter}.csv"
                    plot_filename = f"{PLOT_FILENAME_PREFIX}{cycle_counter}.png"

                    await export_to_csv(temp_data_log, csv_filename)  # Export data to CSV
                    await plot_csv(csv_filename, plot_filename)  # Plot the data and save as PNG

                    cycle_counter += 1  # Increment the cycle counter
                    break  # Break inner loop to reset peak and start a new capture
                elif above_threshold == False:
                    temp_data_log.append([timestamp, scaled_process_value, scaled_peak_value])

                await asyncio.sleep(0.1)  # Adjust the reading interval as needed

    except asyncio.CancelledError:
        _logger.info("Reading task cancelled.")
    except Exception as e:
        _logger.error(f"An error occurred during data reading: {e}")

async def export_to_csv(data_log: list, filename: str):
    """Export the collected data to a CSV file."""
    try:
        with open(filename, 'w', newline='') as csvfile:  # Open in write mode to overwrite existing data
            csv_writer = csv.writer(csvfile)
            # Write header row
            csv_writer.writerow(["Timestamp", "Process Value", "Peak Value"])
            # Write data rows
            csv_writer.writerows(data_log)
        _logger.info(f"Data exported to {filename}")
    except Exception as e:
        _logger.error(f"Error exporting to CSV: {e}")

async def plot_csv(csv_filename: str, png_filename: str):
    """Plot data from CSV and save as PNG."""
    try:
        # Read the CSV file
        df = pd.read_csv(csv_filename)

        # Convert the 'Timestamp' column to datetime
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

        # Plot 'Peak Value' against 'Timestamp'
        plt.plot(df['Timestamp'], df['Peak Value'], label='Peak Value')

        # Add labels and title
        plt.xlabel('Time')
        plt.ylabel('Peak Value')
        plt.title('Time vs Peak Value')

        # Rotate date labels for better visibility
        plt.xticks(rotation=45)

        # Format the x-axis to show datetime more clearly
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))

        # Optionally set the tick frequency for the x-axis (this may need tweaking)
        plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))  # Adjust interval as needed

        # Show grid for better visualization
        plt.grid(True)

        # Adjust layout to avoid clipping
        plt.tight_layout()

        # Save the plot as a PNG file (you can specify the path)
        plt.savefig(png_filename)
        plt.close()  # Close the plot to free memory
        _logger.info(f"Plot saved to {png_filename}")
    except Exception as e:
        _logger.error(f"Error plotting CSV: {e}")

async def write_header_to_csv(filename: str):
    """Write the header row to the CSV file."""
    try:
        with open(filename, 'w', newline='') as csvfile:  # Open in write mode to create the file
            csv_writer = csv.writer(csvfile)
            # Write header row
            csv_writer.writerow(["Timestamp", "Process Value", "Peak Value"])
        _logger.info(f"Header written to {filename}")
    except Exception as e:
        _logger.error(f"Error writing header to CSV: {e}")

def file_exists(filename: str) -> bool:
    """Check if the CSV file exists."""
    try:
        with open(filename, 'r') as f:
            return True
    except FileNotFoundError:
        return False

async def run_async_client(client: modbusClient.AsyncModbusSerialClient):
    """Run async client for continuous reading and export."""
    _logger.info("### Client starting")
    try:
        await client.connect()
        if client.connected:
            _logger.info("### Client connected")
            data_log = []
            await read_process_and_peak(client, data_log)
            client.close()
        else:
            _logger.error("### Failed to connect to the Modbus server")
    except Exception as e:
        _logger.error(f"An error occurred: {e}")
    finally:
        client.close()
    _logger.info("### End of Program")


async def main(cmdline=None):
    """Combine setup and run."""
    # Create instrument instance
    client = modbusClient.AsyncModbusSerialClient(
            port,
            timeout=1,
            baudrate=baudrate,
            stopbits=1,
            parity="N",
            bytesize=8
        )
    await run_async_client(client)


if __name__ == "__main__":
    asyncio.run(main(), debug=True)