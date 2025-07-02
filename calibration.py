import json
import numpy as np

def load_calibration(filename="config.json"):
    with open(filename, "r") as f:
        data = json.load(f)
    return np.array(data["analogs_mv"]), np.array(data["positions_mm"])

def analog_to_mm(analog_mv, analogs_mv, positions_mm):
    # Clamp to calibration range for safety
    analog_mv = np.clip(analog_mv, analogs_mv.min(), analogs_mv.max())
    return float(np.interp(analog_mv, analogs_mv, positions_mm))

def mm_to_analog(position_mm, analogs_mv, positions_mm):
    # Clamp to calibration range for safety
    position_mm = np.clip(position_mm, positions_mm.min(), positions_mm.max())
    return float(np.interp(position_mm, positions_mm, analogs_mv))

if __name__ == "__main__":
    analogs_mv, positions_mm = load_calibration()
    print("Analog 403 mV --> {:.2f} mm".format(analog_to_mm(403, analogs_mv, positions_mm)))
    print("Position 54.5 mm --> {:.2f} mV".format(mm_to_analog(54.5, analogs_mv, positions_mm)))
