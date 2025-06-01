#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import threading
import asyncio
import math
import os
import json
import sys
import aiohttp

# --- Imports des modules de l'application ---
from constants import (
    DEFAULT_RADIUS, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_STATION_DISTANCE_LS,
    DEFAULT_INCLUDE_PLANETARY, DEFAULT_INCLUDE_FLEET_CARRIERS,
    RESET_DEFAULT_RADIUS, RESET_DEFAULT_MAX_AGE_DAYS,
    RESET_DEFAULT_MAX_STATION_DISTANCE_LS, RESET_DEFAULT_INCLUDE_PLANETARY,
    RESET_DEFAULT_INCLUDE_FLEET_CARRIERS, RESET_DEFAULT_LANGUAGE,
    RESET_DEFAULT_SORT_OPTION, RESET_DEFAULT_CUSTOM_JOURNAL_DIR, LOG_FILE,
    KEY_RADIUS, KEY_MAX_AGE_DAYS, KEY_MAX_STATION_DISTANCE_LS,
    KEY_INCLUDE_PLANETARY, KEY_INCLUDE_FLEET_CARRIERS, KEY_LANGUAGE,
    KEY_CUSTOM_JOURNAL_DIR, KEY_CUSTOM_PAD_SIZES, KEY_SORT_OPTION,
    DEFAULT_LANGUAGE,
    PURCHASABLE_SHIPS_LIST,
    DEFAULT_SHIPYARD_RADIUS_LY,
    DEFAULT_OUTFITTING_RADIUS_LY,
    # Importer les couleurs depuis constants.py
    ED_ORANGE, ED_DARK_GREY, ED_MEDIUM_GREY, ED_LIGHT_GREY_TEXT, ED_WHITE_TEXT,
    ED_BUTTON_BG, ED_BUTTON_ACTIVE_BG, ED_BUTTON_PRESSED_BG,
    ED_INPUT_BG, ED_INPUT_TEXT, ED_HIGHLIGHT_BG, ED_HIGHLIGHT_TEXT
)
import settings_manager
import journal_parser
import language as lang_module
import optimizer_logic
import shipyard_db_manager
import outfitting_db_manager

# --- Imports des modules d'onglets ---
import gui_analysis_tab
import gui_services_tab
import gui_shipyard_tab
import gui_outfitting_tab
import gui_materials_tab
import gui_multihop_trade_tab # <<< NOUVEL IMPORT
import gui_settings_window

logger = logging.getLogger(__name__)

# ---- Variables Globales de l'État de l'Application ----
# Ces variables globales pourraient être encapsulées dans une classe d'état à l'avenir
# pour une meilleure gestion, mais pour l'instant, elles fonctionnent.
CURRENT_SYSTEM = "?"
CURRENT_STATION = "?"
CURRENT_SHIP_TYPE = "Unknown"
CURRENT_CARGO_CAPACITY = 0
CURRENT_PAD_SIZE = "?"
EFFECTIVE_JOURNAL_DIR_DISPLAY = "Auto-detecting..."

# Événements d'annulation pour les opérations des différents onglets
CANCEL_OPERATION_EVENT = threading.Event()
NEAREST_SERVICES_CANCEL_EVENT = threading.Event()
SHIPYARD_OPERATION_CANCEL_EVENT = threading.Event()
OUTFITTING_OPERATION_CANCEL_EVENT = threading.Event()
MATERIALS_OPERATION_CANCEL_EVENT = threading.Event()
MULTI_HOP_TRADE_CANCEL_EVENT = threading.Event() # <<< NOUVEL ÉVÉNEMENT

root = None
notebook = None
style = None

journal_dir_label_var = None # tk.StringVar pour le label du répertoire du journal

progress_bar = None
cancel_btn = None
progress_cancel_frame = None

# Variables Tkinter pour les paramètres (partagées avec la fenêtre des paramètres)
radius_var = None
age_var = None
station_dist_var = None
include_planetary_var = None
include_fleet_carriers_var = None
sort_var = None
language_var = None
shipyard_radius_var = None
outfitting_radius_var = None

