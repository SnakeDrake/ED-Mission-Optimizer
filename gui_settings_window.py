#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging

# --- Imports des modules de l'application ---
from constants import (
    # Importer les constantes nécessaires pour les valeurs par défaut et les clés de settings
    DEFAULT_RADIUS, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_STATION_DISTANCE_LS,
    DEFAULT_INCLUDE_PLANETARY, DEFAULT_INCLUDE_FLEET_CARRIERS,
    RESET_DEFAULT_RADIUS, RESET_DEFAULT_MAX_AGE_DAYS,
    RESET_DEFAULT_MAX_STATION_DISTANCE_LS, RESET_DEFAULT_INCLUDE_PLANETARY,
    RESET_DEFAULT_INCLUDE_FLEET_CARRIERS, RESET_DEFAULT_LANGUAGE,
    RESET_DEFAULT_SORT_OPTION, RESET_DEFAULT_CUSTOM_JOURNAL_DIR,
    KEY_RADIUS, KEY_MAX_AGE_DAYS, KEY_MAX_STATION_DISTANCE_LS,
    KEY_INCLUDE_PLANETARY, KEY_INCLUDE_FLEET_CARRIERS, KEY_LANGUAGE,
    KEY_CUSTOM_JOURNAL_DIR, KEY_CUSTOM_PAD_SIZES, KEY_SORT_OPTION,
    DEFAULT_NUM_JOURNAL_FILES_MISSIONS, KEY_NUM_JOURNAL_FILES_MISSIONS,
    DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS, KEY_MAX_STATIONS_FOR_TRADE_LOOPS,
    DEFAULT_MAX_GENERAL_TRADE_ROUTES, KEY_MAX_GENERAL_TRADE_ROUTES,
    DEFAULT_TOP_N_IMPORTS_FILTER, KEY_TOP_N_IMPORTS_FILTER,
    DEFAULT_SHIPYARD_RADIUS_LY # Si le rayon du chantier est un setting ici
    # KEY_SHIPYARD_RADIUS # Si vous ajoutez une clé dédiée pour le rayon du chantier
)
import settings_manager
import language as lang_module
# gui_analysis_tab est nécessaire pour on_select_journal_dir_pressed
# Cela crée une dépendance, il faudra peut-être la gérer via un callback passé par gui_main
import gui_analysis_tab
import gui_main # Pour update_gui_text_after_language_change, _set_buttons_state, refresh_location_and_ship_display

logger = logging.getLogger(__name__)

# Références aux widgets et variables de la fenêtre des settings
settings_window = None
settings_status_label = None

# Références aux variables Tkinter partagées (seront passées)
s_root = None
s_radius_var = None
s_age_var = None
s_station_dist_var = None
s_shipyard_radius_var = None # Variable pour le rayon du chantier naval
s_include_planetary_var = None
s_include_fleet_carriers_var = None
s_journal_dir_label_var = None
s_language_var = None
s_sort_var = None # Si l'option de tri est aussi gérée/affichée ici

# Référence à la fonction de mise à jour de la langue de l'UI principale
s_update_main_gui_texts_func = None
s_update_status_func_main = None # Pour mettre à jour le statut principal si besoin
s_set_buttons_state_main_func = None # Pour mettre à jour l'état des boutons principaux

