#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
import logging
import threading
import asyncio
import math
import os
import json
import aiohttp

from constants import (
    LOG_FILE, KEY_RADIUS, KEY_MAX_AGE_DAYS, KEY_MAX_STATION_DISTANCE_LS,
    KEY_INCLUDE_PLANETARY, KEY_INCLUDE_FLEET_CARRIERS, KEY_SORT_OPTION,
    KEY_NUM_JOURNAL_FILES_MISSIONS,DEFAULT_NUM_JOURNAL_FILES_MISSIONS,
    KEY_MAX_STATIONS_FOR_TRADE_LOOPS, DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS,
    KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES,
    KEY_TOP_N_IMPORTS_FILTER, DEFAULT_TOP_N_IMPORTS_FILTER,
    LOCAL_SELLERS_DATA_FILE,
    ED_ORANGE,
    COST_COLOR,
    PROFIT_COLOR,
    ED_MEDIUM_GREY, ED_WHITE_TEXT, ED_DARK_GREY,
    TAG_REWARD, TAG_COST, TAG_PROFIT, TAG_HEADER, TAG_SUBHEADER, TAG_TOTAL_PROFIT_LEG,
    BASE_FONT_FAMILY, BASE_FONT_SIZE,
    KEY_CUSTOM_PAD_SIZES
)
import settings_manager
import journal_parser
import api_handler
from api_handler import OperationCancelledError
import optimizer_logic
import language as lang_module
import shipyard_db_manager


logger = logging.getLogger(__name__)

# ---- Variables d'état spécifiques à l'onglet Analyse ----
CURRENT_SYSTEM_ANALYSIS = "?"
CURRENT_STATION_ANALYSIS = "?"
CURRENT_SHIP_TYPE_ANALYSIS = "Unknown"
CURRENT_CARGO_CAPACITY_ANALYSIS = 0
CURRENT_PAD_SIZE_ANALYSIS = "?"
EFFECTIVE_JOURNAL_DIR_ANALYSIS = journal_parser.EFFECTIVE_JOURNAL_DIR

# ---- Widgets spécifiques à l'onglet Analyse ----
analysis_tab_frame = None
status_lbl = None
db_status_label = None
shipyard_db_status_lbl = None
global_label = None
ship_label = None
cargo_label = None
journal_dir_display_label = None
open_settings_btn = None
refresh_loc_btn = None
update_btn = None
launch_btn = None
commod_sugg_btn = None
sort_by_label_widget = None
sort_by_dist_ly_radio_btn = None
sort_by_profit_radio_btn = None
sort_by_dist_ls_radio_btn = None
to_collect_label_widget = None
commod_list = None
total_lbl = None
unknown_pad_frame = None
unknown_pad_ship_label = None
unknown_pad_entry = None
save_pad_size_btn = None
text_out_mission_supply = None
text_out_round_trip = None

# Variables tk partagées
s_radius_var = None
s_age_var = None
s_station_dist_var = None
s_include_planetary_var = None
s_include_fleet_carriers_var = None
s_sort_var = None
s_journal_dir_label_var = None
s_language_var = None

# Callbacks et éléments partagés
s_shared_root = None
s_update_status_func = None
s_set_buttons_state_func = None
s_open_settings_window_func = None
s_cancel_main_event = None
s_sort_treeview_column_general_func = None
s_settings_window_ref = None # Peut être utilisé pour le parentage des dialogues
s_update_journal_dir_display_label_func = None # Fonction de gui_main

# Données pour suggestions
top_sourcing_stations_for_suggestions = []
commod_sugg_window = None

# --- Fonctions spécifiques à l'onglet Analyse ---

def _update_gui_with_player_info(sys_name, sta_name, ship_name, cargo_cap, pad_sz, eff_dir):
    """ Met à jour les labels d'info joueur sur cet onglet EN UTILISANT LES PARAMÈTRES FOURNIS. """
    global global_label, ship_label, cargo_label, status_lbl, unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, unknown_pad_ship_label, analysis_tab_frame

    logger.debug(f"AnalysisTab: _update_gui_with_player_info called with Sys='{sys_name}', Sta='{sta_name}', Ship='{ship_name}', Pad='{pad_sz}'")

    if not all([global_label, ship_label, cargo_label, analysis_tab_frame]):
        logger.warning("AnalysisTab: _update_gui_with_player_info - GUI elements not ready.")
        return

    loc_text = f"{lang_module.get_string('location_label_prefix')} {sys_name} / {sta_name if sta_name and sta_name != '?' else 'N/A'}"
    ship_text = f"{lang_module.get_string('ship_label_prefix')} {ship_name} (Pad {pad_sz})"
    cargo_text = f"{lang_module.get_string('cargo_label_prefix')} {cargo_cap} t"

    is_error_or_cancel_status = False
    if status_lbl and status_lbl.winfo_exists():
        current_status_text = status_lbl.cget("text").lower()
        cancel_text = lang_module.get_string("cancel_button").lower()
        error_text = lang_module.get_string("error_dialog_title").lower()
        is_error_or_cancel_status = cancel_text in current_status_text or \
                                    error_text in current_status_text or \
                                    "erreur" in current_status_text

    if sys_name == "No Journal Dir" or sys_name == "Error - No Journal" or sys_name == "No Events":
        global_label.config(text=f"{lang_module.get_string('location_label_prefix')} {lang_module.get_string('error_dialog_title')}/{lang_module.get_string('journal_dir_not_found')}")
        ship_label.config(text=f"{lang_module.get_string('ship_label_prefix')} ? (Pad ?)")
        cargo_label.config(text=f"{lang_module.get_string('cargo_label_prefix')} ?")
        if s_update_status_func: s_update_status_func(f"{lang_module.get_string('error_dialog_title')}: Journal issue ({sys_name}). Check logs or set manually.", None, target_status_label_widget=status_lbl)
        if unknown_pad_frame and unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid_remove()
    else:
        global_label.config(text=loc_text)
        ship_label.config(text=ship_text)
        cargo_label.config(text=cargo_text)
        status_msg_loc = lang_module.get_string("location_ship_refreshed")
        if pad_sz == '?':
            status_msg_loc = lang_module.get_string("pad_size_unknown_status", ship_type=ship_name)
            if unknown_pad_frame and analysis_tab_frame.winfo_exists() :
                if unknown_pad_ship_label: unknown_pad_ship_label.config(text=lang_module.get_string("pad_for_ship_label", ship_type=ship_name))
                if not unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid(in_=analysis_tab_frame, column=0, row=6, columnspan=4, sticky="ew", pady=5, padx=5)
                if unknown_pad_entry: unknown_pad_entry.delete(0, tk.END); unknown_pad_entry.focus_set(); unknown_pad_entry.config(state=tk.NORMAL)
                if save_pad_size_btn: save_pad_size_btn.config(state=tk.NORMAL)
        else:
            if unknown_pad_frame and unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid_remove()

        if not is_error_or_cancel_status and s_update_status_func:
             s_update_status_func(status_msg_loc, None, target_status_label_widget=status_lbl)

    logger.info(f"AnalysisTab GUI updated: Sys='{sys_name}', Station='{sta_name}', Ship='{ship_name}', Pad='{pad_sz}'")


def refresh_location_and_ship_display():
    global status_lbl, s_shared_root
    # Pas besoin de déclarer global pour les variables de module suivantes si _task le fait.
    # global CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, ... (déjà au niveau module)

    logger.debug("AnalysisTab: refresh_location_and_ship_display called")
    if not all([global_label, ship_label, cargo_label, s_shared_root]):
        logger.warning("AnalysisTab: GUI elements or root not ready for location/ship refresh."); return

    set_analysis_buttons_state(operation_running=True, cancellable=False, source_tab="main")
    if s_update_status_func: s_update_status_func(lang_module.get_string("status_refreshing_location_ship"), indeterminate=True, target_status_label_widget=status_lbl)

    def _task():
        # Déclarer global pour modifier les variables au niveau du module depuis cette fonction imbriquée
        global CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, CURRENT_SHIP_TYPE_ANALYSIS
        global CURRENT_CARGO_CAPACITY_ANALYSIS, CURRENT_PAD_SIZE_ANALYSIS, EFFECTIVE_JOURNAL_DIR_ANALYSIS
        global s_update_journal_dir_display_label_func # Pour s'assurer qu'on utilise la globale

        try:
            s, st, sh, c, p, eff_dir, _materials_data = journal_parser.get_player_state_data()
            logger.debug(f"AnalysisTab _task: Data RECEIVED from journal_parser: Sys='{s}', Sta='{st}', Ship='{sh}', Pad='{p}'")

            CURRENT_SYSTEM_ANALYSIS = s
            CURRENT_STATION_ANALYSIS = st
            CURRENT_SHIP_TYPE_ANALYSIS = sh
            CURRENT_CARGO_CAPACITY_ANALYSIS = c
            CURRENT_PAD_SIZE_ANALYSIS = p
            EFFECTIVE_JOURNAL_DIR_ANALYSIS = eff_dir

            if s_shared_root and s_shared_root.winfo_exists() and s_update_journal_dir_display_label_func:
                 s_shared_root.after(0, s_update_journal_dir_display_label_func)

            if s_shared_root and s_shared_root.winfo_exists():
                s_shared_root.after(0, _update_gui_with_player_info, s, st, sh, c, p, eff_dir)

        except Exception as e: # 'e' est défini ici pour ce bloc except
            logger.exception("AnalysisTab RLaSD: Exception in _task thread")
            if s_shared_root and s_shared_root.winfo_exists() and status_lbl and status_lbl.winfo_exists():
                # Capture de 'e' dans la lambda
                s_shared_root.after(0, lambda err_val=e: s_update_status_func(lang_module.get_string("error_refresh_thread", error=err_val), None, target_status_label_widget=status_lbl))
        finally:
            if s_shared_root and s_shared_root.winfo_exists():
                 s_shared_root.after(0, lambda: set_analysis_buttons_state(operation_running=False, source_tab="main"))
    threading.Thread(target=_task, daemon=True).start()


def update_commodities_display_in_gui(needs_dict):
    global commod_list, total_lbl, s_shared_root
    if not all([commod_list, total_lbl, s_shared_root]):
        logger.warning("AnalysisTab: GUI commod_list/total_lbl or root not ready for update.")
        return
    def _update():
        if not (commod_list and commod_list.winfo_exists() and total_lbl and total_lbl.winfo_exists()): return
        commod_list.delete(0, tk.END)
        if needs_dict and isinstance(needs_dict, dict) and needs_dict:
            num_items = len(needs_dict)
            commod_list.config(height=max(1, min(num_items, 5)))
            total_units_needed = sum(needs_dict.values())
            for name, qty in needs_dict.items(): commod_list.insert(tk.END, f"{name.title()}: {qty}")
            total_lbl.config(text=lang_module.get_string("total_units_label", total_units=total_units_needed, num_types=num_items))
        else:
            commod_list.config(height=1)
            commod_list.insert(tk.END, lang_module.get_string("no_active_missions_label"))
            total_lbl.config(text=lang_module.get_string("total_zero_label"))
    if s_shared_root and s_shared_root.winfo_exists():
        s_shared_root.after(0, _update)


