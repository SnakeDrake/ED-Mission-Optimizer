#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import asyncio

# --- Imports des modules de l'application ---
from constants import (
    PURCHASABLE_SHIPS_LIST,
    PLANETARY_STATION_TYPES, 
    FLEET_CARRIER_STATION_TYPES
    # STATION_TYPE_TO_PAD_SIZE_LETTER n'est pas directement utilisé ici, mais par shipyard_logic
)
import shipyard_db_manager
import shipyard_logic
import language as lang_module
import gui_main 

logger = logging.getLogger(__name__)

# ---- Widgets spécifiques à l'onglet Chantier Naval ----
shipyard_tab_frame = None
ship_to_find_var = None 
shipyard_find_ship_btn = None
shipyard_update_db_btn = None
shipyard_results_tree = None
shipyard_status_lbl = None 
shipyard_include_planetary_cb = None
shipyard_include_fc_cb = None

# Références aux éléments partagés de gui_main
s_shipyard_radius_var = None
s_radius_var = None 
s_include_planetary_var = None
s_include_fleet_carriers_var = None
s_station_dist_var = None 
s_update_status_func = None
s_set_buttons_state_func = None
s_get_current_system_func = None
s_cancel_shipyard_event = None
s_root = None
s_shipyard_db_status_lbl_widget_ref = None


# --- Fonctions spécifiques à l'onglet Chantier Naval ---

def on_update_shipyard_db_pressed():
    global s_shipyard_radius_var, s_cancel_shipyard_event, s_shipyard_db_status_lbl_widget_ref, s_radius_var
    global s_update_status_func, shipyard_status_lbl

    current_system = s_get_current_system_func()
    if current_system == "?" or "Error" in current_system or "No Journal" in current_system or "No Events" in current_system:
        msg = lang_module.get_string("error_shipyard_db_update_no_system")
        logger.warning(msg)
        if s_update_status_func: s_update_status_func(msg, target_status_label_widget=shipyard_status_lbl)
        return

    s_cancel_shipyard_event.clear()
    if gui_main._set_buttons_state:
        gui_main._set_buttons_state(operation_running=True, cancellable=True)
    set_shipyard_buttons_state(operation_running=True, cancellable=True, source_tab="shipyard")

    if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_db_validating"), 0, target_status_label_widget=shipyard_status_lbl)

    try:
        radius_to_use_str = s_shipyard_radius_var.get() if s_shipyard_radius_var and s_shipyard_radius_var.get() else s_radius_var.get()
        radius_to_use = float(radius_to_use_str)

        if radius_to_use <= 0:
            raise ValueError(lang_module.get_string("error_radius_positive"))
        if radius_to_use > 100: # Limite EDSM
            logger.warning(f"Le rayon de recherche EDSM ({radius_to_use} AL) pour le chantier naval dépasse la limite de 100 AL. Utilisation de 100 AL.")
            radius_to_use = 100.0
            if s_shipyard_radius_var: s_shipyard_radius_var.set(str(radius_to_use))
            elif s_radius_var: s_radius_var.set(str(radius_to_use))


        def _progress_update_callback(message, percentage):
            if not s_cancel_shipyard_event.is_set() and s_update_status_func:
                s_update_status_func(message, percentage, target_status_label_widget=shipyard_status_lbl)

        async def _async_shipyard_db_update_task():
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_db_updating_for_system", system=current_system), 0, target_status_label_widget=shipyard_status_lbl)
            db_data = None
            try:
                db_data = await shipyard_db_manager.download_regional_shipyard_data(
                    center_system_name=current_system,
                    radius_ly=int(radius_to_use), # EDSM attend un entier pour le rayon
                    cancel_event=s_cancel_shipyard_event,
                    progress_callback=_progress_update_callback
                )
                if s_cancel_shipyard_event.is_set():
                    raise shipyard_db_manager.OperationCancelledError(lang_module.get_string("error_shipyard_db_update_cancelled_post_signal"))

                final_status_msg = lang_module.get_string("status_shipyard_db_update_finished")
                success = True
                if not db_data or not db_data.get("systems_with_shipyards"):
                    final_status_msg += f" ({lang_module.get_string('status_shipyard_db_update_no_data_found')})"
                if s_update_status_func: s_update_status_func(final_status_msg, 100 if success else -1, target_status_label_widget=shipyard_status_lbl)
                if s_shipyard_db_status_lbl_widget_ref:
                    s_shipyard_db_status_lbl_widget_ref.config(text=shipyard_db_manager.get_shipyard_db_update_time_str())
            except shipyard_db_manager.OperationCancelledError:
                logger.info("Mise à jour de la BD des chantiers navals annulée.")
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_db_update_cancelled"), -1, target_status_label_widget=shipyard_status_lbl)
            except Exception as e_async:
                logger.exception("Erreur dans _async_shipyard_db_update_task:")
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_db_update_error_generic", error=e_async), -1, target_status_label_widget=shipyard_status_lbl)

        def _run_in_thread():
            loop = None
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(_async_shipyard_db_update_task())
            except Exception as e_thread:
                logger.exception("Erreur non gérée lors de l'exécution de la tâche async de MàJ BD chantier naval:")
                msg_err_thread = lang_module.get_string("status_shipyard_db_update_thread_error", error=e_thread)
                if not s_cancel_shipyard_event.is_set() and s_update_status_func:
                    s_update_status_func(msg_err_thread, -1, target_status_label_widget=shipyard_status_lbl)
            finally:
                if loop and not loop.is_closed(): loop.close()
                if s_root and s_root.winfo_exists():
                     s_root.after(0, gui_main._set_buttons_state, False, False)
                     s_root.after(0, set_shipyard_buttons_state, False, False, "shipyard")
        threading.Thread(target=_run_in_thread, daemon=True).start()
    except ValueError as ve:
        msg_val_err = lang_module.get_string("settings_error_shipyard_db_update", error=ve); logger.error(msg_val_err)
        if s_update_status_func: s_update_status_func(msg_val_err, -1, target_status_label_widget=shipyard_status_lbl)
        set_shipyard_buttons_state(False, False, "shipyard")
        if gui_main._set_buttons_state: gui_main._set_buttons_state(False, False)
    except Exception as e_main:
        logger.exception("Erreur inattendue avant de lancer le thread de MàJ BD chantier naval:")
        if s_update_status_func: s_update_status_func(f"Erreur lancement MàJ: {e_main}", -1, target_status_label_widget=shipyard_status_lbl)
        set_shipyard_buttons_state(False, False, "shipyard")
        if gui_main._set_buttons_state: gui_main._set_buttons_state(False, False)


