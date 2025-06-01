#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import logging
import threading
import asyncio 
from datetime import datetime, timezone
import math
import os # Pour la gestion des fichiers (sauvegarde/chargement)
import json # Pour la sauvegarde/chargement en JSON
import aiohttp

import language as lang_module
from constants import ( 
    ED_DARK_GREY, ED_ORANGE, ED_MEDIUM_GREY, ED_WHITE_TEXT,
    BASE_FONT_FAMILY, BASE_FONT_SIZE,
    KEY_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS,
    KEY_INCLUDE_FLEET_CARRIERS, DEFAULT_INCLUDE_FLEET_CARRIERS,
    KEY_RADIUS, DEFAULT_RADIUS, 
    KEY_MAX_STATION_DISTANCE_LS, DEFAULT_MAX_STATION_DISTANCE_LS,
    PROFIT_COLOR, TAG_PROFIT,
    MULTI_HOP_ROUTE_CACHE_FILE, # <<< Importer le nom du fichier de cache
    DEFAULT_INCLUDE_PLANETARY, KEY_INCLUDE_PLANETARY
)
import api_handler
from api_handler import OperationCancelledError
import optimizer_logic
import settings_manager

logger = logging.getLogger(__name__)

# ... (Variables globales au module et références aux widgets comme avant) ...
s_shared_root_multihop = None
multihop_tab_page_frame_ref = None
config_frame = None
num_hops_var = None
max_ly_var = None
start_planning_btn = None
num_hops_entry = None 
max_ly_entry = None   
planning_frame = None
current_hop_details_lbl_var = None
suggestions_tree = None
select_hop_btn = None
restart_planning_btn_planning = None
summary_frame = None
route_summary_text = None
clear_summary_btn = None
multihop_status_lbl = None

current_planning_state = {
    "total_hops": 0, "max_ly_per_hop": 0.0, "current_hop_number": 0,
    "planned_route_legs": [], "current_source_system": None, "current_source_station": None,
    "player_cargo_capacity": 0, "player_pad_size": None, "player_pad_size_int": None,
    "is_planning_active": False, "last_selected_trade_data": None,
    "last_saved_total_profit": 0 # Pour stocker le profit de la route sauvegardée
}

s_update_status_func_global = None
s_set_buttons_state_func_global = None
s_cancel_multihop_event = None
s_sort_treeview_column_func = None
s_get_current_system_func_from_main = None
s_get_current_station_func_from_main = None
s_get_current_ship_type_func_from_main = None
s_get_current_cargo_capacity_func_from_main = None
s_get_current_pad_size_func_from_main = None

# --- Fonctions de Sauvegarde et Chargement ---
def _save_planned_route():
    """Sauvegarde l'itinéraire planifié actuel dans un fichier JSON."""
    global current_planning_state
    if not current_planning_state["planned_route_legs"]:
        # Ne rien sauvegarder si la route est vide (par exemple après un clear)
        # Ou supprimer le fichier de cache s'il existe
        if os.path.exists(MULTI_HOP_ROUTE_CACHE_FILE):
            try:
                os.remove(MULTI_HOP_ROUTE_CACHE_FILE)
                logger.info(f"Empty route, removed cache file: {MULTI_HOP_ROUTE_CACHE_FILE}")
            except OSError as e:
                logger.error(f"Error removing empty route cache file {MULTI_HOP_ROUTE_CACHE_FILE}: {e}")
        return

    data_to_save = {
        "planned_route_legs": current_planning_state["planned_route_legs"],
        "total_hops_configured": current_planning_state["total_hops"], # Sauvegarder le contexte
        "max_ly_per_hop_configured": current_planning_state["max_ly_per_hop"],
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "total_route_profit": sum(leg.get("leg_profit", 0) for leg in current_planning_state["planned_route_legs"])
    }
    try:
        with open(MULTI_HOP_ROUTE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2)
        logger.info(f"Multi-hop route saved to {MULTI_HOP_ROUTE_CACHE_FILE}")
        _update_status_local(lang_module.get_string("multihop_status_route_saved"))
    except IOError as e:
        logger.error(f"Error saving multi-hop route to {MULTI_HOP_ROUTE_CACHE_FILE}: {e}")
        _update_status_local(f"Error saving route: {e}") # Traduire si besoin

