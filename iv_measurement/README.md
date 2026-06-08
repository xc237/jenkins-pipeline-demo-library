# B1500A Temperature-Dependent IV Measurement

Automated temperature-dependent drain-to-source IV sweep using the
Keysight B1500A Semiconductor Parameter Analyzer over GPIB, with a
temperature controller read at every cycle.

---

## What this script does

`b1500_iv.py` runs a fully automated, repeating measurement loop designed for
studying how a device's current–voltage (IV) characteristic changes with
temperature (for example during a cryostat cool-down or warm-up).

**Step-by-step loop (repeats every 10 minutes by default)**

```
1. Read temperature  ──► query Blueforse controller via GPIB → get value in Kelvin
2. IV sweep          ──► B1500A forces V from −0.5 V to +0.5 V in 101 steps
                         at each step it measures the resulting current (SMU1)
                         while SMU2 holds Terminal− at 0 V (grounded reference)
3. Save outputs      ──► three files written per cycle (CSV, XLSX, PNG)
                         file names are tagged with cycle number, temperature,
                         and a datetime stamp so each cycle is uniquely identified
4. Wait interval     ──► script sleeps for the configured interval (default 10 min)
5. Repeat            ──► goes back to step 1 for the next cycle
                         runs indefinitely (Ctrl-C to stop) or for a fixed number
                         of cycles when --cycles N is passed
```

**What "IV sweep" means physically**  
SMU1 (Channel 1) is connected to the positive terminal of the device under test.  
It ramps the voltage from −0.5 V to +0.5 V in 101 equal steps (step size 0.01 V)  
and measures the current flowing through the device at each voltage step.  
SMU2 (Channel 2) is connected to the negative terminal and is held at 0 V,  
acting as the grounded reference.  
The result is an IV curve: current (in amps, converted to mA for display) as a  
function of applied voltage.

**VISA / driver architecture (two layers)**  
There are two separate components needed to talk to the hardware:

| Layer | What it is | How it is installed |
|---|---|---|
| Keysight IO Libraries Suite | Low-level VISA backend — the driver DLL that communicates with the GPIB hardware | Download and install from Keysight's website |
| `pyvisa` (Python package) | Python wrapper that calls into the Keysight VISA backend | `pip install pyvisa` via `requirements.txt` |

Both are required. IO Libraries Suite alone gives no Python API. `pyvisa` alone
(without a backend) raises `VisaIOError: Cannot find any VISA implementation`.

**Simulation mode**  
Pass `--simulate` to run without any hardware. The script generates a synthetic
diode-like IV curve (exponential model with small Gaussian noise) and a
temperature that drifts slowly from 300 K down to 77 K. All three output files
are still written exactly as in real mode, so you can test the full pipeline
offline.

---

**Workflow (repeats every 10 minutes by default)**
```
Read temperature → IV sweep → Save CSV / XLSX / PNG → Wait → Repeat
```

---

## Hardware setup

| Role          | Instrument          | Channel / Address       |
|---------------|---------------------|-------------------------|
| SMU1 Terminal+| B1500A SMU1         | Channel 1 – force V, measure I |
| SMU2 Terminal−| B1500A SMU2         | Channel 2 – grounded reference |
| B1500A        | Keysight B1500A     | `GPIB1::17::INSTR`      |
| Temp. ctrl.   | Blueforse           | `GPIB0::12::INSTR`      |

- Connect the PC to both instruments with **Keysight GPIB cables**.  
- Install **Keysight IO Libraries Suite** – this provides the VISA backend.  
- Confirm GPIB address of B1500 is **17** (front panel: System → GPIB).  
- Confirm GPIB address of the temperature controller and set `--temp-visa`.

---

## Installation (Windows)

