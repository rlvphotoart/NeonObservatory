from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd


DEFAULT_OUTPUT_NAME = "signal_check_results.xlsx"

REFERENCE_REQUIRED = ["Signal long name", "Signal short name", "Report event"]
LOGS_REQUIRED = ["triggerOrContext", "message"]

# Important: 0 is a valid value, not empty.
NULL_STRINGS = {"", "null", "none", "empty", "[null]", "nan", "n/a", "na"}


@dataclass
class CheckConfig:
    reference_path: str
    logs_path: str
    output_path: str
    export_debug: bool = True


def read_table(file_path: str) -> pd.DataFrame:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(file_path)
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix == ".tsv":
        return pd.read_csv(file_path, sep="\t")
    raise ValueError(f"Unsupported file type: {suffix}")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(value).lower())


def is_null_like(value: Any) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    if isinstance(value, list):
        if len(value) == 0:
            return True
        return all(is_null_like(item) for item in value)

    if isinstance(value, tuple):
        if len(value) == 0:
            return True
        return all(is_null_like(item) for item in value)

    if isinstance(value, str):
        text = value.strip().lower()
        return text in NULL_STRINGS

    return False


def clean_for_excel(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    if value is None:
        return ""
    return str(value)


def candidate_keys_from_reference(
    signal_long_name: str,
    signal_short_name: str = "",
    signal_name: str = "",
) -> list[tuple[str, str]]:
    """
    Returns deterministic candidates only.
    Each item: (candidate_key, strategy)
    """
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(candidate: str, strategy: str) -> None:
        candidate = normalize_text(candidate)
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append((candidate, strategy))

    long_name = normalize_text(signal_long_name)
    short_name = normalize_text(signal_short_name)
    full_signal_name = normalize_text(signal_name)

    if long_name:
        add(long_name, "signal_long_name_exact")
        add(long_name[:1].lower() + long_name[1:] if long_name else long_name, "signal_long_name_lower_first")
        add(long_name.replace("_", ""), "signal_long_name_no_underscore")

        if long_name.startswith("DurationSpeedRange_"):
            suffix = long_name.replace("DurationSpeedRange_", "", 1)
            if suffix == "0":
                add("durationSpeedRange0", "duration_speed_special")
            elif suffix == "More_120":
                add("durationSpeedRangeMore120", "duration_speed_special")
            else:
                parts = suffix.split("_")
                if len(parts) == 2 and all(part.isdigit() for part in parts):
                    add(f"durationSpeedRangeBetween{parts[0]}And{parts[1]}", "duration_speed_special")

    if short_name:
        add(short_name, "signal_short_name_exact")

    if full_signal_name:
        add(full_signal_name.split("/")[-1], "signal_name_leaf")

    return candidates


def build_data_key_index(data_dict: dict[str, Any]) -> dict[str, str]:
    """canonical -> original"""
    index: dict[str, str] = {}
    for key in data_dict.keys():
        index[canonical_key(key)] = key
    return index


def find_signal_in_message(
    raw_message: str,
    signal_long_name: str,
    signal_short_name: str = "",
    signal_name: str = "",
) -> tuple[bool, Any, str, str]:
    """
    Returns:
        matched(bool),
        value(any),
        matched_key(str),
        strategy(str)
    """
    if not isinstance(raw_message, str) or not raw_message.strip():
        return False, None, "", "empty_message"

    try:
        payload = json.loads(raw_message)
    except Exception:
        return False, None, "", "invalid_json"

    data = payload.get("data")
    if not isinstance(data, dict):
        return False, None, "", "missing_data_dict"

    key_index = build_data_key_index(data)

    for candidate, strategy in candidate_keys_from_reference(signal_long_name, signal_short_name, signal_name):
        ckey = canonical_key(candidate)
        if ckey in key_index:
            real_key = key_index[ckey]
            return True, data.get(real_key), real_key, strategy

    return False, None, "", "no_matching_data_key"


def validate_reference_columns(df: pd.DataFrame) -> None:
    cols = {normalize_text(c) for c in df.columns}
    missing = [c for c in REFERENCE_REQUIRED if normalize_text(c) not in cols]
    if missing:
        raise ValueError(f"Reference file is missing required columns: {missing}")


def validate_logs_columns(df: pd.DataFrame) -> None:
    cols = {normalize_text(c) for c in df.columns}
    missing = [c for c in LOGS_REQUIRED if normalize_text(c) not in cols]
    if missing:
        raise ValueError(f"Logs file is missing required columns: {missing}")


def load_reference_file(path: str) -> pd.DataFrame:
    df = read_table(path)
    validate_reference_columns(df)
    return df.rename(columns=lambda x: normalize_text(x))


def load_logs_file(path: str) -> pd.DataFrame:
    df = read_table(path)
    validate_logs_columns(df)
    return df.rename(columns=lambda x: normalize_text(x))


def create_preview_text(reference_df: Optional[pd.DataFrame], logs_df: Optional[pd.DataFrame]) -> str:
    lines: list[str] = []

    if reference_df is not None:
        lines.append("=== REFERENCE (CCS) ===")
        lines.append(f"Rows: {len(reference_df)}")
        lines.append(f"Columns: {list(reference_df.columns)}")
        lines.append(reference_df.head(8).to_string(index=False))
        lines.append("")

    if logs_df is not None:
        lines.append("=== LOGS (UU) ===")
        lines.append(f"Rows: {len(logs_df)}")
        lines.append(f"Columns: {list(logs_df.columns)}")
        lines.append(logs_df.head(5).to_string(index=False))
        lines.append("")

    if reference_df is None and logs_df is None:
        lines.append("No files loaded yet.")

    return "\n".join(lines)


def run_signal_check(
    reference_df: pd.DataFrame,
    logs_df: pd.DataFrame,
    config: CheckConfig,
    progress_callback: Optional[Callable[[str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference_df = reference_df.copy()
    logs_df = logs_df.copy()

    reference_df = reference_df.fillna("")
    logs_df = logs_df.fillna("")

    reference_df = reference_df[
        (reference_df["Report event"].astype(str).str.strip() != "")
        & (reference_df["Signal long name"].astype(str).str.strip() != "")
    ].copy()

    logs_df["triggerOrContext"] = logs_df["triggerOrContext"].astype(str).map(normalize_text)
    logs_df["message"] = logs_df["message"].astype(str)

    summary_rows: list[dict[str, Any]] = []
    debug_rows: list[dict[str, Any]] = []

    total = len(reference_df)

    if log_callback:
        log_callback("Initializing analysis engine...")
        log_callback(f"Reference rows eligible for processing: {total}")
        log_callback(f"Log rows loaded: {len(logs_df)}")

    for idx, (_, ref_row) in enumerate(reference_df.iterrows(), start=1):
        trigger = normalize_text(ref_row["Report event"])
        signal_long = normalize_text(ref_row["Signal long name"])
        signal_short = normalize_text(ref_row.get("Signal short name", ""))
        signal_name = normalize_text(ref_row.get("Signal name", ""))

        if progress_callback:
            progress_callback(f"Processing {idx}/{total}: {signal_long}")

        trigger_logs = logs_df[logs_df["triggerOrContext"] == trigger].copy()
        trigger_occurrences = len(trigger_logs)

        signal_occurrences = 0
        null_occurrences = 0
        values_seen: list[str] = []
        matched_keys: set[str] = set()
        strategies: set[str] = set()

        for occ_idx, (_, log_row) in enumerate(trigger_logs.iterrows(), start=1):
            matched, value, matched_key, strategy = find_signal_in_message(
                raw_message=log_row["message"],
                signal_long_name=signal_long,
                signal_short_name=signal_short,
                signal_name=signal_name,
            )

            is_null = False
            if matched:
                signal_occurrences += 1
                matched_keys.add(matched_key)
                strategies.add(strategy)

                if is_null_like(value):
                    null_occurrences += 1
                    is_null = True

                values_seen.append(clean_for_excel(value))

            if config.export_debug:
                debug_rows.append(
                    {
                        "Trigger": trigger,
                        "Signal long name": signal_long,
                        "Signal short name": signal_short,
                        "Signal name": signal_name,
                        "Occurrence Index": occ_idx,
                        "Trigger Occurrences": trigger_occurrences,
                        "Matched Signal": "YES" if matched else "NO",
                        "Matched Key": matched_key,
                        "Match Strategy": strategy,
                        "Extracted Value": clean_for_excel(value),
                        "Is Null / Empty": "YES" if is_null else "NO",
                        "Raw Message": log_row["message"],
                    }
                )

        present = "YES" if signal_occurrences > 0 else "NO"

        if trigger_occurrences == 0:
            status = "TRIGGER NOT FOUND"
        elif signal_occurrences == 0:
            status = "SIGNAL NOT FOUND"
        else:
            status = "FOUND"

        summary_rows.append(
            {
                "Trigger": trigger,
                "Signal long name": signal_long,
                "Signal short name": signal_short,
                "Signal name": signal_name,
                "Trigger Occurrences": trigger_occurrences,
                "Signal Occurrences": signal_occurrences,
                "Null/Empty Occurrences": null_occurrences,
                "Present in Logs": present,
                "Matched Key(s)": " | ".join(sorted(k for k in matched_keys if k)),
                "Match Strategy": " | ".join(sorted(s for s in strategies if s)),
                "Values Seen": " | ".join(values_seen),
                "Status": status,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    debug_df = pd.DataFrame(debug_rows)

    write_output(Path(config.output_path), summary_df, debug_df, config.export_debug)

    if log_callback:
        log_callback("Analysis completed.")
        log_callback(f"Summary rows: {len(summary_df)}")
        if config.export_debug:
            log_callback(f"Debug rows: {len(debug_df)}")
        log_callback(f"Saved to: {config.output_path}")

    return summary_df, debug_df


def write_output(
    output_path: Path,
    summary_df: pd.DataFrame,
    debug_df: pd.DataFrame,
    export_debug: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Summary")

        if export_debug:
            debug_df.to_excel(writer, index=False, sheet_name="Debug")

        readme = pd.DataFrame(
            [
                {"Field": "Logic", "Value": "Rows are matched by Report event = triggerOrContext."},
                {
                    "Field": "Signal match",
                    "Value": "Signal is searched only inside JSON data keys, using deterministic aliases from Signal long name / Signal name / Signal short name.",
                },
                {"Field": "Occurrence", "Value": "Signal Occurrences = number of trigger messages where the signal key was found."},
                {"Field": "Values", "Value": "Values Seen contains all extracted values in occurrence order."},
                {"Field": "Null rule", "Value": "0 is valid. None, empty string, EMPTY, NaN, [null], [] are treated as null/empty."},
                {"Field": "Status", "Value": "FOUND / SIGNAL NOT FOUND / TRIGGER NOT FOUND."},
            ]
        )
        readme.to_excel(writer, index=False, sheet_name="Read Me")

    auto_format_excel(output_path)


def auto_format_excel(output_path: Path) -> None:
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, PatternFill

        wb = load_workbook(output_path)

        header_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
        found_fill = PatternFill(fill_type="solid", fgColor="E8F5E9")
        missing_fill = PatternFill(fill_type="solid", fgColor="FDE9E7")
        warn_fill = PatternFill(fill_type="solid", fgColor="FFF4CC")

        for ws in wb.worksheets:
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = header_fill

            for column_cells in ws.columns:
                max_len = 0
                letter = column_cells[0].column_letter

                for cell in column_cells:
                    value = "" if cell.value is None else str(cell.value)
                    if len(value) > max_len:
                        max_len = len(value)

                ws.column_dimensions[letter].width = min(max_len + 2, 60)

            if ws.title == "Summary":
                headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[1])}
                status_col = headers.get("Status")

                if status_col:
                    for row in range(2, ws.max_row + 1):
                        cell = ws.cell(row=row, column=status_col)
                        if cell.value == "FOUND":
                            cell.fill = found_fill
                        elif cell.value == "SIGNAL NOT FOUND":
                            cell.fill = warn_fill
                        elif cell.value == "TRIGGER NOT FOUND":
                            cell.fill = missing_fill

        wb.save(output_path)
    except Exception:
        pass