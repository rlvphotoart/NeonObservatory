from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import customtkinter as ctk
import pandas as pd
from tkinter import filedialog, messagebox

from signal_checker_core import (
    DEFAULT_OUTPUT_NAME,
    CheckConfig,
    create_preview_text,
    load_logs_file,
    load_reference_file,
    run_signal_check,
)

APP_TITLE = "NEON_OBSERVATORY | Signal Analysis"

# Theme colors inspired by Stitch
BG = "#0a0e14"
SURFACE = "#151a21"
SURFACE_HIGH = "#1b2028"
SURFACE_LOW = "#0f141a"
PRIMARY = "#69daff"
PRIMARY_STRONG = "#00c0ea"
SECONDARY = "#45fec9"
TEXT = "#f1f3fc"
TEXT_MUTED = "#a8abb3"
OUTLINE = "#44484f"
ERROR = "#ff716c"
WARNING = "#ffd166"


class SignalCheckerModernUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1440x900")
        self.minsize(1220, 780)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.configure(fg_color=BG)

        self.reference_df: Optional[pd.DataFrame] = None
        self.logs_df: Optional[pd.DataFrame] = None

        self.reference_path_var = ctk.StringVar()
        self.logs_path_var = ctk.StringVar()
        self.output_path_var = ctk.StringVar()
        self.export_debug_var = ctk.BooleanVar(value=True)
        self.default_export_debug_var = ctk.BooleanVar(value=True)

        self.status_var = ctk.StringVar(value="Ready for deep-scan analysis.")
        self.last_analysis_var = ctk.StringVar(value="N/A")
        self.signal_health_var = ctk.StringVar(value="0.0%")

        self.reference_rows_var = ctk.StringVar(value="0")
        self.logs_rows_var = ctk.StringVar(value="0")
        self.eligible_signals_var = ctk.StringVar(value="0")
        self.last_output_var = ctk.StringVar(value="Not generated yet")
        self.last_run_summary_var = ctk.StringVar(value="No analysis executed yet")
        self.appearance_mode_var = ctk.StringVar(value="Dark")

        self.current_page = "signal_analysis"
        self.last_summary_df: Optional[pd.DataFrame] = None
        self.last_debug_df: Optional[pd.DataFrame] = None

        self.session_logs: list[str] = []
        self.ui_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.dashboard_stat_labels: dict[str, ctk.CTkLabel] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_sidebar()
        self._build_main_container()

        self.after(100, self._process_ui_queue)

        self._log("Initializing NEON_OBSERVATORY Core Modules...")
        self._log("Kernel handshake successful. Interface synchronized.")
        self._log("Awaiting user trigger for RUN_CHECK sequence...")

        self.refresh_all_views()
        self.switch_page("signal_analysis")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_topbar(self) -> None:
        topbar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, height=56)
        topbar.grid(row=0, column=0, columnspan=2, sticky="nsew")
        topbar.grid_columnconfigure(0, weight=1)
        topbar.grid_propagate(False)

        left = ctk.CTkFrame(topbar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=18, pady=10)

        title = ctk.CTkLabel(
            left,
            text="NEON_OBSERVATORY",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=PRIMARY_STRONG,
        )
        title.pack(side="left", padx=(4, 0))

        right = ctk.CTkFrame(topbar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=18, pady=10)

        ctk.CTkButton(
            right,
            text="Settings",
            width=90,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            text_color=TEXT,
            command=lambda: self.switch_page("settings"),
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            right,
            text="Help",
            width=70,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            text_color=TEXT,
            command=self._show_help,
        ).pack(side="left", padx=6)

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=250, fg_color=SURFACE, corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(8, weight=1)
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="COMMAND_CENTER",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=PRIMARY_STRONG,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 2))

        ctk.CTkLabel(
            sidebar,
            text="V.2.1.0-STABLE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 20))

        items = [
            ("dashboard", "Dashboard"),
            ("live_stream", "Live Stream"),
            ("signal_analysis", "Signal Analysis"),
            ("file_explorer", "File Explorer"),
            ("settings", "Settings"),
        ]

        for i, (key, label) in enumerate(items, start=2):
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                height=42,
                anchor="w",
                corner_radius=10,
                fg_color="transparent",
                hover_color=SURFACE_HIGH,
                text_color=TEXT_MUTED,
                command=lambda k=key: self.switch_page(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=14, pady=6)
            self.nav_buttons[key] = btn

        ctk.CTkButton(
            sidebar,
            text="Support",
            height=40,
            anchor="w",
            corner_radius=10,
            fg_color="transparent",
            hover_color=SURFACE_HIGH,
            text_color=TEXT_MUTED,
            command=self._show_help,
        ).grid(row=9, column=0, sticky="ew", padx=14, pady=6)

        ctk.CTkButton(
            sidebar,
            text="Exit",
            height=40,
            anchor="w",
            corner_radius=10,
            fg_color="transparent",
            hover_color=SURFACE_HIGH,
            text_color=ERROR,
            command=self.destroy,
        ).grid(row=10, column=0, sticky="ew", padx=14, pady=(0, 20))

    def _build_main_container(self) -> None:
        self.main_container = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main_container.grid(row=1, column=1, sticky="nsew", padx=18, pady=18)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.pages["dashboard"] = self._build_dashboard_page()
        self.pages["live_stream"] = self._build_live_stream_page()
        self.pages["signal_analysis"] = self._build_signal_analysis_page()
        self.pages["file_explorer"] = self._build_file_explorer_page()
        self.pages["settings"] = self._build_settings_page()

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def _build_dashboard_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.main_container, fg_color="transparent", corner_radius=0)
        page.grid_rowconfigure(2, weight=1)
        page.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="DASHBOARD",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PRIMARY_STRONG,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Operational overview for the current session.",
            font=ctk.CTkFont(size=14),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        stats_row = ctk.CTkFrame(page, fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        stats_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.dashboard_stat_labels["reference_rows"] = self._create_dashboard_stat_card(
            stats_row, 0, "Reference Rows", self.reference_rows_var, PRIMARY
        )
        self.dashboard_stat_labels["logs_rows"] = self._create_dashboard_stat_card(
            stats_row, 1, "Log Rows", self.logs_rows_var, SECONDARY
        )
        self.dashboard_stat_labels["eligible"] = self._create_dashboard_stat_card(
            stats_row, 2, "Eligible Signals", self.eligible_signals_var, WARNING
        )
        self.dashboard_stat_labels["health"] = self._create_dashboard_stat_card(
            stats_row, 3, "Signal Health", self.signal_health_var, PRIMARY_STRONG
        )

        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(content, fg_color=SURFACE, corner_radius=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="SESSION OVERVIEW",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 12))

        overview = ctk.CTkFrame(left, fg_color=SURFACE_LOW, corner_radius=14)
        overview.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
        overview.grid_columnconfigure(1, weight=1)

        self.dashboard_last_time = self._overview_row(overview, 0, "Last Analysis Time", self.last_analysis_var)
        self.dashboard_last_output = self._overview_row(overview, 1, "Last Output", self.last_output_var)
        self.dashboard_last_run = self._overview_row(overview, 2, "Last Run Summary", self.last_run_summary_var)

        self.dashboard_terminal = ctk.CTkTextbox(
            left,
            fg_color=SURFACE_LOW,
            corner_radius=14,
            border_width=1,
            border_color=OUTLINE,
            text_color=TEXT,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.dashboard_terminal.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.dashboard_terminal.configure(state="disabled")

        right = ctk.CTkFrame(content, fg_color=SURFACE, corner_radius=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="QUICK ACTIONS",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 12))

        ctk.CTkButton(
            right,
            text="Go to Signal Analysis",
            height=42,
            fg_color=PRIMARY_STRONG,
            hover_color=PRIMARY,
            text_color=BG,
            command=lambda: self.switch_page("signal_analysis"),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=6)

        ctk.CTkButton(
            right,
            text="Open File Explorer",
            height=42,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=lambda: self.switch_page("file_explorer"),
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=6)

        ctk.CTkButton(
            right,
            text="Open Live Stream",
            height=42,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=lambda: self.switch_page("live_stream"),
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=6)

        ctk.CTkButton(
            right,
            text="Refresh Dashboard",
            height=42,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.refresh_all_views,
        ).grid(row=4, column=0, sticky="ew", padx=18, pady=6)

        info_box = ctk.CTkTextbox(
            right,
            height=250,
            fg_color=SURFACE_LOW,
            corner_radius=12,
            border_width=1,
            border_color=OUTLINE,
            text_color=TEXT_MUTED,
            wrap="word",
        )
        info_box.grid(row=5, column=0, sticky="nsew", padx=18, pady=(18, 18))
        info_box.insert(
            "1.0",
            "Dashboard ideas implemented:\n\n"
            "- Live operational stats\n"
            "- Session summary\n"
            "- Quick navigation\n"
            "- Recent activity log\n\n"
            "This page gives you a manager-style cockpit view over the current analysis session."
        )
        info_box.configure(state="disabled")

        return page

    def _build_live_stream_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.main_container, fg_color="transparent", corner_radius=0)
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="LIVE STREAM",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PRIMARY_STRONG,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top,
            text="Realtime session console and execution events.",
            font=ctk.CTkFont(size=14),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")

        ctk.CTkButton(
            actions,
            text="Refresh Stream",
            width=130,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.refresh_all_views,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            actions,
            text="Clear Stream",
            width=120,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.clear_logs,
        ).pack(side="left", padx=6)

        stream_card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        stream_card.grid(row=1, column=0, sticky="nsew")
        stream_card.grid_rowconfigure(1, weight=1)
        stream_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            stream_card,
            text="SYSTEM EVENT STREAM",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 12))

        self.live_stream_text = ctk.CTkTextbox(
            stream_card,
            fg_color=SURFACE_LOW,
            corner_radius=14,
            border_width=1,
            border_color=OUTLINE,
            text_color=TEXT,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.live_stream_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.live_stream_text.configure(state="disabled")

        return page

    def _build_signal_analysis_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.main_container, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        self._build_stats_row(page)
        self._build_config_row(page)
        self._build_status_bar(page)
        self._build_terminal(page)

        return page

    def _build_file_explorer_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.main_container, fg_color="transparent", corner_radius=0)
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="FILE EXPLORER",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PRIMARY_STRONG,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Open selected files and inspect current paths.",
            font=ctk.CTkFont(size=14),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ctk.CTkButton(
            header,
            text="Refresh",
            width=120,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.refresh_all_views,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        self.file_rows = {}
        row_idx = 0
        for key, title in [
            ("reference", "Reference file"),
            ("logs", "Logs file"),
            ("output", "Output Excel"),
        ]:
            frame = ctk.CTkFrame(card, fg_color=SURFACE_LOW, corner_radius=14)
            frame.grid(row=row_idx, column=0, sticky="ew", padx=18, pady=(18 if row_idx == 0 else 0, 14))
            frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                frame,
                text=title.upper(),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))

            path_label = ctk.CTkLabel(
                frame,
                text="Not selected",
                font=ctk.CTkFont(size=13),
                text_color=TEXT,
                justify="left",
                anchor="w",
                wraplength=700,
            )
            path_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))

            btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
            btn_frame.grid(row=0, column=2, rowspan=2, sticky="e", padx=14, pady=14)

            open_file_btn = ctk.CTkButton(
                btn_frame,
                text="Open File",
                width=100,
                fg_color=SURFACE_HIGH,
                hover_color=OUTLINE,
                command=lambda k=key: self.open_selected_file(k),
            )
            open_file_btn.pack(side="left", padx=5)

            open_folder_btn = ctk.CTkButton(
                btn_frame,
                text="Open Folder",
                width=110,
                fg_color=SURFACE_HIGH,
                hover_color=OUTLINE,
                command=lambda k=key: self.open_selected_folder(k),
            )
            open_folder_btn.pack(side="left", padx=5)

            self.file_rows[key] = {
                "path_label": path_label,
                "open_file_btn": open_file_btn,
                "open_folder_btn": open_folder_btn,
            }
            row_idx += 1

        self.file_info_box = ctk.CTkTextbox(
            card,
            height=200,
            fg_color=SURFACE_LOW,
            corner_radius=14,
            border_width=1,
            border_color=OUTLINE,
            text_color=TEXT_MUTED,
            wrap="word",
        )
        self.file_info_box.grid(row=row_idx, column=0, sticky="nsew", padx=18, pady=(4, 18))
        self.file_info_box.configure(state="disabled")

        return page

    def _build_settings_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.main_container, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="SETTINGS",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PRIMARY_STRONG,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Session behavior and interface preferences.",
            font=ctk.CTkFont(size=14),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)

        # Appearance
        appearance_box = ctk.CTkFrame(card, fg_color=SURFACE_LOW, corner_radius=14)
        appearance_box.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=18)

        ctk.CTkLabel(
            appearance_box,
            text="APPEARANCE MODE",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self.appearance_option = ctk.CTkOptionMenu(
            appearance_box,
            values=["Dark", "Light", "System"],
            variable=self.appearance_mode_var,
            command=self.change_appearance_mode,
            fg_color=SURFACE_HIGH,
            button_color=PRIMARY_STRONG,
            button_hover_color=PRIMARY,
        )
        self.appearance_option.pack(anchor="w", padx=14, pady=(0, 14))

        # Defaults
        defaults_box = ctk.CTkFrame(card, fg_color=SURFACE_LOW, corner_radius=14)
        defaults_box.grid(row=0, column=1, sticky="nsew", padx=(8, 18), pady=18)

        ctk.CTkLabel(
            defaults_box,
            text="DEFAULT EXECUTION OPTIONS",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=14, pady=(14, 8))

        ctk.CTkSwitch(
            defaults_box,
            text="Enable Debug Export by default",
            variable=self.default_export_debug_var,
            progress_color=SECONDARY,
            command=self.apply_default_settings,
        ).pack(anchor="w", padx=14, pady=(0, 14))

        # Maintenance
        maintenance_box = ctk.CTkFrame(card, fg_color=SURFACE_LOW, corner_radius=14)
        maintenance_box.grid(row=1, column=0, sticky="nsew", padx=(18, 8), pady=(0, 18))

        ctk.CTkLabel(
            maintenance_box,
            text="MAINTENANCE",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=14, pady=(14, 8))

        ctk.CTkButton(
            maintenance_box,
            text="Apply Defaults to Current Session",
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.apply_default_settings,
        ).pack(anchor="w", padx=14, pady=6)

        ctk.CTkButton(
            maintenance_box,
            text="Clear Session Logs",
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.clear_logs,
        ).pack(anchor="w", padx=14, pady=6)

        ctk.CTkButton(
            maintenance_box,
            text="Refresh All Views",
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            command=self.refresh_all_views,
        ).pack(anchor="w", padx=14, pady=(6, 14))

        # About
        about_box = ctk.CTkFrame(card, fg_color=SURFACE_LOW, corner_radius=14)
        about_box.grid(row=1, column=1, sticky="nsew", padx=(8, 18), pady=(0, 18))

        ctk.CTkLabel(
            about_box,
            text="ABOUT",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=14, pady=(14, 8))

        about_text = ctk.CTkTextbox(
            about_box,
            height=180,
            fg_color=SURFACE_LOW,
            corner_radius=10,
            border_width=0,
            text_color=TEXT_MUTED,
            wrap="word",
        )
        about_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        about_text.insert(
            "1.0",
            "NEON_OBSERVATORY\n\n"
            "Signal Analysis desktop interface with:\n"
            "- deterministic signal extraction\n"
            "- Excel summary/debug export\n"
            "- operational dashboard\n"
            "- live stream monitoring\n"
            "- file explorer helpers\n\n"
            "Built on Python + CustomTkinter."
        )
        about_text.configure(state="disabled")

        return page

    # ------------------------------------------------------------------
    # Signal Analysis layout pieces
    # ------------------------------------------------------------------
    def _build_stats_row(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        row.grid_columnconfigure((0, 1, 2), weight=1)

        self.last_analysis_card = self._create_metric_card(
            row,
            title="Last Analysis Time",
            value_var=self.last_analysis_var,
            subtitle="REALTIME_SYNCED",
            value_color=PRIMARY,
        )
        self.last_analysis_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.health_card = self._create_metric_card(
            row,
            title="Signal Health",
            value_var=self.signal_health_var,
            subtitle="SYSTEM_STATUS",
            value_color=SECONDARY,
        )
        self.health_card.grid(row=0, column=1, sticky="nsew", padx=8)

        action_card = ctk.CTkFrame(row, fg_color=SURFACE_HIGH, corner_radius=16)
        action_card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        action_card.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            action_card,
            text="Execution",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 8))

        self.run_button = ctk.CTkButton(
            action_card,
            text="RUN CHECK",
            height=48,
            corner_radius=12,
            fg_color=PRIMARY_STRONG,
            hover_color=PRIMARY,
            text_color=BG,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.run_in_thread,
        )
        self.run_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

        ctk.CTkButton(
            action_card,
            text="PREVIEW",
            height=40,
            corner_radius=10,
            fg_color=SURFACE,
            hover_color=OUTLINE,
            border_width=1,
            border_color=OUTLINE,
            command=self.preview_loaded,
        ).grid(row=2, column=0, sticky="ew", padx=(18, 6), pady=(0, 18))

        ctk.CTkButton(
            action_card,
            text="RESET",
            height=40,
            corner_radius=10,
            fg_color=SURFACE,
            hover_color=OUTLINE,
            border_width=1,
            border_color=OUTLINE,
            command=self.reset,
        ).grid(row=2, column=1, sticky="ew", padx=(6, 18), pady=(0, 18))

    def _create_metric_card(
        self,
        parent: ctk.CTkFrame,
        title: str,
        value_var: ctk.StringVar,
        subtitle: str,
        value_color: str,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=16)

        ctk.CTkLabel(
            card,
            text=title.upper(),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            card,
            textvariable=value_var,
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color=value_color,
        ).pack(anchor="w", padx=18)

        ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=SECONDARY if value_color == PRIMARY else TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(8, 16))

        return card

    def _build_config_row(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="nsew", pady=(0, 16))
        row.grid_columnconfigure(0, weight=2)
        row.grid_columnconfigure(1, weight=1)

        # File config
        file_card = ctk.CTkFrame(row, fg_color=SURFACE, corner_radius=16)
        file_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        file_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            file_card,
            text="FILE_CONFIGURATION",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 12))

        self._file_row(file_card, 1, "Reference file (CCS)", self.reference_path_var, self.load_reference, "BROWSE")
        self._file_row(file_card, 2, "Logs file (UU)", self.logs_path_var, self.load_logs, "BROWSE")
        self._file_row(file_card, 3, "Output Excel", self.output_path_var, self.choose_output, "SAVE AS")

        # Options
        options_card = ctk.CTkFrame(row, fg_color=SURFACE, corner_radius=16)
        options_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        options_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            options_card,
            text="OPTIONS",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 12))

        switch_box = ctk.CTkFrame(options_card, fg_color=SURFACE_LOW, corner_radius=12)
        switch_box.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            switch_box,
            text="Debug Export",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 2))

        ctk.CTkLabel(
            switch_box,
            text="Extended metadata log",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 14))

        ctk.CTkSwitch(
            switch_box,
            text="",
            variable=self.export_debug_var,
            progress_color=SECONDARY,
            button_color=TEXT,
            button_hover_color=PRIMARY,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=14)

        self.options_info_box = ctk.CTkTextbox(
            options_card,
            height=120,
            fg_color=SURFACE_LOW,
            corner_radius=12,
            border_width=1,
            border_color=OUTLINE,
            text_color=TEXT_MUTED,
            wrap="word",
        )
        self.options_info_box.grid(row=2, column=0, sticky="nsew", padx=18, pady=(8, 18))
        self.options_info_box.configure(state="disabled")

    def _file_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: ctk.StringVar,
        command,
        button_text: str,
    ) -> None:
        ctk.CTkLabel(
            parent,
            text=label.upper(),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=row * 2 - 1, column=0, sticky="w", padx=18, pady=(8, 4))

        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row * 2, column=0, sticky="ew", padx=18, pady=(0, 6))
        frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=40,
            corner_radius=10,
            fg_color=SURFACE_LOW,
            border_color=OUTLINE,
            text_color=TEXT,
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            frame,
            text=button_text,
            width=120,
            height=40,
            corner_radius=10,
            fg_color=SURFACE_HIGH,
            hover_color=OUTLINE,
            text_color=TEXT,
            command=command,
        ).grid(row=0, column=1, sticky="e")

    def _build_status_bar(self, parent: ctk.CTkFrame) -> None:
        status_card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=16)
        status_card.grid(row=2, column=0, sticky="ew", pady=(0, 16))

        ctk.CTkLabel(
            status_card,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PRIMARY,
        ).pack(anchor="w", padx=18, pady=14)

    def _build_terminal(self, parent: ctk.CTkFrame) -> None:
        terminal_card = ctk.CTkFrame(parent, fg_color=SURFACE_LOW, corner_radius=16, border_width=1, border_color=OUTLINE)
        terminal_card.grid(row=3, column=0, sticky="nsew")
        terminal_card.grid_columnconfigure(0, weight=1)
        terminal_card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(terminal_card, fg_color=SURFACE, corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(
            header,
            text="SYSTEM TERMINAL",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=12, pady=8)

        self.terminal_text = ctk.CTkTextbox(
            terminal_card,
            fg_color=SURFACE_LOW,
            corner_radius=12,
            text_color=TEXT,
            wrap="none",
            border_width=0,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.terminal_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.terminal_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------
    def switch_page(self, page_key: str) -> None:
        self.current_page = page_key

        for key, frame in self.pages.items():
            frame.grid_forget()

        self.pages[page_key].grid(row=0, column=0, sticky="nsew")

        for key, btn in self.nav_buttons.items():
            active = key == page_key
            btn.configure(
                fg_color=SURFACE_HIGH if active else "transparent",
                text_color=PRIMARY_STRONG if active else TEXT_MUTED,
                border_width=1 if active else 0,
                border_color=PRIMARY_STRONG if active else OUTLINE,
            )

        self.refresh_all_views()

    def _create_dashboard_stat_card(
        self,
        parent: ctk.CTkFrame,
        column: int,
        title: str,
        value_var: ctk.StringVar,
        color: str,
    ) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=16)
        card.grid(row=0, column=column, sticky="nsew", padx=8 if column not in (0, 3) else (0 if column == 0 else 8, 0 if column == 3 else 8))

        ctk.CTkLabel(
            card,
            text=title.upper(),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(16, 6))

        label = ctk.CTkLabel(
            card,
            textvariable=value_var,
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=color,
        )
        label.pack(anchor="w", padx=18, pady=(0, 16))
        return label

    def _overview_row(self, parent: ctk.CTkFrame, row: int, title: str, value_var: ctk.StringVar):
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=row, column=0, sticky="w", padx=14, pady=(14 if row == 0 else 4, 4))

        value_label = ctk.CTkLabel(
            parent,
            textvariable=value_var,
            font=ctk.CTkFont(size=13),
            text_color=TEXT,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        value_label.grid(row=row, column=1, sticky="w", padx=14, pady=(14 if row == 0 else 4, 4))
        return value_label

    # ------------------------------------------------------------------
    # Utility / system
    # ------------------------------------------------------------------
    def _show_help(self) -> None:
        messagebox.showinfo(
            "Help",
            "Workflow:\n\n"
            "1. Load Reference file\n"
            "2. Load Logs file\n"
            "3. Choose output Excel path\n"
            "4. Press RUN CHECK\n\n"
            "Use Dashboard for overview, Live Stream for console monitoring, "
            "File Explorer for opening paths, and Settings for preferences."
        )

    def change_appearance_mode(self, mode: str) -> None:
        value = mode.lower()
        if value not in {"dark", "light", "system"}:
            return
        ctk.set_appearance_mode(value)
        self._log(f"Appearance mode changed to: {mode}")
        self._set_status(f"Appearance mode set to {mode}.")

    def apply_default_settings(self) -> None:
        self.export_debug_var.set(self.default_export_debug_var.get())
        state = "enabled" if self.export_debug_var.get() else "disabled"
        self._log(f"Default settings applied. Debug export {state}.")
        self._set_status(f"Default settings applied. Debug export {state}.")
        self.refresh_all_views()

    def clear_logs(self) -> None:
        self.session_logs.clear()
        self._refresh_log_widgets()
        self._set_status("Session logs cleared.")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def _terminal_set(self, widget: ctk.CTkTextbox, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _terminal_append(self, widget: ctk.CTkTextbox, text: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}"
        self.session_logs.append(entry)
        self._refresh_log_widgets()

    def _refresh_log_widgets(self) -> None:
        content = "\n".join(self.session_logs) if self.session_logs else ""
        if hasattr(self, "terminal_text"):
            self._terminal_set(self.terminal_text, content)
        if hasattr(self, "live_stream_text"):
            self._terminal_set(self.live_stream_text, content)
        if hasattr(self, "dashboard_terminal"):
            self._terminal_set(self.dashboard_terminal, content)

    def _process_ui_queue(self) -> None:
        try:
            while True:
                action, payload = self.ui_queue.get_nowait()

                if action == "status":
                    self._set_status(payload)
                elif action == "log":
                    self._log(payload)
                elif action == "preview":
                    self._terminal_set(self.terminal_text, payload)
                elif action == "done":
                    self._set_status(payload)
                    self._log(payload)
                    self.run_button.configure(state="normal")
                    self.refresh_all_views()
                    messagebox.showinfo("Finished", payload)
                elif action == "error":
                    self._set_status(payload)
                    self._log(payload)
                    self.run_button.configure(state="normal")
                    messagebox.showerror("Run failed", payload)
                elif action == "metrics":
                    parts = payload.split("|")
                    if len(parts) == 2:
                        self.last_analysis_var.set(parts[0])
                        self.signal_health_var.set(parts[1])
                        self.refresh_all_views()

        except queue.Empty:
            pass

        self.after(100, self._process_ui_queue)

    def _safe_path(self, key: str) -> str:
        if key == "reference":
            return self.reference_path_var.get().strip()
        if key == "logs":
            return self.logs_path_var.get().strip()
        if key == "output":
            return self.output_path_var.get().strip()
        return ""

    def _open_path(self, path: str) -> None:
        if not path:
            raise ValueError("No path selected.")

        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        system = platform.system().lower()

        if system == "windows":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif system == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)

    def open_selected_file(self, key: str) -> None:
        path = self._safe_path(key)
        if not path:
            messagebox.showwarning("Missing path", "No path is currently selected.")
            return

        try:
            self._open_path(path)
            self._log(f"Opened file: {path}")
        except Exception as exc:
            messagebox.showerror("Open file failed", str(exc))

    def open_selected_folder(self, key: str) -> None:
        path = self._safe_path(key)
        if not path:
            messagebox.showwarning("Missing path", "No path is currently selected.")
            return

        try:
            target = Path(path)
            folder = target if target.is_dir() else target.parent
            self._open_path(str(folder))
            self._log(f"Opened folder: {folder}")
        except Exception as exc:
            messagebox.showerror("Open folder failed", str(exc))

    # ------------------------------------------------------------------
    # Refresh views / metrics
    # ------------------------------------------------------------------
    def refresh_all_views(self) -> None:
        self._update_metrics()
        self._update_options_info()
        self._update_file_explorer()
        self._refresh_log_widgets()

    def _update_metrics(self) -> None:
        ref_rows = len(self.reference_df) if self.reference_df is not None else 0
        log_rows = len(self.logs_df) if self.logs_df is not None else 0

        eligible = 0
        if self.reference_df is not None:
            try:
                ref = self.reference_df.fillna("")
                eligible = len(
                    ref[
                        (ref["Report event"].astype(str).str.strip() != "")
                        & (ref["Signal long name"].astype(str).str.strip() != "")
                    ]
                )
            except Exception:
                eligible = 0

        self.reference_rows_var.set(str(ref_rows))
        self.logs_rows_var.set(str(log_rows))
        self.eligible_signals_var.set(str(eligible))

        if self.last_summary_df is not None and len(self.last_summary_df) > 0:
            total = len(self.last_summary_df)
            found = int((self.last_summary_df["Status"] == "FOUND").sum()) if "Status" in self.last_summary_df.columns else 0
            signal_not_found = int((self.last_summary_df["Status"] == "SIGNAL NOT FOUND").sum()) if "Status" in self.last_summary_df.columns else 0
            trigger_not_found = int((self.last_summary_df["Status"] == "TRIGGER NOT FOUND").sum()) if "Status" in self.last_summary_df.columns else 0

            health = (found / total * 100) if total else 0.0
            self.signal_health_var.set(f"{health:.1f}%")
            self.last_run_summary_var.set(
                f"FOUND: {found} | SIGNAL NOT FOUND: {signal_not_found} | TRIGGER NOT FOUND: {trigger_not_found}"
            )
        else:
            self.last_run_summary_var.set("No analysis executed yet")
            if self.last_analysis_var.get() == "N/A":
                self.signal_health_var.set("0.0%")

    def _update_options_info(self) -> None:
        ref_name = Path(self.reference_path_var.get()).name if self.reference_path_var.get().strip() else "Not loaded"
        log_name = Path(self.logs_path_var.get()).name if self.logs_path_var.get().strip() else "Not loaded"
        out_name = Path(self.output_path_var.get()).name if self.output_path_var.get().strip() else "Not selected"
        debug_state = "ON" if self.export_debug_var.get() else "OFF"

        text = (
            "Ready for deep-scan analysis.\n\n"
            f"Reference: {ref_name}\n"
            f"Logs: {log_name}\n"
            f"Output: {out_name}\n"
            f"Debug Export: {debug_state}\n\n"
            "Ensure paths are correct and the output location is write-accessible before execution."
        )

        self.options_info_box.configure(state="normal")
        self.options_info_box.delete("1.0", "end")
        self.options_info_box.insert("1.0", text)
        self.options_info_box.configure(state="disabled")

    def _update_file_explorer(self) -> None:
        mapping = {
            "reference": self.reference_path_var.get().strip(),
            "logs": self.logs_path_var.get().strip(),
            "output": self.output_path_var.get().strip(),
        }

        for key, value in mapping.items():
            label = self.file_rows[key]["path_label"]
            open_file_btn = self.file_rows[key]["open_file_btn"]
            open_folder_btn = self.file_rows[key]["open_folder_btn"]

            if value:
                label.configure(text=value, text_color=TEXT)
                open_file_btn.configure(state="normal")
                open_folder_btn.configure(state="normal")
            else:
                label.configure(text="Not selected", text_color=TEXT_MUTED)
                open_file_btn.configure(state="disabled")
                open_folder_btn.configure(state="disabled")

        info_lines = [
            "CURRENT FILE SUMMARY",
            "",
            f"Reference rows: {self.reference_rows_var.get()}",
            f"Log rows: {self.logs_rows_var.get()}",
            f"Eligible signals: {self.eligible_signals_var.get()}",
            f"Last output: {self.last_output_var.get()}",
        ]

        self.file_info_box.configure(state="normal")
        self.file_info_box.delete("1.0", "end")
        self.file_info_box.insert("1.0", "\n".join(info_lines))
        self.file_info_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------
    def load_reference(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose reference file",
            filetypes=[("Supported", "*.csv *.xlsx *.xls *.xlsm *.tsv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            df = load_reference_file(path)
        except Exception as exc:
            messagebox.showerror("Reference load failed", str(exc))
            return

        self.reference_df = df
        self.reference_path_var.set(path)

        if not self.output_path_var.get():
            self.output_path_var.set(str(Path(path).with_name(DEFAULT_OUTPUT_NAME)))

        self._set_status(f"Loaded reference: {Path(path).name} ({len(df)} rows)")
        self._log(f"Reference file loaded: {path}")
        self.refresh_all_views()

    def load_logs(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose logs file",
            filetypes=[("Supported", "*.csv *.xlsx *.xls *.xlsm *.tsv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            df = load_logs_file(path)
        except Exception as exc:
            messagebox.showerror("Logs load failed", str(exc))
            return

        self.logs_df = df
        self.logs_path_var.set(path)

        if not self.output_path_var.get():
            self.output_path_var.set(str(Path(path).with_name(DEFAULT_OUTPUT_NAME)))

        self._set_status(f"Loaded logs: {Path(path).name} ({len(df)} rows)")
        self._log(f"Logs file loaded: {path}")
        self.refresh_all_views()

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Choose output file",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if path:
            self.output_path_var.set(path)
            self._log(f"Output path set: {path}")
            self.refresh_all_views()

    def preview_loaded(self) -> None:
        preview = create_preview_text(self.reference_df, self.logs_df)
        self._terminal_set(self.terminal_text, preview)
        self._set_status("Preview updated.")
        self._log("Preview refreshed with currently loaded datasets.")

    def reset(self) -> None:
        self.reference_df = None
        self.logs_df = None
        self.last_summary_df = None
        self.last_debug_df = None

        self.reference_path_var.set("")
        self.logs_path_var.set("")
        self.output_path_var.set("")
        self.export_debug_var.set(self.default_export_debug_var.get())

        self.last_analysis_var.set("N/A")
        self.signal_health_var.set("0.0%")
        self.reference_rows_var.set("0")
        self.logs_rows_var.set("0")
        self.eligible_signals_var.set("0")
        self.last_output_var.set("Not generated yet")
        self.last_run_summary_var.set("No analysis executed yet")

        self._terminal_set(self.terminal_text, "")
        self._set_status("Reset complete.")
        self._log("System reset complete.")
        self.refresh_all_views()

    # ------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------
    def get_config(self) -> Optional[CheckConfig]:
        if self.reference_df is None or self.logs_df is None:
            messagebox.showwarning("Missing files", "Load both the reference file and the logs file first.")
            return None

        output_path = self.output_path_var.get().strip()
        if not output_path:
            messagebox.showwarning("Missing output", "Choose where to save the output Excel.")
            return None

        return CheckConfig(
            reference_path=self.reference_path_var.get().strip(),
            logs_path=self.logs_path_var.get().strip(),
            output_path=output_path,
            export_debug=self.export_debug_var.get(),
        )

    def run_in_thread(self) -> None:
        config = self.get_config()
        if config is None:
            return

        self.run_button.configure(state="disabled")
        self._set_status("Starting analysis...")
        self._log("RUN_CHECK sequence started.")

        thread = threading.Thread(target=self.run_check_safe, args=(config,), daemon=True)
        thread.start()

    def run_check_safe(self, config: CheckConfig) -> None:
        try:
            self.run_check(config)
        except Exception as exc:
            self.ui_queue.put(("error", f"Error: {exc}"))

    def run_check(self, config: CheckConfig) -> None:
        def progress_callback(text: str) -> None:
            self.ui_queue.put(("status", text))

        def log_callback(text: str) -> None:
            self.ui_queue.put(("log", text))

        summary_df, debug_df = run_signal_check(
            reference_df=self.reference_df,
            logs_df=self.logs_df,
            config=config,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

        self.last_summary_df = summary_df
        self.last_debug_df = debug_df

        now_text = datetime.now().strftime("%H:%M:%S")
        total = len(summary_df)
        found = 0
        if total > 0 and "Status" in summary_df.columns:
            found = int((summary_df["Status"] == "FOUND").sum())

        health = f"{(found / total * 100):.1f}%" if total else "0.0%"
        self.last_output_var.set(config.output_path)

        self.ui_queue.put(("metrics", f"{now_text}|{health}"))

        msg = (
            f"Done. Summary rows: {len(summary_df)}. "
            f"Debug rows: {len(debug_df) if config.export_debug else 0}. "
            f"Saved to: {config.output_path}"
        )
        self.ui_queue.put(("done", msg))


def main() -> None:
    app = SignalCheckerModernUI()
    app.mainloop()


if __name__ == "__main__":
    main()