def on_save_settings_pressed():
    """ Sauvegarde les paramètres modifiés. """
    global settings_status_label # Label de statut de CETTE fenêtre
    global s_radius_var, s_age_var, s_station_dist_var, s_include_planetary_var, s_include_fleet_carriers_var, s_sort_var, s_language_var, s_shipyard_radius_var
    global s_update_main_gui_texts_func, s_update_status_func_main, s_set_buttons_state_main_func

    if s_set_buttons_state_main_func: s_set_buttons_state_main_func(operation_running=True, cancellable=False) # Geler l'UI principale
    if s_update_status_func_main: s_update_status_func_main(lang_module.get_string("status_validating_saving_settings"), indeterminate=True, target_status_label_widget=settings_status_label)
    
    if settings_status_label and settings_status_label.winfo_exists():
        settings_status_label.config(text=lang_module.get_string("settings_status_saving"))
    
    msg = ""
    try:
        r = float(s_radius_var.get()); a = int(s_age_var.get()); sd = float(s_station_dist_var.get())
        sr_val = float(s_shipyard_radius_var.get())
        ip = s_include_planetary_var.get(); ifc = s_include_fleet_carriers_var.get()
        sv_val = s_sort_var.get() if s_sort_var else RESET_DEFAULT_SORT_OPTION # Fallback si s_sort_var n'est pas passé
        selected_lang_code = s_language_var.get()

        if r <= 0: raise ValueError(lang_module.get_string("error_radius_positive"))
        if sr_val <= 0: raise ValueError(lang_module.get_string("error_radius_positive") + " (Shipyard)")
        if a < 0: raise ValueError(lang_module.get_string("error_db_age_non_negative"))
        if sd < 0: raise ValueError(lang_module.get_string("error_station_dist_non_negative"))
        if sv_val not in ['d', 'b', 's']: raise ValueError("Invalid sort option.")
        if selected_lang_code not in lang_module.get_available_languages(): raise ValueError("Invalid language code.")

        settings_manager.update_setting(KEY_RADIUS, r)
        settings_manager.update_setting(KEY_MAX_AGE_DAYS, a)
        settings_manager.update_setting(KEY_MAX_STATION_DISTANCE_LS, sd)
        # Si KEY_SHIPYARD_RADIUS est une clé de setting distincte :
        # settings_manager.update_setting(KEY_SHIPYARD_RADIUS, sr_val)
        # Sinon, si shipyard_radius_var est juste pour le widget et que la valeur est partagée avec KEY_RADIUS,
        # ou gérée différemment, ajustez ici. Pour l'instant, on suppose qu'elle est juste lue pour validation.

        settings_manager.update_setting(KEY_INCLUDE_PLANETARY, ip)
        settings_manager.update_setting(KEY_INCLUDE_FLEET_CARRIERS, ifc)
        settings_manager.update_setting(KEY_SORT_OPTION, sv_val)
        
        current_lang_in_settings = settings_manager.get_setting(KEY_LANGUAGE)
        lang_changed = current_lang_in_settings != selected_lang_code
        settings_manager.update_setting(KEY_LANGUAGE, selected_lang_code) # set_language est appelé dans update_setting

        if settings_manager.save_settings_to_file():
            msg = lang_module.get_string("settings_saved_successfully"); logger.info(msg)
            if settings_status_label and settings_status_label.winfo_exists():
                 settings_status_label.config(text=msg)
                 if settings_window and settings_window.winfo_exists():
                    settings_window.after(3000, lambda: settings_status_label.config(text="") if settings_status_label and settings_status_label.winfo_exists() else None)
            if lang_changed and s_update_main_gui_texts_func:
                s_update_main_gui_texts_func() # Mettre à jour l'UI principale
        else:
            msg = lang_module.get_string("settings_failed_to_save"); logger.error(msg)
            if settings_status_label and settings_status_label.winfo_exists(): settings_status_label.config(text=msg)
    except ValueError as ve:
        msg = lang_module.get_string("settings_validation_error", error=ve); logger.error(msg)
        if settings_status_label and settings_status_label.winfo_exists(): settings_status_label.config(text=msg)
    except Exception as e:
        logger.exception("Unexpected error saving settings:"); msg = lang_module.get_string("settings_error_saving", error=e)
        if settings_status_label and settings_status_label.winfo_exists(): settings_status_label.config(text=msg)
    
    if s_update_status_func_main: s_update_status_func_main(msg, None, target_status_label_widget=settings_status_label)
    if s_set_buttons_state_main_func: s_set_buttons_state_main_func(False, False)