def on_select_journal_dir_pressed():
    global s_shared_root, s_settings_window_ref, status_lbl
    global EFFECTIVE_JOURNAL_DIR_ANALYSIS, s_update_journal_dir_display_label_func

    initial_dir_to_browse = settings_manager.get_setting(KEY_CUSTOM_JOURNAL_DIR)
    if not initial_dir_to_browse or not os.path.isdir(initial_dir_to_browse):
        if EFFECTIVE_JOURNAL_DIR_ANALYSIS and EFFECTIVE_JOURNAL_DIR_ANALYSIS not in ["Auto-detecting...", "Not Found", "Error processing journals"] and os.path.isdir(EFFECTIVE_JOURNAL_DIR_ANALYSIS):
            initial_dir_to_browse = os.path.dirname(EFFECTIVE_JOURNAL_DIR_ANALYSIS)
        else: initial_dir_to_browse = os.path.expanduser("~")

    # Déterminer la fenêtre parente pour le dialogue. Utiliser la fenêtre des settings si elle est ouverte, sinon la fenêtre principale.
    parent_for_dialog = None
    if gui_settings_window.settings_window and gui_settings_window.settings_window.winfo_exists(): # Accès direct à la réf de la fenêtre settings
        parent_for_dialog = gui_settings_window.settings_window
    elif s_shared_root and s_shared_root.winfo_exists():
        parent_for_dialog = s_shared_root
    
    new_dir = filedialog.askdirectory(
        initialdir=initial_dir_to_browse,
        title=lang_module.get_string("settings_change_journal_dir_button"),
        parent=parent_for_dialog # Utiliser la fenêtre parente déterminée
    )
    if new_dir:
        settings_manager.update_setting(KEY_CUSTOM_JOURNAL_DIR, new_dir)
        logger.info(f"Custom journal directory selected by user: {new_dir}")
        
        if s_update_status_func: # Ceci mettra à jour le label de statut de l'onglet Analyse
            s_update_status_func(lang_module.get_string("journal_dir_set_permanent_status"), None, target_status_label_widget=status_lbl)
        
        if s_update_journal_dir_display_label_func: # Mettre à jour le label dans Settings via la fonction passée
             s_update_journal_dir_display_label_func()

        refresh_location_and_ship_display() # Rafraîchir pour prendre en compte le nouveau chemin
    else:
        logger.info("Journal directory selection cancelled by user.")


def on_save_pad_size_pressed():
    global unknown_pad_entry, save_pad_size_btn, unknown_pad_frame, status_lbl
    global CURRENT_SHIP_TYPE_ANALYSIS, CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS # Variables de module
    global CURRENT_CARGO_CAPACITY_ANALYSIS, CURRENT_PAD_SIZE_ANALYSIS, EFFECTIVE_JOURNAL_DIR_ANALYSIS

    if s_set_buttons_state_func: s_set_buttons_state_func(operation_running=True, cancellable=False)
    if s_update_status_func: s_update_status_func(lang_module.get_string("status_saving_pad_size"), indeterminate=True, target_status_label_widget=status_lbl)
    try:
        ship_type_to_save_pad_for = CURRENT_SHIP_TYPE_ANALYSIS
        entered_pad_size_str = unknown_pad_entry.get().strip()
        if not ship_type_to_save_pad_for or ship_type_to_save_pad_for in ["Unknown", "Journal not found", "Error", "Error - No Journal"]:
            msg = lang_module.get_string("error_current_ship_unknown_pad"); logger.error(msg)
            if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl)
        else:
            try:
                pad_size_int = int(entered_pad_size_str)
                if pad_size_int not in [1, 2, 3]: raise ValueError(lang_module.get_string("pad_size_error", error="Invalid value (must be 1, 2, or 3)"))
                current_custom_pad_sizes = settings_manager.get_setting(KEY_CUSTOM_PAD_SIZES, {})
                if not isinstance(current_custom_pad_sizes, dict): current_custom_pad_sizes = {}
                current_custom_pad_sizes[ship_type_to_save_pad_for.lower()] = pad_size_int
                settings_manager.update_setting(KEY_CUSTOM_PAD_SIZES, current_custom_pad_sizes)
                logger.info(f"Custom pad size for '{ship_type_to_save_pad_for}' set to {pad_size_int} in memory.")
                if settings_manager.save_settings_to_file():
                    msg = lang_module.get_string("pad_size_saved_status", pad_size=pad_size_int, ship_type=ship_type_to_save_pad_for); logger.info(msg)
                    CURRENT_PAD_SIZE_ANALYSIS = str(pad_size_int) # Mettre à jour l'état de cet onglet
                    _update_gui_with_player_info( # Appeler avec les valeurs d'état actuelles de cet onglet
                        CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS,
                        CURRENT_SHIP_TYPE_ANALYSIS, CURRENT_CARGO_CAPACITY_ANALYSIS,
                        CURRENT_PAD_SIZE_ANALYSIS, EFFECTIVE_JOURNAL_DIR_ANALYSIS
                    )
                else:
                    msg = lang_module.get_string("failed_to_save_settings_after_pad"); logger.error(msg)
                    if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl)
            except ValueError as ve:
                msg = lang_module.get_string("pad_size_error", error=ve); logger.error(msg)
                if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl)
            except Exception as ex:
                logger.exception("Unexpected error saving pad size details:"); msg = f"Error saving pad size details: {ex}"
                if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl)
    finally:
        if s_set_buttons_state_func: s_set_buttons_state_func(False, False)


def on_update_db_pressed():
    global status_lbl, db_status_label, s_shared_root, text_out_mission_supply
    global CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS

    if CURRENT_SYSTEM_ANALYSIS == "?" or "Error" in CURRENT_SYSTEM_ANALYSIS or "No Journal" in CURRENT_SYSTEM_ANALYSIS or "No Events" in CURRENT_SYSTEM_ANALYSIS:
        msg = lang_module.get_string("error_db_update_no_system"); logger.warning(msg)
        if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl)
        if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END); text_out_mission_supply.insert(tk.END, msg + "\n"); text_out_mission_supply.config(state=tk.DISABLED)
        return

    s_cancel_main_event.clear()
    set_analysis_buttons_state(operation_running=True, cancellable=True, source_tab="main")
    if s_update_status_func: s_update_status_func(lang_module.get_string("status_validating_settings_db_update"), 0, target_status_label_widget=status_lbl)
    try:
        radius_to_use = float(s_radius_var.get()); max_age_to_use = int(s_age_var.get()); include_fc_setting = s_include_fleet_carriers_var.get()
        if radius_to_use <= 0: raise ValueError(lang_module.get_string("settings_validation_error", error="Radius must be positive."))
        if max_age_to_use < 0: raise ValueError(lang_module.get_string("settings_validation_error", error="DB Age must be non-negative."))

        def _progress_update_callback(message, percentage):
            if not s_cancel_main_event.is_set() and s_update_status_func:
                s_update_status_func(message, percentage, target_status_label_widget=status_lbl)

        async def _async_db_update_task_wrapper():
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_updating_databases_for_system", system=CURRENT_SYSTEM_ANALYSIS), 0, target_status_label_widget=status_lbl)
            departure_data_res, local_data_res = (None, None)
            try:
                departure_data_res, local_data_res = await api_handler.update_databases_if_needed( None, CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, radius_to_use, max_age_to_use, include_fc_setting, s_cancel_main_event, _progress_update_callback, force_refresh=True)
                if s_cancel_main_event.is_set(): raise OperationCancelledError(lang_module.get_string("status_db_update_cancelled"))
                final_status_msg = lang_module.get_string("status_db_update_finished"); success = True
                if not departure_data_res and (CURRENT_STATION_ANALYSIS and CURRENT_STATION_ANALYSIS != "?") : final_status_msg += lang_module.get_string("status_db_update_departure_error"); success = False
                if not local_data_res and (CURRENT_SYSTEM_ANALYSIS and CURRENT_SYSTEM_ANALYSIS != "?"): final_status_msg += lang_module.get_string("status_db_update_local_error"); success = False
                if s_update_status_func: s_update_status_func(final_status_msg, 100 if success else -1, target_status_label_widget=status_lbl)
                if db_status_label: db_status_label.config(text=optimizer_logic.get_last_db_update_time_str())
            except OperationCancelledError:
                logger.info("DB Update operation was actively cancelled.")
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_db_update_cancelled"), -1, target_status_label_widget=status_lbl)
            except Exception as e_async: # 'e_async' est défini ici
                logger.exception("Error in _async_db_update_task_wrapper:")
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_db_update_error_generic", error=e_async), -1, target_status_label_widget=status_lbl)
                if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.insert(tk.END, f"{lang_module.get_string('status_db_update_error_generic', error=e_async)}\n"); text_out_mission_supply.config(state=tk.DISABLED)

        def _run_in_thread():
            loop = None
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(_async_db_update_task_wrapper())
            except Exception as e_thread: # 'e_thread' est défini ici
                logger.exception("Unhandled error running async DB update task in thread:"); msg_err_thread = lang_module.get_string("status_db_update_thread_error", error=e_thread)
                if not s_cancel_main_event.is_set() and s_update_status_func:
                    s_update_status_func(msg_err_thread, -1, target_status_label_widget=status_lbl)
                if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.insert(tk.END, msg_err_thread + "\n"); text_out_mission_supply.config(state=tk.DISABLED)
            finally:
                if loop and not loop.is_closed(): loop.close()
                if s_shared_root and s_shared_root.winfo_exists(): s_shared_root.after(0, set_analysis_buttons_state, False, False, "main")
        threading.Thread(target=_run_in_thread, daemon=True).start()
    except ValueError as ve:
        msg_val_err = lang_module.get_string("settings_error_db_update", error=ve); logger.error(msg_val_err)
        if s_update_status_func: s_update_status_func(msg_val_err, -1, target_status_label_widget=status_lbl)
        if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END); text_out_mission_supply.insert(tk.END, msg_val_err + "\n"); text_out_mission_supply.config(state=tk.DISABLED)
        set_analysis_buttons_state(False, False, "main")
    except Exception as e_main_db: # 'e_main_db' est défini ici
        logger.exception("Unexpected error before launching market DB update:")
        if s_update_status_func: s_update_status_func(lang_module.get_string("status_db_update_error_generic", error=e_main_db), -1, target_status_label_widget=status_lbl) # Utiliser une clé générique
        set_analysis_buttons_state(False, False, "main")

# Le reste de async_analysis_task_local et des autres fonctions doit être revu pour :
# 1. Utiliser CURRENT_..._ANALYSIS et EFFECTIVE_JOURNAL_DIR_ANALYSIS.
# 2. Utiliser s_shared_root.after(...)
# 3. S'assurer que les lambdas capturent correctement les variables d'exception (ex: err_val=e)
# 4. Utiliser s_sort_treeview_column_general_func pour le tri dans on_commodities_suggestions_pressed.