def _load_saved_route():
    """Charge un itinéraire sauvegardé depuis un fichier JSON, si existant."""
    global current_planning_state
    if os.path.exists(MULTI_HOP_ROUTE_CACHE_FILE):
        try:
            with open(MULTI_HOP_ROUTE_CACHE_FILE, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            current_planning_state["planned_route_legs"] = saved_data.get("planned_route_legs", [])
            # Restaurer le contexte si besoin (pour affichage ou reprise future)
            current_planning_state["total_hops"] = saved_data.get("total_hops_configured", 0)
            current_planning_state["max_ly_per_hop"] = saved_data.get("max_ly_per_hop_configured", 0.0)
            current_planning_state["last_saved_total_profit"] = saved_data.get("total_route_profit", 0)
            # La planification n'est pas active au chargement, on est en mode récapitulatif
            current_planning_state["is_planning_active"] = False 
            current_planning_state["current_hop_number"] = len(current_planning_state["planned_route_legs"]) # Le nombre de sauts terminés

            if num_hops_var and current_planning_state["total_hops"] > 0: # Mettre à jour les champs de config
                 num_hops_var.set(str(current_planning_state["total_hops"]))
            if max_ly_var and current_planning_state["max_ly_per_hop"] > 0:
                 max_ly_var.set(f"{current_planning_state['max_ly_per_hop']:.1f}")

            logger.info(f"Multi-hop route loaded from {MULTI_HOP_ROUTE_CACHE_FILE}")
            return True
        except (IOError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error loading or parsing saved route from {MULTI_HOP_ROUTE_CACHE_FILE}: {e}")
            # Supprimer le fichier corrompu pour éviter des erreurs répétées
            try: os.remove(MULTI_HOP_ROUTE_CACHE_FILE)
            except OSError: pass
            return False
    return False

# --- Fonctions de l'UI (existantes, avec modifications mineures si besoin) ---
def _update_status_local(message, percentage=None, indeterminate=False):
    # ... (inchangée)
    if multihop_status_lbl and multihop_status_lbl.winfo_exists():
        multihop_status_lbl.config(text=message)
    if s_update_status_func_global:
        s_update_status_func_global(message, percentage, indeterminate, target_status_label_widget=multihop_status_lbl)

def _configure_ui_for_state(state_name):
    # ... (inchangée)
    global config_frame, planning_frame, summary_frame, start_planning_btn, restart_planning_btn_planning, select_hop_btn, num_hops_entry, max_ly_entry

    config_inputs_state = tk.DISABLED if state_name in ["planning_hop", "summary"] else tk.NORMAL
    if num_hops_entry and num_hops_entry.winfo_exists(): num_hops_entry.config(state=config_inputs_state)
    if max_ly_entry and max_ly_entry.winfo_exists(): max_ly_entry.config(state=config_inputs_state)

    if state_name == "initial_config":
        if config_frame and config_frame.winfo_exists(): config_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        if planning_frame and planning_frame.winfo_exists(): planning_frame.grid_remove()
        if summary_frame and summary_frame.winfo_exists(): summary_frame.grid_remove()
        if start_planning_btn and start_planning_btn.winfo_exists(): start_planning_btn.config(state=tk.NORMAL)
        if restart_planning_btn_planning and restart_planning_btn_planning.winfo_exists(): restart_planning_btn_planning.config(state=tk.DISABLED) 
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        current_planning_state["is_planning_active"] = False
    elif state_name == "planning_hop":
        if config_frame and config_frame.winfo_exists(): config_frame.grid()
        if planning_frame and planning_frame.winfo_exists(): planning_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        if summary_frame and summary_frame.winfo_exists(): summary_frame.grid_remove()
        if start_planning_btn and start_planning_btn.winfo_exists(): start_planning_btn.config(state=tk.DISABLED)
        if restart_planning_btn_planning and restart_planning_btn_planning.winfo_exists(): restart_planning_btn_planning.config(state=tk.NORMAL)
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        current_planning_state["is_planning_active"] = True
    elif state_name == "summary":
        if config_frame and config_frame.winfo_exists(): config_frame.grid()
        if planning_frame and planning_frame.winfo_exists(): planning_frame.grid_remove()
        if summary_frame and summary_frame.winfo_exists(): summary_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        if start_planning_btn and start_planning_btn.winfo_exists(): start_planning_btn.config(state=tk.NORMAL)
        if restart_planning_btn_planning and restart_planning_btn_planning.winfo_exists(): restart_planning_btn_planning.config(state=tk.DISABLED)
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        current_planning_state["is_planning_active"] = False


def on_start_planning_pressed():
    # ... (logique existante, mais s'assurer de réinitialiser avant de démarrer un nouveau plan)
    global num_hops_var, max_ly_var, current_planning_state

    # Effacer un éventuel plan précédent avant de commencer un nouveau
    on_restart_or_clear_pressed(clear_summary_only=False, called_from_start=True) # Ajout d'un drapeau

    _update_status_local(lang_module.get_string("multihop_status_validating_inputs"))
    try:
        hops = int(num_hops_var.get())
        max_ly = float(max_ly_var.get())
        if not (1 <= hops <= 10): # Limite à 10 sauts par exemple
            _update_status_local(lang_module.get_string("multihop_status_input_hops_num_error"))
            messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("multihop_status_input_hops_num_error"), parent=s_shared_root_multihop)
            return
        if max_ly <= 0:
            _update_status_local(lang_module.get_string("multihop_status_input_max_ly_error"))
            messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("multihop_status_input_max_ly_error"), parent=s_shared_root_multihop)
            return
    except ValueError:
        msg = lang_module.get_string("settings_validation_error", error="Hops and Max LY must be valid numbers.")
        _update_status_local(msg)
        messagebox.showerror(lang_module.get_string("error_dialog_title"), msg, parent=s_shared_root_multihop)
        return

    current_planning_state.update({
        "total_hops": hops, "max_ly_per_hop": max_ly, # "planned_route_legs" déjà vidé par on_restart...
        "current_hop_number": 0, "last_selected_trade_data": None
    })

    _update_status_local(lang_module.get_string("multihop_status_getting_player_info"))
    
    start_system = s_get_current_system_func_from_main()
    start_station = s_get_current_station_func_from_main()
    cargo_cap_val = s_get_current_cargo_capacity_func_from_main()
    pad_size_val = s_get_current_pad_size_func_from_main()
    
    try: cargo_cap = int(cargo_cap_val) 
    except (ValueError, TypeError): cargo_cap = 0

    pad_size_str = str(pad_size_val)
    try:
        current_planning_state["player_pad_size_int"] = int(pad_size_str) if pad_size_str.isdigit() else None
    except ValueError:
        current_planning_state["player_pad_size_int"] = None
        
    if "?" in [start_system, start_station, pad_size_str] or \
       any(err_token in start_system for err_token in ["Unknown", "Error", "No Journal", "No Events"]) or \
       cargo_cap <= 0:
        _update_status_local(lang_module.get_string("multihop_status_player_info_error"))
        messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("multihop_status_player_info_error"), parent=s_shared_root_multihop)
        _configure_ui_for_state("initial_config")
        return

    current_planning_state.update({
        "current_source_system": start_system, "current_source_station": start_station,
        "player_cargo_capacity": cargo_cap, "player_pad_size": pad_size_str
    })
    
    logger.info(f"Starting multi-hop planning: {hops} hops, {max_ly} LY/hop. From: {start_station} ({start_system}). Cargo: {cargo_cap}T, Pad: {pad_size_str}.")
    _configure_ui_for_state("planning_hop")
    _plan_next_hop()


