#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import asyncio

from constants import (
    OUTFITTING_CATEGORIES_DISPLAY,
    MODULE_SIZES, MODULE_CLASSES_DISPLAY_ORDER, MODULE_MOUNTS_DISPLAY,
    DEFAULT_OUTFITTING_RADIUS_LY
)
import language as lang_module
import gui_main # Accès à sort_treeview_column_general et _set_buttons_state
import module_catalog_data
import outfitting_db_manager
import outfitting_logic

logger = logging.getLogger(__name__)

# ---- Widgets ----
outfitting_tab_frame = None; outfitting_notebook = None
outfitting_search_frame = None; outfitting_results_frame = None
category_var = None; module_var = None
category_combobox_widget = None; module_combobox_widget = None
size_filter_var = None; class_filter_var = None; mount_filter_var = None
size_filter_label = None; size_filter_combobox = None
class_filter_label = None; class_filter_combobox = None
mount_filter_label = None; mount_filter_combobox = None
search_list_lb = None; add_to_search_list_btn = None; remove_from_search_list_btn = None
search_outfitting_btn = None; update_outfitting_db_btn = None
outfitting_search_status_lbl = None; outfitting_results_tree = None; outfitting_results_status_lbl = None
current_search_list_modules = {} # {display_name_ui: edsm_id}

# Références partagées
s_outfitting_radius_var = None; s_radius_var = None; s_include_planetary_var = None
s_include_fleet_carriers_var = None; s_station_dist_var = None; s_update_status_func_global = None
s_set_buttons_state_global_func = None; s_get_current_system_func = None
s_cancel_outfitting_event = None; s_root = None; s_outfitting_db_status_lbl_widget_ref = None
filters_row_frame_ref = None # Référence au frame des filtres Taille/Classe/Montage

# --- Fonctions ---
def clear_dependent_comboboxes(clear_size=True, clear_class=True, clear_mount=True, clear_module=True):
    global size_filter_combobox, class_filter_combobox, mount_filter_combobox, module_combobox_widget
    global size_filter_var, class_filter_var, mount_filter_var, module_var
    any_text = lang_module.get_string("filter_any")
    
    if clear_size and size_filter_combobox: 
        size_filter_combobox['values'] = [any_text]
        size_filter_var.set(any_text)
    if clear_class and class_filter_combobox: 
        class_filter_combobox['values'] = [any_text]
        class_filter_var.set(any_text)
    if clear_mount and mount_filter_combobox: 
        mount_filter_combobox['values'] = [any_text]
        mount_filter_var.set(any_text)
    if clear_module and module_combobox_widget: 
        module_combobox_widget['values'] = []
        module_var.set('')

def on_category_selected(event=None):
    global category_combobox_widget, size_filter_combobox, size_filter_var 
    global mount_filter_combobox, mount_filter_var, mount_filter_label, filters_row_frame_ref # filters_row_frame_ref est le parent
    
    selected_category_display = category_combobox_widget.get()
    clear_dependent_comboboxes() 
    if not selected_category_display: 
        if mount_filter_label and mount_filter_label.winfo_ismapped(): mount_filter_label.grid_remove()
        if mount_filter_combobox and mount_filter_combobox.winfo_ismapped(): mount_filter_combobox.grid_remove()
        return

    any_text = lang_module.get_string("filter_any")
    
    available_sizes_raw = module_catalog_data.get_distinct_sizes_for_category(selected_category_display)
    available_sizes_for_ui = [any_text] + [str(s) for s in available_sizes_raw if s is not None]
    if size_filter_combobox:
        size_filter_combobox['values'] = available_sizes_for_ui
        size_filter_var.set(any_text)

    category_key = module_catalog_data.get_category_key_from_display_name(selected_category_display)
    if category_key == "HARDPOINT":
        # Assurer que les widgets sont bien dans le filters_row_frame_ref avant de les afficher/cacher avec grid
        if mount_filter_label and filters_row_frame_ref: mount_filter_label.grid(row=0, column=4, padx=(10,2), pady=2, sticky="w", in_=filters_row_frame_ref)
        if mount_filter_combobox and filters_row_frame_ref: mount_filter_combobox.grid(row=0, column=5, padx=(0,5), pady=2, sticky="ew", in_=filters_row_frame_ref)
        
        available_mounts_raw = module_catalog_data.get_distinct_mounts_for_category(selected_category_display)
        available_mounts_for_ui = [any_text] + [lang_module.get_string(f"mount_{m.lower().replace(' ', '')}") for m in available_mounts_raw]
        if mount_filter_combobox : mount_filter_combobox['values'] = available_mounts_for_ui
        if mount_filter_var : mount_filter_var.set(any_text)
    else:
        if mount_filter_label and mount_filter_label.winfo_ismapped(): mount_filter_label.grid_remove()
        if mount_filter_combobox and mount_filter_combobox.winfo_ismapped(): mount_filter_combobox.grid_remove()
        if mount_filter_var : mount_filter_var.set(any_text) 
    on_filters_changed(None) 

