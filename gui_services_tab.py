#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import asyncio
import aiohttp # Pour _fetch_services_async

# --- Imports des modules de l'application ---
from constants import (
    # Importer SEULEMENT les constantes utilisées par cet onglet
    # Par exemple, si vous avez des listes de services spécifiques ou des clés de traduction
    ED_ORANGE, 
    COST_COLOR, 
    PROFIT_COLOR,
    ED_MEDIUM_GREY, ED_WHITE_TEXT, ED_DARK_GREY,
    TAG_REWARD, TAG_COST, TAG_PROFIT, TAG_HEADER, TAG_SUBHEADER, TAG_TOTAL_PROFIT_LEG, # Pour le formatage du texte
    BASE_FONT_FAMILY, BASE_FONT_SIZE # Pour le formatage du texte
)
import api_handler # Pour fetch_json et BASE_URL, HEADERS
from api_handler import OperationCancelledError as ApiOperationCancelledError # Spécifique à api_handler
import language as lang_module

# Importer gui_main pour accéder aux éléments partagés si nécessaire (attention aux dépendances circulaires)
# Il est préférable d'utiliser shared_elements_dict autant que possible.
import gui_main

logger = logging.getLogger(__name__)

# ---- Widgets spécifiques à l'onglet Services ----
services_tab_frame = None
services_tab_tree = None
services_tab_status_lbl = None
service_type_var = None
service_pad_size_var = None
service_type_label_widget = None
service_min_pad_label_widget = None
find_services_btn_widget = None

# Références aux éléments partagés de gui_main
s_update_status_func = None
s_set_buttons_state_func = None
s_get_current_system_func = None
s_cancel_services_event = None
s_root = None # Référence à la fenêtre principale pour les dialogues modaux

# --- Fonctions spécifiques à l'onglet Services ---

def on_find_nearest_services_pressed(pad_size_map_display_text_to_api_value):
    """ Gère le clic sur le bouton 'Trouver Services Proches'. """
    global services_tab_tree, services_tab_status_lbl, service_type_var, service_pad_size_var
    global s_update_status_func, s_set_buttons_state_func, s_get_current_system_func, s_cancel_services_event, s_root

    current_system = s_get_current_system_func()
    if not current_system or current_system == "?":
        messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("error_service_search_no_system"), parent=s_root)
        return
    selected_service_api_value = service_type_var.get()
    if not selected_service_api_value:
        messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("error_service_search_no_service"), parent=s_root)
        return

    s_cancel_services_event.clear()
    if s_update_status_func:
        s_update_status_func(lang_module.get_string("status_service_searching_for", service=selected_service_api_value), indeterminate=True, target_status_label_widget=services_tab_status_lbl)
    
    # Appel à la fonction globale de gui_main pour gérer l'état du bouton Annuler et des autres onglets
    if gui_main._set_buttons_state: # S'assurer que la fonction est accessible
        gui_main._set_buttons_state(operation_running=True, cancellable=True) # Indiquer que l'opération est en cours

    set_services_buttons_state(operation_running=True, cancellable=True, source_tab="services") # Gérer les boutons de cet onglet


    if services_tab_tree:
        for item in services_tab_tree.get_children():
            services_tab_tree.delete(item)

    async def _fetch_services_async():
        try:
            api_params = {}
            selected_pad_display_text = service_pad_size_var.get()
            pad_api_value_for_request = pad_size_map_display_text_to_api_value.get(selected_pad_display_text)

            if pad_api_value_for_request is not None:
                 api_params['minLandingPadSize'] = pad_api_value_for_request

            url = f"{api_handler.BASE_URL}system/name/{current_system}/nearest/{selected_service_api_value.lower()}"
            async with aiohttp.ClientSession(headers=api_handler.HEADERS) as session:
                results = await api_handler.fetch_json(session, url, params=api_params, cancel_event=s_cancel_services_event)

            if s_cancel_services_event.is_set():
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_search_cancelled"), -1, target_status_label_widget=services_tab_status_lbl)
                return

            if results and isinstance(results, list):
                if services_tab_tree:
                    for station_data in results:
                        s_name = station_data.get('stationName', 'N/A'); sys_name = station_data.get('systemName', 'N/A')
                        dist_ly_val = station_data.get('distanceLy', station_data.get('distance'))
                        dist_ly = f"{dist_ly_val:.1f}" if isinstance(dist_ly_val, (int,float)) else str(dist_ly_val)
                        pad = station_data.get('maxLandingPadSize', '?');
                        dist_ls_val = station_data.get('distanceToArrival')
                        dist_ls = f"{dist_ls_val:.0f}" if isinstance(dist_ls_val, (int,float)) else str(dist_ls_val)
                        faction_info = station_data.get('controllingFaction', {})
                        faction = faction_info.get('name', 'N/A') if isinstance(faction_info, dict) else 'N/A'
                        services_tab_tree.insert("", tk.END, values=(s_name, sys_name, dist_ly, pad, dist_ls, faction ))
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_found_stations", count=len(results)), -1, target_status_label_widget=services_tab_status_lbl)
            elif isinstance(results, dict) and results.get('error'):
                 if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_api_error", error_message=results['error'].get('message', 'Unknown')), -1, target_status_label_widget=services_tab_status_lbl)
                 logger.error(f"API error for nearest service: {results}")
            else:
                if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_no_stations_found"), -1, target_status_label_widget=services_tab_status_lbl)
                logger.warning(f"No stations found or unexpected API response for nearest service: {results}")
        except ApiOperationCancelledError:
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_search_cancelled"), -1, target_status_label_widget=services_tab_status_lbl); logger.info("Nearest services search cancelled.")
        except Exception as e:
            logger.exception("Error fetching nearest services:")
            if s_update_status_func: s_update_status_func(lang_module.get_string("status_service_error_fetching", error=e), -1, target_status_label_widget=services_tab_status_lbl)
        finally:
            if gui_main.root and gui_main.root.winfo_exists(): # Utiliser gui_main.root
                 # Remettre les boutons globaux dans leur état par défaut via la fonction globale
                 gui_main.root.after(0, gui_main._set_buttons_state, False, False)
                 # Remettre les boutons de cet onglet dans leur état par défaut
                 gui_main.root.after(0, set_services_buttons_state, False, False, "services")


    threading.Thread(target=lambda: asyncio.run(_fetch_services_async()), daemon=True).start()

