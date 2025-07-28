import asyncio
import logging
import pymodbus.client as modbusClient
from datetime import datetime
import csv

_logger = logging.getLogger(__file__)
_logger.setLevel("DEBUG")
# Configure logging
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
_logger.addHandler(handler)

# Configure serial port
port = "/dev/ttyRS485"  # Replace with your serial port
baudrate = 9600
slave_address = 240  # Make sure this matches your DP400S configuration (parameter 126)

async def read_process_and_peak(client: modbusClient.AsyncModbusSerialClient, data_log: list):
    """Continuously read process and peak values and log them."""
    try:
        while True:
            # Read current process value (Modbus addresses 1000 and 1001)
            process_rr = await client.read_holding_registers(1000, count=2, slave=slave_address)
            if process_rr.isError():
                _logger.error(f"Error reading process value: {process_rr}")
                await asyncio.sleep(0.1)
                continue
            process_value = client.convert_from_registers(process_rr.registers, client.DATATYPE.INT32)
            scaled_process_value = process_value / 100  # Assuming a scaling factor of 100 based on your previous peak output

            # Read max peak value (Modbus addresses 1004 and 1005)
            peak_rr = await client.read_holding_registers(1004, count=2, slave=slave_address)
            if peak_rr.isError():
                _logger.error(f"Error reading peak value: {peak_rr}")
                await asyncio.sleep(0.1)
                continue
            peak_value = client.convert_from_registers(peak_rr.registers, client.DATATYPE.INT32)
            scaled_peak_value = peak_value / 100  # Assuming the same scaling factor for peak

            timestamp = datetime.now().isoformat()
            data_log.append([timestamp, scaled_process_value, scaled_peak_value])
            _logger.debug(f"Timestamp: {timestamp}, Process Value: {scaled_process_value}, Peak Value: {scaled_peak_value}")

            # Simple peak detection: Stop logging if current process value is equal to the peak value
            if scaled_process_value >= scaled_peak_value:
                _logger.info("Potential peak reached or exceeded. Stopping data logging.")
                break

            await asyncio.sleep(0.1) # Adjust the reading interval as needed

    except asyncio.CancelledError:
        _logger.info("Reading task cancelled.")
    except Exception as e:
        _logger.error(f"An error occurred during data reading: {e}")

async def export_to_csv(data_log: list, filename="process_data.csv"):
    """Export the collected data to a CSV file."""
    try:
        with open(filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            # Write header row
            csv_writer.writerow(["Timestamp", "Process Value", "Peak Value"])
            # Write data rows
            csv_writer.writerows(data_log)
        _logger.info(f"Data exported to {filename}")
    except Exception as e:
        _logger.error(f"Error exporting to CSV: {e}")

async def run_async_client(client: modbusClient.AsyncModbusSerialClient):
    """Run async client for continuous reading and export."""
    _logger.info("### Client starting")
    await client.connect()
    if client.connected:
        _logger.info("### Client connected")
        data_log = []
        reading_task = asyncio.create_task(read_process_and_peak(client, data_log))
        await reading_task  # Wait for the reading task to complete (until peak is detected or an error occurs)
        await export_to_csv(data_log)
        client.close()
    else:
        _logger.error("### Failed to connect to the Modbus server")
    _logger.info("### End of Program")


async def main(cmdline=None):
    """Combine setup and run."""
    # Create instrument instance
    _logger.info("### Starting Modbus Client")
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
    _logger.info("### Starting main function")
    asyncio.run(main(), debug=True)