# Références aux widgets labels de statut de BD (pour mise à jour centralisée)
ref_db_status_label_widget = None
ref_shipyard_db_status_lbl_widget = None
ref_outfitting_db_status_lbl_widget = None

# ---- Fonctions Utilitaires Globales pour l'UI ----
def update_status_and_progress(message, percentage=None, indeterminate=False, target_status_label_widget=None):
    global progress_bar, progress_cancel_frame, root
    if root and root.winfo_exists():
        def _update():
            if target_status_label_widget and target_status_label_widget.winfo_exists():
                target_status_label_widget.config(text=message)
            
            if progress_bar and progress_bar.winfo_exists() and progress_cancel_frame and progress_cancel_frame.winfo_exists():
                if indeterminate:
                    if not progress_bar.winfo_ismapped(): progress_bar.grid(column=0, row=0, sticky="ew", padx=(0,5))
                    progress_bar.config(mode='indeterminate'); progress_bar.start()
                elif percentage is not None:
                    if not progress_bar.winfo_ismapped(): progress_bar.grid(column=0, row=0, sticky="ew", padx=(0,5))
                    progress_bar.config(mode='determinate', value=percentage, maximum=100)
                    if percentage >= 100 or percentage < 0:
                        progress_bar.stop()
                        if progress_bar.winfo_ismapped(): progress_bar.grid_remove()
                else:
                    progress_bar.stop(); progress_bar.config(value=0)
                    if progress_bar.winfo_ismapped(): progress_bar.grid_remove()
        
        if threading.current_thread() is threading.main_thread(): _update()
        else: root.after(0, _update)

def update_journal_dir_display_label():
    global journal_dir_label_var
    if journal_dir_label_var:
        path_to_display_custom = settings_manager.get_setting(KEY_CUSTOM_JOURNAL_DIR)
        current_effective_dir = journal_parser.EFFECTIVE_JOURNAL_DIR 
        if path_to_display_custom:
            journal_dir_label_var.set(f"{lang_module.get_string('journal_dir_custom_prefix')} {path_to_display_custom}")
        elif current_effective_dir and current_effective_dir not in ["Auto-detecting...", "Not Found", "Error processing journals", "No Journal Dir", "No Events"]:
            journal_dir_label_var.set(f"{lang_module.get_string('journal_dir_auto_prefix')} {current_effective_dir}")
        elif current_effective_dir == "Not Found":
             journal_dir_label_var.set(lang_module.get_string('journal_dir_not_found'))
        else:
            journal_dir_label_var.set(lang_module.get_string('journal_dir_auto_detecting'))


def _set_buttons_state(operation_running=False, cancellable=False, source_tab_name=None):
    global cancel_btn, progress_cancel_frame
    
    cancel_button_state = tk.NORMAL if operation_running and cancellable else tk.DISABLED
    if progress_cancel_frame and progress_cancel_frame.winfo_exists():
        if operation_running and cancellable:
            if cancel_btn and not cancel_btn.winfo_ismapped():
                cancel_btn.grid(column=1, row=0, sticky="e", padx=(5,0))
        else:
            if cancel_btn and cancel_btn.winfo_ismapped():
                cancel_btn.grid_remove()
    if cancel_btn:
        cancel_btn.config(state=cancel_button_state)

    # Propager l'état aux onglets
    if hasattr(gui_analysis_tab, 'set_analysis_buttons_state'):
        gui_analysis_tab.set_analysis_buttons_state(operation_running, cancellable, source_tab_name)
    if hasattr(gui_services_tab, 'set_services_buttons_state'):
        gui_services_tab.set_services_buttons_state(operation_running, cancellable, source_tab_name)
    if hasattr(gui_shipyard_tab, 'set_shipyard_buttons_state'):
        gui_shipyard_tab.set_shipyard_buttons_state(operation_running, cancellable, source_tab_name)
    if hasattr(gui_outfitting_tab, 'set_outfitting_buttons_state'):
        gui_outfitting_tab.set_outfitting_buttons_state(operation_running, cancellable, source_tab_name)
    if hasattr(gui_materials_tab, 'set_materials_buttons_state'):
        gui_materials_tab.set_materials_buttons_state(operation_running, cancellable, source_tab_name)
    if hasattr(gui_multihop_trade_tab, 'set_multihop_trade_buttons_state'): # <<< NOUVELLE LIGNE
        gui_multihop_trade_tab.set_multihop_trade_buttons_state(operation_running, cancellable, source_tab_name)


