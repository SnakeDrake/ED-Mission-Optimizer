#!/usr/bin/env python3
import json
import os
import logging
from constants import (
    SETTINGS_FILE, DEFAULT_RADIUS, DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_STATION_DISTANCE_LS, DEFAULT_INCLUDE_PLANETARY,
    DEFAULT_INCLUDE_FLEET_CARRIERS,
    DEFAULT_CUSTOM_JOURNAL_DIR, RESET_DEFAULT_SORT_OPTION,
    DEFAULT_NUM_JOURNAL_FILES_MISSIONS,
    DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS,
    DEFAULT_MAX_GENERAL_TRADE_ROUTES,
    DEFAULT_TOP_N_IMPORTS_FILTER,
    DEFAULT_LANGUAGE, # NOUVEAU
    KEY_RADIUS, KEY_MAX_AGE_DAYS, KEY_MAX_STATION_DISTANCE_LS,
    KEY_INCLUDE_PLANETARY, KEY_INCLUDE_FLEET_CARRIERS,
    KEY_CUSTOM_JOURNAL_DIR, KEY_CUSTOM_PAD_SIZES, KEY_SORT_OPTION,
    KEY_NUM_JOURNAL_FILES_MISSIONS, KEY_MAX_STATIONS_FOR_TRADE_LOOPS,
    KEY_MAX_GENERAL_TRADE_ROUTES,
    KEY_TOP_N_IMPORTS_FILTER,
    KEY_LANGUAGE # NOUVEAU
)

logger = logging.getLogger(__name__)

APP_SETTINGS = {}
CUSTOM_SHIP_PAD_SIZES = {}

