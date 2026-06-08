# B1500A Temperature-Dependent IV Measurement

Automated temperature-dependent drain-to-source IV sweep using the
Keysight B1500A Semiconductor Parameter Analyzer over GPIB, with a
temperature controller read at every cycle.

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

## Installation

```bash
pip install -r requirements.txt
```

> **No `pyvisa-py` needed.** PyVISA finds the Keysight VISA backend
> automatically once IO Libraries Suite is installed.

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

## Running a measurement

### Real hardware – run indefinitely (Ctrl-C to stop)
```bash
python b1500_iv.py \
    --visa      "GPIB1::17::INSTR" \
    --temp-visa "GPIB0::12::INSTR" \
    --temp-cmd  "KRDG? A" \
    --sample    "Diode_A1"
```

### Real hardware – run a fixed number of cycles
```bash
python b1500_iv.py --sample "Diode_A1" --cycles 5 --interval 10
```

### Simulation (no instruments required)
```bash
python b1500_iv.py --simulate --sample "Test" --cycles 3 --interval 1
```

### All CLI options
| Option          | Default              | Description                                  |
|-----------------|----------------------|----------------------------------------------|
| `--visa`        | `GPIB1::17::INSTR`   | B1500A VISA address                          |
| `--temp-visa`   | `GPIB0::12::INSTR`   | Temperature controller VISA address          |
| `--temp-cmd`    | `KRDG? A`            | Query command to read temperature            |
| `--sample`      | `DUT`                | Device name (used in file names)             |
| `--cycles`      | `0` (infinite)       | Number of IV cycles; 0 = run until Ctrl-C   |
| `--interval`    | `10`                 | Minutes between cycles                       |
| `--output-dir`  | `iv_results`         | Output directory                             |
| `--simulate`    | off                  | Synthetic data mode, no hardware needed      |

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