def on_cancel_pressed():
    global CANCEL_OPERATION_EVENT, NEAREST_SERVICES_CANCEL_EVENT, SHIPYARD_OPERATION_CANCEL_EVENT
    global OUTFITTING_OPERATION_CANCEL_EVENT, MATERIALS_OPERATION_CANCEL_EVENT, MULTI_HOP_TRADE_CANCEL_EVENT # <<< Ajouté MULTI_HOP
    global notebook, cancel_btn
    
    active_event_to_set = None
    status_label_to_update = None
    operation_name = "unknown"

    if notebook and notebook.winfo_exists():
        try:
            selected_tab_index = notebook.index(notebook.select())
            if selected_tab_index == 0:
                active_event_to_set = CANCEL_OPERATION_EVENT
                if hasattr(gui_analysis_tab, 'status_lbl'): status_label_to_update = gui_analysis_tab.status_lbl
                operation_name = "Analysis"
            elif selected_tab_index == 1:
                active_event_to_set = NEAREST_SERVICES_CANCEL_EVENT
                if hasattr(gui_services_tab, 'services_tab_status_lbl'): status_label_to_update = gui_services_tab.services_tab_status_lbl
                operation_name = "Services Search"
            elif selected_tab_index == 2:
                active_event_to_set = SHIPYARD_OPERATION_CANCEL_EVENT
                if hasattr(gui_shipyard_tab, 'shipyard_status_lbl'): status_label_to_update = gui_shipyard_tab.shipyard_status_lbl
                operation_name = "Shipyard Search"
            elif selected_tab_index == 3:
                active_event_to_set = OUTFITTING_OPERATION_CANCEL_EVENT
                if hasattr(gui_outfitting_tab, 'outfitting_search_status_lbl'): status_label_to_update = gui_outfitting_tab.outfitting_search_status_lbl
                operation_name = "Outfitting Search"
            elif selected_tab_index == 4:
                active_event_to_set = MATERIALS_OPERATION_CANCEL_EVENT
                if hasattr(gui_materials_tab, 'materials_tab_status_lbl'): status_label_to_update = gui_materials_tab.materials_tab_status_lbl
                operation_name = "Materials Update"
            elif selected_tab_index == 5: # <<< NOUVELLE CONDITION (vérifier l'index)
                active_event_to_set = MULTI_HOP_TRADE_CANCEL_EVENT
                # if hasattr(gui_multihop_trade_tab, 'multihop_status_lbl'): status_label_to_update = gui_multihop_trade_tab.multihop_status_lbl # Si un tel label existe
                operation_name = "Multi-Hop Planning"
        except (tk.TclError, IndexError):
            logger.warning("on_cancel_pressed: Active tab could not be determined. Defaulting to main cancel event.")
            active_event_to_set = CANCEL_OPERATION_EVENT 
            operation_name = "Unknown (Fallback)"

    if active_event_to_set:
        logger.info(f"Cancel button pressed for {operation_name} operation. Setting cancel event.")
        active_event_to_set.set()
        if status_label_to_update and status_label_to_update.winfo_exists():
            status_label_to_update.config(text=lang_module.get_string("cancellation_requested"))
    else:
        logger.info("Cancel pressed, but no specific operation context found or no active event to set.")

    if cancel_btn:
        cancel_btn.config(state=tk.DISABLED)


