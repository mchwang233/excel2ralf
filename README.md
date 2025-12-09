# excel2ralf

A small utility for converting register definition spreadsheets into [RALF](https://www.veripool.org/projects/verilator/wiki/Verilator) register model blocks.

## Features
- Reads Excel worksheets containing register metadata (BlockName, RegName, RegOffset, Bit, FieldName, Access, ResetValue, Description).
- Forward-fills block, register, and offset values so only the first row of each group needs to be populated.
- Generates RALF blocks with correctly sized fields, access attributes, and optional reset values.

## Requirements
- Python 3.8+
- [pandas](https://pandas.pydata.org/)
- [openpyxl](https://openpyxl.readthedocs.io/en/stable/)

Install dependencies with:

```bash
pip install pandas openpyxl
```

## Usage
From the repository root:

```bash
python excel_to_ralf.py \
    --excel regs.xlsx \
    --sheet Sheet1 \
    --out regs.ralf \
    --bytes 4
```

### Arguments
- `--excel` (required): Path to the input Excel file.
- `--sheet` (default: `0`): Sheet name or index to read.
- `--out` (required): Path where the generated RALF file will be written.
- `--bytes` (default: `4`): Value for the `bytes` attribute in each `block`.
- Run `python excel_to_ralf.py -h` for the latest flag list; the script prints the
  generated file path when finished.

## Excel format
The script expects the following columns:

| Column      | Notes                                               |
| ----------- | --------------------------------------------------- |
| BlockName   | Optional name for grouping registers; default `TOP` |
| RegName     | Register name                                       |
| RegOffset   | Register offset (e.g., `0x0`, `4`)                  |
| Bit         | Bit range (`7:0` or `3`)                            |
| FieldName   | Field name                                          |
| Access      | Access type (`rw`, `ro`, etc.)                      |
| ResetValue  | Optional reset value (supports `0x`, `0b`, decimal) |
| Description | Free-form description (not used in RALF output)     |

Empty `BlockName`, `RegName`, and `RegOffset` cells are forward-filled so you can leave repeated values blank after the first row of a group.

### Minimal working example
Copy the following rows into an Excel worksheet named `Sheet1` and save it as `regs.xlsx`:

| BlockName | RegName | RegOffset | Bit | FieldName | Access | ResetValue | Description      |
| --------- | ------- | --------- | --- | --------- | ------ | ---------- | ---------------- |
| TOP       | CTRL    | 0x0       | 0   | enable    | rw     | 1          | Control register |
|           |         |           | 7:4 | mode      | rw     | 0xA        | Mode select      |

Run:

```bash
python excel_to_ralf.py --excel regs.xlsx --sheet Sheet1 --out regs.ralf
```

Resulting `regs.ralf` (excerpt):

```
block TOP {
  bytes 4;
    register CTRL @'h0 {
        field enable @0 {
           bits 1;
           access rw;
           reset 1'h1;
        }
        field mode @4 {
           bits 4;
           access rw;
           reset 4'hA;
        }
    }
}
```

## Output
The generated RALF groups fields by block and register, emitting field definitions with bit positions, widths, access attributes, and reset values when provided. Offsets are normalized to hexadecimal (e.g., `0x4` becomes `@'h4`).

## Notes
- Invalid or empty `Bit` entries are skipped for that row.
- Reset values are masked to the field width before being emitted.
- `RegOffset` values accept decimal or hex; invalid offsets default to `0`.
- `FieldName` is required per row; rows without a field name are ignored to avoid empty entries.

## License
This project is provided as-is without a specified license.