def _plan_next_hop():
    # ... (logique existante) ...
    # Assurez-vous que cette fonction gère l'annulation via s_cancel_multihop_event
    # et met à jour l'UI avec _update_status_local et _populate_suggestions_tree
    # comme dans la version précédente.
    # Les appels à api_handler et optimizer_logic se feront ici dans le _task_for_hop_planning.
    global current_planning_state, suggestions_tree, select_hop_btn, current_hop_details_lbl_var, s_cancel_multihop_event

    if s_cancel_multihop_event and s_cancel_multihop_event.is_set():
        _update_status_local(lang_module.get_string("multihop_status_route_cancelled"))
        _configure_ui_for_state("initial_config")
        if s_set_buttons_state_func_global: s_set_buttons_state_func_global(operation_running=False)
        return

    current_planning_state["current_hop_number"] += 1
    hop_num = current_planning_state["current_hop_number"]
    total_hops = current_planning_state["total_hops"]
    source_station = current_planning_state["current_source_station"]
    source_system = current_planning_state["current_source_system"]

    if current_hop_details_lbl_var:
        current_hop_details_lbl_var.set(lang_module.get_string("multihop_hop_details_label",
            current_hop_num=hop_num, total_hops_num=total_hops,
            current_station_name=source_station, current_system_name=source_system))
    if select_hop_btn:
        remaining_hops = total_hops - hop_num
        if remaining_hops >= 0:
            select_hop_btn.config(text=lang_module.get_string("multihop_select_and_finish_button") if remaining_hops == 0 else lang_module.get_string("multihop_select_and_continue_button", remaining_hops=remaining_hops), state=tk.DISABLED)

    _update_status_local(lang_module.get_string("multihop_status_planning_hop", hop_num_current=hop_num, hop_num_total=total_hops, station_name=source_station), indeterminate=True)
    
    if suggestions_tree:
        for item in suggestions_tree.get_children():
            suggestions_tree.delete(item)

    if s_set_buttons_state_func_global: s_set_buttons_state_func_global(operation_running=True, cancellable=True, source_tab_name="multihop")

    def _task_for_hop_planning():
        loop = None
        found_trades_local = []
        error_message_local = None

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if s_cancel_multihop_event and s_cancel_multihop_event.is_set(): raise OperationCancelledError("Hop planning cancelled before API calls.")

            _update_status_local(lang_module.get_string("multihop_status_updating_market_data", system_name=source_system), 0, indeterminate=True)
            
            settings = settings_manager.get_all_settings()
            api_max_age = settings.get(KEY_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS)
            api_include_fc_for_db_update = settings.get(KEY_INCLUDE_FLEET_CARRIERS, DEFAULT_INCLUDE_FLEET_CARRIERS)
            api_radius_for_db_update = current_planning_state["max_ly_per_hop"]

            async def _update_db_async():
                async with aiohttp.ClientSession(headers=getattr(api_handler, 'HEADERS', None)) as http_session:
                    return await api_handler.update_databases_if_needed(
                        http_session, current_system=source_system, current_station=source_station,
                        radius_val=api_radius_for_db_update, max_age_days_param=api_max_age,
                        include_fleet_carriers_val=api_include_fc_for_db_update, 
                        cancel_event=s_cancel_multihop_event,
                        progress_callback_main=_update_status_local)
            
            departure_data, local_data = loop.run_until_complete(_update_db_async())

            if s_cancel_multihop_event and s_cancel_multihop_event.is_set(): raise OperationCancelledError("Hop planning cancelled after DB update.")

            if not local_data or not local_data.get('station_markets'):
                error_message_local = lang_module.get_string("status_db_update_local_error") + " (No market data for surroundings)"
                logger.warning(error_message_local)
            else:
                _update_status_local(lang_module.get_string("multihop_status_finding_trades", station_name=source_station), 75, indeterminate=True)
                
                source_station_exports = []
                if departure_data and source_system == departure_data.get("system") and source_station == departure_data.get("station"):
                    source_station_exports = departure_data.get("offers", [])
                    logger.debug(f"Using departure data for source {source_station} exports ({len(source_station_exports)} items).")
                elif local_data and source_system in local_data.get("station_markets", {}) and \
                     source_station in local_data["station_markets"][source_system].get("stations_data", {}):
                    source_station_exports = local_data["station_markets"][source_system]["stations_data"][source_station].get("sells_to_player", [])
                    logger.debug(f"Using local cache for source {source_station} exports ({len(source_station_exports)} items).")
                else:
                    logger.warning(f"No export data found for source station {source_station} in departure or local data.")

                max_ls_from_settings = float(settings.get(KEY_MAX_STATION_DISTANCE_LS, DEFAULT_MAX_STATION_DISTANCE_LS))
                planetary_from_settings = settings.get(KEY_INCLUDE_PLANETARY, DEFAULT_INCLUDE_PLANETARY)
                fc_filter_for_logic = settings.get(KEY_INCLUDE_FLEET_CARRIERS, DEFAULT_INCLUDE_FLEET_CARRIERS)

                async def _find_trades_async():
                    async with aiohttp.ClientSession(headers=getattr(api_handler, 'HEADERS', None)) as http_session:
                        return await optimizer_logic.find_best_outbound_trades_for_hop(
                            http_session=http_session, source_system_name=source_system, source_station_name=source_station,
                            player_cargo_capacity=current_planning_state["player_cargo_capacity"],
                            player_pad_size_int=current_planning_state["player_pad_size_int"],
                            max_ly_per_hop_radius=current_planning_state["max_ly_per_hop"],
                            max_station_dist_ls_filter=max_ls_from_settings,
                            include_planetary_filter=planetary_from_settings,
                            include_fleet_carriers_filter=fc_filter_for_logic, 
                            departure_data_for_source=source_station_exports,
                            local_market_data=local_data,
                            cancel_event=s_cancel_multihop_event)
                found_trades_local = loop.run_until_complete(_find_trades_async())

        except OperationCancelledError as oce:
            error_message_local = lang_module.get_string("multihop_status_route_cancelled")
            logger.info(f"Hop planning task cancelled: {oce}")
        except Exception as e:
            logger.exception(f"Error during hop {hop_num} planning task:")
            error_message_local = lang_module.get_string("materials_error_refreshing", error=str(e))
        finally:
            if loop and not loop.is_closed(): loop.close()

            def _finalize_hop_ui():
                if error_message_local:
                    _update_status_local(error_message_local, -1)
                    if "cancelled" not in error_message_local.lower() and s_shared_root_multihop:
                         messagebox.showerror(lang_module.get_string("error_dialog_title"), error_message_local, parent=s_shared_root_multihop)
                elif found_trades_local:
                    _populate_suggestions_tree(found_trades_local)
                else:
                    _update_status_local(lang_module.get_string("multihop_status_no_trades_found"), 100)
                    _populate_suggestions_tree([])

                if s_set_buttons_state_func_global: s_set_buttons_state_func_global(operation_running=False)
            
            if s_shared_root_multihop and s_shared_root_multihop.winfo_exists():
                s_shared_root_multihop.after(0, _finalize_hop_ui)

    threading.Thread(target=_task_for_hop_planning, daemon=True).start()