def open_settings_window_global():
    global root, radius_var, age_var, station_dist_var, include_planetary_var, include_fleet_carriers_var, journal_dir_label_var, language_var, sort_var, shipyard_radius_var, outfitting_radius_var

    if gui_settings_window.settings_window and gui_settings_window.settings_window.winfo_exists():
        gui_settings_window.settings_window.focus()
        return

    on_select_journal_dir_func = gui_analysis_tab.on_select_journal_dir_pressed if hasattr(gui_analysis_tab, 'on_select_journal_dir_pressed') else lambda: logger.error("on_select_journal_dir_pressed function not found in gui_analysis_tab")

    settings_shared_elements = {
        "root": root,
        "radius_var": radius_var, "age_var": age_var, "station_dist_var": station_dist_var,
        "shipyard_radius_var": shipyard_radius_var, "outfitting_radius_var": outfitting_radius_var,
        "include_planetary_var": include_planetary_var, "include_fleet_carriers_var": include_fleet_carriers_var,
        "journal_dir_label_var": journal_dir_label_var,
        "language_var": language_var, "sort_var": sort_var,
        "update_main_gui_texts_func": update_gui_text_after_language_change,
        "update_status_func": update_status_and_progress,
        "set_buttons_state_func": _set_buttons_state,
        "select_journal_dir_func": on_select_journal_dir_func,
        "update_journal_dir_display_label_func": update_journal_dir_display_label
    }
    gui_settings_window.create_settings_window(settings_shared_elements)


def update_gui_text_after_language_change():
    global root, notebook
    global ref_db_status_label_widget, ref_shipyard_db_status_lbl_widget, ref_outfitting_db_status_lbl_widget
    
    logger.info("Attempting to update GUI texts for new language (gui_main).")
    if not root or not root.winfo_exists():
        logger.warning("Cannot update GUI texts: root window does not exist.")
        return
        
    root.title(lang_module.get_string("app_title"))

    if ref_db_status_label_widget and ref_db_status_label_widget.winfo_exists():
        ref_db_status_label_widget.config(text=optimizer_logic.get_last_db_update_time_str())
    if ref_shipyard_db_status_lbl_widget and ref_shipyard_db_status_lbl_widget.winfo_exists():
        ref_shipyard_db_status_lbl_widget.config(text=shipyard_db_manager.get_shipyard_db_update_time_str())
    if ref_outfitting_db_status_lbl_widget and ref_outfitting_db_status_lbl_widget.winfo_exists():
        ref_outfitting_db_status_lbl_widget.config(text=outfitting_db_manager.get_outfitting_db_update_time_str())

    update_journal_dir_display_label()

    if notebook:
        try:
            current_tab_idx = -1
            if notebook.winfo_exists() and notebook.select(): # Vérifier si notebook existe encore
                current_tab_idx = notebook.index(notebook.select())
            
            num_tabs = len(notebook.tabs())
            if num_tabs > 0: notebook.tab(0, text=lang_module.get_string("analysis_tab_title"))
            if num_tabs > 1: notebook.tab(1, text=lang_module.get_string("services_tab_title"))
            if num_tabs > 2: notebook.tab(2, text=lang_module.get_string("shipyard_tab_title"))
            if num_tabs > 3: notebook.tab(3, text=lang_module.get_string("outfitting_tab_title"))
            if num_tabs > 4: notebook.tab(4, text=lang_module.get_string("materials_tab_title"))
            if num_tabs > 5: notebook.tab(5, text=lang_module.get_string("multihop_trade_tab_title")) # <<< NOUVELLE LIGNE

            if current_tab_idx != -1 and current_tab_idx < num_tabs and notebook.winfo_exists(): # Re-vérifier winfo_exists
                notebook.select(current_tab_idx)
        except tk.TclError as e:
            logger.warning(f"Could not update notebook tab titles: {e}")

    # Appeler les fonctions de mise à jour de texte pour chaque onglet
    if hasattr(gui_analysis_tab, 'update_analysis_tab_texts'): gui_analysis_tab.update_analysis_tab_texts()
    if hasattr(gui_services_tab, 'update_services_tab_texts'): gui_services_tab.update_services_tab_texts()
    if hasattr(gui_shipyard_tab, 'update_shipyard_tab_texts'): gui_shipyard_tab.update_shipyard_tab_texts()
    if hasattr(gui_outfitting_tab, 'update_outfitting_tab_texts'): gui_outfitting_tab.update_outfitting_tab_texts()
    if hasattr(gui_materials_tab, 'update_materials_tab_texts'): gui_materials_tab.update_materials_tab_texts()
    if hasattr(gui_multihop_trade_tab, 'update_multihop_trade_tab_texts'): gui_multihop_trade_tab.update_multihop_trade_tab_texts() # <<< NOUVELLE LIGNE

    if gui_settings_window.settings_window and gui_settings_window.settings_window.winfo_exists():
        gui_settings_window.settings_window.destroy()
        open_settings_window_global()
        
    logger.info("GUI texts updated for new language (gui_main).")


