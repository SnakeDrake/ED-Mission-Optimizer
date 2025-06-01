#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading # Gardé si des opérations longues sont réintroduites
from datetime import datetime # Pour le formatage du timestamp

from constants import (
    MATERIAL_CATEGORIES, ALL_MATERIALS_DATA, MATERIALS_LOOKUP, get_material_limit,
    ED_ORANGE, ED_DARK_GREY, ED_MEDIUM_GREY, ED_LIGHT_GREY_TEXT, ED_WHITE_TEXT,
    ED_MAT_DARK_RED, ED_MAT_RED, ED_MAT_DARK_ORANGE, ED_MAT_YELLOW_GREEN,
    ED_MAT_GREEN_MEDIUM, ED_MAT_GREEN_BRIGHT,
    ED_MAT_TEXT_ON_DARK, ED_MAT_TEXT_ON_LIGHT
)
import language as lang_module
import journal_parser

logger = logging.getLogger(__name__)

# Variables globales au module
materials_data_store = {"Raw": {}, "Manufactured": {}, "Encoded": {}, "timestamp": None}
materials_tab_status_lbl = None # Pour le timestamp/statut
treeviews = {} # Dictionnaire pour stocker les treeviews par catégorie
refresh_materials_button_widget = None # Référence au bouton de rafraîchissement
s_shared_root = None # Référence à la fenêtre racine de l'application

MATERIAL_ROW_TAGS_CONFIG = [
    ('percent_0_9', ED_MAT_DARK_RED, ED_MAT_TEXT_ON_DARK),
    ('percent_10_29', ED_MAT_RED, ED_MAT_TEXT_ON_DARK),
    ('percent_30_49', ED_MAT_DARK_ORANGE, ED_MAT_TEXT_ON_LIGHT),
    ('percent_50_69', ED_ORANGE, ED_MAT_TEXT_ON_LIGHT),
    ('percent_70_89', ED_MAT_YELLOW_GREEN, ED_MAT_TEXT_ON_LIGHT),
    ('percent_90_99', ED_MAT_GREEN_MEDIUM, ED_MAT_TEXT_ON_DARK),
    ('percent_100', ED_MAT_GREEN_BRIGHT, ED_MAT_TEXT_ON_LIGHT)
]

def get_row_tag_for_percentage(percentage_float):
    if percentage_float >= 100.0:
        return 'percent_100'
    elif percentage_float >= 90.0:
        return 'percent_90_99'
    elif percentage_float >= 70.0:
        return 'percent_70_89'
    elif percentage_float >= 50.0:
        return 'percent_50_69'
    elif percentage_float >= 30.0:
        return 'percent_30_49'
    elif percentage_float >= 10.0:
        return 'percent_10_29'
    elif percentage_float >= 0: # Inclut 0%
        return 'percent_0_9'
    return None