> **This script is designed to run on Windows.** The instructions below use Windows Command Prompt (`cmd`) and PowerShell. Run all commands from the `iv_measurement\` folder.

It is best practice to install Python dependencies inside a **virtual environment** rather than globally, so project packages don't conflict with your system Python or other projects.

**Command Prompt (cmd)**
```cmd
:: 1. Create a virtual environment (one-time setup)
python -m venv .venv

:: 2. Activate it
.venv\Scripts\activate.bat

:: 3. Install dependencies
pip install -r requirements.txt
```

**PowerShell**
```powershell
# 1. Create a virtual environment (one-time setup)
python -m venv .venv

# 2. Activate it
# Note: if you get an execution-policy error, first run:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

> After activation your shell prompt shows `(.venv)` — all `python` and `pip` commands now operate inside the isolated environment.  
> To deactivate when you're done: run `deactivate`.

**What each package does:**

| Package | Version | Purpose |
|---|---|---|
| `pyvisa` | ≥ 1.13 | Python wrapper that calls into the Keysight VISA backend to send GPIB commands to the B1500A and temperature controller |
| `numpy` | ≥ 1.24 | Generates the voltage sweep array; stores and processes current readings as numeric arrays |
| `matplotlib` | ≥ 3.7 | Draws the two-panel IV plot (linear + semi-log) and saves it as a PNG |
| `pandas` | ≥ 2.0 | Builds a tidy table from the sweep data, used for CSV and Excel export |
| `openpyxl` | ≥ 3.1 | Write engine that pandas uses to create the `.xlsx` Excel workbook |