def on_filters_changed(event=None): 
    global category_combobox_widget, size_filter_var, class_filter_var, mount_filter_var
    global class_filter_combobox, module_combobox_widget, module_var

    selected_category_display = category_combobox_widget.get()
    if not selected_category_display:
        if class_filter_combobox: class_filter_combobox['values'] = [lang_module.get_string("filter_any")]; class_filter_var.set(lang_module.get_string("filter_any"))
        if module_combobox_widget: module_combobox_widget['values'] = []; module_var.set('')
        return

    any_text = lang_module.get_string("filter_any")
    size_val_str = size_filter_var.get()
    size_filter = int(size_val_str) if size_val_str != any_text and size_val_str.isdigit() else None
    
    available_classes_raw = module_catalog_data.get_distinct_classes_for_category(selected_category_display, size_filter=size_filter)
    available_classes_for_ui = [any_text] + available_classes_raw
    if class_filter_combobox:
        current_class_selection = class_filter_var.get()
        class_filter_combobox['values'] = available_classes_for_ui
        if current_class_selection in available_classes_for_ui: class_filter_var.set(current_class_selection)
        elif available_classes_for_ui: class_filter_var.set(any_text)
        else: class_filter_var.set('')

    class_val_str = class_filter_var.get()
    class_filter = class_val_str if class_val_str != any_text else None
    
    mount_filter = None
    category_key = module_catalog_data.get_category_key_from_display_name(selected_category_display)
    if category_key == "HARDPOINT" and mount_filter_combobox and mount_filter_combobox.winfo_ismapped():
        mount_val_str_ui = mount_filter_var.get()
        if mount_val_str_ui != any_text:
            for mount_const_key in MODULE_MOUNTS_DISPLAY: 
                if lang_module.get_string(f"mount_{mount_const_key.lower().replace(' ', '')}") == mount_val_str_ui:
                    mount_filter = mount_const_key; break
    
    modules_display_names = module_catalog_data.get_ui_modules_for_category(
        selected_category_display, size_filter=size_filter, class_filter=class_filter, mount_filter=mount_filter
    )
    if module_combobox_widget:
        current_module_selection = module_var.get()
        module_combobox_widget['values'] = modules_display_names
        if current_module_selection in modules_display_names: module_var.set(current_module_selection)
        elif modules_display_names: module_var.set(modules_display_names[0])
        else: module_var.set('')

def populate_initial_filters():
    global category_combobox_widget, size_filter_var, class_filter_var, mount_filter_var
    any_text = lang_module.get_string("filter_any")
    if size_filter_var: size_filter_var.set(any_text)
    if class_filter_var: class_filter_var.set(any_text)
    if mount_filter_var: mount_filter_var.set(any_text)
    loaded_data = outfitting_db_manager.load_outfitting_data_from_file()
    if loaded_data: module_catalog_data.build_dynamic_catalogs_from_db(loaded_data)
    else:
        module_catalog_data.DYNAMIC_MODULE_DETAILS_CATALOG.clear()
        module_catalog_data.UI_MODULE_SELECTION_CATALOG = {cat_key: {} for cat_key in OUTFITTING_CATEGORIES_DISPLAY.keys()}
        logger.warning("populate_initial_filters: Aucune donnée d'équipement locale.")
    if category_combobox_widget:
        categories = module_catalog_data.get_ui_categories()
        category_combobox_widget['values'] = categories
        if categories: category_combobox_widget.set(categories[0]); on_category_selected(None) 
        else: category_combobox_widget.set(''); clear_dependent_comboboxes()
    else: logger.error("populate_initial_filters: category_combobox_widget non initialisé.")

def on_add_module_to_list_pressed():
    global category_var, module_var, search_list_lb, current_search_list_modules
    selected_category_display = category_var.get(); selected_module_display = module_var.get()
    if not selected_category_display or not selected_module_display:
        messagebox.showwarning(lang_module.get_string("error_dialog_title_warning"), lang_module.get_string("error_outfitting_no_module_selected_for_list"), parent=s_root)
        return
    if selected_module_display in current_search_list_modules:
        messagebox.showinfo(lang_module.get_string("Info"), lang_module.get_string("error_outfitting_module_already_in_list", module=selected_module_display), parent=s_root)
        return
    module_id = module_catalog_data.get_module_id_from_ui_selection(selected_category_display, selected_module_display)
    if module_id:
        current_search_list_modules[selected_module_display] = module_id
        search_list_lb.insert(tk.END, selected_module_display)
        logger.info(f"Module '{selected_module_display}' (ID: {module_id}) ajouté.")
    else: messagebox.showerror(lang_module.get_string("error_dialog_title"), lang_module.get_string("error_outfitting_module_id_not_found"), parent=s_root)