def set_services_buttons_state(operation_running=False, cancellable=False, source_tab="services"):
    """ Gère l'état des boutons spécifiques à l'onglet Services. """
    global find_services_btn_widget
    action_buttons_state = tk.DISABLED if operation_running else tk.NORMAL
    if find_services_btn_widget:
        find_services_btn_widget.config(state=action_buttons_state)
    # La gestion du bouton Annuler global est faite par gui_main._set_buttons_state

def update_services_tab_texts():
    """ Met à jour les textes des widgets de l'onglet Services. """
    global services_tab_frame, service_type_label_widget, service_min_pad_label_widget, find_services_btn_widget, services_tab_tree, services_tab_status_lbl, service_pad_size_var

    if service_type_label_widget: service_type_label_widget.config(text=lang_module.get_string("service_type_label"))
    if service_min_pad_label_widget: service_min_pad_label_widget.config(text=lang_module.get_string("service_min_pad_label"))
    if find_services_btn_widget: find_services_btn_widget.config(text=lang_module.get_string("service_find_button"))

    # Mise à jour du combobox de taille de pad
    if service_pad_size_var and gui_main.root: # Utiliser gui_main.root
        pad_size_map_display_text_to_api_value_current_lang = {
            lang_module.get_string("service_pad_any"): None,
            lang_module.get_string("service_pad_small"): "S",
            lang_module.get_string("service_pad_medium"): "M",
            lang_module.get_string("service_pad_large"): "L"
        }
        try:
            # Trouver le combobox (cela peut être fragile si la structure change)
            # Supposons que service_controls_frame est le parent
            service_controls_frame = service_min_pad_label_widget.master 
            pad_size_combo_services_widget = None
            for child in service_controls_frame.winfo_children():
                if isinstance(child, ttk.Combobox) and child.cget("textvariable") == str(service_pad_size_var): # Comparer en string
                    pad_size_combo_services_widget = child
                    break
            
            if pad_size_combo_services_widget:
                current_selection_text = service_pad_size_var.get()
                current_api_value = None
                # Trouver la valeur API basée sur le texte actuellement sélectionné (qui pourrait être dans l'ancienne langue)
                for lang_code_iter_check in lang_module.TRANSLATIONS: # Assurez-vous que TRANSLATIONS est accessible
                    temp_map_old_lang = {
                        lang_module.TRANSLATIONS[lang_code_iter_check].get("service_pad_any"): None,
                        lang_module.TRANSLATIONS[lang_code_iter_check].get("service_pad_small"): "S",
                        lang_module.TRANSLATIONS[lang_code_iter_check].get("service_pad_medium"): "M",
                        lang_module.TRANSLATIONS[lang_code_iter_check].get("service_pad_large"): "L"
                    }
                    if current_selection_text in temp_map_old_lang:
                        current_api_value = temp_map_old_lang[current_selection_text]; break
                
                pad_size_combo_services_widget['values'] = list(pad_size_map_display_text_to_api_value_current_lang.keys())
                
                new_display_text_to_set = lang_module.get_string("service_pad_any") # Fallback
                for disp_text, api_val in pad_size_map_display_text_to_api_value_current_lang.items():
                    if api_val == current_api_value: new_display_text_to_set = disp_text; break
                service_pad_size_var.set(new_display_text_to_set)
        except (IndexError, AttributeError, tk.TclError) as e_combo:
            logger.warning(f"Could not update service pad size combobox text: {e_combo}")


    # Mise à jour des en-têtes du Treeview
    if services_tab_tree:
        cols_services_keys_tree = ["tree_col_station", "tree_col_system", "tree_col_distance_ly", "tree_col_pad", "tree_col_dist_star_ls", "tree_col_faction"]
        for key_col in cols_services_keys_tree:
            new_display_name_col = lang_module.get_string(key_col)
            try:
                current_heading_config_col = services_tab_tree.heading(key_col)
                current_text_with_indicator_col = current_heading_config_col.get("text", "")
                sort_indicator_col = ""
                if "▼" in current_text_with_indicator_col: sort_indicator_col = " ▼"
                elif "▲" in current_text_with_indicator_col: sort_indicator_col = " ▲"
                services_tab_tree.heading(key_col, text=new_display_name_col + sort_indicator_col)
            except tk.TclError: pass # Colonne non trouvée, ignorer

    # Label de statut de l'onglet
    if services_tab_status_lbl:
        current_text_services = services_tab_status_lbl.cget("text")
        is_default_service_msg = any(current_text_services == lang_module.TRANSLATIONS[lc].get("service_select_and_find") for lc in lang_module.TRANSLATIONS)
        if is_default_service_msg: services_tab_status_lbl.config(text=lang_module.get_string("service_select_and_find"))