> **Important — two-layer VISA setup:**  
> `pyvisa` (installed via pip) is the **Python API layer**.  
> Keysight IO Libraries Suite (installed separately from Keysight's website) is the **hardware backend** — the driver DLL that physically talks to the GPIB interface.  
> Both must be installed. `pyvisa` alone cannot communicate with hardware; IO Libraries Suite alone provides no Python API.  
> No `pyvisa-py` is needed — PyVISA auto-detects the Keysight backend once IO Libraries Suite is installed.

---

## Sweep parameters (edit `b1500_iv.py` to change)

| Parameter           | Value          |
|---------------------|----------------|
| Start voltage       | −0.5 V         |
| Stop voltage        | +0.5 V         |
| Step size           | 0.01 V         |
| Points              | 101            |
| Current compliance  | 100 mA         |
| Integration time    | MED            |
| Interval between IV | 10 min         |

---

## Running a measurement (Windows)

> All examples below are for **Windows**. Run them from the `iv_measurement\` folder with the virtual environment active (prompt shows `(.venv)`).  
> **Line-continuation character:** `^` in Command Prompt, `` ` `` in PowerShell.

### All CLI options and their defaults

| Option          | Default              | Description                                  |
|-----------------|----------------------|----------------------------------------------|
| `--visa`        | `GPIB1::17::INSTR`   | B1500A VISA address                          |
| `--temp-visa`   | `GPIB0::12::INSTR`   | Temperature controller VISA address          |
| `--temp-cmd`    | `KRDG? A`            | Query command to read temperature            |
| `--sample`      | `DUT`                | Device name (used in file names)             |
| `--cycles`      | `0` (infinite)       | Number of IV cycles; 0 = run until Ctrl-C   |
| `--interval`    | `10`                 | Minutes between cycles                       |
| `--output-dir`  | `iv_results`         | Output directory for CSV / XLSX / PNG files  |
| `--simulate`    | off (flag)           | Synthetic data mode, no hardware needed      |

---

### 1 — Minimal call (all defaults)

Omitting every argument uses the defaults shown in the table above:  
B1500A at `GPIB1::17::INSTR`, temperature controller at `GPIB0::12::INSTR`,  
sample name `DUT`, 10-minute interval, infinite cycles, output to `iv_results\`.

**Command Prompt**
```cmd
python b1500_iv.py
```

**PowerShell**
```powershell
python b1500_iv.py
```

---

### 2 — Real hardware, custom addresses and sample name, run indefinitely

Supply the GPIB addresses that match your bench setup. Press **Ctrl-C** to stop.

**Command Prompt**
```cmd
python b1500_iv.py ^
    --visa      "GPIB1::17::INSTR" ^
    --temp-visa "GPIB0::12::INSTR" ^
    --temp-cmd  "KRDG? A" ^
    --sample    "Diode_A1"
```

**PowerShell**
```powershell
python b1500_iv.py `
    --visa      "GPIB1::17::INSTR" `
    --temp-visa "GPIB0::12::INSTR" `
    --temp-cmd  "KRDG? A" `
    --sample    "Diode_A1"
```

> `--cycles` is omitted → defaults to `0` (infinite).  
> `--interval` is omitted → defaults to `10` minutes between cycles.  
> `--output-dir` is omitted → files are saved to `iv_results\`.

---

### 3 — Real hardware, fixed number of cycles with custom interval

**Command Prompt**
```cmd
python b1500_iv.py --sample "Diode_A1" --cycles 5 --interval 10
```

**PowerShell**
```powershell
python b1500_iv.py --sample "Diode_A1" --cycles 5 --interval 10
```

> `--cycles 5` → stops automatically after 5 IV sweeps.  
> `--interval 10` → 10 minutes between each sweep (same as the default, shown explicitly for clarity).  
> `--visa` / `--temp-visa` omitted → uses default GPIB addresses.

---

### 4 — Real hardware, custom output directory

**Command Prompt**
```cmd
python b1500_iv.py --sample "Diode_A1" --output-dir "C:\Data\RunA"
```

**PowerShell**
```powershell
python b1500_iv.py --sample "Diode_A1" --output-dir "C:\Data\RunA"
```

> All CSV / XLSX / PNG files for this run are written to `C:\Data\RunA\`.

---

### 5 — Simulation mode (no instruments required)

Use this to verify the full pipeline (file writing, plots) without any hardware connected.

**Command Prompt**
```cmd
python b1500_iv.py --simulate --sample "Test" --cycles 3 --interval 1
```

**PowerShell**
```powershell
python b1500_iv.py --simulate --sample "Test" --cycles 3 --interval 1
```

> `--simulate` → generates a synthetic diode IV curve with slow temperature drift (300 K → 77 K). No GPIB connection is attempted.  
> `--cycles 3` → runs exactly 3 cycles then exits.  
> `--interval 1` → only 1 minute between cycles, so the test completes quickly.  
> All three output files (CSV, XLSX, PNG) are still written exactly as in real mode.

---

## Temperature controller query commands

The temperature controller used in this setup is from **Blueforse**.

| Model            | `--temp-cmd`   | Notes                         |
|------------------|----------------|-------------------------------|
| Blueforse        | `KRDG? A`      | Channel A in Kelvin           |
| Lakeshore 331/335/336 | `KRDG? A` | Channel A in Kelvin           |
| Lakeshore 340    | `KRDG? A`      | Same syntax                   |
| Oxford ITC 503   | `R1`           | Sensor 1 temperature          |
| Cryocon 22C      | `INPUT A:TEMP?`| Channel A                     |

---

## Output files

All files are written to `iv_results/` (or `--output-dir`).  
Each cycle produces three files tagged with cycle number and temperature:

```
iv_results/
  Diode_A1_cycle001_295.3K_20260608_120000_IV.csv
  Diode_A1_cycle001_295.3K_20260608_120000_IV.xlsx
  Diode_A1_cycle001_295.3K_20260608_120000_IV.png
  Diode_A1_cycle002_290.1K_20260608_121012_IV.csv
  ...
```

**File name format:**  
`<sample>_cycle<NNN>_<T>K_<YYYYMMDD>_<HHMMSS>_IV.<ext>`

| Part | Example | Meaning |
|---|---|---|
| `sample` | `Diode_A1` | Value of `--sample` |
| `cycleNNN` | `cycle001` | Cycle number, zero-padded to 3 digits |
| `<T>K` | `295.3K` | Temperature in Kelvin at cycle start |
| datetime | `20260608_120000` | Date and time the cycle started |
| ext | `.csv` / `.xlsx` / `.png` | File type |

---

### Sample CSV file content

Each CSV has a metadata header (lines starting with `#`), a column name row,
a units row, and then one data row per voltage step.

```csv
# Instrument: Keysight B1500A
# Measurement: IV Sweep
# Temperature (K): 295.3
# Sample: Diode_A1
# Cycle: 1
# Terminal+ CH1: SMU1 (force V, measure I)
# Terminal- CH2: SMU2 (grounded reference)
# Compliance(A): 0.1
# V_Start (V): -0.5
# V_Stop (V): 0.5
# V_Step (V): 0.01
# Points: 101
# Timestamp: 2026-06-08 12:00:00
Voltage(V),Current(A),Current(mA)
V,A,mA
-0.500000,-9.999231e-10,-9.999231e-07
-0.490000,-9.931842e-10,-9.931842e-07
-0.480000,-9.864325e-10,-9.864325e-07
...
0.000000,1.023400e-09,1.023400e-06
...
0.480000,3.421870e-04,3.421870e-01
0.490000,4.187620e-04,4.187620e-01
0.500000,5.123450e-04,5.123450e-01
```

- **Row 1–13** (`# …`): metadata — Origin treats these as comment rows.
- **Row 14** (`Voltage(V),Current(A),Current(mA)`): column long names.
- **Row 15** (`V,A,mA`): units row — Origin maps these to column units automatically.
- **Row 16 onward**: one measurement per voltage step (101 rows total for the default −0.5 V to +0.5 V sweep).
- Currents in the forward-bias region (positive V) grow exponentially; in reverse bias they are near the leakage floor (~1 nA for a silicon diode).

---

### Sample XLSX file content

The Excel workbook contains a single sheet called **`IV_Data`** with three
columns and 101 data rows (plus a header row):

| Voltage (V) | Current (A)  | Current (mA) |
|-------------|--------------|--------------|
| −0.500000   | −9.999231e-10| −9.999231e-07|
| −0.490000   | −9.931842e-10| −9.931842e-07|
| …           | …            | …            |
| 0.500000    | 5.123450e-04 | 5.123450e-01 |

The XLSX does not include the `#` metadata header rows — it is a clean
data-only table, making it easy to chart directly in Excel or import into
Origin.

---

### Sample PNG plot

Each PNG contains a **two-panel figure** saved at 150 DPI:

| Panel | X axis | Y axis | Scale |
|---|---|---|---|
| Left | Voltage (V) | Current (mA) | Linear |
| Right | Voltage (V) | \|Current\| (A) | Semi-log (log₁₀) |

The linear panel shows the classic diode S-curve; the semi-log panel makes
the exponential forward current and the flat reverse leakage floor both
clearly visible in one plot.

---

### Origin import tip (CSV)
1. **File → Import → Single ASCII**  
2. Set delimiter to **comma**.  
3. Mark the `#` comment rows as **Comments**, the `Voltage(V)…` row as
   **Long Names**, and the `V, A, mA` row as **Units**.  
4. Click OK – Origin auto-creates X/Y columns with units.

To overlay multiple temperature curves in Origin:
- Import all CSVs into the same workbook (File → Import → Multiple ASCII)
- Select all Current(mA) columns → Insert → Graph → Line

---

## Verifying the GPIB connections (quick test)

```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())                    # lists all detected instruments

# B1500A
b = rm.open_resource("GPIB1::17::INSTR")
print(b.query("*IDN?"))                       # Keysight Technologies,B1500A,...
b.close()

# Temperature controller (adjust address)
t = rm.open_resource("GPIB0::12::INSTR")
print(t.query("KRDG? A"))                     # e.g.  295.123
t.close()
```
