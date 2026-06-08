# Researcher's Guide to the IV Measurement Script

**Who this is for:** Researchers who will use this script to collect data in the lab.  
No programming knowledge is needed to follow this guide.

---

## What does this script do?

The script automatically measures how electrical current flows through your device (for example a diode or a transistor) as the voltage across it is changed — this is called an **IV curve** (Current–Voltage curve).

It does this repeatedly over time, recording the temperature of your device at the start of every measurement. This lets you see how the device's electrical behaviour changes as it cools down or warms up — for example during a cryostat experiment.

Every time the script completes one measurement it saves three files automatically:
- A **spreadsheet** (Excel `.xlsx`) — open in Excel or Origin
- A **data file** (`.csv`) — open in Origin, Excel, or any text editor
- A **plot image** (`.png`) — a ready-made graph you can put in a report

---

## What hardware is involved?

You need two instruments connected to your PC via GPIB cables:

| Instrument | What it does |
|---|---|
| **Keysight B1500A** | The precision source-measure unit — it applies voltage to your device and measures the resulting current |
| **Temperature controller** (Blueforse or Lakeshore) | Reads the temperature of your device at the start of each measurement cycle |

Your device (diode, transistor, etc.) is connected to the B1500A with probe cables:
- **Channel 1 (SMU1) → positive terminal** of your device — the script sweeps voltage here
- **Channel 2 (SMU2) → negative terminal** of your device — held at 0 V as a reference

The script runs on a Windows PC. It sends instructions to the B1500A and temperature controller over the GPIB cables, exactly as if you were pressing buttons on their front panels — but automatically.

---

## What does one measurement cycle look like?

Each cycle follows these four steps, then repeats:

```
Step 1 ─ Read temperature
          The script asks the temperature controller: "what is the temperature right now?"
          It records the answer in Kelvin.

Step 2 ─ IV sweep
          The B1500A ramps the voltage across your device from −0.5 V up to +0.5 V
          in 101 small steps (0.01 V each).
          At every step it measures the current flowing through the device.

Step 3 ─ Save files
          Three files are written (CSV, Excel, PNG) labelled with the cycle number,
          temperature, and date/time so you always know which file belongs to which run.

Step 4 ─ Wait
          The script pauses for 10 minutes (by default) before starting the next cycle.
          You can change this wait time — see below.
```

This loop runs indefinitely until you press **Ctrl-C** to stop it, or until a fixed number of cycles you specify is reached.

---

## Before you start: one-time setup

> You only need to do this once on the measurement PC.