def on_restore_defaults_pressed():
    """ Restaure les paramètres par défaut. """
    global settings_status_label
    global s_radius_var, s_age_var, s_station_dist_var, s_include_planetary_var, s_include_fleet_carriers_var, s_sort_var, s_language_var, s_shipyard_radius_var
    global s_update_main_gui_texts_func, s_update_status_func_main, s_set_buttons_state_main_func

    parent_window = settings_window if settings_window and settings_window.winfo_exists() else s_root
    if messagebox.askyesno(lang_module.get_string("message_box_restore_defaults_title"), lang_module.get_string("message_box_restore_defaults_content"), parent=parent_window):
        logger.info("Restoring default settings as requested by user.")
        if s_set_buttons_state_main_func: s_set_buttons_state_main_func(operation_running=True, cancellable=False)
        if s_update_status_func_main: s_update_status_func_main(lang_module.get_string("settings_status_restoring"), indeterminate=True, target_status_label_widget=settings_status_label)
        
        if settings_status_label and settings_status_label.winfo_exists():
            settings_status_label.config(text=lang_module.get_string("settings_status_restoring"))

        # Mise à jour des variables Tkinter partagées
        s_radius_var.set(str(RESET_DEFAULT_RADIUS)); s_age_var.set(str(RESET_DEFAULT_MAX_AGE_DAYS)); s_station_dist_var.set(str(RESET_DEFAULT_MAX_STATION_DISTANCE_LS))
        s_include_planetary_var.set(RESET_DEFAULT_INCLUDE_PLANETARY); s_include_fleet_carriers_var.set(RESET_DEFAULT_INCLUDE_FLEET_CARRIERS)
        if s_sort_var: s_sort_var.set(RESET_DEFAULT_SORT_OPTION)
        s_language_var.set(RESET_DEFAULT_LANGUAGE)
        s_shipyard_radius_var.set(str(DEFAULT_SHIPYARD_RADIUS_LY))


        # Mise à jour des settings dans settings_manager
        settings_manager.update_setting(KEY_RADIUS, RESET_DEFAULT_RADIUS); settings_manager.update_setting(KEY_MAX_AGE_DAYS, RESET_DEFAULT_MAX_AGE_DAYS)
        settings_manager.update_setting(KEY_MAX_STATION_DISTANCE_LS, RESET_DEFAULT_MAX_STATION_DISTANCE_LS); settings_manager.update_setting(KEY_INCLUDE_PLANETARY, RESET_DEFAULT_INCLUDE_PLANETARY)
        settings_manager.update_setting(KEY_INCLUDE_FLEET_CARRIERS, RESET_DEFAULT_INCLUDE_FLEET_CARRIERS); settings_manager.update_setting(KEY_SORT_OPTION, RESET_DEFAULT_SORT_OPTION)
        settings_manager.update_setting(KEY_CUSTOM_JOURNAL_DIR, RESET_DEFAULT_CUSTOM_JOURNAL_DIR); settings_manager.update_setting(KEY_NUM_JOURNAL_FILES_MISSIONS, DEFAULT_NUM_JOURNAL_FILES_MISSIONS)
        settings_manager.update_setting(KEY_MAX_STATIONS_FOR_TRADE_LOOPS, DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS); settings_manager.update_setting(KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES)
        settings_manager.update_setting(KEY_TOP_N_IMPORTS_FILTER, DEFAULT_TOP_N_IMPORTS_FILTER)
        
        current_lang_in_settings = settings_manager.get_setting(KEY_LANGUAGE)
        lang_changed_by_reset = current_lang_in_settings != RESET_DEFAULT_LANGUAGE
        settings_manager.update_setting(KEY_LANGUAGE, RESET_DEFAULT_LANGUAGE)


        custom_pads_ref = settings_manager.get_setting(KEY_CUSTOM_PAD_SIZES)
        if isinstance(custom_pads_ref, dict): custom_pads_ref.clear()
        else: settings_manager.update_setting(KEY_CUSTOM_PAD_SIZES, {})
        if settings_manager.CUSTOM_SHIP_PAD_SIZES: settings_manager.CUSTOM_SHIP_PAD_SIZES.clear()

        msg_restore = ""
        if settings_manager.save_settings_to_file():
            msg_restore = lang_module.get_string("settings_defaults_restored_saved"); logger.info(msg_restore)
            if settings_status_label and settings_status_label.winfo_exists():
                 settings_status_label.config(text=msg_restore)
                 if settings_window and settings_window.winfo_exists():
                    settings_window.after(3000, lambda: settings_status_label.config(text="") if settings_status_label and settings_status_label.winfo_exists() else None)
            if lang_changed_by_reset and s_update_main_gui_texts_func:
                s_update_main_gui_texts_func()
        else:
            msg_restore = lang_module.get_string("settings_failed_save_restored")
            if settings_status_label and settings_status_label.winfo_exists(): settings_status_label.config(text=msg_restore)
        
        if s_update_status_func_main: s_update_status_func_main(msg_restore, None, target_status_label_widget=settings_status_label)
        if gui_main.update_journal_dir_display_label: gui_main.update_journal_dir_display_label() # Appel à la fonction de gui_main

        # Gérer le unknown_pad_frame via une fonction de l'onglet analyse
        if gui_analysis_tab.unknown_pad_frame and gui_analysis_tab.unknown_pad_frame.winfo_ismapped():
            gui_analysis_tab.unknown_pad_frame.grid_remove()

        if s_set_buttons_state_main_func: s_set_buttons_state_main_func(False, False);
        # Pas besoin d'appeler refresh_location_and_ship_display ici, l'utilisateur peut le faire manuellement
        # Si un rafraîchissement est nécessaire pour appliquer certains settings, cela peut être fait par l'utilisateur