def _populate_suggestions_tree(trades_data):
    # ... (inchangée)
    global suggestions_tree, select_hop_btn
    if not (suggestions_tree and suggestions_tree.winfo_exists()): return

    for item in suggestions_tree.get_children():
        suggestions_tree.delete(item)
    
    if not trades_data:
        _update_status_local(lang_module.get_string("multihop_status_no_trades_found"))
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        return

    for trade in trades_data:
        suggestions_tree.insert("", tk.END, values=(
            trade.get("dest_station", "?"), trade.get("dest_system", "?"),
            trade.get("commodity_localised", trade.get("commodity_to_buy", "?")),
            f"{trade.get('buy_price_at_source', 0):,.0f}", f"{trade.get('sell_price_at_dest', 0):,.0f}",
            f"{trade.get('profit_per_unit', 0):,.0f}", f"{trade.get('est_total_profit', 0):,.0f}",
            f"{trade.get('distance_ly', 0.0):.1f}", trade.get("landing_pad", "?"),
            f"{trade.get('dist_to_star', 0):,.0f}"
        ), iid=f"{trade.get('dest_system')}_{trade.get('dest_station')}_{trade.get('commodity_to_buy', 'unknown')}")
    
    _update_status_local(lang_module.get_string("multihop_status_select_next_hop"))

def on_suggestion_selected(event):
    # ... (inchangée)
    global suggestions_tree, select_hop_btn, current_planning_state
    
    if not (suggestions_tree and suggestions_tree.winfo_exists()): return
    selected_items = suggestions_tree.selection()

    if not selected_items:
        current_planning_state["last_selected_trade_data"] = None
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        return

    selected_item_iid = selected_items[0]
    item_values = suggestions_tree.item(selected_item_iid, "values")
    
    try:
        current_planning_state["last_selected_trade_data"] = {
            "dest_station": item_values[0], "dest_system": item_values[1],
            "commodity_to_buy": item_values[2], 
            "buy_price_at_source": float(str(item_values[3]).replace(',', '')),
            "sell_price_at_dest": float(str(item_values[4]).replace(',', '')),
            "profit_per_unit": float(str(item_values[5]).replace(',', '')),
            "est_total_profit": float(str(item_values[6]).replace(',', '')),
            "distance_ly": float(item_values[7]),
            "landing_pad": item_values[8],
            "dist_to_star": float(str(item_values[9]).replace(',', ''))
        }
        logger.debug(f"Trade selected from Treeview: {current_planning_state['last_selected_trade_data']}")
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.NORMAL)
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing selected trade data from Treeview: {e}. Values: {item_values}")
        current_planning_state["last_selected_trade_data"] = None
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)