def create_services_tab(notebook_parent, shared_elements_dict):
    """ Crée l'onglet Services et tous ses widgets. """
    global services_tab_frame, services_tab_tree, services_tab_status_lbl, service_type_var, service_pad_size_var
    global service_type_label_widget, service_min_pad_label_widget, find_services_btn_widget
    global s_update_status_func, s_set_buttons_state_func, s_get_current_system_func, s_cancel_services_event, s_root

    # Stocker les références partagées
    s_update_status_func = shared_elements_dict["update_status_func"]
    s_set_buttons_state_func = shared_elements_dict["set_buttons_state_func"]
    s_get_current_system_func = shared_elements_dict["get_current_system_func"]
    s_cancel_services_event = shared_elements_dict["cancel_services_event"]
    s_root = shared_elements_dict["root"]


    services_tab_frame = ttk.Frame(notebook_parent, padding="10")
    notebook_parent.add(services_tab_frame, text=lang_module.get_string("services_tab_title"))
    services_tab_frame.columnconfigure(0, weight=1) # Pour que le Treeview s'étende

    # --- Cadre des Contrôles pour l'onglet Services ---
    service_controls_frame = ttk.Frame(services_tab_frame)
    service_controls_frame.grid(row=0, column=0, sticky="ew", pady=(0,10), padx=5)
    service_controls_frame.columnconfigure(1, weight=0) # Combobox type de service
    service_controls_frame.columnconfigure(3, weight=0) # Combobox taille de pad
    service_controls_frame.columnconfigure(4, weight=1) # Bouton (pour l'étirer à droite si besoin)

    service_type_label_widget = ttk.Label(service_controls_frame, text=lang_module.get_string("service_type_label"))
    service_type_label_widget.grid(row=0, column=0, padx=(0,5), pady=5, sticky=tk.W)
    
    services_list_api_values = ["interstellar-factors", "material-trader", "technology-broker", "black-market", "universal-cartographics", "refuel", "repair", "shipyard", "outfitting", "search-and-rescue"]
    service_type_var = tk.StringVar()
    service_combo = ttk.Combobox(service_controls_frame, textvariable=service_type_var, values=services_list_api_values, state="readonly", width=25)
    service_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
    if services_list_api_values: service_combo.set(services_list_api_values[0]) # Sélectionner le premier par défaut

    service_min_pad_label_widget = ttk.Label(service_controls_frame, text=lang_module.get_string("service_min_pad_label"))
    service_min_pad_label_widget.grid(row=0, column=2, padx=(10,5), pady=5, sticky=tk.W)
    
    pad_size_map_services_display_text_to_api_value = {
        lang_module.get_string("service_pad_any"): None,
        lang_module.get_string("service_pad_small"): "S",
        lang_module.get_string("service_pad_medium"): "M",
        lang_module.get_string("service_pad_large"): "L"
    }
    service_pad_size_var = tk.StringVar() # Utiliser la variable globale de ce module
    pad_size_combo_services = ttk.Combobox(service_controls_frame, textvariable=service_pad_size_var,
                                           values=list(pad_size_map_services_display_text_to_api_value.keys()),
                                           state="readonly", width=15)
    pad_size_combo_services.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
    pad_size_combo_services.set(lang_module.get_string("service_pad_any")) # Sélectionner "Any" par défaut

    find_services_btn_widget = ttk.Button(service_controls_frame, text=lang_module.get_string("service_find_button"),
                                          command=lambda: on_find_nearest_services_pressed(pad_size_map_services_display_text_to_api_value))
    find_services_btn_widget.grid(row=0, column=4, padx=(10,0), pady=5, sticky=tk.E)


    # --- Treeview pour les résultats ---
    cols_services_keys = ["tree_col_station", "tree_col_system", "tree_col_distance_ly", "tree_col_pad", "tree_col_dist_star_ls", "tree_col_faction"]
    services_tab_tree = ttk.Treeview(services_tab_frame, columns=cols_services_keys, show='headings', style="Treeview")
    
    for i, key in enumerate(cols_services_keys):
        col_display_name = lang_module.get_string(key)
        anchor_val = tk.W if key in ["tree_col_station", "tree_col_system", "tree_col_faction"] else tk.E
        width_val = 180 if key in ["tree_col_station", "tree_col_system", "tree_col_faction"] else 100
        if key == "tree_col_distance_ly": width_val = 80
        if key == "tree_col_pad": width_val = 60

        data_type = "str_ci" # type de données par défaut pour le tri
        if key in ["tree_col_distance_ly", "tree_col_dist_star_ls"]: data_type = "float"
        elif key == "tree_col_pad": data_type = "str" # 'S', 'M', 'L' sont des chaînes

        # Utiliser gui_main.sort_treeview_column_general
        services_tab_tree.heading(key, text=col_display_name, anchor=tk.W,
                                  command=lambda tv=services_tab_tree, c_key=key, dt=data_type: gui_main.sort_treeview_column_general(tv, c_key, dt))
        services_tab_tree.column(key, width=width_val, anchor=anchor_val, stretch=tk.YES if i < 2 or key == "tree_col_faction" else tk.NO)


    services_tab_tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    services_tab_frame.rowconfigure(1, weight=1) # Permettre au Treeview de s'étendre verticalement

    # --- Label de Statut pour l'onglet Services ---
    services_tab_status_lbl = ttk.Label(services_tab_frame, text=lang_module.get_string("service_select_and_find"), style="Status.TLabel")
    services_tab_status_lbl.grid(row=2, column=0, sticky="ew", padx=5, pady=(5,0))

    logger.debug("Services tab created.")
    return services_tab_frame