async def async_analysis_task_local(http_session, radius_ly_param, max_db_age_days_param, max_station_dist_ls_param, sort_by_param, include_planetary_param, include_fleet_carriers_param, cancel_event: threading.Event, progress_callback_gui):
    mission_supply_output_segments = []; trade_routes_output_segments = []; analysis_error_occurred = False
    global top_sourcing_stations_for_suggestions, commod_sugg_btn # Ces variables sont globales au module `gui_analysis_tab`
    # Utiliser les variables d'état globales de ce module
    global CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, CURRENT_SHIP_TYPE_ANALYSIS
    global CURRENT_CARGO_CAPACITY_ANALYSIS, CURRENT_PAD_SIZE_ANALYSIS, EFFECTIVE_JOURNAL_DIR_ANALYSIS
    global s_shared_root, status_lbl, text_out_mission_supply, text_out_round_trip, db_status_label # Widgets de l'UI

    MAX_STATIONS_FOR_ROUND_TRIPS = int(settings_manager.get_setting(KEY_MAX_STATIONS_FOR_TRADE_LOOPS, DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS))
    top_sourcing_stations_for_suggestions.clear()
    if commod_sugg_btn and s_shared_root and s_shared_root.winfo_exists():
        def _disable_sugg_btn(): # Fonction locale, pas besoin de global
            if commod_sugg_btn and commod_sugg_btn.winfo_exists(): commod_sugg_btn.config(state=tk.DISABLED)
        if threading.current_thread() is threading.main_thread(): _disable_sugg_btn()
        else: s_shared_root.after(0, _disable_sugg_btn)
    
    try:
        progress_callback_gui(lang_module.get_string("status_loading_journal"), 5)
        logger.info(f"Analysis using journal directory: {EFFECTIVE_JOURNAL_DIR_ANALYSIS}")
        try: num_journal_files_for_missions = int(settings_manager.get_setting(KEY_NUM_JOURNAL_FILES_MISSIONS, DEFAULT_NUM_JOURNAL_FILES_MISSIONS))
        except ValueError: num_journal_files_for_missions = DEFAULT_NUM_JOURNAL_FILES_MISSIONS
        journal_events_for_missions = journal_parser.load_journal_events(EFFECTIVE_JOURNAL_DIR_ANALYSIS, num_files_to_check=num_journal_files_for_missions)
        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (after loading journal).")
        if not journal_events_for_missions: mission_supply_output_segments.append((lang_module.get_string("materials_no_journal_events_status") + f" (checked {num_journal_files_for_missions} files)\n", None))
        
        needed_commodities = {}; total_rewards_from_missions = 0
        progress_callback_gui(lang_module.get_string("status_parsing_missions"), 10)
        if journal_events_for_missions: needed_commodities, total_rewards_from_missions = journal_parser.parse_active_missions(journal_events_for_missions)
        
        if s_shared_root: s_shared_root.after(0, lambda nd=needed_commodities: update_commodities_display_in_gui(nd)) # Capturer needed_commodities
        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (after parsing missions).")
        
        departure_data, local_data = None, None; db_update_start_progress = 15; db_update_end_progress = 45
        progress_callback_gui(lang_module.get_string("status_checking_market_data"), db_update_start_progress)
        
        def db_update_progress_for_analysis(message, percentage):
            if cancel_event.is_set(): return # Stopper si annulé
            current_progress = db_update_start_progress + (percentage / 100.0) * (db_update_end_progress - db_update_start_progress)
            progress_callback_gui(f"{lang_module.get_string('status_db_update_progress_prefix')}: {message}", int(current_progress))
        
        departure_data, local_data = await api_handler.update_databases_if_needed(http_session, CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, radius_ly_param, max_db_age_days_param, include_fleet_carriers_param, cancel_event, db_update_progress_for_analysis)
        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (during/after DB Update).")
        
        if s_shared_root and db_status_label: s_shared_root.after(0, lambda: db_status_label.config(text=optimizer_logic.get_last_db_update_time_str()))
        current_progress_after_db = db_update_end_progress
        
        if needed_commodities:
            mission_supply_output_segments.extend([(lang_module.get_string("missions_needs_label", count=len(needed_commodities), total_units=sum(needed_commodities.values())), None), (f"{total_rewards_from_missions:,.0f} CR", TAG_REWARD), ("\n", None)])
            mission_supply_output_segments.extend([(lang_module.get_string("missions_ship_label", ship_type=CURRENT_SHIP_TYPE_ANALYSIS, pad_size=CURRENT_PAD_SIZE_ANALYSIS, cargo_capacity=CURRENT_CARGO_CAPACITY_ANALYSIS), None), (lang_module.get_string("missions_est_trips_label", trips=math.ceil(sum(needed_commodities.values()) / CURRENT_CARGO_CAPACITY_ANALYSIS) if CURRENT_CARGO_CAPACITY_ANALYSIS > 0 else 'N/A') + "\n", None)])
            sort_option_map_display = {'d': lang_module.get_string("sort_by_dist_ly"), 'b': lang_module.get_string("sort_by_profit"), 's': lang_module.get_string("sort_by_dist_ls")}; readable_sort_option = sort_option_map_display.get(sort_by_param, sort_by_param)
            planetary_filter_text = lang_module.get_string("planetary_filter_included") if include_planetary_param else lang_module.get_string("planetary_filter_excluded")
            fc_filter_text = lang_module.get_string("fc_filter_included") if include_fleet_carriers_param else lang_module.get_string("fc_filter_excluded")
            mission_supply_output_segments.extend([(lang_module.get_string("missions_filters_label", dist_ls=max_station_dist_ls_param, planetary=planetary_filter_text, fc=fc_filter_text) + "\n", None), (lang_module.get_string("missions_sorting_label", sort_option=readable_sort_option) + "\n", None), ("=" * 60 + "\n", None), (lang_module.get_string("missions_supply_options_header") + "\n", TAG_HEADER), ("=" * 60 + "\n\n", None)])
            if not local_data or not local_data.get('station_markets'):
                 if needed_commodities: mission_supply_output_segments.append((lang_module.get_string("status_db_update_local_error") + " (for mission sourcing)\n", None)); logger.warning("Could not get valid local market data for mission item sourcing.")
            
            progress_callback_gui(lang_module.get_string("status_analyzing_purchase_options"), current_progress_after_db + 5)
            full_opts, partial_opts, complement_opts = optimizer_logic.generate_purchase_suggestions(needed_commodities, local_data, departure_data, CURRENT_PAD_SIZE_ANALYSIS, max_station_dist_ls_param, include_planetary_param, include_fleet_carriers_param, CURRENT_SYSTEM_ANALYSIS, cancel_event=cancel_event)
            profit_calc = lambda data: total_rewards_from_missions - sum(needed_commodities.get(cn,0) * cp for cn,cp in data['commodities'].items()); sort_key_func_full = lambda x: x['distance_ly'];
            if sort_by_param == 'b': sort_key_func_full = lambda x: -profit_calc(x)
            elif sort_by_param == 's': sort_key_func_full = lambda x: x.get('distance_ls', float('inf'))
            full_opts.sort(key=sort_key_func_full)
            
            # Boucle pour full_opts
            if full_opts:
                for opt_data in full_opts[:5]: top_sourcing_stations_for_suggestions.append({'system_name': opt_data['system_name'], 'station_name': opt_data['station_name'], 'distance_ly': opt_data.get('distance_ly'), 'distance_ls': opt_data.get('distance_ls')})
                mission_supply_output_segments.append((lang_module.get_string("missions_full_supply_options_subheader") + "\n", TAG_SUBHEADER))
                for opt_idx, opt_data in enumerate(full_opts[:5]):
                    # ... (logique affichage full_opts, identique à la version précédente)
                    if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (processing full supply options).")
                    dist_ls_info = f" ({opt_data.get('distance_ls', float('inf')):.0f} LS)" if opt_data.get('distance_ls', float('inf')) != float('inf') else " (? LS)"; pad_disp = str(opt_data.get('pad_size_int', '?')); pad_info = f" (Pad {pad_disp})"
                    cost = sum(needed_commodities.get(cn,0) * cp for cn, cp in opt_data['commodities'].items()); profit = total_rewards_from_missions - cost
                    mission_supply_output_segments.extend([(f"  Station: {opt_data['station_name']}{dist_ls_info}{pad_info} ({opt_data['system_name']})\n", None), (f"    Dist LY: {opt_data['distance_ly']:.1f} | Cost: ", None), (f"{cost:,.0f} CR", TAG_COST), (f" | Profit: ", None), (f"{profit:,.0f} CR", TAG_PROFIT), ("\n\n", None) ])
                if partial_opts: # Affichage des options partielles si full_opts existent
                    mission_supply_output_segments.append(("\n" + lang_module.get_string("missions_partial_supply_options_subheader") + "\n", TAG_SUBHEADER))
                    for opt_idx_p, opt_data_p in enumerate(partial_opts[:5]):
                        # ... (logique affichage partial_opts + complements, identique à la version précédente)
                        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (processing partial supply options).")
                        dist_ls_info_p = f" ({opt_data_p.get('distance_ls', float('inf')):.0f} LS)" if opt_data_p.get('distance_ls', float('inf')) != float('inf') else " (? LS)"
                        pad_disp_p = str(opt_data_p.get('pad_size_int', '?')); pad_info_p = f" (Pad {pad_disp_p})"
                        partial_cost_p = sum(needed_commodities.get(cn,0) * cp for cn, cp in opt_data_p['commodities'].items())
                        mission_supply_output_segments.append((f"  Station: {opt_data_p['station_name']}{dist_ls_info_p}{pad_info_p} ({opt_data_p['system_name']})\n", None))
                        mission_supply_output_segments.append((f"    Dist LY: {opt_data_p['distance_ly']:.1f} | Covers {len(opt_data_p['commodities'])} of {len(needed_commodities)} types.\n", None))
                        mission_supply_output_segments.append((f"    Items available here (cost for these: ", None)); mission_supply_output_segments.append((f"{partial_cost_p:,.0f} CR", TAG_COST)); mission_supply_output_segments.append(("):\n", None))
                        for comm_name, price in opt_data_p['commodities'].items():
                            mission_supply_output_segments.append((f"      - {comm_name.title()}: {needed_commodities.get(comm_name,0)} @ {price:,.0f} CR/u\n", None))
                        if opt_idx_p == 0 and complement_opts:
                            mission_supply_output_segments.append((f"    Complementary sources for remaining items (for the above best partial):\n", TAG_SUBHEADER))
                            missing_after_this_partial = {cn: qty for cn, qty in needed_commodities.items() if cn not in opt_data_p['commodities']}
                            total_complement_cost = 0; complement_details_segments = []; all_complements_found = True
                            for comm_name_missing, qty_missing in missing_after_this_partial.items():
                                if comm_name_missing in complement_opts:
                                    comp_src = complement_opts[comm_name_missing]; comp_cost_unit = comp_src['price']; total_complement_cost += qty_missing * comp_cost_unit
                                    complement_details_segments.extend([(f"      - {comm_name_missing.title()}: {qty_missing} units from {comp_src['station_name']} ({comp_src['system_name']}) @ {comp_src['price']:,.0f} CR/u\n", None),
                                                                        (f"        (Dist: {comp_src['distance_ly']:.1f} LY, {comp_src.get('distance_ls', float('inf')):.0f} LS, Pad {comp_src.get('pad_size_int', '?')})\n", None)])
                                else:
                                    all_complements_found = False; complement_details_segments.append((f"      - {comm_name_missing.title()}: No complementary source found matching filters.\n", None))
                            if complement_details_segments:
                                 mission_supply_output_segments.extend(complement_details_segments)
                                 if all_complements_found:
                                     total_mission_cost_with_complements = partial_cost_p + total_complement_cost
                                     total_profit_with_complements = total_rewards_from_missions - total_mission_cost_with_complements
                                     mission_supply_output_segments.extend([(f"    Combined Cost (this station + complements): ", None), (f"{total_mission_cost_with_complements:,.0f} CR", TAG_COST),
                                                                            (f" | Est. Total Profit: ", None), (f"{total_profit_with_complements:,.0f} CR\n", TAG_PROFIT)])
                                 else: mission_supply_output_segments.append((f"    (Cannot calculate total profit as some complementary items are missing)\n", None))
                        mission_supply_output_segments.append(("\n", None))
            else: # No full_opts
                mission_supply_output_segments.extend([(lang_module.get_string("missions_no_full_supply") + "\n", None)])
                if partial_opts: # Si pas de full_opts, mais des partial_opts
                    mission_supply_output_segments.append(("\n" + lang_module.get_string("missions_partial_supply_options_subheader") + "\n", TAG_SUBHEADER))
                    for opt_idx_p, opt_data_p in enumerate(partial_opts[:5]):
                        # ... (logique affichage partial_opts + complements, identique à ci-dessus)
                        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (processing partial supply options).")
                        dist_ls_info_p = f" ({opt_data_p.get('distance_ls', float('inf')):.0f} LS)" if opt_data_p.get('distance_ls', float('inf')) != float('inf') else " (? LS)"
                        pad_disp_p = str(opt_data_p.get('pad_size_int', '?')); pad_info_p = f" (Pad {pad_disp_p})"
                        partial_cost_p = sum(needed_commodities.get(cn,0) * cp for cn, cp in opt_data_p['commodities'].items())
                        mission_supply_output_segments.append((f"  Station: {opt_data_p['station_name']}{dist_ls_info_p}{pad_info_p} ({opt_data_p['system_name']})\n", None))
                        mission_supply_output_segments.append((f"    Dist LY: {opt_data_p['distance_ly']:.1f} | Covers {len(opt_data_p['commodities'])} of {len(needed_commodities)} types.\n", None))
                        mission_supply_output_segments.append((f"    Items available here (cost for these: ", None)); mission_supply_output_segments.append((f"{partial_cost_p:,.0f} CR", TAG_COST)); mission_supply_output_segments.append(("):\n", None))
                        for comm_name, price in opt_data_p['commodities'].items():
                            mission_supply_output_segments.append((f"      - {comm_name.title()}: {needed_commodities.get(comm_name,0)} @ {price:,.0f} CR/u\n", None))
                        if opt_idx_p == 0 and complement_opts:
                            mission_supply_output_segments.append((f"    Complementary sources for remaining items (for the above best partial):\n", TAG_SUBHEADER))
                            missing_after_this_partial = {cn: qty for cn, qty in needed_commodities.items() if cn not in opt_data_p['commodities']}
                            total_complement_cost = 0; complement_details_segments = []; all_complements_found = True
                            for comm_name_missing, qty_missing in missing_after_this_partial.items():
                                if comm_name_missing in complement_opts:
                                    comp_src = complement_opts[comm_name_missing]; comp_cost_unit = comp_src['price']; total_complement_cost += qty_missing * comp_cost_unit
                                    complement_details_segments.extend([(f"      - {comm_name_missing.title()}: {qty_missing} units from {comp_src['station_name']} ({comp_src['system_name']}) @ {comp_src['price']:,.0f} CR/u\n", None),
                                                                        (f"        (Dist: {comp_src['distance_ly']:.1f} LY, {comp_src.get('distance_ls', float('inf')):.0f} LS, Pad {comp_src.get('pad_size_int', '?')})\n", None)])
                                else:
                                    all_complements_found = False; complement_details_segments.append((f"      - {comm_name_missing.title()}: No complementary source found matching filters.\n", None))
                            if complement_details_segments:
                                 mission_supply_output_segments.extend(complement_details_segments)
                                 if all_complements_found:
                                     total_mission_cost_with_complements = partial_cost_p + total_complement_cost
                                     total_profit_with_complements = total_rewards_from_missions - total_mission_cost_with_complements
                                     mission_supply_output_segments.extend([(f"    Combined Cost (this station + complements): ", None), (f"{total_mission_cost_with_complements:,.0f} CR", TAG_COST),
                                                                            (f" | Est. Total Profit: ", None), (f"{total_profit_with_complements:,.0f} CR\n", TAG_PROFIT)])
                                 else: mission_supply_output_segments.append((f"    (Cannot calculate total profit as some complementary items are missing)\n", None))
                        mission_supply_output_segments.append(("\n", None))
                else: # Ni full_opts ni partial_opts
                    mission_supply_output_segments.append((lang_module.get_string("missions_no_supply_options") + "\n", None))
            
            mission_supply_output_segments.append(("—" * 50 + "\n", None)) # Séparateur

            # Logique des routes commerciales aller-retour
            trade_routes_output_segments.extend([("=" * 60 + "\n", None), (lang_module.get_string("missions_round_trip_header") + "\n", TAG_HEADER), ("=" * 60 + "\n\n", None)])
            candidate_stations_for_loops_info = []; seen_for_loops = set()
            opts_for_loops = full_opts if full_opts else (partial_opts if partial_opts else [])
            for opt_data in opts_for_loops:
                if len(seen_for_loops) >= MAX_STATIONS_FOR_ROUND_TRIPS: break
                key = (opt_data['system_name'], opt_data['station_name'])
                if key not in seen_for_loops: candidate_stations_for_loops_info.append(opt_data); seen_for_loops.add(key)
            
            num_loop_candidates = len(candidate_stations_for_loops_info); loop_start_progress = current_progress_after_db + 20; loop_end_progress = current_progress_after_db + 40
            if not candidate_stations_for_loops_info: trade_routes_output_segments.append((lang_module.get_string("missions_no_stations_for_round_trip")+"\n", None))
            else:
                logger.info(f"Checking round trip trades for up to {num_loop_candidates} stations (mission related).")
                for idx, station_info_for_loop in enumerate(candidate_stations_for_loops_info):
                    # ... (logique des routes commerciales aller-retour utilisant CURRENT_..._ANALYSIS et autres variables d'état)
                    if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled (during mission round trip trades).")
                    current_loop_prog_val = loop_start_progress + ( (idx + 1.0) / num_loop_candidates ) * (loop_end_progress - loop_start_progress) if num_loop_candidates > 0 else loop_start_progress
                    pickup_sys = station_info_for_loop['system_name']; pickup_sta = station_info_for_loop['station_name']
                    progress_callback_gui(f"Analyzing round trip for {pickup_sta} ({idx+1}/{num_loop_candidates})...", int(current_loop_prog_val))

                    player_buys_from_pickup_offers = [] # Réinitialiser pour chaque station
                    station_b_is_current_station_a = (pickup_sys == CURRENT_SYSTEM_ANALYSIS and pickup_sta == CURRENT_STATION_ANALYSIS)
                    if not station_b_is_current_station_a and local_data and pickup_sys in local_data.get('station_markets', {}) and pickup_sta in local_data['station_markets'][pickup_sys].get('stations_data', {}):
                        station_detail_b = local_data['station_markets'][pickup_sys]['stations_data'][pickup_sta]
                        player_buys_from_pickup_offers = station_detail_b.get('sells_to_player', [])
                    elif station_b_is_current_station_a and departure_data: # Si la station de pickup est la station actuelle
                        player_buys_from_pickup_offers = [{'commodityName': o.get('commodityName'), 'commodity_localised': o.get('commodity_localised', o.get('commodityName')), 'price': o.get('buyPrice', 0), 'stock': o.get('stock', 0), 'quantity_at_station': o.get('stock', 0)} for o in departure_data.get('offers', []) if o.get('buyPrice', 0) > 0 and o.get('stock', 0) > 0]
                    else: # Données non en cache, appel API
                        player_buys_from_pickup_offers = await api_handler.get_station_specific_market_data(http_session, pickup_sys, pickup_sta, max_days_ago=max_db_age_days_param, include_fleet_carriers=include_fleet_carriers_param, player_action='buy', cancel_event=cancel_event)
                    if player_buys_from_pickup_offers is None: player_buys_from_pickup_offers = [] # S'assurer que c'est une liste

                    departure_offers_for_loop = departure_data.get('offers', []) if departure_data else []
                    outbound_trades_list, return_trades_list = await optimizer_logic.suggest_round_trip_opportunities(http_session, CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, pickup_sys, pickup_sta, sum(needed_commodities.values()), CURRENT_CARGO_CAPACITY_ANALYSIS, departure_offers_for_loop, player_buys_from_pickup_offers, local_data, max_db_age_days_param, include_fleet_carriers_param, cancel_event=cancel_event) # include_fc_param était manquant
                    trade_routes_output_segments.extend([("\n" + "—" * 50 + "\n", None), (lang_module.get_string("missions_trade_ops_for_trip_to", station_name=pickup_sta, system_name=pickup_sys) + "\n", TAG_SUBHEADER), (lang_module.get_string("missions_outbound_from_to", current_station=CURRENT_STATION_ANALYSIS or CURRENT_SYSTEM_ANALYSIS, pickup_station=pickup_sta) + "\n", None)])
                    total_outbound_profit_leg = 0
                    if outbound_trades_list:
                        for trade in outbound_trades_list: total_outbound_profit_leg += trade['total_profit']; trade_routes_output_segments.extend([(f"    - Buy: {trade['commodity_localised']} (Qty: {trade['quantity']}) @ ", None), (f"{trade['buy_price_at_source']:,.0f} CR/u", TAG_COST), (f"\n      Sell @ ", None), (f"{trade['sell_price_at_dest']:,.0f} CR/u", TAG_PROFIT), (f". Profit/u: ", None), (f"{trade['profit_per_unit']:,.0f}", TAG_PROFIT), (f" (Total: ", None), (f"{trade['total_profit']:,.0f} CR", TAG_PROFIT), (")\n", None)])
                        if total_outbound_profit_leg > 0 : trade_routes_output_segments.extend([(f"    Potential Total Outbound Profit for this leg: ", None), (f"{total_outbound_profit_leg:,.0f} CR", TAG_TOTAL_PROFIT_LEG), ("\n", None)])
                    else: trade_routes_output_segments.append(("    "+lang_module.get_string("missions_no_profitable_outbound")+"\n", None))
                    remaining_cargo_disp = max(0, CURRENT_CARGO_CAPACITY_ANALYSIS - sum(needed_commodities.values()))
                    trade_routes_output_segments.extend([(f"\n  {lang_module.get_string('missions_return_leg_from_to', pickup_station=pickup_sta, current_station=CURRENT_STATION_ANALYSIS or CURRENT_SYSTEM_ANALYSIS, cargo_space=remaining_cargo_disp)}:\n", None)])
                    total_return_profit_leg = 0
                    if return_trades_list:
                        for trade in return_trades_list: total_return_profit_leg += trade['total_profit']; trade_routes_output_segments.extend([(f"    - Buy: {trade['commodity_localised']} (Qty: {trade['quantity']}) @ ", None), (f"{trade['buy_price_at_source']:,.0f} CR/u at {pickup_sta}", TAG_COST), (f"\n      Sell @ ", None), (f"{trade['sell_price_at_dest']:,.0f} CR/u. Profit/u: ", TAG_PROFIT), (f"{trade['profit_per_unit']:,.0f}", TAG_PROFIT), (f" (Total: ", None), (f"{trade['total_profit']:,.0f} CR", TAG_PROFIT), (")\n", None)])
                        if total_return_profit_leg > 0: trade_routes_output_segments.extend([(f"    Potential Total Return Profit for this leg: ", None), (f"{total_return_profit_leg:,.0f} CR", TAG_TOTAL_PROFIT_LEG), ("\n", None)])
                    else: trade_routes_output_segments.append(("    "+lang_module.get_string("missions_no_profitable_return")+"\n", None))

        else: # Pas de needed_commodities (pas de missions)
            if not journal_events_for_missions: mission_supply_output_segments.append((lang_module.get_string("materials_no_journal_events_status") + "\n", None)) # Utiliser une clé plus générique
            else: mission_supply_output_segments.append((lang_module.get_string("no_active_missions_found") + "\n", TAG_SUBHEADER))
            
            general_trade_start_progress = current_progress_after_db + 5
            progress_callback_gui(lang_module.get_string("no_active_missions_found") + ". " + lang_module.get_string("status_checking_market_data") + "...", general_trade_start_progress)
            if not departure_data and (not local_data or not local_data.get('station_markets')):
                trade_routes_output_segments.append((lang_module.get_string("status_db_update_local_error") + " (for general trade search)\n", None)); logger.warning("Insufficient market data available for general trade search.")
            else:
                logger.info(f"Initiating general market trade search. Current Cargo: {CURRENT_CARGO_CAPACITY_ANALYSIS}t")
                general_trades = await optimizer_logic.find_general_market_trades(http_session, CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, departure_data.get('offers') if departure_data else [], local_data, CURRENT_CARGO_CAPACITY_ANALYSIS, max_station_dist_ls_param, include_planetary_param, include_fleet_carriers_param, CURRENT_PAD_SIZE_ANALYSIS, max_db_age_days_param, include_fleet_carriers_param, cancel_event=cancel_event)
                max_general_routes_to_show = int(settings_manager.get_setting(KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES))
                trade_routes_output_segments.extend([("=" * 60 + "\n", None), (lang_module.get_string("general_market_trade_routes_header", count=max_general_routes_to_show) + "\n", TAG_HEADER), ("=" * 60 + "\n\n", None)])
                if general_trades:
                    logger.debug(f"async_analysis_task: general_trades has {len(general_trades)} items to process for display.")
                    for i, route_info in enumerate(general_trades): # Limiter à max_general_routes_to_show
                        if i >= max_general_routes_to_show: break
                        if cancel_event.is_set(): raise OperationCancelledError("Analysis cancelled while formatting general trades.")
                        # ... (logique d'affichage des routes générales, identique à la version précédente)
                        route_type_display = route_info.get('route_type_display', 'Trade Route'); main_route_title_parts = [lang_module.get_string("general_route_display", index=i+1, route_type=route_type_display)]
                        if route_info.get('is_A_to_X', False):
                            dest_ly_dist_str = f"{route_info.get('dest_ly_dist', '?'):.1f} LY" if route_info.get('dest_ly_dist') is not None and route_info.get('dest_ly_dist') != float('inf') else ""
                            dest_ls_dist_str = f"{route_info.get('dest_ls_dist', '?'):.0f} LS" if route_info.get('dest_ls_dist') is not None and route_info.get('dest_ls_dist') != float('inf') else ""
                            if dest_ly_dist_str or dest_ls_dist_str: main_route_title_parts.append(lang_module.get_string("general_route_dest_details", ly_dist=dest_ly_dist_str, separator=', ' if dest_ly_dist_str and dest_ls_dist_str else '', ls_dist=dest_ls_dist_str))
                        else: # is_X_to_A
                            source_ly_dist_str = f"{route_info.get('source_ly_dist', '?'):.1f} LY" if route_info.get('source_ly_dist') is not None and route_info.get('source_ly_dist') != float('inf') else ""
                            source_ls_dist_str = f"{route_info.get('source_ls_dist', '?'):.0f} LS" if route_info.get('source_ls_dist') is not None and route_info.get('source_ls_dist') != float('inf') else ""
                            if source_ly_dist_str or source_ls_dist_str: main_route_title_parts.append(lang_module.get_string("general_route_source_details", ly_dist=source_ly_dist_str, separator=', ' if source_ly_dist_str and source_ls_dist_str else '', ls_dist=source_ls_dist_str))
                        trade_routes_output_segments.append(("".join(main_route_title_parts) + "\n", TAG_SUBHEADER))
                        if 'preliminary_outbound_leg' in route_info and route_info['preliminary_outbound_leg']: # Cas X -> A, prelim est A -> X
                            prelim_trade = route_info['preliminary_outbound_leg'][0]
                            prelim_dest_ly_str = f"{route_info.get('source_ly_dist', '?'):.1f} LY" if route_info.get('source_ly_dist') is not None else ""; prelim_dest_ls_str = f"{route_info.get('source_ls_dist', '?'):.0f} LS" if route_info.get('source_ls_dist') is not None else ""
                            prelim_dest_details_text = f" ({route_info['source_system']}";
                            if prelim_dest_ly_str: prelim_dest_details_text += f", {prelim_dest_ly_str}"
                            if prelim_dest_ls_str: prelim_dest_details_text += f", {prelim_dest_ls_str}"
                            prelim_dest_details_text += ")"
                            trade_routes_output_segments.extend([(lang_module.get_string("general_suggested_outbound_to", station_name=route_info['source_station'], details=prelim_dest_details_text) + "\n", TAG_SUBHEADER), (f"    - Buy: {prelim_trade['commodity_localised']} (Qty: {prelim_trade['quantity']}) @ ", None), (f"{prelim_trade['buy_price_at_source']:,.0f} CR/u at {CURRENT_STATION_ANALYSIS}", TAG_COST), (f"\n      Sell @ ", None), (f"{prelim_trade['sell_price_at_dest']:,.0f} CR/u at {route_info['source_station']}", TAG_PROFIT), (f". Profit/u: ", None), (f"{prelim_trade['profit_per_unit']:,.0f}", TAG_PROFIT), (f" (Total: ", None), (f"{prelim_trade['total_profit']:,.0f} CR", TAG_PROFIT), (")\n", None), (f"    ----\n", None) ])
                        
                        source_details_text = f"{route_info['source_station']} ({route_info['source_system']}"
                        if not route_info.get('is_A_to_X', False):
                            if route_info.get('source_ly_dist') is not None and route_info.get('source_ly_dist') != float('inf'): source_details_text += f", {route_info['source_ly_dist']:.1f} LY"
                            if route_info.get('source_ls_dist') is not None and route_info.get('source_ls_dist') != float('inf'): source_details_text += f", {route_info['source_ls_dist']:.0f} LS"
                        source_details_text += ")"
                        
                        dest_details_text = f"{route_info['dest_station']} ({route_info['dest_system']}"
                        if route_info.get('is_A_to_X', False):
                             if route_info.get('dest_ly_dist') is not None and route_info.get('dest_ly_dist') != float('inf'): dest_details_text += f", {route_info['dest_ly_dist']:.1f} LY"
                             if route_info.get('dest_ls_dist') is not None and route_info.get('dest_ls_dist') != float('inf'): dest_details_text += f", {route_info['dest_ls_dist']:.0f} LS"
                        dest_details_text += ")"
                        
                        trade_routes_output_segments.extend([(lang_module.get_string("general_main_leg_buy", commodity=route_info['commodity_localised'], quantity=route_info['quantity']) + "\n", None), (lang_module.get_string("general_from_station_details", station_details=source_details_text) + " ", None), (lang_module.get_string("buy_at_price", price=route_info['buy_price_at_source']), TAG_COST), (f"\n  {lang_module.get_string('general_sell_to_station_details', station_details=dest_details_text)} ", None), (lang_module.get_string("sell_at_price", price=route_info['sell_price_at_dest']), TAG_PROFIT), (f"\n  {lang_module.get_string('general_profit_per_unit')} ", None), (f"{route_info['profit_per_unit']:,.0f}", TAG_PROFIT), (f" | {lang_module.get_string('general_total_profit_qty')} ", None), (lang_module.get_string("total_profit_value", profit=route_info['total_profit']), TAG_PROFIT), ("\n\n", None)])
                else:
                    trade_routes_output_segments.append((lang_module.get_string("general_no_routes_found")+"\n", None)); logger.debug("async_analysis_task: No general_trades items were found by optimizer_logic to display.")
        
        progress_callback_gui(lang_module.get_string("status_finalizing_analysis"), 95)
    except OperationCancelledError: 
        logger.info("Analysis task was cancelled by user.")
        raise # Relancer pour que le wrapper de thread le gère
    except Exception as e_async_task: # 'e_async_task' est défini ici
        logger.exception("Critical error during async analysis task execution:")
        mission_supply_output_segments = [(lang_module.get_string("critical_error_analysis_task", error=e_async_task, log_file=LOG_FILE), None)]
        trade_routes_output_segments = [] # Vider les routes commerciales en cas d'erreur majeure
        analysis_error_occurred = True # Marquer qu'une erreur s'est produite
    finally:
        if s_shared_root and s_shared_root.winfo_exists():
            was_cancelled_flag = cancel_event.is_set()
            final_status_msg_text = lang_module.get_string("status_analysis_finished")
            if analysis_error_occurred: final_status_msg_text = lang_module.get_string("status_analysis_error_generic")
            elif was_cancelled_flag:
                final_status_msg_text = lang_module.get_string("status_analysis_cancelled")
                if not mission_supply_output_segments or all(not seg[0].strip() for seg in mission_supply_output_segments): mission_supply_output_segments = [(lang_module.get_string("analysis_cancelled_by_user_message") + "\n", None)]
                if not trade_routes_output_segments or all(not seg[0].strip() for seg in trade_routes_output_segments): trade_routes_output_segments = []

            # S'assurer que les listes sont copiées pour éviter les problèmes de modification pendant l'itération par `after`
            final_mission_segs = list(mission_supply_output_segments)
            final_trade_segs = list(trade_routes_output_segments)

            s_shared_root.after(0, _update_text_outputs_from_thread_final_inner, final_mission_segs, final_trade_segs, final_status_msg_text, analysis_error_occurred, was_cancelled_flag)

