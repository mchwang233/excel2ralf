#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
把 Excel（BlockName, RegName, RegOffset, Bit, FieldName, Access, ResetValue, Description）
转换成 RALF 寄存器模型。

依赖：
    pip install pandas openpyxl

用法示例：
    python excel_to_ralf.py \
        --excel regs.xlsx \
        --sheet Sheet1 \
        --out regs.ralf
"""

import argparse
from pathlib import Path

import pandas as pd


def sanitize(s):
    """把 NaN/None 变成空串，其余转成 str。"""
    if pd.isna(s):
        return ""
    return str(s)


def parse_bit_range(bit_str):
    """
    解析 Bit 字段，支持：
        "7:0" -> (7, 0)
        "3"   -> (3, 3)
    Bit 为空或非法时抛 ValueError，由调用方决定是否跳过。
    """
    if pd.isna(bit_str):
        raise ValueError("Bit 列为空")

    bit_str = str(bit_str).strip()
    if not bit_str:
        raise ValueError("Bit 列为空字符串")

    if ":" in bit_str:
        hi_s, lo_s = bit_str.split(":", 1)
        return int(hi_s), int(lo_s)
    else:
        b = int(bit_str)
        return b, b


def parse_reset_value(rv_str):
    """
    把 ResetValue 转成整数，用于合成寄存器 reset。
    支持 "0x1", "1", "0b1" 这种；失败返回 None。
    """
    s = str(rv_str).strip()
    if not s:
        return None
    try:
        return int(s, 0)
    except Exception:
        return None


def load_excel(path, sheet):
    df = pd.read_excel(path, sheet_name=sheet)
    required = [
        "BlockName",
        "RegName",
        "RegOffset",
        "Bit",
        "FieldName",
        "Access",
        "ResetValue",
        "Description",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少列: {missing}")

    # 关键修改：向下填充 BlockName/RegName/RegOffset/Hierarchy，
    # 以支持只在首行填写，其余行留空的写法
    for col in ["BlockName", "RegName", "RegOffset", "Hierarchy"]:
        if col in df.columns:
            df[col] = df[col].ffill()

    return df


def generate_ralf(df, bytes_per_word=4):
    """
    根据 8 列格式生成符合目标风格的 RALF：

    block <BlockName> {
      bytes 4;
      register REGNAME @'hOFFSET { ... }
    }
    """
    lines = []
    first_block = True

    # 按 BlockName 分组
    for block_name, block_df in df.groupby("BlockName", sort=False):
        block_name = sanitize(block_name) or "TOP"

        # 针对当前 block 读取 Hierarchy 列（如果存在），取该 block 中第一行的值
        # 生成供 field 名称使用的后门前缀，例如：`PRCM_hierarchyU_apb_slvtop.slvif.ff_regb_ddrc_ch0_lpddr5
        hierarchy_macro = ""
        hierarchy_inst = ""
        if "Hierarchy" in block_df.columns:
            first_h = sanitize(block_df["Hierarchy"].iloc[0])
            if first_h:
                hierarchy_macro = f"`{block_name}_hierarchy{first_h}"
                hierarchy_inst = first_h

        if not first_block:
            lines.append("")
        first_block = False

    # block 头部 + bytes 行（例如：block DWC_ddrctl_axi_0_AXI_Port0_block {\n  bytes 4;）
        lines.append(f"block {block_name} {{")
        lines.append(f"  bytes {bytes_per_word};")

    # 在 block 内按 (RegName, RegOffset) 分寄存器
        for (reg_name, offset), reg_df in block_df.groupby(
            ["RegName", "RegOffset"], sort=False
        ):
            reg_name = sanitize(reg_name)
            offset = sanitize(offset)

            # 解析 offset 为整数，再转为不带 0x 的 hex，用于 @'hXXX
            try:
                offset_int = int(str(offset).strip(), 0)
            except Exception:
                offset_int = 0
            offset_hex = format(offset_int, "X")  # 不带 0x 的大写 HEX

            # 输出寄存器头
            lines.append(f"    register {reg_name} @'h{offset_hex} {{")

            # 为该寄存器生成字段
            for _, row in reg_df.iterrows():
                base_fname = sanitize(row["FieldName"])
                fname = base_fname
                if not fname:
                    continue

                # 如果字段名为 reserved（忽略大小写），则不生成该 field
                if base_fname.strip().lower() == "reserved":
                    continue

                bit_raw = row["Bit"]
                try:
                    hi, lo = parse_bit_range(bit_raw)
                except ValueError:
                    # Bit 非法或为空，不生成该 field
                    continue

                width = hi - lo + 1
                lsb = lo

                faccess = str(row["Access"]).strip() or "rw"
                faccess = faccess.lower()
                # 如果为只读 "r"，输出为 "ro" 以符合 RALF 访问类型习惯
                if faccess == "r":
                    faccess = "ro"

                # reset: 使用 WIDTH'hHEX 形式
                rv_int = parse_reset_value(row["ResetValue"])
                reset_str = None
                if rv_int is not None:
                    # 对当前 field 的 reset 按位宽截断
                    mask = (1 << width) - 1
                    rv_field = rv_int & mask
                    reset_str = f"{width}'h{rv_field:X}"

                # 如果存在 Hierarchy 信息，则将 field 名扩展为
                #   field <原始字段名> (<Hierarchy 实例路径>) @<lsb> {
                # 例如：field lpddr5 (U_apb_slvtop.slvif.ff_regb_ddrc_ch0_lpddr5) @3 {
                if "Hierarchy" in reg_df.columns:
                    h_val = sanitize(row["Hierarchy"])
                    if h_val:
                        fname = f"{base_fname} ({h_val})"

                lines.append(f"        field {fname} @{lsb} {{")
                lines.append(f"           bits {width};")
                lines.append(f"           access {faccess};")
                if reset_str is not None:
                    lines.append(f"           reset {reset_str};")
                lines.append("        }")

            lines.append("    }")
            lines.append("")

        lines.append("}")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Excel -> RALF converter")
    p.add_argument("--excel", required=True, help="输入 Excel 文件路径")
    p.add_argument("--sheet", default=0, help="Sheet 名称或索引，默认 0")
    p.add_argument("--out", required=True, help="输出 RALF 文件路径")
    p.add_argument("--bytes", type=int, default=4, help="block bytes 属性，默认 4")
    args = p.parse_args()

    df = load_excel(args.excel, args.sheet)
    ralf_text = generate_ralf(df, bytes_per_word=args.bytes)
    Path(args.out).write_text(ralf_text, encoding="utf-8")
    print(f"生成 RALF: {args.out}")


if __name__ == "__main__":
    main()