def create_settings_window(shared_elements):
    """ Crée et affiche la fenêtre des paramètres. """
    global settings_window, settings_status_label
    global s_root, s_radius_var, s_age_var, s_station_dist_var, s_shipyard_radius_var, s_include_planetary_var, s_include_fleet_carriers_var, s_journal_dir_label_var, s_language_var, s_sort_var
    global s_update_main_gui_texts_func, s_update_status_func_main, s_set_buttons_state_main_func

    # Stocker les références partagées
    s_root = shared_elements["root"]
    s_radius_var = shared_elements["radius_var"]
    s_age_var = shared_elements["age_var"]
    s_station_dist_var = shared_elements["station_dist_var"]
    s_shipyard_radius_var = shared_elements["shipyard_radius_var"]
    s_include_planetary_var = shared_elements["include_planetary_var"]
    s_include_fleet_carriers_var = shared_elements["include_fleet_carriers_var"]
    s_journal_dir_label_var = shared_elements["journal_dir_label_var"]
    s_language_var = shared_elements["language_var"]
    s_sort_var = shared_elements.get("sort_var") # Peut être None si non utilisé par tous les appelants
    s_update_main_gui_texts_func = shared_elements["update_main_gui_texts_func"]
    s_update_status_func_main = shared_elements["update_status_func"] # C'est la fonction globale de gui_main
    s_set_buttons_state_main_func = shared_elements["set_buttons_state_func"]


    if settings_window and settings_window.winfo_exists():
        settings_window.focus()
        return

    settings_window = tk.Toplevel(s_root)
    settings_window.title(lang_module.get_string("settings_window_title"))
    settings_window.configure(bg=gui_main.ED_DARK_GREY) # Utiliser les constantes de gui_main
    settings_window.resizable(False, False)

    root_x, root_y, root_width, root_height = s_root.winfo_x(), s_root.winfo_y(), s_root.winfo_width(), s_root.winfo_height()
    win_width, win_height = 450, 650
    pos_x, pos_y = root_x + (root_width // 2) - (win_width // 2), root_y + (root_height // 2) - (win_height // 2)
    settings_window.geometry(f'{win_width}x{win_height}+{pos_x}+{pos_y}')
    settings_window.transient(s_root); settings_window.grab_set()

    def _on_settings_close():
        global settings_window
        if settings_window: settings_window.grab_release(); settings_window.destroy(); settings_window = None
    settings_window.protocol("WM_DELETE_WINDOW", _on_settings_close)

    main_settings_frame = ttk.Frame(settings_window, padding="10"); main_settings_frame.pack(fill=tk.BOTH, expand=True)
    settings_status_label = ttk.Label(main_settings_frame, text="", style='Status.TLabel', anchor=tk.W); settings_status_label.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0), padx=5)

    # Section Journal
    journal_lf = ttk.Labelframe(main_settings_frame, text=lang_module.get_string("settings_journal_dir_label"), padding="10"); journal_lf.pack(fill=tk.X, pady=5, padx=5, side=tk.TOP)
    ttk.Label(journal_lf, textvariable=s_journal_dir_label_var, style='Path.TLabel', wraplength=380).pack(fill=tk.X, pady=(0,5))
    # La fonction on_select_journal_dir_pressed est dans gui_analysis_tab, il faut une manière de l'appeler
    # Soit la passer via shared_elements, soit la rendre plus globale
    # Pour l'instant, on suppose que gui_analysis_tab.on_select_journal_dir_pressed est accessible globalement (ce qui n'est pas idéal)
    # ou que la fonction de gui_main qui l'appelle est passée.
    # shared_elements peut contenir 'select_journal_dir_func': gui_analysis_tab.on_select_journal_dir_pressed
    select_journal_dir_func = shared_elements.get('select_journal_dir_func', lambda: logger.error("Fonction de sélection de répertoire de journal non fournie"))
    ttk.Button(journal_lf, text=lang_module.get_string("settings_change_journal_dir_button"), command=select_journal_dir_func).pack(pady=5)

    # Section Paramètres de recherche
    search_params_lf = ttk.Labelframe(main_settings_frame, text=lang_module.get_string("settings_search_params_label"), padding="10"); search_params_lf.pack(fill=tk.X, pady=5, padx=5, side=tk.TOP)
    param_grid = ttk.Frame(search_params_lf); param_grid.pack(fill=tk.X); param_grid.columnconfigure(1, weight=1)
    ttk.Label(param_grid, text=lang_module.get_string("settings_radius_label")).grid(row=0, column=0, sticky=tk.W, padx=2, pady=3); ttk.Entry(param_grid, width=10, textvariable=s_radius_var).grid(row=0, column=1, sticky=tk.EW, padx=2, pady=3)
    ttk.Label(param_grid, text=lang_module.get_string("settings_db_age_label")).grid(row=1, column=0, sticky=tk.W, padx=2, pady=3); ttk.Entry(param_grid, width=10, textvariable=s_age_var).grid(row=1, column=1, sticky=tk.EW, padx=2, pady=3)
    ttk.Label(param_grid, text=lang_module.get_string("settings_max_station_dist_label")).grid(row=2, column=0, sticky=tk.W, padx=2, pady=3); ttk.Entry(param_grid, width=10, textvariable=s_station_dist_var).grid(row=2, column=1, sticky=tk.EW, padx=2, pady=3)
    ttk.Label(param_grid, text=lang_module.get_string("settings_shipyard_radius_label")).grid(row=3, column=0, sticky=tk.W, padx=2, pady=3); ttk.Entry(param_grid, width=10, textvariable=s_shipyard_radius_var).grid(row=3, column=1, sticky=tk.EW, padx=2, pady=3)

    cb_frame = ttk.Frame(search_params_lf); cb_frame.pack(fill=tk.X, pady=(8,5))
    ttk.Checkbutton(cb_frame, text=lang_module.get_string("settings_include_planetary_cb"), variable=s_include_planetary_var).pack(anchor=tk.W, padx=2, pady=2)
    ttk.Checkbutton(cb_frame, text=lang_module.get_string("settings_include_fc_cb"), variable=s_include_fleet_carriers_var).pack(anchor=tk.W, padx=2, pady=2)

    # Section Langue
    language_lf = ttk.Labelframe(main_settings_frame, text=lang_module.get_string("settings_language_label"), padding="10"); language_lf.pack(fill=tk.X, pady=5, padx=5, side=tk.TOP)
    available_langs_dict = lang_module.get_available_languages()
    lang_display_names = [f"{name} ({code})" for code, name in available_langs_dict.items()]; lang_codes = list(available_langs_dict.keys())
    lang_combo = ttk.Combobox(language_lf, textvariable=s_language_var, values=lang_display_names, state="readonly", width=30)
    current_lang_code_for_selection = s_language_var.get(); display_value_to_set_in_combo = f"{available_langs_dict.get(current_lang_code_for_selection, 'English')} ({current_lang_code_for_selection})"
    if display_value_to_set_in_combo not in lang_display_names: default_code = lang_codes[0] if lang_codes else ""; s_language_var.set(default_code); display_value_to_set_in_combo = lang_display_names[0] if lang_display_names else ""
    lang_combo.set(display_value_to_set_in_combo)
    def on_lang_combo_select(event):
        selected_display_val = lang_combo.get()
        for code, name in available_langs_dict.items():
            if f"{name} ({code})" == selected_display_val: s_language_var.set(code); break
    lang_combo.bind("<<ComboboxSelected>>", on_lang_combo_select); lang_combo.pack(pady=5)

    # Section Actions
    actions_lf = ttk.Labelframe(main_settings_frame, text=lang_module.get_string("settings_actions_label"), padding="10"); actions_lf.pack(fill=tk.X, pady=(10,5), padx=5, side=tk.TOP)
    buttons_frame_settings = ttk.Frame(actions_lf); buttons_frame_settings.pack(pady=5, fill=tk.X)
    ttk.Button(buttons_frame_settings, text=lang_module.get_string("settings_save_button"), command=on_save_settings_pressed).pack(side=tk.LEFT, padx=(0, 5), pady=(2,5))
    ttk.Button(buttons_frame_settings, text=lang_module.get_string("settings_restore_defaults_button"), command=on_restore_defaults_pressed).pack(side=tk.LEFT, padx=5, pady=(2,5))
    ttk.Button(buttons_frame_settings, text=lang_module.get_string("settings_close_button"), command=_on_settings_close).pack(side=tk.RIGHT, padx=(5, 0), pady=(2,5))

    logger.debug("Settings window created.")