def on_find_ship_pressed():
    global ship_to_find_var, shipyard_results_tree, shipyard_status_lbl
    global s_radius_var, s_station_dist_var, s_include_planetary_var, s_include_fleet_carriers_var, s_shipyard_radius_var
    global s_update_status_func, s_get_current_system_func, s_root

    selected_ship_display_name = ship_to_find_var.get()
    if not selected_ship_display_name:
        messagebox.showwarning(lang_module.get_string("error_dialog_title_warning"), lang_module.get_string("error_shipyard_no_ship_selected"), parent=s_root)
        return

    if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_loading_data"), indeterminate=True, target_status_label_widget=shipyard_status_lbl)
    if gui_main._set_buttons_state: gui_main._set_buttons_state(operation_running=True, cancellable=False)
    set_shipyard_buttons_state(operation_running=True, cancellable=False, source_tab="shipyard")

    if shipyard_results_tree:
        for item in shipyard_results_tree.get_children():
            shipyard_results_tree.delete(item)

    try:
        shipyard_data = shipyard_db_manager.load_shipyard_data_from_file()
        if not shipyard_data or "systems_with_shipyards" not in shipyard_data:
            if s_update_status_func: s_update_status_func(lang_module.get_string("error_shipyard_db_not_found_or_empty"), -1, target_status_label_widget=shipyard_status_lbl)
            set_shipyard_buttons_state(False, False, "shipyard")
            if gui_main._set_buttons_state: gui_main._set_buttons_state(False, False)
            return

        current_system = s_get_current_system_func()
        current_sys_coords = None
        if current_system and current_system != "?":
            # Essayer de trouver les coordonnées du système actuel dans les données du chantier naval
            # d'abord en tant que clé principale, puis en tant que "sourceSystem"
            if "systems_with_shipyards" in shipyard_data and current_system in shipyard_data["systems_with_shipyards"]:
                current_sys_coords = shipyard_data["systems_with_shipyards"][current_system].get("coords")
            elif shipyard_data.get("sourceSystem") == current_system and \
                 shipyard_data.get("systems_with_shipyards", {}).get(current_system, {}).get("coords"): # Vérifier que le système source a des coordonnées
                 current_sys_coords = shipyard_data["systems_with_shipyards"][current_system]["coords"]
            else:
                 logger.warning(f"Coordonnées du système actuel '{current_system}' non trouvées dans les données de shipyard_data.json. Le tri par distance pourrait ne pas fonctionner comme prévu.")


        max_dist_ly_str = s_shipyard_radius_var.get() if s_shipyard_radius_var and s_shipyard_radius_var.get() else s_radius_var.get()
        max_dist_ly_val = float(max_dist_ly_str) if max_dist_ly_str else None # Peut être None si non défini
        
        max_station_dist_ls_val = None
        if s_station_dist_var and s_station_dist_var.get():
            try:
                max_station_dist_ls_val = float(s_station_dist_var.get())
            except ValueError:
                logger.warning(f"Valeur de distance LS invalide: '{s_station_dist_var.get()}'. Ignorée.")
                max_station_dist_ls_val = None
                
        include_planetary_val = s_include_planetary_var.get()
        include_fc_val = s_include_fleet_carriers_var.get()

        logger.debug(f"Shipyard search filters: Target Ship: '{selected_ship_display_name}', Max LY: {max_dist_ly_val}, Max LS: {max_station_dist_ls_val}, Planetary: {include_planetary_val}, FC: {include_fc_val}, Current Sys Coords: {current_sys_coords}")

        found_stations = shipyard_logic.find_stations_selling_ship(
            ship_name_to_find=selected_ship_display_name,
            all_shipyard_data=shipyard_data,
            current_player_system_coords=current_sys_coords,
            max_distance_ly_filter=max_dist_ly_val,
            max_station_dist_ls=max_station_dist_ls_val,
            include_planetary=include_planetary_val,
            include_fleet_carriers=include_fc_val
        )

        if found_stations:
            for station_info in found_stations:
                dist_ly_str = f"{station_info['distanceLy']:.1f}" if station_info.get('distanceLy') is not None and station_info['distanceLy'] != float('inf') else "?"
                dist_ls_str = f"{station_info['distanceToArrival']:.0f}" if station_info.get('distanceToArrival') is not None else "?"
                pad_size_str = station_info.get("deducedPadSize", "?") # Récupérer la taille de pad déduite

                shipyard_results_tree.insert("", tk.END, values=(
                    station_info.get("stationName", "N/A"),
                    station_info.get("systemName", "N/A"),
                    dist_ly_str,
                    dist_ls_str,
                    station_info.get("stationType", "N/A"),
                    pad_size_str # Ajouter la taille de pad
                ))
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_found_stations", count=len(found_stations)), -1, target_status_label_widget=shipyard_status_lbl)
        else:
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_shipyard_no_stations_found_for_ship", ship=selected_ship_display_name), -1, target_status_label_widget=shipyard_status_lbl)

    except Exception as e:
        logger.exception("Erreur lors de la recherche de vaisseau :")
        if s_update_status_func: s_update_status_func(lang_module.get_string("error_shipyard_find_ship_generic", error=e), -1, target_status_label_widget=shipyard_status_lbl)
    finally:
        set_shipyard_buttons_state(False, False, "shipyard")
        if gui_main._set_buttons_state: gui_main._set_buttons_state(False, False)