def on_remove_module_from_list_pressed():
    global search_list_lb, current_search_list_modules
    selected_indices = search_list_lb.curselection()
    if not selected_indices:
        messagebox.showwarning(lang_module.get_string("error_dialog_title_warning"), lang_module.get_string("error_outfitting_no_module_selected_to_remove"), parent=s_root)
        return
    for index in reversed(selected_indices):
        module_display_name_to_remove = search_list_lb.get(index)
        search_list_lb.delete(index)
        if module_display_name_to_remove in current_search_list_modules:
            del current_search_list_modules[module_display_name_to_remove]
            logger.info(f"Module '{module_display_name_to_remove}' retiré.")

def on_update_outfitting_db_pressed():
    global s_outfitting_radius_var, s_radius_var, s_cancel_outfitting_event, s_outfitting_db_status_lbl_widget_ref
    global s_update_status_func_global, outfitting_search_status_lbl, s_get_current_system_func

    current_system = s_get_current_system_func()
    if current_system == "?" or "Error" in current_system:
        msg = lang_module.get_string("error_outfitting_db_update_no_system")
        logger.warning(msg)
        if s_update_status_func_global: s_update_status_func_global(msg, target_status_label_widget=outfitting_search_status_lbl)
        return

    s_cancel_outfitting_event.clear()
    if gui_main._set_buttons_state: gui_main._set_buttons_state(operation_running=True, cancellable=True)
    set_outfitting_buttons_state(operation_running=True, cancellable=True, source_tab="outfitting_search")
    if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_db_validating"), 0, target_status_label_widget=outfitting_search_status_lbl)

    try:
        radius_to_use_str = (s_outfitting_radius_var.get() if s_outfitting_radius_var and s_outfitting_radius_var.get() 
                             else (s_radius_var.get() if s_radius_var else str(DEFAULT_OUTFITTING_RADIUS_LY)))
        radius_to_use = float(radius_to_use_str)
        if radius_to_use <= 0: raise ValueError(lang_module.get_string("error_radius_positive"))
        if radius_to_use > 100:
            logger.warning(f"Rayon EDSM pour équipement ({radius_to_use}) > 100 AL. Utilisation de 100 AL.")
            radius_to_use = 100.0
            if s_outfitting_radius_var: s_outfitting_radius_var.set(str(radius_to_use))
            elif s_radius_var: s_radius_var.set(str(radius_to_use))

        def _progress_cb(message, percentage):
            if not s_cancel_outfitting_event.is_set() and s_update_status_func_global:
                s_update_status_func_global(message, percentage, target_status_label_widget=outfitting_search_status_lbl)

        async def _async_task():
            if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_db_updating", system=current_system), 0, target_status_label_widget=outfitting_search_status_lbl)
            db_data = None
            try:
                db_data = await outfitting_db_manager.download_regional_outfitting_data(current_system, int(radius_to_use), s_cancel_outfitting_event, _progress_cb)
                if s_cancel_outfitting_event.is_set(): raise outfitting_db_manager.EdsOperationCancelledError("Cancel after signal")
                final_msg = lang_module.get_string("status_outfitting_db_update_finished")
                if not db_data or not db_data.get("systems_with_outfitting"):
                    final_msg += f" ({lang_module.get_string('status_outfitting_db_no_data_found')})"
                if s_update_status_func_global: s_update_status_func_global(final_msg, 100, target_status_label_widget=outfitting_search_status_lbl)
                if s_outfitting_db_status_lbl_widget_ref:
                    s_outfitting_db_status_lbl_widget_ref.config(text=outfitting_db_manager.get_outfitting_db_update_time_str())
                populate_initial_filters() # Crucial
                logger.info("Catalogue de modules et comboboxes mis à jour après la MàJ BD.")
            except outfitting_db_manager.EdsOperationCancelledError:
                logger.info("MàJ BD Équipement annulée.")
                if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_db_cancelled"), -1, target_status_label_widget=outfitting_search_status_lbl)
            except Exception as e_async:
                logger.exception("Erreur dans _async_task pour MàJ BD Équipement:")
                if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_db_error", error=e_async), -1, target_status_label_widget=outfitting_search_status_lbl)
        
        def _run_in_thread():
            loop = None
            try: 
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(_async_task())
            except Exception as e_thread: 
                logger.exception("Erreur thread MàJ BD Équipement:"); msg_err = lang_module.get_string("status_outfitting_db_thread_error", error=e_thread)
                if not s_cancel_outfitting_event.is_set() and s_update_status_func_global:
                     s_update_status_func_global(msg_err, -1, target_status_label_widget=outfitting_search_status_lbl)
            finally:
                if loop and not loop.is_closed(): loop.close()
                if s_root and s_root.winfo_exists():
                    s_root.after(0, gui_main._set_buttons_state, False, False)
                    s_root.after(0, set_outfitting_buttons_state, False, False, "outfitting_search")
        threading.Thread(target=_run_in_thread, daemon=True).start()

    except ValueError as ve:
        msg_val_err = lang_module.get_string("settings_error_outfitting_db_update", error=ve); logger.error(msg_val_err)
        if s_update_status_func_global: s_update_status_func_global(msg_val_err, -1, target_status_label_widget=outfitting_search_status_lbl)
        set_outfitting_buttons_state(False, False, "outfitting_search"); gui_main._set_buttons_state(False,False)
    except Exception as e_main_thread:
        logger.exception("Erreur inattendue avant thread MàJ BD Équipement:")
        if s_update_status_func_global: s_update_status_func_global(f"Erreur init MàJ: {e_main_thread}", -1, target_status_label_widget=outfitting_search_status_lbl)
        set_outfitting_buttons_state(False, False, "outfitting_search"); gui_main._set_buttons_state(False,False)