def on_select_hop_pressed():
    # ... (logique existante)
    # À la fin, si c'est le dernier saut :
    # _save_planned_route() # Appeler la sauvegarde
    global current_planning_state, route_summary_text, select_hop_btn
    
    selected_trade = current_planning_state.get("last_selected_trade_data")
    if not selected_trade:
        messagebox.showwarning(lang_module.get_string("warning_title"), lang_module.get_string("multihop_status_select_next_hop"), parent=s_shared_root_multihop)
        return
    if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)

    buy_price = selected_trade["buy_price_at_source"]
    cargo_cap = current_planning_state["player_cargo_capacity"]
    quantity_to_trade = 0
    if cargo_cap > 0 and buy_price > 0:
        quantity_to_trade = math.floor(cargo_cap) 
    elif cargo_cap > 0:
        quantity_to_trade = math.floor(cargo_cap)
    
    actual_leg_profit = quantity_to_trade * selected_trade["profit_per_unit"]

    leg_info = {
        "hop_num": current_planning_state["current_hop_number"],
        "source_system": current_planning_state["current_source_system"],
        "source_station": current_planning_state["current_source_station"],
        "dest_system": selected_trade["dest_system"],
        "dest_station": selected_trade["dest_station"],
        "commodity_name": selected_trade["commodity_to_buy"],
        "buy_price_each": selected_trade["buy_price_at_source"],
        "sell_price_each": selected_trade["sell_price_at_dest"],
        "profit_per_unit": selected_trade["profit_per_unit"],
        "quantity": int(quantity_to_trade),
        "leg_profit": actual_leg_profit,
        "distance_ly_to_dest_system": selected_trade.get("distance_ly", 0.0),
        "distance_ls_to_dest_station": selected_trade.get("dist_to_star", 0)
    }
    current_planning_state["planned_route_legs"].append(leg_info)
    logger.info(f"Leg {leg_info['hop_num']} added: {leg_info['source_station']} -> {leg_info['dest_station']} with {leg_info['commodity_name']}, Qty: {leg_info['quantity']}")

    current_planning_state["current_source_system"] = selected_trade["dest_system"]
    current_planning_state["current_source_station"] = selected_trade["dest_station"]
    current_planning_state["last_selected_trade_data"] = None

    if current_planning_state["current_hop_number"] < current_planning_state["total_hops"]:
        _plan_next_hop()
    else: # Dernier saut terminé
        _update_status_local(lang_module.get_string("multihop_status_route_complete"))
        _display_route_summary()
        _save_planned_route() # <<< SAUVEGARDER LA ROUTE
        _configure_ui_for_state("summary")


def _display_route_summary():
    # ... (logique existante pour afficher, avec les distances et couleurs)
    global route_summary_text, current_planning_state
    if not (route_summary_text and route_summary_text.winfo_exists()): return

    route_summary_text.config(state=tk.NORMAL)
    route_summary_text.delete("1.0", tk.END)
    
    route_summary_text.tag_configure(TAG_PROFIT, foreground=PROFIT_COLOR)

    total_route_profit = 0
    for leg in current_planning_state["planned_route_legs"]:
        dist_ly_str = f"{leg.get('distance_ly_to_dest_system', 0.0):.1f}"
        dist_ls_str = f"{leg.get('distance_ls_to_dest_station', 0):,.0f}"
        
        leg_details_text = lang_module.get_string("multihop_summary_leg_with_distances",
            leg_num=leg["hop_num"], source_station=leg["source_station"], source_system=leg["source_system"],
            dest_station=leg["dest_station"], dest_system=leg["dest_system"],
            dist_ly=dist_ly_str, dist_ls=dist_ls_str)
        route_summary_text.insert(tk.END, leg_details_text + "\n")
        
        route_summary_text.insert(tk.END, lang_module.get_string("multihop_summary_buy",
            quantity=leg["quantity"], commodity_name=leg["commodity_name"], buy_price_each=leg["buy_price_each"]) + "\n")
        route_summary_text.insert(tk.END, lang_module.get_string("multihop_summary_sell",
            commodity_name=leg["commodity_name"], sell_price_each=leg["sell_price_each"]) + "\n")
        
        profit_leg_text = lang_module.get_string("multihop_summary_profit_leg", leg_profit=leg["leg_profit"])
        route_summary_text.insert(tk.END, profit_leg_text + "\n\n", TAG_PROFIT)
        
        total_route_profit += leg["leg_profit"]
    
    route_summary_text.insert(tk.END, "------------------------------------\n")
    total_profit_text = lang_module.get_string("multihop_summary_total_profit", total_route_profit=total_route_profit)
    route_summary_text.insert(tk.END, total_profit_text + "\n", TAG_PROFIT)
    current_planning_state["last_saved_total_profit"] = total_route_profit # Mettre à jour pour la sauvegarde
    
    route_summary_text.config(state=tk.DISABLED)


def on_restart_or_clear_pressed(clear_summary_only=False, called_from_start=False): # Ajout de called_from_start
    global suggestions_tree, route_summary_text, current_planning_state, num_hops_var, max_ly_var, select_hop_btn
    
    if suggestions_tree and suggestions_tree.winfo_exists():
        for item in suggestions_tree.get_children(): suggestions_tree.delete(item)
    if route_summary_text and route_summary_text.winfo_exists():
        route_summary_text.config(state=tk.NORMAL)
        route_summary_text.delete("1.0", tk.END)
        route_summary_text.config(state=tk.DISABLED)

    if not clear_summary_only:
        current_planning_state.update({
            "planned_route_legs": [], "current_hop_number": 0, "last_selected_trade_data": None,
            "is_planning_active": False, "last_saved_total_profit": 0
        })
        # Ne pas effacer les champs num_hops et max_ly si appelé depuis on_start_planning_pressed
        # if not called_from_start:
        # if num_hops_var: num_hops_var.set("3") 
        # if max_ly_var: max_ly_var.set("60.0")
        _configure_ui_for_state("initial_config")
        
        # Supprimer le fichier de cache uniquement si ce n'est pas un clear appelé par start
        if not called_from_start and os.path.exists(MULTI_HOP_ROUTE_CACHE_FILE):
            try:
                os.remove(MULTI_HOP_ROUTE_CACHE_FILE)
                logger.info(f"Cleared and removed cache file: {MULTI_HOP_ROUTE_CACHE_FILE}")
                _update_status_local(lang_module.get_string("multihop_status_cleared_saved_route"))
            except OSError as e:
                logger.error(f"Error removing cache file {MULTI_HOP_ROUTE_CACHE_FILE}: {e}")
        elif not called_from_start: # Si pas appelé par start et pas de fichier, juste statut idle
             _update_status_local(lang_module.get_string("multihop_status_idle"))

        logger.info("Multi-hop planning reset (full).")
    else: # clear_summary_only == True
        logger.info("Multi-hop summary cleared (display only).")
        # Ne pas changer l'état de l'UI si on efface juste le récapitulatif pour en afficher un nouveau (ex: après chargement)
    
    if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)