def load_settings():
    global APP_SETTINGS, CUSTOM_SHIP_PAD_SIZES
    settings_data = {}
    current_custom_pad_sizes = {}
    settings_file_path = os.path.abspath(SETTINGS_FILE)
    logger.debug(f"Attempting to load settings from: {settings_file_path}")
    try:
        if os.path.exists(settings_file_path):
            with open(settings_file_path, 'r', encoding='utf-8') as f: settings_data = json.load(f)
            logger.info(f"Successfully loaded and parsed JSON from {settings_file_path}")
            loaded_custom_sizes = settings_data.get(KEY_CUSTOM_PAD_SIZES, {}) if isinstance(settings_data, dict) else {}
            if isinstance(loaded_custom_sizes, dict):
                validated_custom_sizes = {}
                for ship_name, pad_size in loaded_custom_sizes.items():
                    try:
                        ship_name_clean = str(ship_name).lower(); pad_size_int = int(pad_size)
                        if pad_size_int in [1, 2, 3]: validated_custom_sizes[ship_name_clean] = pad_size_int
                        else: logger.warning(f"Invalid custom pad size '{pad_size}' for ship '{ship_name}'.")
                    except (ValueError, TypeError): logger.warning(f"Invalid format for custom pad size for ship '{ship_name}'.")
                current_custom_pad_sizes = validated_custom_sizes
        else: logger.warning(f"Settings file {settings_file_path} not found. Using defaults."); settings_data = {}
    except json.JSONDecodeError as json_err: logger.error(f"Error decoding JSON from {settings_file_path}: {json_err}. Using defaults."); settings_data = {}; current_custom_pad_sizes = {}
    except Exception as e: logger.warning(f"An unexpected error occurred loading settings from {settings_file_path}: {e}. Using defaults."); settings_data = {}; current_custom_pad_sizes = {}

    custom_journal_dir = settings_data.get(KEY_CUSTOM_JOURNAL_DIR, DEFAULT_CUSTOM_JOURNAL_DIR)
    radius = settings_data.get(KEY_RADIUS, DEFAULT_RADIUS)
    max_age_days = settings_data.get(KEY_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS)
    max_station_distance_ls = settings_data.get(KEY_MAX_STATION_DISTANCE_LS, DEFAULT_MAX_STATION_DISTANCE_LS)
    include_planetary = settings_data.get(KEY_INCLUDE_PLANETARY, DEFAULT_INCLUDE_PLANETARY)
    include_fleet_carriers = settings_data.get(KEY_INCLUDE_FLEET_CARRIERS, DEFAULT_INCLUDE_FLEET_CARRIERS)
    sort_option = settings_data.get(KEY_SORT_OPTION, RESET_DEFAULT_SORT_OPTION)
    num_journal_files = settings_data.get(KEY_NUM_JOURNAL_FILES_MISSIONS, DEFAULT_NUM_JOURNAL_FILES_MISSIONS)
    max_stations_loops = settings_data.get(KEY_MAX_STATIONS_FOR_TRADE_LOOPS, DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS)
    max_general_routes = settings_data.get(KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES)
    top_n_imports_filter = settings_data.get(KEY_TOP_N_IMPORTS_FILTER, DEFAULT_TOP_N_IMPORTS_FILTER)
    language_setting = settings_data.get(KEY_LANGUAGE, DEFAULT_LANGUAGE) # NOUVEAU

    try: radius = float(radius); assert radius > 0
    except: radius = DEFAULT_RADIUS; logger.warning(f"Invalid radius, using default: {DEFAULT_RADIUS}")
    try: max_age_days = int(max_age_days); assert max_age_days >= 0
    except: max_age_days = DEFAULT_MAX_AGE_DAYS; logger.warning(f"Invalid max_age_days, using default: {DEFAULT_MAX_AGE_DAYS}")
    try: max_station_distance_ls = float(max_station_distance_ls); assert max_station_distance_ls >= 0
    except: max_station_distance_ls = DEFAULT_MAX_STATION_DISTANCE_LS; logger.warning(f"Invalid max_station_distance_ls, using default: {DEFAULT_MAX_STATION_DISTANCE_LS}")
    if not isinstance(include_planetary, bool): include_planetary = DEFAULT_INCLUDE_PLANETARY; logger.warning(f"Invalid include_planetary, using default: {DEFAULT_INCLUDE_PLANETARY}")
    if not isinstance(include_fleet_carriers, bool): include_fleet_carriers = DEFAULT_INCLUDE_FLEET_CARRIERS; logger.warning(f"Invalid include_fleet_carriers, using default: {DEFAULT_INCLUDE_FLEET_CARRIERS}")
    if custom_journal_dir is not None and not isinstance(custom_journal_dir, str): logger.warning(f"Invalid type for custom_journal_dir. Resetting."); custom_journal_dir = DEFAULT_CUSTOM_JOURNAL_DIR
    if sort_option not in ['d', 'b', 's']: sort_option = RESET_DEFAULT_SORT_OPTION; logger.warning(f"Invalid sort_option, using default: {RESET_DEFAULT_SORT_OPTION}")
    try: num_journal_files = int(num_journal_files); assert num_journal_files > 0
    except: num_journal_files = DEFAULT_NUM_JOURNAL_FILES_MISSIONS; logger.warning(f"Invalid num_journal_files, using default: {DEFAULT_NUM_JOURNAL_FILES_MISSIONS}")
    try: max_stations_loops = int(max_stations_loops); assert max_stations_loops >= 0
    except: max_stations_loops = DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS; logger.warning(f"Invalid max_stations_loops, using default: {DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS}")
    try: max_general_routes = int(max_general_routes); assert max_general_routes >= 0
    except: max_general_routes = DEFAULT_MAX_GENERAL_TRADE_ROUTES; logger.warning(f"Invalid max_general_routes, using default: {DEFAULT_MAX_GENERAL_TRADE_ROUTES}")
    try: top_n_imports_filter = int(top_n_imports_filter); assert top_n_imports_filter >= 0
    except: top_n_imports_filter = DEFAULT_TOP_N_IMPORTS_FILTER; logger.warning(f"Invalid top_n_imports_filter, using default: {DEFAULT_TOP_N_IMPORTS_FILTER}")

    # NOUVEAU: Validation de la langue
    import language as lang_module # Pour accéder aux langues disponibles
    if language_setting not in lang_module.get_available_languages():
        logger.warning(f"Invalid language setting '{language_setting}', using default: {DEFAULT_LANGUAGE}")
        language_setting = DEFAULT_LANGUAGE


    APP_SETTINGS = {
        KEY_RADIUS: radius, KEY_MAX_AGE_DAYS: max_age_days, KEY_MAX_STATION_DISTANCE_LS: max_station_distance_ls,
        KEY_INCLUDE_PLANETARY: include_planetary, KEY_INCLUDE_FLEET_CARRIERS: include_fleet_carriers,
        KEY_CUSTOM_JOURNAL_DIR: custom_journal_dir, KEY_CUSTOM_PAD_SIZES: current_custom_pad_sizes,
        KEY_SORT_OPTION: sort_option, KEY_NUM_JOURNAL_FILES_MISSIONS: num_journal_files,
        KEY_MAX_STATIONS_FOR_TRADE_LOOPS: max_stations_loops,
        KEY_MAX_GENERAL_TRADE_ROUTES: max_general_routes,
        KEY_TOP_N_IMPORTS_FILTER: top_n_imports_filter,
        KEY_LANGUAGE: language_setting # NOUVEAU
    }
    CUSTOM_SHIP_PAD_SIZES.clear(); CUSTOM_SHIP_PAD_SIZES.update(APP_SETTINGS[KEY_CUSTOM_PAD_SIZES])
    logger.debug(f"Final loaded APP_SETTINGS: {APP_SETTINGS}"); return APP_SETTINGS

def save_settings_to_file():
    global APP_SETTINGS
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f: json.dump(APP_SETTINGS, f, indent=2)
        logger.info(f"Settings saved to {SETTINGS_FILE}: {APP_SETTINGS}"); return True
    except Exception as e: logger.error(f"Error saving settings: {e}"); return False

def update_setting(key, value):
    global APP_SETTINGS, CUSTOM_SHIP_PAD_SIZES
    APP_SETTINGS[key] = value
    if key == KEY_CUSTOM_PAD_SIZES:
        CUSTOM_SHIP_PAD_SIZES.clear()
        if isinstance(value, dict): CUSTOM_SHIP_PAD_SIZES.update(value)
    # NOUVEAU: Si la langue est changée, l'appliquer directement
    if key == KEY_LANGUAGE:
        import language as lang_module # Importer ici pour éviter dépendance circulaire au niveau module
        lang_module.set_language(value)
    logger.debug(f"Setting '{key}' updated in APP_SETTINGS to '{value}'")

def get_setting(key, default=None): return APP_SETTINGS.get(key, default)
def get_all_settings(): return APP_SETTINGS.copy()
def get_custom_pad_sizes(): return CUSTOM_SHIP_PAD_SIZES.copy()