def set_shipyard_buttons_state(operation_running=False, cancellable=False, source_tab="shipyard"):
    global shipyard_find_ship_btn, shipyard_update_db_btn
    action_buttons_state = tk.DISABLED if operation_running else tk.NORMAL
    if shipyard_find_ship_btn: shipyard_find_ship_btn.config(state=action_buttons_state)
    if shipyard_update_db_btn: shipyard_update_db_btn.config(state=action_buttons_state)


def update_shipyard_tab_texts():
    global shipyard_tab_frame, shipyard_update_db_btn, shipyard_find_ship_btn, shipyard_results_tree, shipyard_status_lbl
    global shipyard_include_planetary_cb, shipyard_include_fc_cb

    if shipyard_tab_frame and shipyard_tab_frame.winfo_exists():
        try:
            shipyard_controls_frame_widget = shipyard_tab_frame.winfo_children()[0]
            if shipyard_controls_frame_widget.winfo_children():
                radius_label_widget_shipyard = shipyard_controls_frame_widget.winfo_children()[0]
                if isinstance(radius_label_widget_shipyard, ttk.Label):
                     radius_label_widget_shipyard.config(text=lang_module.get_string("shipyard_radius_label"))

                ship_select_label_widget = shipyard_controls_frame_widget.winfo_children()[2]
                if isinstance(ship_select_label_widget, ttk.Label):
                    ship_select_label_widget.config(text=lang_module.get_string("shipyard_select_ship_label"))
            
            if shipyard_update_db_btn: shipyard_update_db_btn.config(text=lang_module.get_string("shipyard_update_db_button"))
            if shipyard_find_ship_btn: shipyard_find_ship_btn.config(text=lang_module.get_string("shipyard_find_ship_button"))

            if len(shipyard_tab_frame.winfo_children()) > 1:
                shipyard_filters_frame_direct_child = shipyard_tab_frame.winfo_children()[1]
                if isinstance(shipyard_filters_frame_direct_child, ttk.Frame):
                    if shipyard_include_planetary_cb and shipyard_include_planetary_cb.winfo_exists():
                        shipyard_include_planetary_cb.config(text=lang_module.get_string("settings_include_planetary_cb"))
                    if shipyard_include_fc_cb and shipyard_include_fc_cb.winfo_exists():
                        shipyard_include_fc_cb.config(text=lang_module.get_string("settings_include_fc_cb"))
        except IndexError:
            logger.warning("Could not find expected widgets in shipyard_tab_frame for language update.")

        if shipyard_results_tree:
            cols_shipyard_keys = ["tree_col_shipyard_station", "tree_col_shipyard_system",
                                  "tree_col_shipyard_dist_ly", "tree_col_shipyard_dist_ls",
                                  "tree_col_shipyard_type", "tree_col_shipyard_pad_size"] 
            for key_col_sy in cols_shipyard_keys:
                new_display_name_sy = lang_module.get_string(key_col_sy)
                try:
                    current_heading_config_sy = shipyard_results_tree.heading(key_col_sy)
                    current_text_with_indicator_sy = current_heading_config_sy.get("text", "")
                    sort_indicator_sy = ""
                    if "▼" in current_text_with_indicator_sy: sort_indicator_sy = " ▼"
                    elif "▲" in current_text_with_indicator_sy: sort_indicator_sy = " ▲"
                    shipyard_results_tree.heading(key_col_sy, text=new_display_name_sy + sort_indicator_sy)
                except tk.TclError: pass

    if shipyard_status_lbl:
        current_text_shipyard = shipyard_status_lbl.cget("text")
        is_default_shipyard_msg = any(current_text_shipyard == lang_module.TRANSLATIONS[lc].get("shipyard_select_ship_and_find") for lc in lang_module.TRANSLATIONS)
        if is_default_shipyard_msg: shipyard_status_lbl.config(text=lang_module.get_string("shipyard_select_ship_and_find"))


