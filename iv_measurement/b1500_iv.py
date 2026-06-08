"""
B1500 Semiconductor Parameter Analyzer – IV Measurement Script
================================================================
Hardware:  Keysight B1500A
Device:    2-terminal (e.g. diode, resistor, memristor)
Interface: GPIB via Keysight IO Libraries Suite (GPIB1::17::INSTR)
Setup:     SMU1 (Channel 1) → Terminal+ (force voltage, measure current)
           SMU2 (Channel 2) → Terminal− (grounded reference)

Sweep:     Terminal voltage  -0.5 V → +0.5 V, step 0.01 V (101 points)
Output:    • Matplotlib IV plot (PNG)
           • CSV data file (importable by Origin, Excel, …)
           • Excel workbook (.xlsx)

Requirements (install with `pip install -r requirements.txt`):
    pyvisa, Keysight IO Libraries Suite (provides the VISA backend),
    numpy, matplotlib, pandas, openpyxl

Usage
-----
  python b1500_iv.py                              # real hardware (GPIB1::17)
  python b1500_iv.py --simulate                   # no hardware needed
  python b1500_iv.py --visa "GPIB1::17::INSTR"    # explicit address
  python b1500_iv.py --sample "MyDiode"           # custom device label
"""

import argparse
import csv
import datetime
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Optional: pyvisa import – skipped gracefully in simulation mode
# ---------------------------------------------------------------------------
try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_VISA_ADDRESS  = "GPIB1::17::INSTR"   # Keysight GPIB cable, board 1, address 17

# Temperature controller (change address and query command to match your model)
# Blueforse (default):               GPIB0::12::INSTR, query = "KRDG? A"
# Lakeshore 331/335/336 example:     GPIB0::12::INSTR, query = "KRDG? A"
# Oxford ITC example:                GPIB0::24::INSTR, query = "R1"
DEFAULT_TEMP_ADDRESS  = "GPIB0::12::INSTR"
DEFAULT_TEMP_CMD      = "KRDG? A"   # Blueforse / Lakeshore: read Channel-A temperature (Kelvin)

CHANNEL_PLUS  = 1   # SMU1 – Terminal+ (force voltage, measure current)
CHANNEL_MINUS = 2   # SMU2 – Terminal− (grounded reference)

V_START        = -0.5    # V
V_STOP         =  0.5    # V
V_STEP         =  0.01   # V

COMPLIANCE_I   = 0.1     # A  (100 mA)
COMPLIANCE_V   = 2.0     # V  (used when sourcing current)

INTEGRATION_TIME       = "MED"  # SHORT | MED | LONG  (affects accuracy/speed)
HOLD_TIME              = 0.000  # seconds before sweep starts
STEP_DELAY             = 0.000  # seconds between each sweep step

# Temperature-loop defaults (overridable via CLI)
DEFAULT_CYCLES         = 0      # 0 = run indefinitely until Ctrl-C
DEFAULT_INTERVAL_MIN   = 10     # minutes between consecutive IV measurements


