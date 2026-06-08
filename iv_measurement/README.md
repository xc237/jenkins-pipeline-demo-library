# B1500A IV Measurement

Automated drain-to-source IV sweep using the Keysight B1500A Semiconductor
Parameter Analyzer over GPIB.

---

## Hardware setup

| Role   | SMU    | B1500 channel | GPIB                     |
|--------|--------|---------------|--------------------------|
| Drain  | SMU1   | Channel 1     | `GPIB1::17::INSTR`       |
| Source | SMU2   | Channel 2     | (same instrument, grounded) |

- Connect the PC to the B1500A with a **Keysight GPIB cable** (board index 1).  
- Install **Keysight IO Libraries Suite** – this provides the VISA backend that
  PyVISA uses automatically.  
- Confirm the GPIB address of the instrument is **17** (check from the B1500
  front panel: System → GPIB).

---

## Installation

```bash
pip install -r requirements.txt
```

> **No `pyvisa-py` needed.** PyVISA will find the Keysight VISA backend
> automatically once IO Libraries Suite is installed.

---

## Sweep parameters (edit `b1500_iv.py` to change)

| Parameter        | Value          |
|------------------|----------------|
| Start voltage    | −0.5 V         |
| Stop voltage     | +0.5 V         |
| Step size        | 0.01 V         |
| Points           | 101            |
| Current compliance | 100 mA       |
| Integration time | MED            |

---

## Running a measurement

### Real hardware
```bash
python b1500_iv.py --sample "Diode_A1"
```

### Simulation (no instrument required)
```bash
python b1500_iv.py --simulate --sample "Test"
```

### Custom VISA address
```bash
python b1500_iv.py --visa "GPIB1::17::INSTR" --sample "MyDUT"
```

---

## Output files

All files are written to `iv_results/` (created automatically):

| File                        | Format | Import into Origin?          |
|-----------------------------|--------|------------------------------|
| `<sample>_<ts>_IV.csv`      | CSV    | ✅ File → Import → ASCII     |
| `<sample>_<ts>_IV.png`      | PNG    | ✅ Insert → Graph             |
| `<sample>_<ts>_IV.xlsx`     | Excel  | ✅ File → Import → Excel     |

### Origin import tip (CSV)
1. **File → Import → Single ASCII**  
2. Set delimiter to **comma**.  
3. Mark the `#` comment rows as **Comments**, the `Voltage(V)…` row as
   **Long Names**, and the `V, A, mA` row as **Units**.  
4. Click OK – Origin auto-creates X/Y columns.

---

## Verifying the GPIB connection (quick test)

```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())          # should show 'GPIB1::17::INSTR'
inst = rm.open_resource("GPIB1::17::INSTR")
print(inst.query("*IDN?"))          # Keysight Technologies,B1500A,...
inst.close()
```