def _update_text_outputs_from_thread_final_inner(mission_segs, trade_segs, final_status_ui_param, an_error_occurred_param, was_cancelled_param):
    """Fonction interne appelée par .after() pour mettre à jour l'UI finale."""
    global commod_sugg_btn, text_out_mission_supply, text_out_round_trip, status_lbl, s_update_status_func # Accès aux widgets et fonctions
    
    current_status_to_show_final = final_status_ui_param
    is_mission_segs_effectively_empty = not mission_segs or all(not seg[0].strip() for seg in mission_segs)
    is_trade_segs_effectively_empty = not trade_segs or all(not seg[0].strip() for seg in trade_segs)
    
    if not an_error_occurred_param and not was_cancelled_param:
        if is_mission_segs_effectively_empty and is_trade_segs_effectively_empty:
            current_status_to_show_final = lang_module.get_string("analysis_complete_no_suggestions")
            if is_mission_segs_effectively_empty: mission_segs = [(lang_module.get_string("no_mission_data_display") + "\n", None)]
            if is_trade_segs_effectively_empty: trade_segs = [(lang_module.get_string("no_trade_data_display") + "\n", None)]
        elif is_mission_segs_effectively_empty and not is_trade_segs_effectively_empty : 
            mission_segs = [(lang_module.get_string("no_active_missions_found") + "\n", None)]
            
    if text_out_mission_supply and text_out_mission_supply.winfo_exists():
        text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END)
        if mission_segs:
            for text_segment, tag_name in mission_segs: text_out_mission_supply.insert(tk.END, text_segment, tag_name or ())
        text_out_mission_supply.yview_moveto(0.0); text_out_mission_supply.config(state=tk.DISABLED)
    
    if text_out_round_trip and text_out_round_trip.winfo_exists():
        text_out_round_trip.config(state=tk.NORMAL); text_out_round_trip.delete('1.0', tk.END)
        if trade_segs:
            for text_segment, tag_name in trade_segs: text_out_round_trip.insert(tk.END, text_segment, tag_name or ())
        text_out_round_trip.yview_moveto(0.0); text_out_round_trip.config(state=tk.DISABLED)
    
    progress_val_final = 100 if not (an_error_occurred_param or was_cancelled_param) else -1
    if s_update_status_func: s_update_status_func(current_status_to_show_final, progress_val_final, target_status_label_widget=status_lbl)
    
    if commod_sugg_btn and commod_sugg_btn.winfo_exists():
        if top_sourcing_stations_for_suggestions and not (an_error_occurred_param or was_cancelled_param): commod_sugg_btn.config(state=tk.NORMAL)
        else: commod_sugg_btn.config(state=tk.DISABLED)


