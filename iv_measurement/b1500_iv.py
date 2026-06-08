"""
B1500 Semiconductor Parameter Analyzer – IV Measurement Script
================================================================
Hardware:  Keysight B1500A
Interface: GPIB via Keysight IO Libraries Suite (GPIB1::17::INSTR)
Setup:     SMU1 (Channel 1) → Drain
           SMU2 (Channel 2) → Source (grounded)

Sweep:     Drain voltage  -0.5 V → +0.5 V, step 0.01 V (101 points)
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
DEFAULT_VISA_ADDRESS = "GPIB1::17::INSTR"   # Keysight GPIB cable, board 1, address 17
CHANNEL_DRAIN  = 1   # SMU1 – drain
CHANNEL_SOURCE = 2   # SMU2 – source (forced to 0 V)

V_START        = -0.5    # V
V_STOP         =  0.5    # V
V_STEP         =  0.01   # V

COMPLIANCE_I   = 0.1     # A  (100 mA)
COMPLIANCE_V   = 2.0     # V  (used when sourcing current)

INTEGRATION_TIME = "MED"  # SHORT | MED | LONG  (affects accuracy/speed)
HOLD_TIME        = 0.000  # seconds before sweep starts
STEP_DELAY       = 0.000  # seconds between each sweep step


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
        """Enable drain (CH1) and source (CH2) channels."""
        # CN – connect (power on) channels
        self.write(f"CN {CHANNEL_DRAIN},{CHANNEL_SOURCE}")

        # Set integration time  (AIT: auto-integration, 2=MED)
        mode_map = {"SHORT": 1, "MED": 2, "LONG": 3}
        n = mode_map.get(INTEGRATION_TIME, 2)
        self.write(f"AIT 2,{n}")        # AIT type,mode

        # Source channel: force 0 V (ground the source)
        # DV chNum, vRange, voltage, iComp
        self.write(f"DV {CHANNEL_SOURCE},0,0,{COMPLIANCE_I}")

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
# Plotting
# ---------------------------------------------------------------------------
def plot_iv(
    voltages: np.ndarray,
    currents: np.ndarray,
    title: str = "IV Characteristic",
    output_path: str | None = None,
):
    """Plot drain current vs drain voltage and optionally save to file."""
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
    Set delimiter = comma, mark row 1 as "Comments", row 2 as "Long Names".
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "Instrument":  "Keysight B1500A",
        "Measurement": "IV Sweep",
        "Drain (CH1)": "SMU1",
        "Source (CH2)":"SMU2 (grounded)",
        "V_Start (V)": str(voltages[0]),
        "V_Stop (V)":  str(voltages[-1]),
        "V_Step (V)":  str(round(voltages[1] - voltages[0], 6)),
        "Points":      str(len(voltages)),
        "Timestamp":   timestamp,
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
# Main measurement routine
# ---------------------------------------------------------------------------
def run_iv_measurement(
    visa_address: str = DEFAULT_VISA_ADDRESS,
    simulate: bool = False,
    output_dir: str = ".",
    sample_name: str = "DUT",
):
    """
    Full end-to-end IV measurement workflow.

    Parameters
    ----------
    visa_address : str
        VISA resource string, e.g. "GPIB0::17::INSTR" or
        "USB0::0x0957::0x0B0B::MY12345678::INSTR"
    simulate : bool
        If True, generate synthetic data instead of talking to hardware.
    output_dir : str
        Directory for output files (created if absent).
    sample_name : str
        Label used in file names and plot titles.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.join(output_dir, f"{sample_name}_{timestamp}")

    controller = B1500Controller(visa_address, simulate=simulate)

    try:
        # ---- Setup ----
        controller.connect()
        controller.reset()
        controller.initialise_channels()

        # ---- Sweep ----
        print(
            f"\nStarting IV sweep: {V_START} V → {V_STOP} V, "
            f"step {V_STEP} V  ({round((V_STOP - V_START) / V_STEP) + 1} points)"
        )
        voltages, currents = controller.iv_sweep(V_START, V_STOP, V_STEP)
        print(f"  Min current: {currents.min():.4e} A")
        print(f"  Max current: {currents.max():.4e} A")

    finally:
        controller.disconnect()

    # ---- Save data ----
    csv_path  = base_name + "_IV.csv"
    plot_path = base_name + "_IV.png"
    save_data(voltages, currents, csv_path, metadata={"Sample": sample_name})

    try:
        xlsx_path = base_name + "_IV.xlsx"
        save_data_xlsx(voltages, currents, xlsx_path)
    except ImportError:
        print("[WARN] openpyxl not installed – skipping Excel export")

    # ---- Plot ----
    title = f"IV Characteristic – {sample_name}"
    plot_iv(voltages, currents, title=title, output_path=plot_path)

    print(f"\n[DONE] All output files in: {output_dir}/")
    return voltages, currents


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _parse_args():
    parser = argparse.ArgumentParser(
        description="B1500 IV Measurement – drain voltage sweep"
    )
    parser.add_argument(
        "--visa",
        default=DEFAULT_VISA_ADDRESS,
        help=f"VISA resource address (default: {DEFAULT_VISA_ADDRESS})",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode (no instrument required)",
    )
    parser.add_argument(
        "--output-dir",
        default="iv_results",
        help="Output directory for CSV, PNG, and XLSX files (default: iv_results)",
    )
    parser.add_argument(
        "--sample",
        default="DUT",
        help="Sample / device-under-test name (used in file names)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_iv_measurement(
        visa_address=args.visa,
        simulate=args.simulate,
        output_dir=args.output_dir,
        sample_name=args.sample,
    )