def create_multihop_trade_tab(notebook_widget, shared_elements_dict):
    # ... (Début de la fonction et assignations des shared_elements comme avant) ...
    global multihop_tab_page_frame_ref, s_shared_root_multihop
    global config_frame, num_hops_var, max_ly_var, start_planning_btn, num_hops_entry, max_ly_entry
    global planning_frame, current_hop_details_lbl_var, suggestions_tree, select_hop_btn, restart_planning_btn_planning
    global summary_frame, route_summary_text, clear_summary_btn
    global multihop_status_lbl
    global s_update_status_func_global, s_set_buttons_state_func_global, s_cancel_multihop_event, s_sort_treeview_column_func
    global s_get_current_system_func_from_main, s_get_current_station_func_from_main, s_get_current_ship_type_func_from_main
    global s_get_current_cargo_capacity_func_from_main, s_get_current_pad_size_func_from_main

    s_shared_root_multihop = shared_elements_dict.get("root")
    s_update_status_func_global = shared_elements_dict.get("update_status_func")
    s_set_buttons_state_func_global = shared_elements_dict.get("set_buttons_state_func")
    s_cancel_multihop_event = shared_elements_dict.get("cancel_multihop_event")
    s_sort_treeview_column_func = shared_elements_dict.get("sort_treeview_column_func")
    s_get_current_system_func_from_main = shared_elements_dict.get("get_current_system_func")
    s_get_current_station_func_from_main = shared_elements_dict.get("get_current_station_func")
    s_get_current_ship_type_func_from_main = shared_elements_dict.get("get_current_ship_type_func")
    s_get_current_cargo_capacity_func_from_main = shared_elements_dict.get("get_current_cargo_capacity_func")
    s_get_current_pad_size_func_from_main = shared_elements_dict.get("get_current_pad_size_func")

    multihop_tab_page_frame_ref = ttk.Frame(notebook_widget, style='TFrame')
    notebook_widget.add(multihop_tab_page_frame_ref, text=lang_module.get_string("multihop_trade_tab_title"))

    tab_content_area = ttk.Frame(multihop_tab_page_frame_ref)
    tab_content_area.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
    tab_content_area.columnconfigure(0, weight=1)

    config_frame = ttk.LabelFrame(tab_content_area, text=lang_module.get_string("multihop_config_frame_title"), style='TLabelframe', padding=10)
    num_hops_var = tk.StringVar(value="3")
    max_ly_var = tk.StringVar(value="60.0")
    ttk.Label(config_frame, text=lang_module.get_string("multihop_num_hops_label")).grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
    num_hops_entry = ttk.Spinbox(config_frame, from_=1, to=10, textvariable=num_hops_var, width=5)
    num_hops_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
    ttk.Label(config_frame, text=lang_module.get_string("multihop_max_ly_per_hop_label")).grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
    max_ly_entry = ttk.Entry(config_frame, textvariable=max_ly_var, width=7)
    max_ly_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
    start_planning_btn = ttk.Button(config_frame, text=lang_module.get_string("multihop_start_planning_button"), command=on_start_planning_pressed)
    start_planning_btn.grid(row=0, column=2, rowspan=2, sticky=tk.NSEW, padx=10, pady=2)

    planning_frame = ttk.LabelFrame(tab_content_area, text=lang_module.get_string("multihop_current_hop_frame_title"), style='TLabelframe', padding=10)
    planning_frame.columnconfigure(0, weight=1); planning_frame.rowconfigure(1, weight=1)
    current_hop_details_lbl_var = tk.StringVar()
    ttk.Label(planning_frame, textvariable=current_hop_details_lbl_var, style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(0,5))
    
    suggestions_cols_keys = ["multihop_col_dest_station", "multihop_col_dest_system", "multihop_col_commodity_to_buy",
                             "multihop_col_buy_price_at_source", "multihop_col_sell_price_at_dest", "multihop_col_profit_per_unit",
                             "multihop_col_est_total_profit", "multihop_col_distance_ly", "multihop_col_landing_pad", "multihop_col_dist_to_star"]
    suggestions_tree = ttk.Treeview(planning_frame, columns=suggestions_cols_keys, show="headings", selectmode="browse", height=5)
    for col_key in suggestions_cols_keys:
        tree_col_text = lang_module.get_string(col_key)
        anchor_val = tk.W if any(k in col_key for k in ["station", "system", "commodity"]) else tk.E
        width_val = 160 if "station" in col_key else (120 if "system" in col_key else (180 if "commodity" in col_key else 100))
        stretch_val = tk.YES if any(k in col_key for k in ["station", "commodity"]) else tk.NO
        data_type = "str_ci"
        if any(s in col_key for s in ["price", "profit", "dist_to_star", "distance_ly"]): data_type = "float"
        elif col_key == "multihop_col_landing_pad": data_type = "str_ci"
        
        if s_sort_treeview_column_func:
            suggestions_tree.heading(col_key, text=tree_col_text, anchor=anchor_val, command=lambda c=col_key, t=suggestions_tree, dt=data_type: s_sort_treeview_column_func(t, c, dt))
        else:
            suggestions_tree.heading(col_key, text=tree_col_text, anchor=anchor_val)
        suggestions_tree.column(col_key, width=width_val, minwidth=70, anchor=anchor_val, stretch=stretch_val)

    suggestions_tree.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
    suggestions_tree.bind("<<TreeviewSelect>>", on_suggestion_selected)
    
    select_hop_btn = ttk.Button(planning_frame, text=lang_module.get_string("multihop_select_and_continue_button", remaining_hops=0), command=on_select_hop_pressed, state=tk.DISABLED)
    select_hop_btn.grid(row=2, column=0, sticky=tk.EW, padx=5, pady=5)
    restart_planning_btn_planning = ttk.Button(planning_frame, text=lang_module.get_string("multihop_restart_planning_button"), command=lambda: on_restart_or_clear_pressed(clear_summary_only=False))
    restart_planning_btn_planning.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)

    summary_frame = ttk.LabelFrame(tab_content_area, text=lang_module.get_string("multihop_summary_frame_title"), style='TLabelframe', padding=10)
    summary_frame.columnconfigure(0, weight=1); summary_frame.rowconfigure(0, weight=1)
    route_summary_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, height=10, state=tk.DISABLED,
                                                   bg=ED_MEDIUM_GREY, fg=ED_WHITE_TEXT, insertbackground=ED_WHITE_TEXT,
                                                   font=(BASE_FONT_FAMILY, BASE_FONT_SIZE))
    route_summary_text.tag_configure(TAG_PROFIT, foreground=PROFIT_COLOR)
    route_summary_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    
    # Changement de la commande pour le bouton "Effacer Récapitulatif"
    clear_summary_btn = ttk.Button(summary_frame, text=lang_module.get_string("multihop_clear_summary_button"), command=lambda: on_restart_or_clear_pressed(clear_summary_only=False))
    clear_summary_btn.grid(row=1, column=0, sticky=tk.EW, padx=5, pady=5)

    multihop_status_lbl = ttk.Label(tab_content_area, text=lang_module.get_string("multihop_status_idle"), style="Status.TLabel")
    multihop_status_lbl.grid(row=3, column=0, sticky="ew", padx=5, pady=(10,0))

    # Charger un itinéraire sauvegardé s'il existe
    if _load_saved_route():
        _display_route_summary()
        _configure_ui_for_state("summary")
        _update_status_local(lang_module.get_string("multihop_status_loaded_saved_route"))
    else:
        _configure_ui_for_state("initial_config")
        _update_status_local(lang_module.get_string("multihop_status_no_saved_route"))

    tab_content_area.rowconfigure(0, weight=0) # config_frame
    tab_content_area.rowconfigure(1, weight=1) # planning_frame
    tab_content_area.rowconfigure(2, weight=1) # summary_frame
    tab_content_area.rowconfigure(3, weight=0) # multihop_status_lbl

    logger.info("Multi-Hop Trade Planner tab UI elements created.")
    return multihop_tab_page_frame_ref