def on_launch_analysis_pressed():
    global status_lbl, text_out_mission_supply, text_out_round_trip, s_shared_root
    global CURRENT_SYSTEM_ANALYSIS, EFFECTIVE_JOURNAL_DIR_ANALYSIS

    if CURRENT_SYSTEM_ANALYSIS == "?" or "Error" in CURRENT_SYSTEM_ANALYSIS or "No Journal" in CURRENT_SYSTEM_ANALYSIS or "No Events" in CURRENT_SYSTEM_ANALYSIS:
        msg = lang_module.get_string("error_launch_analysis_no_system"); logger.warning(msg)
        if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl);
        if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END); text_out_mission_supply.insert(tk.END, msg + "\n");text_out_mission_supply.config(state=tk.DISABLED)
        if text_out_round_trip: text_out_round_trip.config(state=tk.NORMAL); text_out_round_trip.delete('1.0', tk.END);text_out_round_trip.config(state=tk.DISABLED)
        return
    
    effective_journal_path_to_use = EFFECTIVE_JOURNAL_DIR_ANALYSIS
    if effective_journal_path_to_use in ["Not Found", "Auto-detecting...", None] or (effective_journal_path_to_use != "Auto-detecting..." and not os.path.isdir(effective_journal_path_to_use)) :
        msg = lang_module.get_string("error_launch_analysis_no_journal"); logger.warning(msg)
        if s_update_status_func: s_update_status_func(msg, None, target_status_label_widget=status_lbl);
        if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END); text_out_mission_supply.insert(tk.END, msg + "\n");text_out_mission_supply.config(state=tk.DISABLED)
        if text_out_round_trip: text_out_round_trip.config(state=tk.NORMAL); text_out_round_trip.delete('1.0', tk.END);text_out_round_trip.config(state=tk.DISABLED)
        return

    s_cancel_main_event.clear()
    set_analysis_buttons_state(operation_running=True, cancellable=True, source_tab="main")
    if text_out_mission_supply: text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.delete('1.0', tk.END); text_out_mission_supply.insert(tk.END, lang_module.get_string("status_starting_analysis") + "\n");text_out_mission_supply.config(state=tk.DISABLED)
    if text_out_round_trip: text_out_round_trip.config(state=tk.NORMAL); text_out_round_trip.delete('1.0', tk.END);text_out_round_trip.config(state=tk.DISABLED)
    if s_update_status_func: s_update_status_func(lang_module.get_string("status_validating_settings_analysis"), 0, indeterminate=False, target_status_label_widget=status_lbl)
    try:
        val_radius = float(s_radius_var.get()); val_age = int(s_age_var.get()); val_dist_ls = float(s_station_dist_var.get())
        if val_radius <= 0: raise ValueError(lang_module.get_string("settings_validation_error", error="Radius must be positive."))
        if val_age < 0: raise ValueError(lang_module.get_string("settings_validation_error", error="DB Age must be non-negative."))
        if val_dist_ls < 0: raise ValueError(lang_module.get_string("settings_validation_error", error="Station distance must be non-negative."))

        def _analysis_progress_callback(message, percentage):
            if not s_cancel_main_event.is_set() and s_update_status_func:
                is_indeterminate = percentage is None and not any(err_token in message.lower() for err_token in [lang_module.get_string("cancel_button").lower(), lang_module.get_string("error_dialog_title").lower(), "erreur"])
                s_update_status_func(message, percentage, indeterminate=is_indeterminate, target_status_label_widget=status_lbl)

        def _run_async_analysis_in_thread():
            current_radius_ly = float(s_radius_var.get()); current_max_db_age_days = int(s_age_var.get()); current_max_station_dist_ls = float(s_station_dist_var.get())
            current_sort_by = s_sort_var.get(); current_include_planetary = s_include_planetary_var.get(); current_include_fleet_carriers = s_include_fleet_carriers_var.get()
            loop = None
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                async def main_coro():
                    async_headers = getattr(api_handler, 'HEADERS', None) # Obtenir HEADERS de manière sûre
                    async with aiohttp.ClientSession(headers=async_headers) as http_session:
                         await async_analysis_task_local(http_session, current_radius_ly, current_max_db_age_days, current_max_station_dist_ls, current_sort_by, current_include_planetary, current_include_fleet_carriers, s_cancel_main_event, _analysis_progress_callback)
                loop.run_until_complete(main_coro())
            except OperationCancelledError: logger.info("Analysis (thread wrapper) was cancelled.")
            except Exception as e_thread_async: # 'e_thread_async' est défini ici
                logger.exception("Critical error in async analysis execution (thread):"); error_message_for_ui = lang_module.get_string("async_analysis_error", error=e_thread_async)
                if not s_cancel_main_event.is_set() and s_shared_root:
                     s_shared_root.after(0, _handle_thread_exception_ui_local, error_message_for_ui, False, status_lbl, e_val=e_thread_async) # Passer e_val
            finally:
                if loop and not loop.is_closed(): loop.close()
                if s_shared_root and s_shared_root.winfo_exists(): s_shared_root.after(0, lambda: set_analysis_buttons_state(False, False, "main"))
                logger.info("Async analysis thread (outer function) completed.")
        threading.Thread(target=_run_async_analysis_in_thread, daemon=True).start()
    except ValueError as ve_settings: # 've_settings' est défini ici
        msg_settings_err = lang_module.get_string("settings_error_analysis", error=ve_settings)
        _handle_thread_exception_ui_local(msg_settings_err, True, status_lbl, e_val=ve_settings) # Passer e_val
    except Exception as e_launch: # 'e_launch' est défini ici
        logger.exception("Error preparing to launch analysis thread:")
        msg_launch_err = lang_module.get_string("launch_error_analysis", error=e_launch)
        _handle_thread_exception_ui_local(msg_launch_err, True, status_lbl, e_val=e_launch) # Passer e_val