def on_find_outfitting_pressed():
    global current_search_list_modules, outfitting_results_tree, outfitting_results_status_lbl, outfitting_notebook
    global s_include_planetary_var, s_include_fleet_carriers_var, s_station_dist_var, s_radius_var, s_outfitting_radius_var
    global s_update_status_func_global, s_get_current_system_func

    module_ids_to_search = list(current_search_list_modules.values())
    if not module_ids_to_search:
        messagebox.showwarning(lang_module.get_string("error_dialog_title_warning"), lang_module.get_string("error_outfitting_no_modules_in_search_list"), parent=s_root)
        return
    if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_searching"), indeterminate=True, target_status_label_widget=outfitting_results_status_lbl)
    if gui_main._set_buttons_state: gui_main._set_buttons_state(operation_running=True, cancellable=False)
    set_outfitting_buttons_state(operation_running=True, cancellable=False, source_tab="outfitting_search")
    if outfitting_results_tree:
        for item in outfitting_results_tree.get_children(): outfitting_results_tree.delete(item)
    try:
        local_outfitting_db = outfitting_db_manager.load_outfitting_data_from_file()
        if not local_outfitting_db or "systems_with_outfitting" not in local_outfitting_db:
            if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("error_outfitting_db_not_loaded"), -1, target_status_label_widget=outfitting_results_status_lbl)
            set_outfitting_buttons_state(False, False, "outfitting_search"); gui_main._set_buttons_state(False, False); return
        current_system = s_get_current_system_func(); current_sys_coords = None
        if current_system and current_system != "?":
            if "systems_with_outfitting" in local_outfitting_db and current_system in local_outfitting_db["systems_with_outfitting"]:
                current_sys_coords = local_outfitting_db["systems_with_outfitting"][current_system].get("coords")
            elif local_outfitting_db.get("sourceSystem") == current_system and local_outfitting_db.get("systems_with_outfitting",{}).get(current_system,{}).get("coords"):
                 current_sys_coords = local_outfitting_db["systems_with_outfitting"][current_system]["coords"]
        radius_str = s_outfitting_radius_var.get() if s_outfitting_radius_var and s_outfitting_radius_var.get() else s_radius_var.get()
        dist_ly_filter = float(radius_str) if radius_str else None
        dist_ls_filter_str = s_station_dist_var.get()
        dist_ls_filter = float(dist_ls_filter_str) if dist_ls_filter_str else None
        
        found_stations = outfitting_logic.find_stations_with_modules(
            requested_module_ids=module_ids_to_search, all_outfitting_data=local_outfitting_db,
            current_player_system_coords=current_sys_coords, max_distance_ly_filter=dist_ly_filter,
            include_planetary=s_include_planetary_var.get(), include_fleet_carriers=s_include_fleet_carriers_var.get(),
            max_station_dist_ls=dist_ls_filter
        )
        if outfitting_notebook: outfitting_notebook.select(outfitting_results_frame)
        if found_stations:
            for station_info in found_stations:
                dist_ly_str = f"{station_info['distanceLy']:.1f}" if station_info.get('distanceLy') is not None and station_info['distanceLy'] != float('inf') else "?"
                dist_ls_str = f"{station_info['distanceToArrival']:.0f}" if station_info.get('distanceToArrival') is not None else "?"
                modules_matched_str = ", ".join(sorted(station_info.get("modulesMatched", [])))
                pad_size_str = station_info.get("deducedPadSize", "?")
                outfitting_results_tree.insert("", tk.END, values=(
                    station_info.get("stationName", "N/A"), station_info.get("systemName", "N/A"),
                    dist_ly_str, pad_size_str, dist_ls_str, station_info.get("stationType", "N/A"),
                    modules_matched_str
                ))
            if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_found_stations_multimodule"), -1, target_status_label_widget=outfitting_results_status_lbl)
        else:
            if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("status_outfitting_no_stations_found_multimodule"), -1, target_status_label_widget=outfitting_results_status_lbl)
    except Exception as e:
        logger.exception("Erreur lors de la recherche d'équipement (multi-modules):")
        if s_update_status_func_global: s_update_status_func_global(lang_module.get_string("error_outfitting_find_generic", error=e), -1, target_status_label_widget=outfitting_results_status_lbl)
    finally:
        set_outfitting_buttons_state(False, False, "outfitting_search"); gui_main._set_buttons_state(False, False)