# ---- Création de la Fenêtre Principale ----
def create_main_window(main_root):
    global root, style, notebook, progress_bar, cancel_btn, progress_cancel_frame
    global radius_var, age_var, station_dist_var, include_planetary_var, include_fleet_carriers_var, sort_var, language_var, journal_dir_label_var, shipyard_radius_var, outfitting_radius_var
    global ref_db_status_label_widget, ref_shipyard_db_status_lbl_widget, ref_outfitting_db_status_lbl_widget

    root = main_root
    root.title(lang_module.get_string("app_title"))
    root.configure(bg=ED_DARK_GREY)
    window_width = 1250 
    window_height = 800
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width/2 - window_width / 2)
    center_y = int(screen_height/2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    style = ttk.Style(root)
    style.theme_use('clam')

    # --- Définition des Styles Personnalisés Elite Dangerous ---
    style.configure('.',
                    background=ED_DARK_GREY,
                    foreground=ED_LIGHT_GREY_TEXT,
                    font=('Segoe UI', 10),
                    borderwidth=1,
                    focusthickness=1, 
                    focuscolor=ED_ORANGE)

    style.configure('TFrame', background=ED_DARK_GREY)
    style.configure('TLabel', background=ED_DARK_GREY, foreground=ED_LIGHT_GREY_TEXT, padding=2)
    style.configure('Header.TLabel', font=('Segoe UI', 11, 'bold'), foreground=ED_ORANGE, background=ED_DARK_GREY)
    style.configure('Status.TLabel', foreground=ED_LIGHT_GREY_TEXT, font=('Segoe UI', 9, 'italic'), background=ED_DARK_GREY)
    style.configure('Path.TLabel', foreground=ED_LIGHT_GREY_TEXT, font=('Segoe UI', 8), background=ED_DARK_GREY)
    style.configure('Error.TLabel', foreground='#FF4136', background=ED_DARK_GREY)

    style.configure('TButton',
                    background=ED_BUTTON_BG, foreground=ED_ORANGE,
                    font=('Segoe UI', 10, 'bold'), borderwidth=1, relief='flat', padding=5,
                    focuscolor=ED_ORANGE)
    style.map('TButton',
              background=[('active', ED_BUTTON_ACTIVE_BG), ('pressed', ED_BUTTON_PRESSED_BG), ('disabled', ED_MEDIUM_GREY)],
              foreground=[('disabled', ED_DARK_GREY)],
              relief=[('pressed', 'sunken'), ('!pressed', 'flat')])

    style.configure('TRadiobutton',
                    background=ED_DARK_GREY, foreground=ED_LIGHT_GREY_TEXT,
                    indicatorcolor=ED_MEDIUM_GREY, font=('Segoe UI', 9), padding=(5,2))
    style.map('TRadiobutton', indicatorcolor=[('selected', ED_ORANGE), ('pressed', ED_ORANGE)],
              background=[('active', ED_MEDIUM_GREY)])

    style.configure('TCheckbutton',
                    background=ED_DARK_GREY, foreground=ED_LIGHT_GREY_TEXT,
                    indicatorcolor=ED_MEDIUM_GREY, font=('Segoe UI', 9), padding=(5,2))
    style.map('TCheckbutton', indicatorcolor=[('selected', ED_ORANGE), ('pressed', ED_ORANGE)],
              background=[('active', ED_MEDIUM_GREY)])

    style.configure('TEntry',
                    fieldbackground=ED_INPUT_BG, foreground=ED_INPUT_TEXT,
                    insertcolor=ED_WHITE_TEXT, borderwidth=1, relief='flat', padding=3)
    style.map('TEntry', bordercolor=[('focus', ED_ORANGE)])

    style.configure('Horizontal.TProgressbar',
                    troughcolor=ED_MEDIUM_GREY, background=ED_ORANGE, bordercolor=ED_DARK_GREY)

    style.configure('TLabelframe',
                    background=ED_DARK_GREY, bordercolor=ED_MEDIUM_GREY, relief='groove',
                    padding=5)
    style.configure('TLabelframe.Label',
                    background=ED_DARK_GREY, foreground=ED_ORANGE, font=('Segoe UI', 9, 'bold'))

    style.configure("TNotebook", background=ED_DARK_GREY, borderwidth=1, bordercolor=ED_MEDIUM_GREY)
    style.configure("TNotebook.Tab",
                    padding=[10, 4], font=('Segoe UI', 9, 'bold'),
                    foreground=ED_LIGHT_GREY_TEXT, background=ED_BUTTON_BG)
    style.map("TNotebook.Tab",
              foreground=[("selected", ED_ORANGE), ("active", ED_ORANGE)],
              background=[("selected", ED_MEDIUM_GREY), ("active", ED_BUTTON_ACTIVE_BG)])

    style.configure("Treeview",
                    background=ED_MEDIUM_GREY, foreground=ED_LIGHT_GREY_TEXT,
                    fieldbackground=ED_MEDIUM_GREY, rowheight=22, font=('Segoe UI', 9))
    style.map("Treeview",
              background=[('selected', ED_HIGHLIGHT_BG)], foreground=[('selected', ED_HIGHLIGHT_TEXT)])

    style.configure("Treeview.Heading",
                    font=('Segoe UI', 10, 'bold'), padding=5,
                    background=ED_BUTTON_BG, foreground=ED_ORANGE, relief="flat",
                    bordercolor=ED_DARK_GREY)
    style.map("Treeview.Heading", relief=[('active','groove'),('pressed','sunken')],
              background=[('active', ED_BUTTON_ACTIVE_BG)])

    style.configure('TCombobox',
                    fieldbackground=ED_INPUT_BG, background=ED_BUTTON_BG,
                    foreground=ED_INPUT_TEXT, arrowcolor=ED_ORANGE, insertcolor=ED_WHITE_TEXT,
                    borderwidth=1, padding=3)
    style.map('TCombobox',
              fieldbackground=[('readonly', ED_INPUT_BG), ('focus', ED_INPUT_BG)],
              selectbackground=[('readonly', ED_HIGHLIGHT_BG), ('focus', ED_HIGHLIGHT_BG)], 
              selectforeground=[('readonly', ED_HIGHLIGHT_TEXT), ('focus', ED_HIGHLIGHT_TEXT)])


    main_frame = ttk.Frame(root, padding="10 10 10 10")
    main_frame.pack(fill=tk.BOTH, expand=True); main_frame.columnconfigure(0, weight=1)

    app_s = settings_manager.get_all_settings()
    radius_var = tk.StringVar(value=str(app_s.get(KEY_RADIUS, DEFAULT_RADIUS)))
    age_var = tk.StringVar(value=str(app_s.get(KEY_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS)))
    station_dist_var = tk.StringVar(value=str(app_s.get(KEY_MAX_STATION_DISTANCE_LS, DEFAULT_MAX_STATION_DISTANCE_LS)))
    shipyard_radius_var = tk.StringVar(value=str(app_s.get(KEY_RADIUS, DEFAULT_SHIPYARD_RADIUS_LY))) # Devrait utiliser une clé dédiée si différent de KEY_RADIUS global
    outfitting_radius_var = tk.StringVar(value=str(app_s.get(KEY_RADIUS, DEFAULT_OUTFITTING_RADIUS_LY))) # Idem

    include_planetary_var = tk.BooleanVar(value=app_s.get(KEY_INCLUDE_PLANETARY, DEFAULT_INCLUDE_PLANETARY))
    include_fleet_carriers_var = tk.BooleanVar(value=app_s.get(KEY_INCLUDE_FLEET_CARRIERS, DEFAULT_INCLUDE_FLEET_CARRIERS))
    
    sort_var = tk.StringVar(value=str(app_s.get(KEY_SORT_OPTION, RESET_DEFAULT_SORT_OPTION)))
    journal_dir_label_var = tk.StringVar()
    language_var = tk.StringVar(value=lang_module.get_current_language_code())

    notebook = ttk.Notebook(main_frame)

    shared_gui_elements = {
        "root": root, "notebook": notebook,
        "radius_var": radius_var, "age_var": age_var, "station_dist_var": station_dist_var,
        "include_planetary_var": include_planetary_var, "include_fleet_carriers_var": include_fleet_carriers_var,
        "sort_var": sort_var, "language_var": language_var, "journal_dir_label_var": journal_dir_label_var,
        "shipyard_radius_var": shipyard_radius_var, "outfitting_radius_var": outfitting_radius_var,
        "open_settings_window_func": open_settings_window_global,
        "update_status_func": update_status_and_progress, "set_buttons_state_func": _set_buttons_state,
        # Utiliser les variables d'état de gui_analysis_tab car c'est lui qui les met à jour via journal_parser
        "get_current_system_func": lambda: gui_analysis_tab.CURRENT_SYSTEM_ANALYSIS if hasattr(gui_analysis_tab, 'CURRENT_SYSTEM_ANALYSIS') else "?",
        "get_current_station_func": lambda: gui_analysis_tab.CURRENT_STATION_ANALYSIS if hasattr(gui_analysis_tab, 'CURRENT_STATION_ANALYSIS') else "?",
        "get_current_ship_type_func": lambda: gui_analysis_tab.CURRENT_SHIP_TYPE_ANALYSIS if hasattr(gui_analysis_tab, 'CURRENT_SHIP_TYPE_ANALYSIS') else "Unknown",
        "get_current_cargo_capacity_func": lambda: gui_analysis_tab.CURRENT_CARGO_CAPACITY_ANALYSIS if hasattr(gui_analysis_tab, 'CURRENT_CARGO_CAPACITY_ANALYSIS') else 0,
        "get_current_pad_size_func": lambda: gui_analysis_tab.CURRENT_PAD_SIZE_ANALYSIS if hasattr(gui_analysis_tab, 'CURRENT_PAD_SIZE_ANALYSIS') else "?",
        
        "cancel_main_event": CANCEL_OPERATION_EVENT, "cancel_services_event": NEAREST_SERVICES_CANCEL_EVENT,
        "cancel_shipyard_event": SHIPYARD_OPERATION_CANCEL_EVENT, "cancel_outfitting_event": OUTFITTING_OPERATION_CANCEL_EVENT,
        "cancel_materials_event": MATERIALS_OPERATION_CANCEL_EVENT,
        "cancel_multihop_event": MULTI_HOP_TRADE_CANCEL_EVENT, # <<< NOUVELLE LIGNE

        "register_analysis_db_status_label_widget": lambda widget: globals().__setitem__('ref_db_status_label_widget', widget),
        "register_shipyard_db_status_label_widget": lambda widget: globals().__setitem__('ref_shipyard_db_status_lbl_widget', widget),
        "register_outfitting_db_status_label_widget": lambda widget: globals().__setitem__('ref_outfitting_db_status_lbl_widget', widget),
        
        "sort_treeview_column_func": sort_treeview_column_general,
        "update_journal_dir_display_label_func": update_journal_dir_display_label # Correction pour NameError
    }

    gui_analysis_tab.create_analysis_tab(notebook, shared_gui_elements)
    gui_services_tab.create_services_tab(notebook, shared_gui_elements)
    gui_shipyard_tab.create_shipyard_tab(notebook, shared_gui_elements)
    gui_outfitting_tab.create_outfitting_tab(notebook, shared_gui_elements)
    gui_materials_tab.create_materials_tab(notebook, shared_gui_elements)
    gui_multihop_trade_tab.create_multihop_trade_tab(notebook, shared_gui_elements) # <<< NOUVELLE LIGNE

    notebook.pack(expand=True, fill='both', pady=(0, 5))

    progress_cancel_frame = ttk.Frame(main_frame)
    progress_cancel_frame.pack(fill=tk.X, padx=5, pady=(0,5), side=tk.BOTTOM)
    progress_cancel_frame.columnconfigure(0, weight=1)
    progress_bar = ttk.Progressbar(progress_cancel_frame, orient=tk.HORIZONTAL, length=100, mode='determinate', style='Horizontal.TProgressbar')
    cancel_btn = ttk.Button(progress_cancel_frame, text=lang_module.get_string("cancel_button"), command=on_cancel_pressed, width=12)

    _set_buttons_state(False)
    if hasattr(gui_analysis_tab, 'refresh_location_and_ship_display'):
        root.after(100, gui_analysis_tab.refresh_location_and_ship_display)
    root.after(200, update_gui_text_after_language_change)
    logger.debug("Main GUI window creation complete with Elite Dangerous styling.")


def sort_treeview_column_general(treeview, column_key, data_type_str):
    current_sort_col_attr = '_sort_col'; current_sort_rev_attr = '_sort_rev'
    last_col = getattr(treeview, current_sort_col_attr, None); last_rev = getattr(treeview, current_sort_rev_attr, False)
    if last_col == column_key: reverse_order = not last_rev
    else: reverse_order = False
    setattr(treeview, current_sort_col_attr, column_key); setattr(treeview, current_sort_rev_attr, reverse_order)
    
    items = []
    for k_item in treeview.get_children(''):
        items.append((treeview.set(k_item, column_key), k_item))
    
    try:
        if data_type_str == "int":
            items.sort(key=lambda t: int(str(t[0]).replace(',', '')), reverse=reverse_order)
        elif data_type_str == "float":
            def sort_key_float(t_item):
                val_str = str(t_item[0]).replace(',', '').replace('?', '').replace('%', '')
                try: return float(val_str)
                except ValueError: return float('inf') if reverse_order else float('-inf')
            items.sort(key=sort_key_float, reverse=reverse_order)
        elif data_type_str == "str_ci": items.sort(key=lambda t: str(t[0]).lower(), reverse=reverse_order)
        else: items.sort(key=lambda t: str(t[0]), reverse=reverse_order)
    except ValueError as e:
        logger.error(f"Sorting error for column {column_key} with type {data_type_str}: {e}. Data sample: {[i[0] for i in items[:5]]}")
        items.sort(key=lambda t: str(t[0]).lower(), reverse=reverse_order) # Fallback
    
    for index, (val, k_item) in enumerate(items):
        treeview.move(k_item, '', index)
    
    # Mettre à jour les indicateurs de tri dans les en-têtes
    for c_key_loop in treeview["columns"]:
        # Essayer d'obtenir le texte de base à partir d'une clé de traduction qui correspond à column_key
        # Si ce n'est pas une clé de traduction directe, il faudrait une autre approche pour stocker/retrouver le texte de base.
        # Pour l'instant, on suppose que column_key PEUT être une clé de traduction valide pour l'en-tête.
        try:
            base_heading_text = lang_module.get_string(column_key) # Ceci pourrait ne pas être correct si column_key != clé de langue
                                                                # ou si le texte original n'est pas la clé.
                                                                # Une meilleure approche : stocker le texte original de l'en-tête
                                                                # ou reconstruire le texte de l'en-tête pour chaque colonne.
            # Pour l'instant, on utilise une approche plus simple :
            # On retire les anciens indicateurs avant d'ajouter le nouveau.
            current_text = treeview.heading(c_key_loop, "text")
            base_text = current_text.replace(" ▲", "").replace(" ▼", "")
            
            new_heading_text = base_text
            if c_key_loop == column_key:
                new_heading_text += " ▲" if not reverse_order else " ▼"
            treeview.heading(c_key_loop, text=new_heading_text)
        except Exception as e_sort_header: # Attraper une exception plus large au cas où get_string échoue
             logger.warning(f"Could not update sort indicator for header '{c_key_loop}': {e_sort_header}")