def _handle_thread_exception_ui_local(error_message, is_setting_error=False, target_status_label_widget=None, e_val=None): # Ajout de e_val
    global s_shared_root, text_out_mission_supply, status_lbl
    active_status_label = target_status_label_widget if target_status_label_widget else status_lbl

    # Formater le message d'erreur avec la valeur de l'exception si disponible
    # Cela suppose que vos chaînes de langue pour les erreurs peuvent accepter un {error}
    full_error_message = str(error_message)
    if "{error}" in full_error_message and e_val is not None: # Si la chaîne attend un formatage et e_val est fourni
        try:
            full_error_message = full_error_message.format(error=e_val)
        except KeyError: # Au cas où la chaîne ne s'attendrait pas à {error} mais e_val est là
            logger.warning(f"Error formatting error message '{full_error_message}' with e_val={e_val}. Using raw message.")
            full_error_message = str(error_message) # Revenir au message brut non formaté

    if s_shared_root and s_shared_root.winfo_exists():
        current_status_text = ""
        if active_status_label and active_status_label.winfo_exists():
            current_status_text = active_status_label.cget("text").lower()
        if not (lang_module.get_string("cancel_button").lower() in current_status_text): # Ne pas écraser si annulé
            if s_update_status_func: s_update_status_func(full_error_message.split('\n')[0], -1, target_status_label_widget=active_status_label)
        
        if text_out_mission_supply and active_status_label == status_lbl and text_out_mission_supply.winfo_exists(): # Si c'est le status_lbl principal de l'onglet
            text_out_mission_supply.config(state=tk.NORMAL); text_out_mission_supply.insert(tk.END, full_error_message + "\n"); text_out_mission_supply.config(state=tk.DISABLED)
        
        if is_setting_error: # Si c'était une erreur de settings avant de lancer le thread
            set_analysis_buttons_state(False, False, "main")