def set_outfitting_buttons_state(operation_running=False, cancellable=False, source_tab="outfitting_search"):
    global search_outfitting_btn, update_outfitting_db_btn, add_to_search_list_btn, remove_from_search_list_btn
    action_buttons_state = tk.DISABLED if operation_running else tk.NORMAL
    if search_outfitting_btn: search_outfitting_btn.config(state=action_buttons_state)
    if update_outfitting_db_btn: update_outfitting_db_btn.config(state=action_buttons_state)
    if add_to_search_list_btn: add_to_search_list_btn.config(state=action_buttons_state)
    if remove_from_search_list_btn: remove_from_search_list_btn.config(state=action_buttons_state)

def update_outfitting_tab_texts():
    global outfitting_search_frame, outfitting_results_frame, outfitting_notebook
    global search_outfitting_btn, update_outfitting_db_btn, outfitting_results_tree
    global outfitting_search_status_lbl, outfitting_results_status_lbl
    global add_to_search_list_btn, remove_from_search_list_btn
    global shipyard_include_planetary_cb, shipyard_include_fc_cb # Utilise les mêmes widgets Checkbutton que shipyard
    global size_filter_label, class_filter_label, mount_filter_label
    global category_combobox_widget, size_filter_combobox, class_filter_combobox, mount_filter_combobox

    if outfitting_notebook:
        try:
            outfitting_notebook.tab(outfitting_search_frame, text=lang_module.get_string("outfitting_tab_search_title"))
            outfitting_notebook.tab(outfitting_results_frame, text=lang_module.get_string("outfitting_tab_results_title"))
        except tk.TclError: pass

    if outfitting_search_frame:
        try:
            # Mises à jour des labels et boutons comme avant
            if len(outfitting_search_frame.winfo_children()) > 0:
                search_top_controls_frame = outfitting_search_frame.winfo_children()[0]
                if len(search_top_controls_frame.winfo_children()) > 0 :
                    search_top_controls_frame.winfo_children()[0].config(text=lang_module.get_string("outfitting_radius_label"))
            if update_outfitting_db_btn: update_outfitting_db_btn.config(text=lang_module.get_string("outfitting_update_db_button"))
            
            if len(outfitting_search_frame.winfo_children()) > 1:
                module_selection_and_filters_main_frame = outfitting_search_frame.winfo_children()[1]
                if len(module_selection_and_filters_main_frame.winfo_children()) > 0:
                    cat_frame = module_selection_and_filters_main_frame.winfo_children()[0]
                    if len(cat_frame.winfo_children()) > 0:
                        cat_frame.winfo_children()[0].config(text=lang_module.get_string("outfitting_category_label"))
                
                if len(module_selection_and_filters_main_frame.winfo_children()) > 1:
                    filters_r_frame_widget = module_selection_and_filters_main_frame.winfo_children()[1]
                    if size_filter_label: size_filter_label.config(text=lang_module.get_string("outfitting_size_filter_label"))
                    if class_filter_label: class_filter_label.config(text=lang_module.get_string("outfitting_class_filter_label"))
                    if mount_filter_label: mount_filter_label.config(text=lang_module.get_string("outfitting_mount_filter_label"))

                if len(module_selection_and_filters_main_frame.winfo_children()) > 2:
                    module_sel_add_f = module_selection_and_filters_main_frame.winfo_children()[2]
                    if len(module_sel_add_f.winfo_children()) > 0:
                        module_sel_add_f.winfo_children()[0].config(text=lang_module.get_string("outfitting_module_label"))
                    if add_to_search_list_btn: add_to_search_list_btn.config(text=lang_module.get_string("outfitting_add_to_list_btn"))

            if len(outfitting_search_frame.winfo_children()) > 2: # search_list_frame
                search_list_f = outfitting_search_frame.winfo_children()[2] 
                if isinstance(search_list_f, ttk.Labelframe): search_list_f.config(text=lang_module.get_string("outfitting_search_list_label"))
                if len(search_list_f.winfo_children()) > 1 and isinstance(search_list_f.winfo_children()[1], ttk.Button):
                     search_list_f.winfo_children()[1].config(text=lang_module.get_string("outfitting_remove_from_list_btn"))

            if len(outfitting_search_frame.winfo_children()) > 3: # general_filter_frame
                general_filters_f = outfitting_search_frame.winfo_children()[3]
                if shipyard_include_planetary_cb: shipyard_include_planetary_cb.config(text=lang_module.get_string("settings_include_planetary_cb"))
                if shipyard_include_fc_cb: shipyard_include_fc_cb.config(text=lang_module.get_string("settings_include_fc_cb"))
            
            if search_outfitting_btn: search_outfitting_btn.config(text=lang_module.get_string("outfitting_search_button"))

            # Mise à jour des valeurs "Any" et des listes des combobox de filtre
            any_text = lang_module.get_string("filter_any")
            if category_combobox_widget: # Recalculer les catégories
                current_cat_val_ui = category_var.get(); ui_cats = module_catalog_data.get_ui_categories()
                category_combobox_widget['values'] = ui_cats
                if current_cat_val_ui in ui_cats: category_var.set(current_cat_val_ui)
                elif ui_cats: category_var.set(ui_cats[0])
                else: category_var.set('')
                on_category_selected() # Redéclenche la cascade pour s'assurer que tout est à jour

        except IndexError as e: logger.error(f"Erreur d'index maj textes onglet recherche equip: {e}", exc_info=True)
        except Exception as e_lang: logger.error(f"Erreur générale maj textes onglet recherche equip: {e_lang}", exc_info=True)

    if outfitting_results_tree:
        cols_keys = ["tree_col_outfitting_station", "tree_col_outfitting_system", "tree_col_outfitting_dist_ly", "tree_col_outfitting_pad_size", "tree_col_outfitting_dist_ls", "tree_col_outfitting_type", "tree_col_outfitting_modules_matched_ui"]
        for key in cols_keys:
            new_text = lang_module.get_string(key)
            try:
                current_heading = outfitting_results_tree.heading(key); current_text = current_heading.get("text", "")
                sort_indicator = " ▲" if "▲" in current_text else (" ▼" if "▼" in current_text else "")
                outfitting_results_tree.heading(key, text=new_text + sort_indicator)
            except tk.TclError: pass

    if outfitting_search_status_lbl:
        is_default = any(outfitting_search_status_lbl.cget("text") == lang_module.TRANSLATIONS[lc].get("outfitting_search_initial_status") for lc in lang_module.TRANSLATIONS)
        if is_default: outfitting_search_status_lbl.config(text=lang_module.get_string("outfitting_search_initial_status"))
    if outfitting_results_status_lbl:
        is_default_res = any(outfitting_results_status_lbl.cget("text") == lang_module.TRANSLATIONS[lc].get("outfitting_results_initial_status") for lc in lang_module.TRANSLATIONS)
        if is_default_res: outfitting_results_status_lbl.config(text=lang_module.get_string("outfitting_results_initial_status"))