**1. Install Python**  
Download Python 3.11 or newer from [python.org](https://www.python.org) and install it.  
During installation tick the box **"Add Python to PATH"**.

**2. Install Keysight IO Libraries Suite**  
Download from Keysight's website and install it. This is the driver that allows the PC to talk to the GPIB instruments. Without it the script cannot communicate with any hardware.

**3. Open Command Prompt and navigate to the script folder**

Press **Win + R**, type `cmd`, press Enter. Then type:
```
cd C:\path\to\iv_measurement
```
(Replace `C:\path\to\iv_measurement` with the actual folder where the script lives.)

**4. Create a virtual environment and install the script's dependencies**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```
You will see `(.venv)` appear at the start of the prompt — this means the environment is active.  
You only need to do steps 3–4 once. After that, just activate the environment each session:
```cmd
.venv\Scripts\activate.bat
```

**5. Confirm the GPIB addresses**  
- B1500A address: check on the front panel → System → GPIB. It should be **17**.  
- Temperature controller address: check its display or manual. Default assumed is **12**.

---

## Running a measurement

All commands below are typed in Command Prompt with the `.venv` active (you see `(.venv)` in the prompt). Make sure you are in the `iv_measurement` folder.

---

### Quickest start — use all defaults

```cmd
python b1500_iv.py
```

This uses:
- B1500A at GPIB address 17
- Temperature controller at GPIB address 12, queried with `KRDG? A`
- Sample name `DUT`
- 10-minute interval between cycles
- Runs forever until you press **Ctrl-C**
- Saves files to a folder called `iv_results` (created automatically)

---

### Give your sample a name (recommended)

The sample name is used in every file name and plot title. Always set it so your files are clearly identified.

```cmd
python b1500_iv.py --sample "Diode_A1"
```

Files will be named like: `Diode_A1_cycle001_295.3K_20260608_120000_IV.csv`

---

### Run a fixed number of cycles then stop automatically

```cmd
python b1500_iv.py --sample "Diode_A1" --cycles 5
```

The script runs exactly 5 measurement cycles and then exits on its own. Useful when you know how many sweeps you need.

---

### Change the wait time between cycles

```cmd
python b1500_iv.py --sample "Diode_A1" --interval 15
```

Waits 15 minutes between cycles instead of the default 10. Use a shorter interval if your temperature is changing quickly; use a longer one if it is stable and you don't need dense time sampling.

---

### Save files to a specific folder

```cmd
python b1500_iv.py --sample "Diode_A1" --output-dir "C:\Data\RunA"
```

All output files go to `C:\Data\RunA\`. The folder is created automatically if it doesn't exist.

---

### Use non-default GPIB addresses

If your B1500A or temperature controller is at a different address than the defaults:

```cmd
python b1500_iv.py --sample "Diode_A1" --visa "GPIB1::14::INSTR" --temp-visa "GPIB0::22::INSTR"
```

---

### Use a different temperature controller query command

Different temperature controller models use different commands to return temperature:

| Controller model | `--temp-cmd` value |
|---|---|
| Blueforse (default) | `KRDG? A` |
| Lakeshore 331 / 335 / 336 | `KRDG? A` |
| Lakeshore 340 | `KRDG? A` |
| Oxford ITC 503 | `R1` |
| Cryocon 22C | `INPUT A:TEMP?` |

```cmd
python b1500_iv.py --sample "Diode_A1" --temp-cmd "R1"
```

---

### Test the script without any hardware connected

If you want to check that the script, file saving, and plots all work before going into the lab:

```cmd
python b1500_iv.py --simulate --sample "Test" --cycles 3 --interval 1
```

`--simulate` generates a realistic synthetic diode IV curve and a slowly drifting temperature. All three output files are still written exactly as in a real measurement. The `--interval 1` means only 1 minute between cycles, so the test finishes quickly.

---

## Understanding the output files

All files are saved in `iv_results\` (or your chosen `--output-dir`).  
After a run you will find files named like:

```
Diode_A1_cycle001_295.3K_20260608_120000_IV.csv
Diode_A1_cycle001_295.3K_20260608_120000_IV.xlsx
Diode_A1_cycle001_295.3K_20260608_120000_IV.png
Diode_A1_cycle002_290.1K_20260608_121012_IV.csv
...
```

The file name always tells you:

| Part | Example | Meaning |
|---|---|---|
| Sample name | `Diode_A1` | What you typed in `--sample` |
| Cycle number | `cycle001` | First measurement = 001, second = 002, … |
| Temperature | `295.3K` | Temperature in Kelvin at the start of this cycle |
| Date and time | `20260608_120000` | 8 June 2026 at 12:00:00 |

### The PNG plot

Each cycle produces a two-panel figure:

- **Left panel (linear scale):** the classic S-shaped diode curve — current in milliamps on the vertical axis, voltage on the horizontal axis. Good for seeing the turn-on voltage and forward current.
- **Right panel (semi-log scale):** the same data with the current axis on a logarithmic scale. This makes it easy to see both the tiny reverse leakage current (flat floor) and the rapidly growing forward current on the same plot.

### The Excel file

One sheet called `IV_Data` with three columns:
- Voltage (V)
- Current (A)
- Current (mA)

101 rows of data per cycle (one per voltage step). Ready to chart directly in Excel.

### The CSV file

The same data as the Excel file, but in plain text. The first several lines start with `#` and contain metadata (instrument name, temperature, compliance, sweep range, timestamp). Origin Software can import these files directly with the metadata assigned to comment/long-name/units rows.

---

## All options at a glance

| What you type | Default if omitted | What it controls |
|---|---|---|
| `--sample "Name"` | `DUT` | Label used in file names and plot titles |
| `--cycles 5` | `0` (runs forever) | How many sweeps to run before stopping |
| `--interval 15` | `10` | Minutes to wait between sweeps |
| `--output-dir "C:\Data"` | `iv_results` | Folder where files are saved |
| `--visa "GPIB1::17::INSTR"` | `GPIB1::17::INSTR` | GPIB address of the B1500A |
| `--temp-visa "GPIB0::12::INSTR"` | `GPIB0::12::INSTR` | GPIB address of the temperature controller |
| `--temp-cmd "KRDG? A"` | `KRDG? A` | Command used to query the temperature |
| `--simulate` | off | Runs with fake data — no hardware needed |

---

## Stopping the script

- **To stop immediately:** press **Ctrl-C** in the Command Prompt window. The script will finish cleanly, disconnect from the instruments, and report how many cycles were completed.
- **To let it finish on its own:** use `--cycles N` to set a fixed number of cycles. The script exits automatically after the last cycle.

---

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `Cannot find any VISA implementation` | Keysight IO Libraries Suite is not installed | Download and install it from Keysight's website |
| `pyvisa is not installed` | Python dependencies were not installed | Run `pip install -r requirements.txt` with the venv active |
| `VisaIOError: GPIB ...` | The instrument is not responding at that address | Check the GPIB address on the front panel and update `--visa` or `--temp-visa` |
| Files not appearing | Script ran but crashed before saving | Read the error message in the terminal; check GPIB connections |
| `(.venv)` not showing | Virtual environment is not active | Run `.venv\Scripts\activate.bat` again |

---

## Quick-start checklist

Before every measurement session:

- [ ] Instruments are on and GPIB cables are connected to the PC
- [ ] Device is connected to B1500A SMU1 (Terminal+) and SMU2 (Terminal−)
- [ ] Command Prompt is open, navigate to `iv_measurement` folder
- [ ] Virtual environment is active — prompt shows `(.venv)`
- [ ] Run `python b1500_iv.py --sample "YourSampleName"` and watch the first cycle complete
- [ ] Check `iv_results\` for the CSV, XLSX, and PNG files

Press **Ctrl-C** when the experiment is finished.