def update_multihop_trade_tab_texts():
    # ... (logique de mise à jour des textes comme avant, s'assurer que les widgets existent) ...
    # (Assurez-vous que les labels dans config_frame sont aussi mis à jour si nécessaire)
    global config_frame, num_hops_entry, max_ly_entry, start_planning_btn, restart_planning_btn_planning
    global planning_frame, current_hop_details_lbl_var, suggestions_tree, select_hop_btn
    global summary_frame, clear_summary_btn 
    global multihop_status_lbl, current_planning_state, s_shared_root_multihop

    if not (s_shared_root_multihop and s_shared_root_multihop.winfo_exists()): return
    if not (config_frame and config_frame.winfo_exists()): return 

    if config_frame: config_frame.config(text=lang_module.get_string("multihop_config_frame_title"))
    # Les labels des champs d'entrée sont typiquement statiques après création.
    # Si vous les stockez (ex: num_hops_text_label = ttk.Label(...)), vous pouvez les mettre à jour ici.
    
    if start_planning_btn: start_planning_btn.config(text=lang_module.get_string("multihop_start_planning_button"))
    
    if planning_frame: planning_frame.config(text=lang_module.get_string("multihop_current_hop_frame_title"))
    if current_hop_details_lbl_var: 
        if current_planning_state["is_planning_active"] and current_planning_state["current_hop_number"] > 0 :
             current_hop_details_lbl_var.set(lang_module.get_string("multihop_hop_details_label",
                current_hop_num=current_planning_state["current_hop_number"], total_hops_num=current_planning_state["total_hops"],
                current_station_name=current_planning_state["current_source_station"] or "?", 
                current_system_name=current_planning_state["current_source_system"] or "?"))
             
    if suggestions_tree:
        for col_key in suggestions_tree["columns"]:
            tree_col_text_key = col_key
            translated_header = lang_module.get_string(tree_col_text_key)
            if translated_header != f"<{tree_col_text_key}>":
                suggestions_tree.heading(col_key, text=translated_header)

    if select_hop_btn:
        remaining_hops = current_planning_state["total_hops"] - current_planning_state["current_hop_number"]
        if current_planning_state["is_planning_active"] and current_planning_state["current_hop_number"] > 0: # S'assurer qu'une planification est active
            if remaining_hops > 0:
                select_hop_btn.config(text=lang_module.get_string("multihop_select_and_continue_button", remaining_hops=remaining_hops))
            elif remaining_hops == 0: # Dernier saut
                 select_hop_btn.config(text=lang_module.get_string("multihop_select_and_finish_button"))
            # else:  Le bouton pourrait garder son dernier texte ou être mis à un état par défaut si remaining_hops < 0 (improbable)

    if restart_planning_btn_planning: restart_planning_btn_planning.config(text=lang_module.get_string("multihop_restart_planning_button"))
    
    if summary_frame: summary_frame.config(text=lang_module.get_string("multihop_summary_frame_title"))
    if clear_summary_btn: clear_summary_btn.config(text=lang_module.get_string("multihop_clear_summary_button"))

    if multihop_status_lbl:
        current_text = multihop_status_lbl.cget("text")
        stable_keys_map = { # Map de la clé de langue à son texte actuel (pour éviter de retraduire les messages dynamiques)
            "multihop_status_idle": lang_module.get_string("multihop_status_idle"),
            "multihop_status_loaded_saved_route": lang_module.get_string("multihop_status_loaded_saved_route"),
            "multihop_status_no_saved_route": lang_module.get_string("multihop_status_no_saved_route"),
            "multihop_status_cleared_saved_route": lang_module.get_string("multihop_status_cleared_saved_route")
        }
        # Vérifier si le texte actuel correspond à l'un des messages stables dans *n'importe quelle* langue précédemment affichée
        found_stable_message = False
        for key, translated_text_in_current_lang in stable_keys_map.items():
            # Vérifier si le texte actuel correspond au texte par défaut ou au texte actuel de la clé
            if current_text == lang_module.TRANSLATIONS[lang_module.DEFAULT_LANG].get(key) or \
               (lang_module.CURRENT_LANG != lang_module.DEFAULT_LANG and current_text == lang_module.TRANSLATIONS[lang_module.CURRENT_LANG].get(key)):
                multihop_status_lbl.config(text=translated_text_in_current_lang)
                found_stable_message = True
                break
        if not found_stable_message and "{timestamp}" not in current_text and "..." not in current_text: # Si ce n'est pas un message dynamique ou en cours
             pass # Ne pas écraser les messages d'erreur ou de statut spécifiques


    if current_planning_state["planned_route_legs"] and not current_planning_state["is_planning_active"]:
        _display_route_summary() # Pour mettre à jour le récapitulatif avec les nouvelles traductions

    logger.debug("Multi-Hop Trade tab texts updated for language change.")