# ---------------------------------------------------------------------------
# B1500Controller
# ---------------------------------------------------------------------------
class B1500Controller:
    """
    Thin wrapper around the B1500A FLEX command set via PyVISA.

    All public methods raise RuntimeError on instrument error so that
    callers can distinguish instrument faults from Python exceptions.
    """

    def __init__(self, visa_address: str, simulate: bool = False):
        self.visa_address = visa_address
        self.simulate = simulate
        self._instrument = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self):
        if self.simulate:
            print("[SIM] Connected (simulation mode – no real hardware)")
            return
        if not PYVISA_AVAILABLE:
            raise ImportError(
                "pyvisa is not installed. Run: pip install pyvisa pyvisa-py"
            )
        rm = pyvisa.ResourceManager()
        self._instrument = rm.open_resource(self.visa_address)
        self._instrument.timeout = 30_000          # 30 s
        self._instrument.read_termination  = "\n"
        self._instrument.write_termination = "\n"
        idn = self._instrument.query("*IDN?")
        print(f"[OK] Connected: {idn.strip()}")

    def disconnect(self):
        if self._instrument:
            self._instrument.close()
            self._instrument = None
        if self.simulate:
            print("[SIM] Disconnected")

    # ------------------------------------------------------------------
    # Low-level send / query helpers
    # ------------------------------------------------------------------
    def write(self, cmd: str):
        if self.simulate:
            return
        self._instrument.write(cmd)

    def query(self, cmd: str) -> str:
        if self.simulate:
            return "0"
        return self._instrument.query(cmd)

    def _check_error(self):
        """Read the B1500 error queue; raise RuntimeError on any fault."""
        if self.simulate:
            return
        resp = self._instrument.query("ERR?")
        code = int(resp.split(",")[0])
        if code != 0:
            raise RuntimeError(f"B1500 error {resp.strip()}")

    # ------------------------------------------------------------------
    # Instrument initialisation
    # ------------------------------------------------------------------
    def reset(self):
        self.write("*RST")
        time.sleep(2)

    def initialise_channels(self):
        """Enable Terminal+ (CH1) and Terminal− (CH2) channels."""
        # CN – connect (power on) channels
        self.write(f"CN {CHANNEL_PLUS},{CHANNEL_MINUS}")

        # Set integration time  (AIT: auto-integration, 2=MED)
        mode_map = {"SHORT": 1, "MED": 2, "LONG": 3}
        n = mode_map.get(INTEGRATION_TIME, 2)
        self.write(f"AIT 2,{n}")        # AIT type,mode

        # Terminal− channel: force 0 V (grounded reference)
        # DV chNum, vRange, voltage, iComp
        self.write(f"DV {CHANNEL_MINUS},0,0,{COMPLIANCE_I}")

        # Output data format: ASCII, one value per line
        self.write("FMT 1,1")

        self._check_error()

    # ------------------------------------------------------------------
    # IV Sweep (staircase)
    # ------------------------------------------------------------------
    def iv_sweep(
        self,
        v_start: float = V_START,
        v_stop:  float = V_STOP,
        v_step:  float = V_STEP,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Perform a staircase voltage sweep on the drain channel and return
        (voltages, currents) as NumPy arrays.

        B1500 FLEX commands used
        ~~~~~~~~~~~~~~~~~~~~~~~~
        MM   – measurement mode (2 = staircase sweep)
        WV   – define staircase voltage sweep
        WT   – wait/hold/delay times
        XE   – execute measurement
        RCV  – read collected data
        """
        n_points = round((v_stop - v_start) / v_step) + 1
        voltages = np.linspace(v_start, v_stop, n_points)

        if self.simulate:
            # Diode-like I-V for realistic simulation
            Is = 1e-9
            n  = 1.5
            Vt = 0.026
            currents = Is * (np.exp(voltages / (n * Vt)) - 1)
            # Add small Gaussian noise
            rng = np.random.default_rng(42)
            currents += rng.normal(0, 1e-10, size=currents.shape)
            return voltages, currents

        # ---- real hardware path ----
        # Measurement mode 2 = staircase sweep, on drain channel
        self.write(f"MM 2,{CHANNEL_DRAIN}")

        # WV chNum, mode, startV, stopV, step, iComp
        #   mode 1 = linear staircase
        self.write(
            f"WV {CHANNEL_DRAIN},1,"
            f"{v_start},{v_stop},{n_points},{COMPLIANCE_I}"
        )

        # Hold / delay times (WT hold, delay, step_delay, trigger_delay, measure_delay)
        self.write(f"WT {HOLD_TIME},{STEP_DELAY}")

        # CMM: current measurement on drain channel
        self.write(f"CMM {CHANNEL_DRAIN},1")   # 1 = compliance-side I

        # Execute sweep
        self.write("XE")
        # Wait for completion (poll status byte or use *OPC?)
        self._instrument.query("*OPC?")        # blocks until done

        # Read raw ASCII data
        raw = self._instrument.read()
        self._check_error()

        # Parse: B1500 returns comma-separated status+value tokens
        # e.g.  "NAI+1.234E-06,NAI+2.345E-06,..."
        currents = self._parse_data(raw, n_points)

        return voltages, currents

    # ------------------------------------------------------------------
    # Data parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_data(raw: str, expected: int) -> np.ndarray:
        """
        Parse B1500 ASCII output (FMT 1,1):
          Each token is  <status><type><value>
          e.g.  "NAI+1.234E-06"
          N = normal, A = A-channel, I = current
        Strip the 3-char header and convert to float.
        """
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        values = []
        for tok in tokens:
            try:
                values.append(float(tok[3:]))   # skip status+channel+unit header
            except (ValueError, IndexError):
                values.append(float("nan"))
        arr = np.array(values, dtype=float)
        if len(arr) != expected:
            print(
                f"[WARN] Expected {expected} points, got {len(arr)}. "
                "Check FLEX output format."
            )
        return arr


# ---------------------------------------------------------------------------
# TemperatureController
# ---------------------------------------------------------------------------
class TemperatureController:
    """
    Generic VISA temperature controller wrapper.

    Works with any instrument that returns a numeric temperature when
    queried with a single SCPI/ASCII command (Lakeshore, Oxford ITC, etc.).

    Parameters
    ----------
    visa_address : str
        VISA resource string for the temperature controller.
    query_cmd : str
        Command sent to read temperature, e.g. "KRDG? A" (Lakeshore) or "R1" (Oxford ITC).
    simulate : bool
        If True, return a synthetic temperature that drifts slowly over time.
    """

    def __init__(
        self,
        visa_address: str = DEFAULT_TEMP_ADDRESS,
        query_cmd: str    = DEFAULT_TEMP_CMD,
        simulate: bool    = False,
    ):
        self.visa_address = visa_address
        self.query_cmd    = query_cmd
        self.simulate     = simulate
        self._instrument  = None
        self._sim_start   = time.monotonic()

    def connect(self):
        if self.simulate:
            print("[SIM] Temperature controller connected (simulation mode)")
            return
        if not PYVISA_AVAILABLE:
            raise ImportError("pyvisa is not installed.")
        rm = pyvisa.ResourceManager()
        self._instrument = rm.open_resource(self.visa_address)
        self._instrument.timeout = 10_000
        self._instrument.read_termination  = "\n"
        self._instrument.write_termination = "\n"
        print(f"[OK] Temperature controller connected: {self.visa_address}")

    def disconnect(self):
        if self._instrument:
            self._instrument.close()
            self._instrument = None
        if self.simulate:
            print("[SIM] Temperature controller disconnected")

    def read_temperature(self) -> float:
        """Return current temperature in Kelvin (or the instrument's native unit)."""
        if self.simulate:
            # Slowly drift from 300 K down – realistic cryostat cool-down
            elapsed_min = (time.monotonic() - self._sim_start) / 60.0
            temp = max(77.0, 300.0 - elapsed_min * 5.0)
            temp += np.random.default_rng().normal(0, 0.05)   # ±0.05 K noise
            return round(temp, 3)

        raw = self._instrument.query(self.query_cmd).strip()
        # Most controllers return a bare float; strip any unit suffix just in case
        try:
            return float(raw.split()[0])
        except ValueError:
            raise RuntimeError(
                f"Could not parse temperature from response: {raw!r}"
            )



def plot_iv(
    voltages: np.ndarray,
    currents: np.ndarray,
    title: str = "IV Characteristic",
    output_path: str | None = None,
):
    """Plot device current vs voltage and optionally save to file."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(title, fontsize=14)

    # ---- Linear scale ----
    ax1 = axes[0]
    ax1.plot(voltages, currents * 1e3, "b-o", markersize=3, linewidth=1.5)
    ax1.axhline(0, color="gray", linewidth=0.7, linestyle="--")
    ax1.axvline(0, color="gray", linewidth=0.7, linestyle="--")
    ax1.set_xlabel("Voltage (V)")
    ax1.set_ylabel("Current (mA)")
    ax1.set_title("Linear Scale")
    ax1.grid(True, alpha=0.4)

    # ---- Log scale (absolute value) ----
    ax2 = axes[1]
    abs_i = np.abs(currents)
    # Avoid log(0) issues
    abs_i = np.where(abs_i < 1e-15, 1e-15, abs_i)
    ax2.semilogy(voltages, abs_i, "r-o", markersize=3, linewidth=1.5)
    ax2.set_xlabel("Voltage (V)")
    ax2.set_ylabel("|Current| (A)")
    ax2.set_title("Semi-log Scale")
    ax2.grid(True, which="both", alpha=0.4)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[OK] Plot saved → {output_path}")
    else:
        plt.show()

    plt.close(fig)


# ---------------------------------------------------------------------------
# Data export  (Origin-compatible CSV)
# ---------------------------------------------------------------------------
def save_data(
    voltages: np.ndarray,
    currents: np.ndarray,
    csv_path: str,
    metadata: dict | None = None,
):
    """
    Save IV data to a CSV file that Origin Software can import directly.

    File layout
    -----------
    # <metadata lines>
    Voltage(V),Current(A),Current(mA)
    -0.5, ...
    ...

    Origin import tip: File → Import → Single ASCII
    Set delimiter = comma, mark comment rows as "Comments",
    the Long-Name row as "Long Names", and the Units row as "Units".
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "Instrument":    "Keysight B1500A",
        "Measurement":   "IV Sweep",
        "Terminal+ CH1": "SMU1 (force V, measure I)",
        "Terminal- CH2": "SMU2 (grounded reference)",
        "Compliance(A)": str(COMPLIANCE_I),
        "V_Start (V)":   str(voltages[0]),
        "V_Stop (V)":    str(voltages[-1]),
        "V_Step (V)":    str(round(voltages[1] - voltages[0], 6)),
        "Points":        str(len(voltages)),
        "Timestamp":     timestamp,
    }
    if metadata:
        meta.update(metadata)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Metadata block (Origin treats lines starting with # as comments)
        for key, val in meta.items():
            writer.writerow([f"# {key}: {val}"])

        # Column headers (Origin "Long Name" row)
        writer.writerow(["Voltage(V)", "Current(A)", "Current(mA)"])

        # Units row (Origin "Units" row — optional but useful)
        writer.writerow(["V", "A", "mA"])

        # Data
        for v, i in zip(voltages, currents):
            writer.writerow([f"{v:.6f}", f"{i:.6e}", f"{i * 1e3:.6e}"])

    print(f"[OK] Data saved  → {csv_path}")


def save_data_xlsx(
    voltages: np.ndarray,
    currents: np.ndarray,
    xlsx_path: str,
):
    """
    Save IV data as an Excel workbook (also importable by Origin).
    Requires openpyxl: pip install openpyxl
    """
    df = pd.DataFrame({
        "Voltage (V)":  voltages,
        "Current (A)":  currents,
        "Current (mA)": currents * 1e3,
    })
    df.to_excel(xlsx_path, index=False, sheet_name="IV_Data")
    print(f"[OK] Excel saved → {xlsx_path}")


# ---------------------------------------------------------------------------
# Main measurement routine  (temperature-loop)
# ---------------------------------------------------------------------------
def run_iv_measurement(
    visa_address:   str   = DEFAULT_VISA_ADDRESS,
    temp_address:   str   = DEFAULT_TEMP_ADDRESS,
    temp_cmd:       str   = DEFAULT_TEMP_CMD,
    simulate:       bool  = False,
    output_dir:     str   = "iv_results",
    sample_name:    str   = "DUT",
    cycles:         int   = DEFAULT_CYCLES,
    interval_min:   float = DEFAULT_INTERVAL_MIN,
):
    """
    Temperature-dependent IV measurement loop.

    Workflow (repeated `cycles` times, or indefinitely if cycles=0)
    ---------------------------------------------------------------
    1. Read temperature from controller
    2. Run IV sweep on B1500 (Terminal+ = CH1, Terminal− = CH2)
    3. Save CSV, XLSX, and PNG tagged with temperature and cycle number
    4. Wait `interval_min` minutes
    5. Go to step 1

    Parameters
    ----------
    visa_address  : VISA address of the B1500A
    temp_address  : VISA address of the temperature controller
    temp_cmd      : SCPI query command for temperature (e.g. "KRDG? A")
    simulate      : If True, use synthetic data (no hardware needed)
    output_dir    : Directory for all output files
    sample_name   : Label for file names and plot titles
    cycles        : Number of IV cycles to run (0 = run until Ctrl-C)
    interval_min  : Minutes to wait between cycles
    """
    os.makedirs(output_dir, exist_ok=True)
    interval_sec = interval_min * 60.0

    # ---- Connect instruments ----
    b1500 = B1500Controller(visa_address, simulate=simulate)
    tc    = TemperatureController(temp_address, temp_cmd, simulate=simulate)

    b1500.connect()
    b1500.reset()
    b1500.initialise_channels()
    tc.connect()

    print(
        f"\n{'='*60}\n"
        f"  Temperature-dependent IV measurement\n"
        f"  Sample    : {sample_name}\n"
        f"  Cycles    : {'∞ (Ctrl-C to stop)' if cycles == 0 else cycles}\n"
        f"  Interval  : {interval_min} min\n"
        f"  Output    : {output_dir}/\n"
        f"{'='*60}\n"
    )

    cycle_num = 0
    try:
        while True:
            cycle_num += 1
            if cycles > 0 and cycle_num > cycles:
                break

            print(f"\n--- Cycle {cycle_num}"
                  + (f"/{cycles}" if cycles > 0 else "") + " ---")

            # Step 1 – Read temperature
            temperature = tc.read_temperature()
            print(f"  Temperature : {temperature:.3f} K")

            # Step 2 – IV sweep
            print(
                f"  IV sweep    : {V_START} V → {V_STOP} V, "
                f"step {V_STEP} V"
            )
            voltages, currents = b1500.iv_sweep(V_START, V_STOP, V_STEP)
            print(f"  I_min       : {currents.min():.4e} A")
            print(f"  I_max       : {currents.max():.4e} A")

            # Step 3 – Save data
            ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            t_tag     = f"{temperature:.1f}K"
            base_name = os.path.join(
                output_dir,
                f"{sample_name}_cycle{cycle_num:03d}_{t_tag}_{ts}"
            )

            extra_meta = {
                "Sample":        sample_name,
                "Cycle":         str(cycle_num),
                "Temperature(K)": f"{temperature:.3f}",
            }

            csv_path  = base_name + "_IV.csv"
            plot_path = base_name + "_IV.png"
            save_data(voltages, currents, csv_path, metadata=extra_meta)

            try:
                xlsx_path = base_name + "_IV.xlsx"
                save_data_xlsx(voltages, currents, xlsx_path)
            except ImportError:
                print("[WARN] openpyxl not installed – skipping Excel export")

            title = (
                f"IV Characteristic – {sample_name}  "
                f"(Cycle {cycle_num}, T = {temperature:.1f} K)"
            )
            plot_iv(voltages, currents, title=title, output_path=plot_path)

            # Step 4 – Wait before next cycle (skip after last cycle)
            if cycles == 0 or cycle_num < cycles:
                print(
                    f"\n  Waiting {interval_min} min until next cycle "
                    f"(Ctrl-C to stop)…"
                )
                _interruptible_sleep(interval_sec)

    except KeyboardInterrupt:
        print("\n[INFO] Measurement loop interrupted by user.")

    finally:
        b1500.disconnect()
        tc.disconnect()

    print(f"\n[DONE] {cycle_num} cycle(s) completed. "
          f"All files saved in: {output_dir}/")


def _interruptible_sleep(seconds: float, tick: float = 5.0):
    """Sleep for `seconds` total, waking every `tick` s to allow KeyboardInterrupt."""
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(tick, remaining))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "B1500 temperature-dependent IV measurement: "
            "read T → IV sweep → save → wait → repeat"
        )
    )
    parser.add_argument(
        "--visa",
        default=DEFAULT_VISA_ADDRESS,
        help=f"VISA address of the B1500A (default: {DEFAULT_VISA_ADDRESS})",
    )
    parser.add_argument(
        "--temp-visa",
        default=DEFAULT_TEMP_ADDRESS,
        help=f"VISA address of the temperature controller (default: {DEFAULT_TEMP_ADDRESS})",
    )
    parser.add_argument(
        "--temp-cmd",
        default=DEFAULT_TEMP_CMD,
        help=f"Query command to read temperature (default: '{DEFAULT_TEMP_CMD}')",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode (no hardware required)",
    )
    parser.add_argument(
        "--output-dir",
        default="iv_results",
        help="Output directory for all files (default: iv_results)",
    )
    parser.add_argument(
        "--sample",
        default="DUT",
        help="Sample / device-under-test name (used in file names)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=DEFAULT_CYCLES,
        help="Number of IV cycles to run (default: 0 = run until Ctrl-C)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_MIN,
        help=f"Minutes between consecutive IV measurements (default: {DEFAULT_INTERVAL_MIN})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_iv_measurement(
        visa_address  = args.visa,
        temp_address  = args.temp_visa,
        temp_cmd      = args.temp_cmd,
        simulate      = args.simulate,
        output_dir    = args.output_dir,
        sample_name   = args.sample,
        cycles        = args.cycles,
        interval_min  = args.interval,
    )