def on_commodities_suggestions_pressed():
    global commod_sugg_window, top_sourcing_stations_for_suggestions, s_shared_root, s_sort_treeview_column_general_func
    # ... (logique de la fonction, s'assurer d'utiliser s_shared_root pour parent, et s_sort_treeview_column_general_func)
    if not top_sourcing_stations_for_suggestions:
        messagebox.showinfo(lang_module.get_string("commod_sugg_window_title"), lang_module.get_string("commod_sugg_no_sourcing_stations_info"), parent=s_shared_root); return
    if commod_sugg_window and commod_sugg_window.winfo_exists(): commod_sugg_window.focus(); return

    commod_sugg_window = tk.Toplevel(s_shared_root)
    commod_sugg_window.title(lang_module.get_string("commod_sugg_window_title"))
    commod_sugg_window.configure(bg=ED_DARK_GREY)
    win_width = 750; win_height = 450
    root_x = s_shared_root.winfo_x(); root_y = s_shared_root.winfo_y()
    root_width = s_shared_root.winfo_width(); root_height = s_shared_root.winfo_height()
    pos_x = root_x + (root_width // 2) - (win_width // 2)
    pos_y = root_y + (root_height // 2) - (win_height // 2)
    commod_sugg_window.geometry(f'{win_width}x{win_height}+{pos_x}+{pos_y}')
    commod_sugg_window.transient(s_shared_root) # Pour que la fenêtre reste au-dessus de la principale
    def _on_sugg_close(): # Fonction de fermeture locale
        global commod_sugg_window
        if commod_sugg_window: commod_sugg_window.destroy(); commod_sugg_window = None
    commod_sugg_window.protocol("WM_DELETE_WINDOW", _on_sugg_close)

    notebook_sugg = ttk.Notebook(commod_sugg_window); notebook_sugg.pack(expand=True, fill='both', padx=10, pady=5)
    sugg_status_label_widget = ttk.Label(commod_sugg_window, text=lang_module.get_string("commod_sugg_status_loading"), style="Status.TLabel"); sugg_status_label_widget.pack(fill=tk.X, padx=10, pady=(0,5))
    local_data_cache = None
    if os.path.exists(LOCAL_SELLERS_DATA_FILE):
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f: local_data_cache = json.load(f)
        except Exception as e: # 'e' est défini ici
            logger.error(f"Could not load {LOCAL_SELLERS_DATA_FILE} for suggestions: {e}"); sugg_status_label_widget.config(text=lang_module.get_string("commod_sugg_error_loading_local", error=e))
            if commod_sugg_window and commod_sugg_window.winfo_exists(): _on_sugg_close()
            messagebox.showerror(lang_module.get_string("commod_sugg_error_dialog_title"), lang_module.get_string("commod_sugg_error_loading_local", error=e), parent=s_shared_root); return
    else:
        sugg_status_label_widget.config(text=lang_module.get_string("commod_sugg_local_data_not_found", file_name=LOCAL_SELLERS_DATA_FILE))
        messagebox.showerror(lang_module.get_string("commod_sugg_data_missing_dialog_title"), lang_module.get_string("commod_sugg_local_data_not_found", file_name=LOCAL_SELLERS_DATA_FILE), parent=s_shared_root)
        if commod_sugg_window and commod_sugg_window.winfo_exists(): _on_sugg_close()
        return

    cols_sugg_keys = ["tree_col_commodity_name", "tree_col_price_player_buys", "tree_col_stock"]
    for station_info_from_top in top_sourcing_stations_for_suggestions:
        sys_name = station_info_from_top['system_name']; sta_name = station_info_from_top['station_name']
        tab_title = f"{sta_name} ({sys_name})"
        if station_info_from_top.get('distance_ly') is not None: tab_title += f" - {station_info_from_top['distance_ly']:.1f} LY"
        tab_frame = ttk.Frame(notebook_sugg, padding="5"); notebook_sugg.add(tab_frame, text=tab_title)

        tree = ttk.Treeview(tab_frame, columns=cols_sugg_keys, show='headings', style="Treeview")
        # S'assurer que s_sort_treeview_column_general_func est appelé correctement
        if s_sort_treeview_column_general_func:
            tree.heading(cols_sugg_keys[0], text=lang_module.get_string(cols_sugg_keys[0]), anchor=tk.W, command=lambda tv=tree, ck=cols_sugg_keys[0], dt="str_ci": s_sort_treeview_column_general_func(tv, ck, dt))
            tree.heading(cols_sugg_keys[1], text=lang_module.get_string(cols_sugg_keys[1]), anchor=tk.E, command=lambda tv=tree, ck=cols_sugg_keys[1], dt="int": s_sort_treeview_column_general_func(tv, ck, dt))
            tree.heading(cols_sugg_keys[2], text=lang_module.get_string(cols_sugg_keys[2]), anchor=tk.E, command=lambda tv=tree, ck=cols_sugg_keys[2], dt="int": s_sort_treeview_column_general_func(tv, ck, dt))
        else: # Fallback si la fonction de tri n'est pas passée
            tree.heading(cols_sugg_keys[0], text=lang_module.get_string(cols_sugg_keys[0]), anchor=tk.W)
            tree.heading(cols_sugg_keys[1], text=lang_module.get_string(cols_sugg_keys[1]), anchor=tk.E)
            tree.heading(cols_sugg_keys[2], text=lang_module.get_string(cols_sugg_keys[2]), anchor=tk.E)

        tree.column(cols_sugg_keys[0], width=300, minwidth=150, anchor=tk.W, stretch=tk.YES)
        tree.column(cols_sugg_keys[1], width=180, minwidth=100, anchor=tk.E, stretch=tk.NO)
        tree.column(cols_sugg_keys[2], width=120, minwidth=80, anchor=tk.E, stretch=tk.NO)
        tree.pack(expand=True, fill='both', side=tk.TOP)
        per_tab_status = ttk.Label(tab_frame, text=lang_module.get_string("commod_sugg_status_loading"), style="Status.TLabel"); per_tab_status.pack(fill=tk.X, side=tk.BOTTOM)
        
        exports_for_station = []
        if local_data_cache and 'station_markets' in local_data_cache and sys_name in local_data_cache['station_markets'] and 'stations_data' in local_data_cache['station_markets'][sys_name] and sta_name in local_data_cache['station_markets'][sys_name]['stations_data']:
            station_market_detail = local_data_cache['station_markets'][sys_name]['stations_data'][sta_name]
            exports_for_station = station_market_detail.get('sells_to_player', [])
        
        if exports_for_station:
            sorted_exports = sorted(exports_for_station, key=lambda x: x.get('commodity_localised', x.get('commodityName','')).lower())
            for item in sorted_exports:
                name = item.get('commodity_localised', item.get('commodityName', 'N/A')); price = f"{item.get('price', 0):,}"; stock = f"{item.get('stock', item.get('quantity_at_station', 0)):,}"
                tree.insert("", tk.END, values=(name, price, stock))
            per_tab_status.config(text=lang_module.get_string("commod_sugg_items_found", count=len(exports_for_station)))
        else:
            per_tab_status.config(text=lang_module.get_string("commod_sugg_no_export_data"))
            logger.warning(f"No 'sells_to_player' data for {sta_name} in {sys_name} within {LOCAL_SELLERS_DATA_FILE}")
    sugg_status_label_widget.config(text=lang_module.get_string("commod_sugg_loaded"))


def set_analysis_buttons_state(operation_running=False, cancellable=False, source_tab="main"): # source_tab="main" par défaut
    global launch_btn, update_btn, refresh_loc_btn, open_settings_btn, commod_sugg_btn, save_pad_size_btn, unknown_pad_entry, unknown_pad_frame

    action_buttons_state = tk.DISABLED if operation_running else tk.NORMAL

    if launch_btn and launch_btn.winfo_exists(): launch_btn.config(state=action_buttons_state)
    if update_btn and update_btn.winfo_exists(): update_btn.config(state=action_buttons_state)
    if refresh_loc_btn and refresh_loc_btn.winfo_exists(): refresh_loc_btn.config(state=action_buttons_state)
    if open_settings_btn and open_settings_btn.winfo_exists(): open_settings_btn.config(state=action_buttons_state)

    if commod_sugg_btn and commod_sugg_btn.winfo_exists():
        if operation_running: commod_sugg_btn.config(state=tk.DISABLED)
        elif top_sourcing_stations_for_suggestions: commod_sugg_btn.config(state=tk.NORMAL)
        else: commod_sugg_btn.config(state=tk.DISABLED)

    if unknown_pad_frame and unknown_pad_frame.winfo_exists() and unknown_pad_frame.winfo_ismapped():
        state_pad_input = tk.NORMAL if not operation_running else tk.DISABLED
        if unknown_pad_entry and unknown_pad_entry.winfo_exists(): unknown_pad_entry.config(state=state_pad_input)
        if save_pad_size_btn and save_pad_size_btn.winfo_exists(): save_pad_size_btn.config(state=state_pad_input)


def update_analysis_tab_texts():
    global analysis_tab_frame, global_label, ship_label, cargo_label, db_status_label, shipyard_db_status_lbl
    global journal_dir_display_label, open_settings_btn, refresh_loc_btn, update_btn, launch_btn, commod_sugg_btn
    global sort_by_label_widget, sort_by_dist_ly_radio_btn, sort_by_profit_radio_btn, sort_by_dist_ls_radio_btn
    global to_collect_label_widget, unknown_pad_ship_label, save_pad_size_btn, status_lbl
    global CURRENT_SYSTEM_ANALYSIS, CURRENT_STATION_ANALYSIS, CURRENT_SHIP_TYPE_ANALYSIS
    global CURRENT_CARGO_CAPACITY_ANALYSIS, CURRENT_PAD_SIZE_ANALYSIS # Variables de module de cet onglet

    # Labels d'info principaux
    if global_label and global_label.winfo_exists():
        loc_text = f"{lang_module.get_string('location_label_prefix')} {CURRENT_SYSTEM_ANALYSIS} / {CURRENT_STATION_ANALYSIS if CURRENT_STATION_ANALYSIS and CURRENT_STATION_ANALYSIS != '?' else 'N/A'}"
        global_label.config(text=loc_text)
    if ship_label and ship_label.winfo_exists(): ship_label.config(text=f"{lang_module.get_string('ship_label_prefix')} {CURRENT_SHIP_TYPE_ANALYSIS} (Pad {CURRENT_PAD_SIZE_ANALYSIS})")
    if cargo_label and cargo_label.winfo_exists(): cargo_label.config(text=f"{lang_module.get_string('cargo_label_prefix')} {CURRENT_CARGO_CAPACITY_ANALYSIS} t")
    if db_status_label and db_status_label.winfo_exists(): db_status_label.config(text=optimizer_logic.get_last_db_update_time_str())
    if shipyard_db_status_lbl and shipyard_db_status_lbl.winfo_exists(): shipyard_db_status_lbl.config(text=shipyard_db_manager.get_shipyard_db_update_time_str())

    # Boutons
    if open_settings_btn and open_settings_btn.winfo_exists(): open_settings_btn.config(text=lang_module.get_string("settings_button"))
    if refresh_loc_btn and refresh_loc_btn.winfo_exists(): refresh_loc_btn.config(text=lang_module.get_string("refresh_button"))
    if update_btn and update_btn.winfo_exists(): update_btn.config(text=lang_module.get_string("update_db_button"))
    if launch_btn and launch_btn.winfo_exists(): launch_btn.config(text=lang_module.get_string("launch_analysis_button"))
    if commod_sugg_btn and commod_sugg_btn.winfo_exists(): commod_sugg_btn.config(text=lang_module.get_string("commod_suggestions_button"))

    # Options de tri
    if sort_by_label_widget and sort_by_label_widget.winfo_exists(): sort_by_label_widget.config(text=lang_module.get_string("status_label_sort_full_by"))
    if sort_by_dist_ly_radio_btn and sort_by_dist_ly_radio_btn.winfo_exists(): sort_by_dist_ly_radio_btn.config(text=lang_module.get_string("sort_by_dist_ly"))
    if sort_by_profit_radio_btn and sort_by_profit_radio_btn.winfo_exists(): sort_by_profit_radio_btn.config(text=lang_module.get_string("sort_by_profit"))
    if sort_by_dist_ls_radio_btn and sort_by_dist_ls_radio_btn.winfo_exists(): sort_by_dist_ls_radio_btn.config(text=lang_module.get_string("sort_by_dist_ls"))

    # Section "À Collecter"
    if to_collect_label_widget and to_collect_label_widget.winfo_exists(): to_collect_label_widget.config(text=lang_module.get_string("to_collect_label"))
    
    # Cadre Pad Inconnu
    if unknown_pad_ship_label and unknown_pad_ship_label.winfo_exists(): unknown_pad_ship_label.config(text=lang_module.get_string("pad_for_ship_label", ship_type=CURRENT_SHIP_TYPE_ANALYSIS))
    if save_pad_size_btn and save_pad_size_btn.winfo_exists(): save_pad_size_btn.config(text=lang_module.get_string("save_pad_button"))

    if status_lbl and status_lbl.winfo_exists():
        current_text = status_lbl.cget("text")
        is_default_status = any(msg_key for msg_key in ["status_ready", "location_ship_refreshed"] if current_text == lang_module.get_string(msg_key))
        if is_default_status: status_lbl.config(text=lang_module.get_string("status_ready"))
    logger.info("Analysis tab texts updated based on current language.")


def create_analysis_tab(notebook_parent, shared_elements_dict):
    # ... (Définition des widgets globaux au module comme avant)
    global analysis_tab_frame, status_lbl, db_status_label, shipyard_db_status_lbl, global_label, ship_label, cargo_label
    global journal_dir_display_label, open_settings_btn, refresh_loc_btn, update_btn, launch_btn, commod_sugg_btn
    global sort_by_label_widget, sort_by_dist_ly_radio_btn, sort_by_profit_radio_btn, sort_by_dist_ls_radio_btn
    global to_collect_label_widget, commod_list, total_lbl
    global unknown_pad_frame, unknown_pad_ship_label, unknown_pad_entry, save_pad_size_btn
    global text_out_mission_supply, text_out_round_trip

    global s_shared_root, s_radius_var, s_age_var, s_station_dist_var, s_include_planetary_var, s_include_fleet_carriers_var
    global s_sort_var, s_journal_dir_label_var, s_language_var
    global s_update_status_func, s_set_buttons_state_func, s_open_settings_window_func
    global s_cancel_main_event, s_sort_treeview_column_general_func, s_settings_window_ref
    global s_update_journal_dir_display_label_func # Ajouté pour stocker la fonction

    # Stocker les références partagées
    s_shared_root = shared_elements_dict["root"]
    s_radius_var = shared_elements_dict["radius_var"]
    s_age_var = shared_elements_dict["age_var"]
    s_station_dist_var = shared_elements_dict["station_dist_var"]
    s_include_planetary_var = shared_elements_dict["include_planetary_var"]
    s_include_fleet_carriers_var = shared_elements_dict["include_fleet_carriers_var"]
    s_sort_var = shared_elements_dict["sort_var"]
    s_journal_dir_label_var = shared_elements_dict["journal_dir_label_var"] # C'est le StringVar
    s_language_var = shared_elements_dict["language_var"]
    s_update_status_func = shared_elements_dict["update_status_func"]
    s_set_buttons_state_func = shared_elements_dict["set_buttons_state_func"]
    s_open_settings_window_func = shared_elements_dict["open_settings_window_func"]
    s_cancel_main_event = shared_elements_dict["cancel_main_event"]
    s_sort_treeview_column_general_func = shared_elements_dict["sort_treeview_column_func"]
    s_update_journal_dir_display_label_func = shared_elements_dict.get("update_journal_dir_display_label_func") # Récupérer la fonction

    # Référence à la fenêtre des paramètres (si passée, pour le parentage des dialogues)
    # s_settings_window_ref = shared_elements_dict.get("settings_window_instance_ref") # Exemple

    analysis_tab_frame = ttk.Frame(notebook_parent, padding="5")
    notebook_parent.add(analysis_tab_frame, text=lang_module.get_string("analysis_tab_title"))
    analysis_tab_frame.columnconfigure(0, weight=1)

    # ---- Top Info Frame ----
    top_info_frame = ttk.Frame(analysis_tab_frame)
    top_info_frame.grid(column=0, row=0, columnspan=4, sticky="ew", pady=(0,5))
    top_info_frame.columnconfigure(0, weight=1) # Location
    top_info_frame.columnconfigure(1, weight=1) # Ship
    top_info_frame.columnconfigure(2, weight=1) # Cargo
    top_info_frame.columnconfigure(3, weight=0) # Container pour DB statuses

    global_label = ttk.Label(top_info_frame, text=f"{lang_module.get_string('location_label_prefix')} ...", style='Header.TLabel')
    global_label.grid(column=0, row=0, sticky=tk.W, padx=5)
    ship_label = ttk.Label(top_info_frame, text=f"{lang_module.get_string('ship_label_prefix')} ...", style='Header.TLabel')
    ship_label.grid(column=1, row=0, sticky=tk.W, padx=5)
    cargo_label = ttk.Label(top_info_frame, text=f"{lang_module.get_string('cargo_label_prefix')} ...", style='Header.TLabel')
    cargo_label.grid(column=2, row=0, sticky=tk.W, padx=5)

    db_status_labels_container = ttk.Frame(top_info_frame)
    db_status_labels_container.grid(column=3, row=0, sticky=tk.E, padx=5) # Aligner à droite
    
    db_status_label = ttk.Label(db_status_labels_container, text=optimizer_logic.get_last_db_update_time_str(), style='Status.TLabel', anchor=tk.E)
    db_status_label.pack(side=tk.RIGHT, padx=(5,0)) # Marché à droite
    if shared_elements_dict.get("register_analysis_db_status_label_widget"):
        shared_elements_dict["register_analysis_db_status_label_widget"](db_status_label)

    shipyard_db_status_lbl = ttk.Label(db_status_labels_container, text=shipyard_db_manager.get_shipyard_db_update_time_str(), style='Status.TLabel', anchor=tk.E)
    shipyard_db_status_lbl.pack(side=tk.RIGHT, padx=(0,5)) # Chantier à gauche de Marché
    if shared_elements_dict.get("register_shipyard_db_status_label_widget"):
        shared_elements_dict["register_shipyard_db_status_label_widget"](shipyard_db_status_lbl)

    # ---- Journal Settings Frame ----
    journal_settings_frame = ttk.Frame(analysis_tab_frame)
    journal_settings_frame.grid(column=0, row=1, columnspan=4, sticky="ew", pady=(0,10))
    journal_settings_frame.columnconfigure(0, weight=1)
    journal_dir_display_label = ttk.Label(journal_settings_frame, textvariable=s_journal_dir_label_var, style='Path.TLabel', anchor=tk.W)
    journal_dir_display_label.grid(column=0, row=0, sticky=tk.EW, padx=(5,0))
    open_settings_btn = ttk.Button(journal_settings_frame, text=lang_module.get_string("settings_button"), command=s_open_settings_window_func, width=15)
    open_settings_btn.grid(column=1, row=0, sticky=tk.E, padx=5)

    # ---- Pre-Analysis Controls ----
    pre_analysis_controls_frame = ttk.Frame(analysis_tab_frame, padding=(0,0))
    pre_analysis_controls_frame.grid(column=0, row=2, columnspan=4, sticky="ew", pady=(0,5))
    pre_analysis_controls_frame.columnconfigure(0, weight=0)
    pre_analysis_controls_frame.columnconfigure(1, weight=0)
    pre_analysis_controls_frame.columnconfigure(2, weight=1)

    update_btn = ttk.Button(pre_analysis_controls_frame, text=lang_module.get_string("update_db_button"), command=on_update_db_pressed, width=12)
    update_btn.grid(column=0, row=0, sticky=tk.W, padx=5, pady=2)

    sort_options_frame = ttk.Frame(pre_analysis_controls_frame)
    sort_options_frame.grid(column=1, row=0, sticky="w", padx=(10,0), pady=2)
    sort_by_label_widget = ttk.Label(sort_options_frame, text=lang_module.get_string("status_label_sort_full_by"))
    sort_by_label_widget.pack(side=tk.LEFT, anchor=tk.W, padx=(0,3))
    sort_by_dist_ly_radio_btn = ttk.Radiobutton(sort_options_frame, text=lang_module.get_string("sort_by_dist_ly"), variable=s_sort_var, value='d')
    sort_by_dist_ly_radio_btn.pack(side=tk.LEFT, anchor=tk.W, padx=2)
    sort_by_profit_radio_btn = ttk.Radiobutton(sort_options_frame, text=lang_module.get_string("sort_by_profit"), variable=s_sort_var, value='b')
    sort_by_profit_radio_btn.pack(side=tk.LEFT, anchor=tk.W, padx=2)
    sort_by_dist_ls_radio_btn = ttk.Radiobutton(sort_options_frame, text=lang_module.get_string("sort_by_dist_ls"), variable=s_sort_var, value='s')
    sort_by_dist_ls_radio_btn.pack(side=tk.LEFT, anchor=tk.W, padx=2)

    commod_display_frame = ttk.Frame(pre_analysis_controls_frame)
    commod_display_frame.grid(column=2, row=0, sticky="ew", padx=(10,5), pady=2)
    commod_display_frame.columnconfigure(1, weight=1)
    to_collect_label_widget = ttk.Label(commod_display_frame, text=lang_module.get_string("to_collect_label"))
    to_collect_label_widget.grid(row=0, column=0, sticky="w", padx=(0,5))
    commod_list = tk.Listbox(commod_display_frame, height=1, bg=ED_MEDIUM_GREY, fg=ED_WHITE_TEXT, highlightbackground=ED_DARK_GREY, relief='flat', borderwidth=1, exportselection=False, font=('Segoe UI', 9))
    commod_list.grid(row=0, column=1, sticky="ew")
    total_lbl = ttk.Label(commod_display_frame, text=lang_module.get_string("total_zero_label"))
    total_lbl.grid(row=0, column=2, sticky="w", padx=(5,0))
    update_commodities_display_in_gui({})

    # ---- Main Action Frame ----
    main_action_frame = ttk.Frame(analysis_tab_frame)
    main_action_frame.grid(column=0, row=3, columnspan=4, sticky="ew", pady=(5,5))
    main_action_frame.columnconfigure(0, weight=1) 
    main_action_frame.columnconfigure(1, weight=0) 
    main_action_frame.columnconfigure(2, weight=0) 
    main_action_frame.columnconfigure(3, weight=0) 
    main_action_frame.columnconfigure(4, weight=1)

    refresh_loc_btn = ttk.Button(main_action_frame, text=lang_module.get_string("refresh_button"), width=20, command=refresh_location_and_ship_display)
    refresh_loc_btn.grid(row=0, column=1, padx=(0,5), pady=2)
    commod_sugg_btn = ttk.Button(main_action_frame, text=lang_module.get_string("commod_suggestions_button"), width=25, command=on_commodities_suggestions_pressed, state=tk.DISABLED)
    commod_sugg_btn.grid(row=0, column=2, padx=5, pady=2)
    launch_btn = ttk.Button(main_action_frame, text=lang_module.get_string("launch_analysis_button"), width=20, command=on_launch_analysis_pressed)
    launch_btn.grid(row=0, column=3, padx=(5,0), pady=2, ipady=2)

    # ---- Status Label ----
    status_lbl = ttk.Label(analysis_tab_frame, text=lang_module.get_string("status_ready"), style='Status.TLabel')
    status_lbl.grid(column=0, row=4, columnspan=4, sticky=tk.EW, pady=(5,0), padx=5)

    # ---- Unknown Pad Frame ----
    unknown_pad_frame = ttk.Frame(analysis_tab_frame, padding=5)
    unknown_pad_ship_label = ttk.Label(unknown_pad_frame, text="")
    unknown_pad_ship_label.pack(side=tk.LEFT, padx=(0,5))
    unknown_pad_entry = ttk.Entry(unknown_pad_frame, width=5)
    unknown_pad_entry.pack(side=tk.LEFT, padx=5)
    save_pad_size_btn = ttk.Button(unknown_pad_frame, text=lang_module.get_string("save_pad_button"), command=on_save_pad_size_pressed, width=10)
    save_pad_size_btn.pack(side=tk.LEFT, padx=5)

    # ---- Results Frame ----
    results_frame = ttk.Frame(analysis_tab_frame)
    results_frame.grid(column=0, row=7, columnspan=4, sticky="nsew", pady=(5,0), padx=5)
    analysis_tab_frame.rowconfigure(7, weight=1)
    results_frame.columnconfigure(0, weight=1)
    results_frame.columnconfigure(1, weight=1)
    results_frame.rowconfigure(0, weight=1)

    text_out_mission_supply = ScrolledText(results_frame, width=60, height=20, bg=ED_MEDIUM_GREY, fg=ED_WHITE_TEXT, insertbackground=ED_WHITE_TEXT, relief='flat', borderwidth=1, wrap=tk.WORD, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE), state=tk.DISABLED)
    text_out_mission_supply.grid(column=0, row=0, sticky="nsew", padx=(0,2))
    text_out_round_trip = ScrolledText(results_frame, width=60, height=20, bg=ED_MEDIUM_GREY, fg=ED_WHITE_TEXT, insertbackground=ED_WHITE_TEXT, relief='flat', borderwidth=1, wrap=tk.WORD, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE), state=tk.DISABLED)
    text_out_round_trip.grid(column=1, row=0, sticky="nsew", padx=(2,0))

    for txt_widget in [text_out_mission_supply, text_out_round_trip]:
        if txt_widget: # S'assurer que le widget existe
            txt_widget.tag_configure(TAG_REWARD, foreground=ED_ORANGE, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE, "bold"))
            txt_widget.tag_configure(TAG_COST, foreground=COST_COLOR, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE, "bold"))
            txt_widget.tag_configure(TAG_PROFIT, foreground=PROFIT_COLOR, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE, "bold"))
            txt_widget.tag_configure(TAG_HEADER, foreground=ED_ORANGE, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE + 1, "bold", "underline"))
            txt_widget.tag_configure(TAG_SUBHEADER, foreground=ED_ORANGE, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE, "bold"))
            txt_widget.tag_configure(TAG_TOTAL_PROFIT_LEG, foreground=PROFIT_COLOR, font=(BASE_FONT_FAMILY, BASE_FONT_SIZE, "bold"))

    # Récupérer la référence à la fenêtre des settings pour le parentage du dialogue de on_select_journal_dir_pressed
    # Cela suppose que gui_settings_window.settings_window est la référence à la fenêtre si elle est ouverte.
    # Il est préférable de passer cette référence via shared_elements_dict si possible.
    global gui_settings_window # Importation du module pour accéder à settings_window
    try:
        # Pour éviter d'importer gui_settings_window au niveau du module et risquer une dépendance circulaire
        # On essaie d'y accéder via un moyen détourné si la fenêtre de settings est gérée globalement.
        # La meilleure solution serait que gui_main fournisse une fonction pour obtenir cette référence.
        import gui_settings_window # Fait ici pour que la fonction on_select_journal_dir_pressed puisse y accéder
    except ImportError:
        logger.warning("gui_settings_window module not found for settings_window reference in gui_analysis_tab.")
        # gui_settings_window restera non défini, on_select_journal_dir_pressed utilisera s_shared_root comme parent.


    logger.debug("Analysis tab created.")
    return analysis_tab_frame