def set_multihop_trade_buttons_state(operation_running=False, cancellable=False, source_tab_name=None):
    # ... (logique existante, s'assurer que num_hops_entry et max_ly_entry sont gérés)
    global start_planning_btn, restart_planning_btn_planning, select_hop_btn, clear_summary_btn, num_hops_entry, max_ly_entry
    
    # Gérer l'état des entrées de configuration basé sur si une planification est active (pas seulement une opération globale)
    config_inputs_can_be_active = not (operation_running or current_planning_state["is_planning_active"])
    if num_hops_entry and num_hops_entry.winfo_exists(): num_hops_entry.config(state=tk.NORMAL if config_inputs_can_be_active else tk.DISABLED)
    if max_ly_entry and max_ly_entry.winfo_exists(): max_ly_entry.config(state=tk.NORMAL if config_inputs_can_be_active else tk.DISABLED)

    if operation_running: # Une opération globale est en cours
        if start_planning_btn and start_planning_btn.winfo_exists(): start_planning_btn.config(state=tk.DISABLED)
        if restart_planning_btn_planning and restart_planning_btn_planning.winfo_exists(): restart_planning_btn_planning.config(state=tk.DISABLED)
        if select_hop_btn and select_hop_btn.winfo_exists(): select_hop_btn.config(state=tk.DISABLED)
        if clear_summary_btn and clear_summary_btn.winfo_exists(): clear_summary_btn.config(state=tk.DISABLED)
    else: # Aucune opération globale, l'état dépend de la phase interne de cet onglet
        current_ui_state = "initial_config" # Par défaut
        if current_planning_state["is_planning_active"]:
            current_ui_state = "planning_hop"
        elif current_planning_state["planned_route_legs"]:
            current_ui_state = "summary"
        
        # L'appel à _configure_ui_for_state gère l'affichage/masquage et certains états de boutons
        # Ici, on s'assure juste que l'état des boutons est cohérent APRÈS la fin d'une opération globale.
        if start_planning_btn and start_planning_btn.winfo_exists(): 
            start_planning_btn.config(state=tk.NORMAL if current_ui_state != "planning_hop" else tk.DISABLED)
        
        if restart_planning_btn_planning and restart_planning_btn_planning.winfo_exists(): 
            restart_planning_btn_planning.config(state=tk.NORMAL if current_ui_state == "planning_hop" else tk.DISABLED)
        
        if clear_summary_btn and clear_summary_btn.winfo_exists(): 
            clear_summary_btn.config(state=tk.NORMAL if current_ui_state == "summary" else tk.DISABLED) # Actif seulement en mode summary

        # L'état de select_hop_btn dépend aussi de la sélection dans le treeview
        if select_hop_btn and select_hop_btn.winfo_exists():
            if current_ui_state == "planning_hop" and current_planning_state.get("last_selected_trade_data"):
                select_hop_btn.config(state=tk.NORMAL)
            else:
                select_hop_btn.config(state=tk.DISABLED)
                
    logger.debug(f"Multi-Hop Trade tab buttons state updated: op_running={operation_running}, source_tab={source_tab_name}, internal_planning_active={current_planning_state['is_planning_active']}")