def create_shipyard_tab(notebook_parent, shared_elements_dict):
    global shipyard_tab_frame, ship_to_find_var, shipyard_find_ship_btn, shipyard_update_db_btn, shipyard_results_tree, shipyard_status_lbl
    global s_shipyard_radius_var, s_include_planetary_var, s_include_fleet_carriers_var, s_station_dist_var, s_radius_var
    global s_update_status_func, s_set_buttons_state_func, s_get_current_system_func, s_cancel_shipyard_event, s_root
    global shipyard_include_planetary_cb, shipyard_include_fc_cb
    global s_shipyard_db_status_lbl_widget_ref

    s_shipyard_radius_var = shared_elements_dict["shipyard_radius_var"]
    s_include_planetary_var = shared_elements_dict["include_planetary_var"]
    s_include_fleet_carriers_var = shared_elements_dict["include_fleet_carriers_var"]
    s_station_dist_var = shared_elements_dict["station_dist_var"]
    s_radius_var = shared_elements_dict["radius_var"]
    s_update_status_func = shared_elements_dict["update_status_func"]
    s_set_buttons_state_func = shared_elements_dict["set_buttons_state_func"]
    s_get_current_system_func = shared_elements_dict["get_current_system_func"]
    s_cancel_shipyard_event = shared_elements_dict["cancel_shipyard_event"]
    s_root = shared_elements_dict["root"]
    s_shipyard_db_status_lbl_widget_ref = shared_elements_dict.get("shipyard_db_status_lbl_widget")

    shipyard_tab_frame = ttk.Frame(notebook_parent, padding="10")
    notebook_parent.add(shipyard_tab_frame, text=lang_module.get_string("shipyard_tab_title"))
    shipyard_tab_frame.columnconfigure(0, weight=1)

    shipyard_controls_frame = ttk.Frame(shipyard_tab_frame)
    shipyard_controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5), padx=5)
    shipyard_controls_frame.columnconfigure(3, weight=1) 

    ttk.Label(shipyard_controls_frame, text=lang_module.get_string("shipyard_radius_label")).grid(row=0, column=0, padx=(0,5), pady=2, sticky=tk.W)
    shipyard_radius_entry = ttk.Entry(shipyard_controls_frame, textvariable=s_shipyard_radius_var, width=7)
    shipyard_radius_entry.grid(row=0, column=1, padx=(0,10), pady=2, sticky=tk.W)

    ttk.Label(shipyard_controls_frame, text=lang_module.get_string("shipyard_select_ship_label")).grid(row=0, column=2, padx=(0,5), pady=2, sticky=tk.W)
    ship_to_find_var = tk.StringVar()
    ship_display_names = sorted(list(PURCHASABLE_SHIPS_LIST.values()))
    ship_combobox = ttk.Combobox(shipyard_controls_frame, textvariable=ship_to_find_var, values=ship_display_names, state="readonly", width=30)
    ship_combobox.grid(row=0, column=3, padx=(0,10), pady=2, sticky=tk.EW)
    if ship_display_names: ship_combobox.set(ship_display_names[0])

    shipyard_find_ship_btn = ttk.Button(shipyard_controls_frame, text=lang_module.get_string("shipyard_find_ship_button"), command=on_find_ship_pressed)
    shipyard_find_ship_btn.grid(row=0, column=4, padx=(0,5), pady=2, sticky=tk.E)
    shipyard_update_db_btn = ttk.Button(shipyard_controls_frame, text=lang_module.get_string("shipyard_update_db_button"), command=on_update_shipyard_db_pressed)
    shipyard_update_db_btn.grid(row=0, column=5, padx=(0,0), pady=2, sticky=tk.E)

    shipyard_filter_options_frame = ttk.Frame(shipyard_tab_frame)
    shipyard_filter_options_frame.grid(row=1, column=0, sticky="w", pady=(0, 5), padx=5)
    
    shipyard_include_planetary_cb = ttk.Checkbutton(shipyard_filter_options_frame, text=lang_module.get_string("settings_include_planetary_cb"), variable=s_include_planetary_var)
    shipyard_include_planetary_cb.pack(side=tk.LEFT, padx=(0, 10))

    shipyard_include_fc_cb = ttk.Checkbutton(shipyard_filter_options_frame, text=lang_module.get_string("settings_include_fc_cb"), variable=s_include_fleet_carriers_var)
    shipyard_include_fc_cb.pack(side=tk.LEFT, padx=(0, 10))
    
    cols_shipyard_keys = ["tree_col_shipyard_station", "tree_col_shipyard_system",
                          "tree_col_shipyard_dist_ly", "tree_col_shipyard_dist_ls",
                          "tree_col_shipyard_type", "tree_col_shipyard_pad_size"] 
    shipyard_results_tree = ttk.Treeview(shipyard_tab_frame, columns=cols_shipyard_keys, show='headings', style="Treeview")
    col_configs_shipyard = {
        "tree_col_shipyard_station": {"width": 220, "anchor": tk.W, "stretch": tk.YES, "type": "str_ci"},
        "tree_col_shipyard_system":  {"width": 150, "anchor": tk.W, "stretch": tk.YES, "type": "str_ci"},
        "tree_col_shipyard_dist_ly": {"width": 80, "anchor": tk.E, "stretch": tk.NO,  "type": "float"},
        "tree_col_shipyard_dist_ls": {"width": 90, "anchor": tk.E, "stretch": tk.NO,  "type": "float"},
        "tree_col_shipyard_type":    {"width": 150, "anchor": tk.W, "stretch": tk.NO,  "type": "str_ci"},
        "tree_col_shipyard_pad_size": {"width": 60, "anchor": tk.CENTER, "stretch": tk.NO, "type": "str_ci"}
    }
    for key in cols_shipyard_keys:
        cfg = col_configs_shipyard[key]
        shipyard_results_tree.heading(key, text=lang_module.get_string(key), anchor=tk.W,
                                      command=lambda tv=shipyard_results_tree, c_key=key, dt=cfg["type"]: gui_main.sort_treeview_column_general(tv, c_key, dt))
        shipyard_results_tree.column(key, width=cfg["width"], anchor=cfg["anchor"], stretch=cfg["stretch"])
    shipyard_results_tree.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
    shipyard_tab_frame.rowconfigure(2, weight=1)

    shipyard_status_lbl = ttk.Label(shipyard_tab_frame, text=lang_module.get_string("shipyard_select_ship_and_find"), style="Status.TLabel")
    shipyard_status_lbl.grid(row=3, column=0, sticky="ew", padx=5, pady=(5,0))

    logger.debug("Shipyard tab created with Pad Size column.")
    return shipyard_tab_frame