def create_outfitting_tab(notebook_parent, shared_elements_dict):
    global outfitting_tab_frame, outfitting_notebook, outfitting_search_frame, outfitting_results_frame
    global category_var, module_var, category_combobox_widget, module_combobox_widget
    global size_filter_var, class_filter_var, mount_filter_var
    global size_filter_label, size_filter_combobox, class_filter_label, class_filter_combobox, mount_filter_label, mount_filter_combobox
    global search_list_lb, add_to_search_list_btn, remove_from_search_list_btn
    global search_outfitting_btn, update_outfitting_db_btn, outfitting_search_status_lbl
    global outfitting_results_tree, outfitting_results_status_lbl
    global s_outfitting_radius_var, s_radius_var, s_include_planetary_var, s_include_fleet_carriers_var, s_station_dist_var
    global s_update_status_func_global, s_set_buttons_state_global_func, s_get_current_system_func, s_cancel_outfitting_event, s_root
    global s_outfitting_db_status_lbl_widget_ref
    global shipyard_include_planetary_cb, shipyard_include_fc_cb # Sera utilisé pour les checkbuttons de filtre
    global filters_row_frame_ref # Stocker la référence

    s_outfitting_radius_var = shared_elements_dict.get("outfitting_radius_var")
    s_radius_var = shared_elements_dict["radius_var"]
    s_include_planetary_var = shared_elements_dict["include_planetary_var"]
    s_include_fleet_carriers_var = shared_elements_dict["include_fleet_carriers_var"]
    s_station_dist_var = shared_elements_dict["station_dist_var"]
    s_update_status_func_global = shared_elements_dict["update_status_func"]
    s_set_buttons_state_global_func = shared_elements_dict["set_buttons_state_func"]
    s_get_current_system_func = shared_elements_dict["get_current_system_func"]
    s_cancel_outfitting_event = shared_elements_dict.get("cancel_outfitting_event", threading.Event())
    s_root = shared_elements_dict["root"]
    s_outfitting_db_status_lbl_widget_ref = shared_elements_dict.get("outfitting_db_status_lbl_widget")

    outfitting_tab_frame = ttk.Frame(notebook_parent, padding="5")
    notebook_parent.add(outfitting_tab_frame, text=lang_module.get_string("outfitting_tab_title"))
    outfitting_tab_frame.columnconfigure(0, weight=1); outfitting_tab_frame.rowconfigure(0, weight=1)
    outfitting_notebook = ttk.Notebook(outfitting_tab_frame)
    outfitting_notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    outfitting_search_frame = ttk.Frame(outfitting_notebook, padding="10")
    outfitting_notebook.add(outfitting_search_frame, text=lang_module.get_string("outfitting_tab_search_title"))
    outfitting_search_frame.columnconfigure(0, weight=1)

    search_top_controls_frame = ttk.Frame(outfitting_search_frame)
    search_top_controls_frame.grid(row=0, column=0, sticky="ew", pady=(0,5))
    search_top_controls_frame.columnconfigure(1, weight=0); search_top_controls_frame.columnconfigure(2, weight=1); search_top_controls_frame.columnconfigure(3, weight=0)
    ttk.Label(search_top_controls_frame, text=lang_module.get_string("outfitting_radius_label")).grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")
    radius_entry_outfitting = ttk.Entry(search_top_controls_frame, textvariable=s_outfitting_radius_var if s_outfitting_radius_var else s_radius_var, width=7)
    radius_entry_outfitting.grid(row=0, column=1, padx=(0,10), pady=5, sticky="w")
    update_outfitting_db_btn = ttk.Button(search_top_controls_frame, text=lang_module.get_string("outfitting_update_db_button"), command=on_update_outfitting_db_pressed)
    update_outfitting_db_btn.grid(row=0, column=3, padx=5, pady=5, sticky="e")

    module_selection_and_filters_main_frame = ttk.Frame(outfitting_search_frame)
    module_selection_and_filters_main_frame.grid(row=1, column=0, sticky="ew", pady=(0,5))
    
    cat_frame = ttk.Frame(module_selection_and_filters_main_frame); cat_frame.pack(fill=tk.X, pady=(0,2))
    ttk.Label(cat_frame, text=lang_module.get_string("outfitting_category_label")).pack(side=tk.LEFT, padx=(0,5))
    category_var = tk.StringVar()
    category_combobox_widget = ttk.Combobox(cat_frame, textvariable=category_var, state="readonly", width=30)
    category_combobox_widget.pack(side=tk.LEFT, padx=(0,10), fill=tk.X, expand=True)
    category_combobox_widget.bind("<<ComboboxSelected>>", on_category_selected)

    filters_row_frame_ref = ttk.Frame(module_selection_and_filters_main_frame); filters_row_frame_ref.pack(fill=tk.X, pady=2)
    any_text = lang_module.get_string("filter_any")
    size_filter_label = ttk.Label(filters_row_frame_ref, text=lang_module.get_string("outfitting_size_filter_label"))
    size_filter_label.grid(row=0, column=0, padx=(0,2), pady=2, sticky="w")
    size_filter_var = tk.StringVar(value=any_text)
    size_filter_combobox = ttk.Combobox(filters_row_frame_ref, textvariable=size_filter_var, state="readonly", width=7, values=[any_text])
    size_filter_combobox.grid(row=0, column=1, padx=(0,10), pady=2, sticky="w")
    size_filter_combobox.bind("<<ComboboxSelected>>", on_filters_changed)
    class_filter_label = ttk.Label(filters_row_frame_ref, text=lang_module.get_string("outfitting_class_filter_label"))
    class_filter_label.grid(row=0, column=2, padx=(10,2), pady=2, sticky="w")
    class_filter_var = tk.StringVar(value=any_text)
    class_filter_combobox = ttk.Combobox(filters_row_frame_ref, textvariable=class_filter_var, state="readonly", width=7, values=[any_text])
    class_filter_combobox.grid(row=0, column=3, padx=(0,10), pady=2, sticky="w")
    class_filter_combobox.bind("<<ComboboxSelected>>", on_filters_changed)
    mount_filter_label = ttk.Label(filters_row_frame_ref, text=lang_module.get_string("outfitting_mount_filter_label"))
    # Pas de .grid() initial pour mount_filter_label
    mount_filter_var = tk.StringVar(value=any_text)
    mount_filter_combobox = ttk.Combobox(filters_row_frame_ref, textvariable=mount_filter_var, state="readonly", width=15, values=[any_text])
    # Pas de .grid() initial pour mount_filter_combobox
    mount_filter_combobox.bind("<<ComboboxSelected>>", on_filters_changed)

    module_select_add_frame = ttk.Frame(module_selection_and_filters_main_frame); module_select_add_frame.pack(fill=tk.X, pady=(5,2))
    module_select_add_frame.columnconfigure(1, weight=1)
    ttk.Label(module_select_add_frame, text=lang_module.get_string("outfitting_module_label")).grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")
    module_var = tk.StringVar()
    module_combobox_widget = ttk.Combobox(module_select_add_frame, textvariable=module_var, state="readonly", width=45)
    module_combobox_widget.grid(row=0, column=1, padx=(0,10), pady=5, sticky="ew")
    add_to_search_list_btn = ttk.Button(module_select_add_frame, text=lang_module.get_string("outfitting_add_to_list_btn"), command=on_add_module_to_list_pressed)
    add_to_search_list_btn.grid(row=0, column=2, padx=(5,0), pady=5, sticky="w")

    search_list_frame = ttk.Labelframe(outfitting_search_frame, text=lang_module.get_string("outfitting_search_list_label"), padding="5")
    search_list_frame.grid(row=2, column=0, sticky="nsew", pady=(5,5)) # row=2
    outfitting_search_frame.rowconfigure(2, weight=1)
    search_list_frame.columnconfigure(0, weight=1); search_list_frame.rowconfigure(0, weight=1)
    search_list_lb = tk.Listbox(search_list_frame, height=5, exportselection=False, selectmode=tk.EXTENDED, background=gui_main.ED_INPUT_BG, foreground=gui_main.ED_INPUT_TEXT, selectbackground=gui_main.ED_HIGHLIGHT_BG, selectforeground=gui_main.ED_HIGHLIGHT_TEXT)
    search_list_lb.grid(row=0, column=0, sticky="nsew", pady=(0,5))
    search_list_scrollbar = ttk.Scrollbar(search_list_frame, orient=tk.VERTICAL, command=search_list_lb.yview)
    search_list_scrollbar.grid(row=0, column=1, sticky="ns", pady=(0,5))
    search_list_lb.config(yscrollcommand=search_list_scrollbar.set)
    remove_from_search_list_btn = ttk.Button(search_list_frame, text=lang_module.get_string("outfitting_remove_from_list_btn"), command=on_remove_module_from_list_pressed)
    remove_from_search_list_btn.grid(row=1, column=0, columnspan=2, pady=(0,5))

    general_filter_frame = ttk.Frame(outfitting_search_frame)
    general_filter_frame.grid(row=3, column=0, sticky="w", pady=(0,10), padx=0) # row=3
    shipyard_include_planetary_cb = ttk.Checkbutton(general_filter_frame, text=lang_module.get_string("settings_include_planetary_cb"), variable=s_include_planetary_var)
    shipyard_include_planetary_cb.pack(side=tk.LEFT, padx=(0,10))
    shipyard_include_fc_cb = ttk.Checkbutton(general_filter_frame, text=lang_module.get_string("settings_include_fc_cb"), variable=s_include_fleet_carriers_var)
    shipyard_include_fc_cb.pack(side=tk.LEFT, padx=(0,10))

    search_outfitting_btn = ttk.Button(outfitting_search_frame, text=lang_module.get_string("outfitting_search_button"), command=on_find_outfitting_pressed)
    search_outfitting_btn.grid(row=4, column=0, pady=(5,5)) # row=4
    outfitting_search_status_lbl = ttk.Label(outfitting_search_frame, text=lang_module.get_string("outfitting_search_initial_status"), style="Status.TLabel")
    outfitting_search_status_lbl.grid(row=5, column=0, sticky="ew", pady=(5,0)) # row=5

    # --- Sous-onglet Résultats Équipement ---
    outfitting_results_frame = ttk.Frame(outfitting_notebook, padding="10")
    outfitting_notebook.add(outfitting_results_frame, text=lang_module.get_string("outfitting_tab_results_title"))
    outfitting_results_frame.columnconfigure(0, weight=1); outfitting_results_frame.rowconfigure(0, weight=1)
    cols_outfitting_keys = ["tree_col_outfitting_station", "tree_col_outfitting_system", "tree_col_outfitting_dist_ly", "tree_col_outfitting_pad_size", "tree_col_outfitting_dist_ls", "tree_col_outfitting_type", "tree_col_outfitting_modules_matched_ui"]
    outfitting_results_tree = ttk.Treeview(outfitting_results_frame, columns=cols_outfitting_keys, show='headings', style="Treeview")
    col_configs_outfitting = {
        "tree_col_outfitting_station": {"width": 180, "anchor": tk.W, "stretch": tk.YES, "type": "str_ci"},
        "tree_col_outfitting_system":  {"width": 120, "anchor": tk.W, "stretch": tk.YES, "type": "str_ci"},
        "tree_col_outfitting_dist_ly": {"width": 70, "anchor": tk.E, "stretch": tk.NO,  "type": "float"},
        "tree_col_outfitting_pad_size": {"width": 50, "anchor": tk.CENTER, "stretch": tk.NO, "type": "str_ci"},
        "tree_col_outfitting_dist_ls": {"width": 80, "anchor": tk.E, "stretch": tk.NO,  "type": "float"},
        "tree_col_outfitting_type":    {"width": 130, "anchor": tk.W, "stretch": tk.NO,  "type": "str_ci"},
        "tree_col_outfitting_modules_matched_ui": {"width": 330, "anchor": tk.W, "stretch": tk.YES, "type": "str_ci"}
    }
    for key in cols_outfitting_keys:
        cfg = col_configs_outfitting[key]
        outfitting_results_tree.heading(key, text=lang_module.get_string(key), anchor=tk.W,
                                      command=lambda tv=outfitting_results_tree, c_key=key, dt=cfg["type"]: gui_main.sort_treeview_column_general(tv, c_key, dt))
        outfitting_results_tree.column(key, width=cfg["width"], anchor=cfg["anchor"], stretch=cfg["stretch"])
    outfitting_results_tree.grid(row=0, column=0, sticky="nsew")
    outfitting_results_status_lbl = ttk.Label(outfitting_results_frame, text=lang_module.get_string("outfitting_results_initial_status"), style="Status.TLabel")
    outfitting_results_status_lbl.grid(row=1, column=0, sticky="ew", pady=(5,0))

    populate_initial_filters()
    logger.debug("Outfitting tab created with advanced filters.")
    return outfitting_tab_frame