def create_materials_tab(notebook_widget, shared_elements_dict):
    global materials_tab_status_lbl, treeviews, refresh_materials_button_widget, s_shared_root

    s_shared_root = shared_elements_dict.get("root") # Stocker la référence racine

    # 1. Créer le Frame principal qui SERA l'onglet. Ne pas utiliser .pack() ou .grid() dessus.
    materials_tab_page_frame = ttk.Frame(notebook_widget, style='TFrame')

    # 2. Ajouter ce Frame au Notebook parent.
    # Le texte sera mis à jour par la fonction de changement de langue de gui_main.
    notebook_widget.add(materials_tab_page_frame, text=lang_module.get_string("materials_tab_title"))

    # 3. Tout le contenu de l'onglet va maintenant à l'intérieur de 'materials_tab_page_frame'.
    # Cadre principal pour le contenu de l'onglet (remplit la page de l'onglet)
    main_content_frame = ttk.Frame(materials_tab_page_frame, padding="5 5 5 5")
    main_content_frame.pack(expand=True, fill=tk.BOTH)
    main_content_frame.columnconfigure(0, weight=1) # La colonne contenant le notebook des catégories s'étend
    main_content_frame.rowconfigure(1, weight=1)    # La ligne contenant le notebook des catégories s'étend

    # Cadre pour les contrôles (bouton Refresh, label de statut)
    controls_frame = ttk.Frame(main_content_frame)
    controls_frame.grid(row=0, column=0, sticky="ew", pady=(0,5))
    
    refresh_materials_button_widget = ttk.Button(
        controls_frame,
        text=lang_module.get_string("refresh_materials_button"),
        command=lambda: refresh_materials_data_display(shared_elements_dict),
        style="TButton"
    )
    refresh_materials_button_widget.pack(side=tk.LEFT, padx=(0,5))
    
    materials_tab_status_lbl = ttk.Label(
        controls_frame, text=lang_module.get_string("materials_status_idle"),
        style="Status.TLabel", anchor=tk.W
    )
    materials_tab_status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # Notebook interne pour les catégories de matériaux
    category_notebook = ttk.Notebook(main_content_frame, style="TNotebook")
    category_notebook.grid(row=1, column=0, sticky="nsew") # S'étend pour remplir l'espace

    sort_func = shared_elements_dict.get("sort_treeview_column_func")

    for category in MATERIAL_CATEGORIES:
        cat_frame = ttk.Frame(category_notebook, style='TFrame', padding=5)
        # Le texte de l'onglet de catégorie sera mis à jour par update_materials_tab_texts
        category_notebook.add(cat_frame, text=lang_module.get_string(f"material_category_{category.lower()}"))

        tree_scroll_y = ttk.Scrollbar(cat_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(cat_frame, orient=tk.HORIZONTAL)

        cols = ("mat_name", "mat_grade", "mat_quantity", "mat_limit", "mat_percentage")
        tree = ttk.Treeview(
            cat_frame,
            columns=cols,
            show="headings",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
            style="Treeview"
        )
        tree_scroll_y.config(command=tree.yview)
        tree_scroll_x.config(command=tree.xview)

        tree.heading("mat_name", text=lang_module.get_string("material_name_header"))
        tree.heading("mat_grade", text=lang_module.get_string("material_grade_header"))
        tree.heading("mat_quantity", text=lang_module.get_string("material_quantity_header"))
        tree.heading("mat_limit", text=lang_module.get_string("material_limit_header"))
        tree.heading("mat_percentage", text=lang_module.get_string("material_percentage_header"))

        tree.column("mat_name", width=250, anchor=tk.W, stretch=tk.YES)
        tree.column("mat_grade", width=60, anchor=tk.CENTER, stretch=tk.NO)
        tree.column("mat_quantity", width=80, anchor=tk.E, stretch=tk.NO)
        tree.column("mat_limit", width=80, anchor=tk.E, stretch=tk.NO)
        tree.column("mat_percentage", width=100, anchor=tk.E, stretch=tk.NO)
        
        if sort_func:
            for col_key_idx, col_key in enumerate(cols): # Utiliser enumerate pour l'index si besoin
                data_type = "str_ci"
                if col_key in ["mat_grade", "mat_quantity", "mat_limit"]: data_type = "int"
                elif col_key == "mat_percentage": data_type = "float"
                # Assigner la commande de tri pour chaque colonne
                tree.heading(col_key, command=lambda c=col_key, t=tree, dt=data_type: sort_func(t, c, dt))
        
        for tag_name, bg_color, fg_color in MATERIAL_ROW_TAGS_CONFIG:
            tree.tag_configure(tag_name, background=bg_color, foreground=fg_color)
        
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(expand=True, fill=tk.BOTH)
        
        treeviews[category] = tree
    
    logger.info("Materials tab created.")
    # Appel initial pour charger les matériaux si souhaité (ex: après un délai)
    # if s_shared_root:
    #    s_shared_root.after(250, lambda: refresh_materials_data_display(shared_elements_dict))
    
    return materials_tab_page_frame # Retourner le frame principal de l'onglet


def update_materials_display():
    global materials_data_store, treeviews, materials_tab_status_lbl

    if not treeviews:
        logger.warning("Materials display update called but treeviews not ready.")
        return

    if not materials_data_store or materials_data_store.get("timestamp") is None:
        if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists():
            materials_tab_status_lbl.config(text=lang_module.get_string("materials_status_not_loaded"))
        for category, tree in treeviews.items():
             if tree.winfo_exists():
                for i in tree.get_children(): tree.delete(i)
        return

    for category, tree in treeviews.items():
        if not tree.winfo_exists(): continue
        for i in tree.get_children(): tree.delete(i)

        all_mats_in_cat = ALL_MATERIALS_DATA.get(category, [])
        items_to_display = []

        for mat_const_data in all_mats_in_cat:
            mat_name_internal_lower = mat_const_data["Name"].lower()
            mat_grade = mat_const_data["Grade"]
            mat_name_display = mat_const_data.get("Name_Localised", mat_name_internal_lower.capitalize())

            player_mat_data = materials_data_store.get(category, {}).get(mat_name_internal_lower, {})
            quantity = player_mat_data.get("Count", 0)
            limit = get_material_limit(mat_name_internal_lower, category, mat_grade)
            
            percentage_float = 0.0
            if limit > 0:
                percentage_float = min(100.0, (quantity / limit) * 100.0) # Assurer que ça ne dépasse pas 100% pour la couleur
            percentage_str = f"{percentage_float:.1f}%"
            
            row_tag_name = get_row_tag_for_percentage(percentage_float)
            # S'assurer que `tags` est un tuple, même s'il est vide ou contient un seul élément.
            current_tags = (row_tag_name,) if row_tag_name else ()

            items_to_display.append({
                "name_display": mat_name_display, "grade": mat_grade, "quantity": quantity,
                "limit": limit, "percentage_str": percentage_str,
                "percentage_float": percentage_float, "tag": current_tags
            })
        
        items_to_display.sort(key=lambda x: (x["grade"], x["name_display"].lower()))

        for item_data in items_to_display:
            tree.insert("", tk.END, values=(
                item_data["name_display"], item_data["grade"], item_data["quantity"],
                item_data["limit"], item_data["percentage_str"]
            ), tags=item_data["tag"])

    if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists():
        timestamp = materials_data_store.get("timestamp", "N/A")
        formatted_timestamp = "N/A"
        if timestamp and timestamp != "N/A":
            try:
                dt_obj = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                formatted_timestamp = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                formatted_timestamp = timestamp 
        materials_tab_status_lbl.config(text=lang_module.get_string('materials_status_updated_at', timestamp=formatted_timestamp))


def refresh_materials_data_display(shared_elements):
    global materials_data_store, materials_tab_status_lbl, refresh_materials_button_widget, s_shared_root
    
    logger.info("Refreshing materials data...")
    if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists():
        materials_tab_status_lbl.config(text=lang_module.get_string("materials_status_loading"))
    if refresh_materials_button_widget and refresh_materials_button_widget.winfo_exists():
        refresh_materials_button_widget.config(state=tk.DISABLED)

    update_status_progress_func = shared_elements.get("update_status_func")
    set_buttons_state_func = shared_elements.get("set_buttons_state_func")
    
    if set_buttons_state_func:
        set_buttons_state_func(operation_running=True, cancellable=False, source_tab_name="materials")
    if update_status_progress_func:
        update_status_progress_func(lang_module.get_string("materials_status_loading"), indeterminate=True, target_status_label_widget=materials_tab_status_lbl)

    def _task():
        # global materials_data_store # Pas besoin ici car on ne l'assigne que dans _update_ui_after_task
        current_mats_from_journal_local = None # Variable locale à _task
        error_occurred_msg = None

        try:
            effective_journal_dir = journal_parser.EFFECTIVE_JOURNAL_DIR
            if not effective_journal_dir or effective_journal_dir in ["Not Found", "Auto-detecting...", "Error processing journals", "No Journal Dir"]:
                logger.info("Journal directory not optimal for materials, attempting re-evaluation.")
                _, _, _, _, _, new_eff_dir, _ = journal_parser.get_player_state_data()
                effective_journal_dir = new_eff_dir
                logger.info(f"Re-evaluated journal directory for materials: {effective_journal_dir}")

            if not effective_journal_dir or effective_journal_dir in ["Not Found", "Auto-detecting...", "Error processing journals", "No Journal Dir"]:
                error_occurred_msg = lang_module.get_string("materials_journal_dir_not_found_error")
            else:
                events = journal_parser.load_journal_events(effective_journal_dir, num_files_to_check=20) # Lire plus de fichiers pour l'event Materials
                if not events:
                    logger.warning("No journal events found for materials parsing.")
                    error_occurred_msg = lang_module.get_string("materials_no_journal_events_status")
                else:
                    current_mats_from_journal_local = journal_parser.get_current_materials_from_events(events)
                    if not (current_mats_from_journal_local and current_mats_from_journal_local.get("timestamp")):
                        logger.warning("Failed to refresh materials: 'Materials' event not found or empty in recent logs.")
                        error_occurred_msg = lang_module.get_string("materials_event_not_found_warning")
        except Exception as e:
            logger.exception("Exception during materials data fetching task:")
            error_occurred_msg = lang_module.get_string("materials_error_refreshing", error=str(e))
        
        # Mise à jour de l'UI dans le thread principal
        def _update_ui_after_task():
            global materials_data_store # Nécessaire pour modifier la variable globale
            final_status_message = ""

            if error_occurred_msg:
                if s_shared_root: # S'assurer que root existe avant d'afficher messagebox
                     messagebox.showwarning(lang_module.get_string("warning_title"), error_occurred_msg, parent=s_shared_root)
                final_status_message = error_occurred_msg
                # Ne pas effacer les anciennes données si une erreur de lecture s'est produite.
                # update_materials_display() ne sera pas appelée pour mettre à jour avec des données vides.
            elif current_mats_from_journal_local: # current_mats_from_journal_local a été peuplé et pas d'erreur avant
                materials_data_store = current_mats_from_journal_local
                update_materials_display() # Met à jour l'affichage et le label de timestamp
                logger.info("Materials data refreshed and display updated.")
                # Le message de statut est géré par update_materials_display
                final_status_message = materials_tab_status_lbl.cget("text") if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists() else lang_module.get_string("status_analysis_finished") # fallback
            else: # Cas où current_mats_from_journal_local est None mais pas d'erreur explicite (devrait être couvert par error_occurred_msg)
                final_status_message = lang_module.get_string("materials_status_load_failed")


            if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists() and final_status_message:
                # Surcharger le message si error_occurred_msg a été défini, sinon update_materials_display a déjà mis le bon message.
                 if error_occurred_msg: materials_tab_status_lbl.config(text=final_status_message)


            if refresh_materials_button_widget and refresh_materials_button_widget.winfo_exists():
                refresh_materials_button_widget.config(state=tk.NORMAL)
            if update_status_progress_func:
                 update_status_progress_func(final_status_message if final_status_message else materials_tab_status_lbl.cget("text") , -1) # -1 pour cacher
            if set_buttons_state_func:
                 set_buttons_state_func(operation_running=False)

        if s_shared_root and s_shared_root.winfo_exists():
             s_shared_root.after(0, _update_ui_after_task)

    threading.Thread(target=_task, daemon=True).start()


def update_materials_tab_texts():
    global materials_tab_status_lbl, treeviews, refresh_materials_button_widget, s_shared_root

    if not (s_shared_root and s_shared_root.winfo_exists()):
        logger.warning("Cannot update materials tab texts: root window does not exist.")
        return

    if refresh_materials_button_widget and refresh_materials_button_widget.winfo_exists():
        refresh_materials_button_widget.config(text=lang_module.get_string("refresh_materials_button"))
    
    # Mettre à jour les textes des onglets du Notebook de catégories
    category_notebook_widget = None
    if treeviews: # Si treeviews a été initialisé, le category_notebook devrait l'être aussi.
        # Tentative de retrouver le category_notebook
        first_tree_key = next(iter(treeviews)) if treeviews else None
        if first_tree_key and treeviews[first_tree_key].winfo_exists():
            # tree -> cat_frame (master) -> category_notebook (master de cat_frame)
            potential_notebook = treeviews[first_tree_key].master.master
            if isinstance(potential_notebook, ttk.Notebook):
                category_notebook_widget = potential_notebook
        
        if category_notebook_widget:
            for i, category_key in enumerate(MATERIAL_CATEGORIES):
                try:
                    if i < len(category_notebook_widget.tabs()):
                        category_notebook_widget.tab(i, text=lang_module.get_string(f"material_category_{category_key.lower()}"))
                except tk.TclError as e:
                    logger.warning(f"Could not update tab text for category {category_key}: {e}")

    for category, tree in treeviews.items():
        if tree.winfo_exists():
            tree.heading("mat_name", text=lang_module.get_string("material_name_header"))
            tree.heading("mat_grade", text=lang_module.get_string("material_grade_header"))
            tree.heading("mat_quantity", text=lang_module.get_string("material_quantity_header"))
            tree.heading("mat_limit", text=lang_module.get_string("material_limit_header"))
            tree.heading("mat_percentage", text=lang_module.get_string("material_percentage_header"))
            
    if materials_tab_status_lbl and materials_tab_status_lbl.winfo_exists():
        current_text = materials_tab_status_lbl.cget("text")
        if materials_data_store.get("timestamp"): # Si des données ont été chargées, retraduire le message de timestamp
            timestamp = materials_data_store.get("timestamp", "N/A")
            formatted_timestamp = "N/A"
            if timestamp and timestamp != "N/A":
                try:
                    dt_obj = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    formatted_timestamp = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError: formatted_timestamp = timestamp
            materials_tab_status_lbl.config(text=lang_module.get_string('materials_status_updated_at', timestamp=formatted_timestamp))
        else: # Sinon, vérifier si c'est un message par défaut à retraduire
            default_messages_keys = ["materials_status_idle", "materials_status_not_loaded", "materials_journal_dir_not_found_error", "materials_no_journal_events_status", "materials_event_not_found_warning", "materials_status_load_failed"]
            is_default_like_message = any(current_text == lang_module.get_string(key) for key in default_messages_keys if lang_module.get_string(key) == current_text) # Comparer la valeur traduite actuelle
            if is_default_like_message:
                materials_tab_status_lbl.config(text=lang_module.get_string("materials_status_idle"))


    logger.info("Materials tab texts updated for language change.")