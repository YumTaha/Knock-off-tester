## 🔌 How to Connect via SSH (using VS Code)

To run the code on the RevPi, you'll need to connect to it remotely using SSH. Here's how:

1. **Plug the RevPi into your network using an Ethernet cable.**
2. **Install VS Code** (if you haven’t already)
3. **Install the "Remote - SSH" extension** in VS Code
4. **Open the Command Palette** in VS Code (Ctrl+Shift+P)
5. Choose `Remote-SSH: Connect to Host...`
6. Enter the connection string:
   ```bash
   pi@revpi111323.local
   ```
7. When prompted, use the password:  `9glmsp`
8. Once connected, open the project folder and run the Python script from the terminal.

---

# 🦷 Mechanical Tooth Knock-Off Tester  
## 📘 What This Project Is For

This machine was built to **automatically knock off teeth from circular saw blades** and record how much force it takes. The goal is to **test how strong the welds are** between the blade and the teeth.

It uses a **linear actuator** to slowly push into a tooth, while a **strain gauge** measures the force. Once the tooth pops off (or the actuator reaches the end), it logs the data and resets for the next test.

---

## 🧰 What’s Inside the Machine

### 1. **Linear Actuator**
- Physically pushes into the saw tooth.
- Has a built-in potentiometer to track its position (how far it's moved).
- Controlled by a **RevPi Connect 4** + **RevPi MIO**.

### 2. **Strain Gauge (Omega DP400S)**
- Measures the force applied when the actuator pushes.
- Connected using **Modbus RTU** on `/dev/ttyRS485`.

### 3. **RevPi (Revolution Pi)**
- Acts as the brain of the machine.
- Runs the Python code.
- Handles motor control, position tracking, and data collection.

---

## 📁 Files You Should Know

| File | What It Does |
|------|--------------|
| `mechanical_tester.py` | Main script that runs everything – moves the actuator, reads force, detects when a tooth breaks off, and saves data. |
| `calibration.py` | Converts raw analog values from the actuator into position (in mm) using the calibration data. |
| `config.json` | Calibration data: maps analog voltage to real-world position in mm. |

---

## 🔄 What Happens During a Test

1. **The actuator moves to the "home" position** (safe starting spot).
2. **It takes a few readings from the strain gauge** to understand the "baseline" (no stress) condition.
3. **The actuator slowly pushes into a saw tooth.**
4. While pushing:
   - It records how much force is being applied.
   - If the force spikes above a set value, it means the tooth has been contacted.
   - When the tooth breaks off and the force drops, it stops.
5. **The actuator returns to the home position.**
6. The test data is saved as:
   - A **CSV file** (with timestamps, positions, and force values).
   - A **plot image** showing stress vs position.

---

## 🖥️ How to Run the Test

### 1. Start the script:

```bash
python3 mechanical_tester.py
```

### 2. Type a command when prompted:

| Command | What It Does |
|---------|---------------|
| `test`  | Runs one full knock-off test |
| `pos`   | Shows the current actuator position |
| `home`  | Sends the actuator to its home position |
| `help`  | Lists all available commands |
| `quit`  | Stops the script safely |

---

## 🧪 Where the Data Goes

After every successful test:

- CSV files go in: `tests/csv/mechanical_test_<number>.csv`
- Plots go in: `tests/plot/test_plot_<number>.png`

Each CSV has:
- Timestamp
- Actuator position (mm)
- Force (stress) change from baseline
- Peak stress seen

Each plot shows:
- How force changed as the actuator moved
- The peak force at tooth contact or breakage

---

## 🧠 What’s Special About This Machine

- It’s **automated**: no need to manually push anything.
- It’s **safe and repeatable**: same position, speed, and force detection every time.
- It **saves and plots all test data**, so you can analyze how strong each weld was.

---

## 🛠️ Calibration (Important!)

The machine needs to know how far it’s moving. The actuator sends back a voltage, which gets converted to mm using calibration.

### Calibration Data File:
`config.json`:
```json
{
  "analogs_mv": [221, 310, 380, ..., 1073],
  "positions_mm": [30.3, 41.4, 50.8, ..., 146.5]
}
```

These values are used in `calibration.py` to:
- Convert **voltage → mm**: `analog_to_mm()`
- Convert **mm → voltage**: `mm_to_analog()`

Don’t mess with this unless you re-calibrate the actuator!

---

## 🚨 Safety and Troubleshooting

| Problem | What to Check |
|--------|----------------|
| No force data | Make sure strain gauge is powered and connected |
| Actuator doesn’t move | Check RevPi, wiring, and power supply |
| Test ends too early | Maybe the force didn’t go above the contact threshold |
| No tooth was detected | Tooth might’ve already been broken off, or not aligned right |

---

## 💻 Software Dependencies

Install these Python packages (if not already):

```bash
pip install revpimodio2 pymodbus simple-pid numpy pandas matplotlib
```

---

## ✅ Final Notes for the Next Student

- Run this machine in a **well-aligned test setup**.
- Always **reset between tests** using the `home` command.
- Check CSVs and plots to verify results.
- If things break or stop working, **read the log messages** – they’re there to help.
- Feel free to improve the script – like adding automation for running many cycles!

Good luck with your weld testing! 🛠️🦷💥
