#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import os
import re
import threading
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from tkinter import filedialog
import math
import sys
import logging
import logging.handlers
import traceback
import tkinter.messagebox

# ---- Configuration ----
BASE_URL = "https://api.ardent-insight.com/v1/"
HEADERS = {"User-Agent": "MissionOptimizer/1.0 (wdsnakedrake@gmail.com)"} # Version incrémentée
CONCURRENCY_LIMIT = 20
DEPARTURE_DATA_FILE = 'departure_market_data.json'
LOCAL_SELLERS_DATA_FILE = 'local_sellers_data.json'
SETTINGS_FILE = 'settings.json'
LOG_FILE = 'mission_optimizer.log'

DEFAULT_RADIUS = 80.0
DEFAULT_MAX_AGE_DAYS = 1
DEFAULT_MAX_STATION_DISTANCE_LS = 5000.0
DEFAULT_INCLUDE_PLANETARY = True
DEFAULT_CUSTOM_JOURNAL_DIR = None

RESET_DEFAULT_RADIUS = 80.0
RESET_DEFAULT_MAX_AGE_DAYS = 1
RESET_DEFAULT_MAX_STATION_DISTANCE_LS = 5000.0
RESET_DEFAULT_INCLUDE_PLANETARY = True
RESET_DEFAULT_SORT_OPTION = 'd'
RESET_DEFAULT_CUSTOM_JOURNAL_DIR = None

PLANETARY_STATION_TYPES = ["CraterOutpost", "OnFootSettlement", "CraterPort", "PlanetaryOutpost", "PlanetaryPort", "OdysseySettlement", "null"]
SHIP_PAD_SIZE = {
    'sidewinder': 1, 'eagle': 1, 'viper mk iii': 1, 'viper mk iv': 1,
    'cobra mk iii': 1, 'cobra mk iv': 1, 'hauler': 1, 'adder': 1,
    'diamondback scout': 1, 'diamondback explorer': 1, 'vulture': 1,
    'imperial courier': 1, 'federal dropship': 2, 'federal gunship': 2,
    'federal assault ship': 2, 'asp scout': 2, 'asp explorer': 2,
    'type-6 transporter': 2, 'type-7 transporter': 3,
    'type-9 heavy': 3, 'type-10 defender': 3, 'keelback': 2,
    'fer-de-lance': 2, 'python': 2, 'anaconda': 3, 'imperial clipper': 2,
    'imperial cutter': 3, 'orca': 2, 'beluga liner': 3, 'dolphin': 1,
    'mamba': 2, 'krait mk ii': 2, 'krait phantom': 2, 'alliance chieftain': 2,
    'alliance challenger': 2, 'alliance crusader': 2, 'type9': 3,
    'federal corvette': 3
}
STATION_PAD_SIZE_MAP = {'S': 1, 'M': 2, 'L': 3}
CUSTOM_SHIP_PAD_SIZES = {}
APP_SETTINGS = {}
EFFECTIVE_JOURNAL_DIR = "Auto-detecting..."

def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    log_file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1024*1024, backupCount=5, encoding='utf-8'
    )
    log_file_handler.setFormatter(log_formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if not root_logger.handlers:
        root_logger.addHandler(log_file_handler)
    logging.info("Logging configured.")

setup_logging()

def load_settings():
    global CUSTOM_SHIP_PAD_SIZES, APP_SETTINGS
    settings_data = {}
    current_custom_pad_sizes = {}
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f: settings_data = json.load(f)
            logging.info(f"Loaded settings from {SETTINGS_FILE}")
            loaded_custom_sizes = settings_data.get('custom_pad_sizes', {})
            if isinstance(loaded_custom_sizes, dict):
                validated_custom_sizes = {}
                for ship_name, pad_size in loaded_custom_sizes.items():
                    try:
                        ship_name_clean = str(ship_name).lower()
                        pad_size_int = int(pad_size)
                        if pad_size_int in [1, 2, 3]: validated_custom_sizes[ship_name_clean] = pad_size_int
                        else: logging.warning(f"Invalid custom pad size '{pad_size}' for ship '{ship_name}'.")
                    except (ValueError, TypeError): logging.warning(f"Invalid format for custom pad size for ship '{ship_name}'.")
                current_custom_pad_sizes = validated_custom_sizes
    except Exception as e:
        logging.warning(f"Error loading settings from {SETTINGS_FILE}: {e}. Using defaults for structure.")
        settings_data = {}
        current_custom_pad_sizes = {}

    CUSTOM_SHIP_PAD_SIZES.clear()
    CUSTOM_SHIP_PAD_SIZES.update(current_custom_pad_sizes)

    radius = settings_data.get('radius', DEFAULT_RADIUS)
    max_age_days = settings_data.get('max_age_days', DEFAULT_MAX_AGE_DAYS)
    max_station_distance_ls = settings_data.get('max_station_distance_ls', DEFAULT_MAX_STATION_DISTANCE_LS)
    include_planetary = settings_data.get('include_planetary', DEFAULT_INCLUDE_PLANETARY)
    custom_journal_dir = settings_data.get('custom_journal_dir', DEFAULT_CUSTOM_JOURNAL_DIR)
    sort_option = settings_data.get('sort_option', RESET_DEFAULT_SORT_OPTION)

    try: radius = float(radius); assert radius > 0
    except: radius = DEFAULT_RADIUS; logging.warning(f"Invalid radius in settings, using default: {DEFAULT_RADIUS}")
    try: max_age_days = int(max_age_days); assert max_age_days >= 0
    except: max_age_days = DEFAULT_MAX_AGE_DAYS; logging.warning(f"Invalid max_age_days in settings, using default: {DEFAULT_MAX_AGE_DAYS}")
    try: max_station_distance_ls = float(max_station_distance_ls); assert max_station_distance_ls >= 0
    except: max_station_distance_ls = DEFAULT_MAX_STATION_DISTANCE_LS; logging.warning(f"Invalid max_station_distance_ls, using default: {DEFAULT_MAX_STATION_DISTANCE_LS}")
    if not isinstance(include_planetary, bool):
        include_planetary = DEFAULT_INCLUDE_PLANETARY
        logging.warning(f"Invalid include_planetary in settings, using default: {DEFAULT_INCLUDE_PLANETARY}")
    if custom_journal_dir is not None and not isinstance(custom_journal_dir, str):
        custom_journal_dir = DEFAULT_CUSTOM_JOURNAL_DIR
        logging.warning(f"Invalid custom_journal_dir type in settings, using default.")
    if sort_option not in ['d', 'b', 's']:
        sort_option = RESET_DEFAULT_SORT_OPTION
        logging.warning(f"Invalid sort_option in settings, using default: {RESET_DEFAULT_SORT_OPTION}")

    APP_SETTINGS = {
        'radius': radius,
        'max_age_days': max_age_days,
        'max_station_distance_ls': max_station_distance_ls,
        'include_planetary': include_planetary,
        'custom_journal_dir': custom_journal_dir,
        'custom_pad_sizes': CUSTOM_SHIP_PAD_SIZES.copy(),
        'sort_option': sort_option
    }
    logging.debug(f"Final loaded APP_SETTINGS: {APP_SETTINGS}")
    return APP_SETTINGS

def save_settings(radius, max_age_days, max_station_distance_ls, include_planetary_val, custom_journal_dir_val, current_custom_pad_sizes, sort_option_val):
    global APP_SETTINGS
    settings_to_save = {
        'radius': float(radius),
        'max_age_days': int(max_age_days),
        'max_station_distance_ls': float(max_station_distance_ls),
        'include_planetary': bool(include_planetary_val),
        'custom_journal_dir': custom_journal_dir_val,
        'custom_pad_sizes': current_custom_pad_sizes,
        'sort_option': sort_option_val
    }
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f: json.dump(settings_to_save, f, indent=2)
        logging.info(f"Settings saved to {SETTINGS_FILE}: {settings_to_save}")
        APP_SETTINGS = settings_to_save.copy()
        CUSTOM_SHIP_PAD_SIZES.clear()
        CUSTOM_SHIP_PAD_SIZES.update(current_custom_pad_sizes)
        return True
    except Exception as e:
        logging.error(f"Error saving settings: {e}")
        return False

def find_journal_dir(preferred_dir=None):
    if preferred_dir and os.path.isdir(preferred_dir):
        logging.info(f"Using preferred journal directory: {preferred_dir}")
        return preferred_dir
    if preferred_dir:
        logging.warning(f"Preferred journal directory '{preferred_dir}' not found or not a directory. Attempting auto-detection.")

    user_profile = os.getenv("USERPROFILE"); home_dir = os.getenv("HOME")
    base_path = user_profile or home_dir
    if not base_path:
        logging.error("Cannot determine user directory for auto-detection.")
        raise FileNotFoundError("USERPROFILE/HOME not set for auto-detection.")

    path_windows = os.path.join(base_path, "Saved Games", "Frontier Developments", "Elite Dangerous")
    if os.path.isdir(path_windows): logging.debug(f"Auto-detected Journal dir (Win): {path_windows}"); return path_windows
    if home_dir:
        steam_path_segment = os.path.join("drive_c", "users", "steamuser", "Saved Games", "Frontier Developments", "Elite Dangerous")
        proton_paths = [os.path.join(home_dir, p_prefix, steam_path_segment) for p_prefix in [".local/share/Steam/steamapps/compatdata/359320/pfx", ".steam/steam/steamapps/compatdata/359320/pfx"]]
        for p_path in proton_paths:
            if os.path.isdir(p_path): logging.debug(f"Auto-detected Journal dir (Proton): {p_path}"); return p_path
        native_linux_path = os.path.join(home_dir, ".local/share/Frontier Developments/Elite Dangerous")
        if os.path.isdir(native_linux_path): logging.debug(f"Auto-detected Journal dir (Native Linux): {native_linux_path}"); return native_linux_path
        path_macos = os.path.join(home_dir, "Library/Application Support/Frontier Developments/Elite Dangerous")
        if os.path.isdir(path_macos): logging.debug(f"Auto-detected Journal dir (macOS): {path_macos}"); return path_macos

    logging.error("Elite Dangerous journal directory not found by auto-detection.")
    raise FileNotFoundError("Elite Dangerous journal directory not found by auto-detection.")

def load_journal_events(journal_dir):
    events = []
    logging.info(f"load_journal_events: Reading from {journal_dir}")
    try:
        journal_files = [f for f in os.listdir(journal_dir) if f.startswith("Journal.") and f.endswith(".log")]
        journal_files.sort(key=lambda f: os.path.getmtime(os.path.join(journal_dir, f)))
        logging.info(f"load_journal_events: Found {len(journal_files)} journal files.")
    except Exception as e: logging.exception(f"load_journal_events: Error accessing {journal_dir}:"); return []
    files_to_process = journal_files[-10:]
    logging.info(f"load_journal_events: Will attempt to read last {len(files_to_process)} journal files: {files_to_process}")
    for fname in files_to_process:
        filepath = os.path.join(journal_dir, fname)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line_content in f:
                    try: events.append(json.loads(line_content))
                    except json.JSONDecodeError: logging.warning(f"Skipping invalid JSON in {fname}")
        except Exception: logging.exception(f"Error reading {fname}")
    logging.info(f"load_journal_events: Total events loaded: {len(events)}")
    return events

def get_ship_pad_size(ship_type):
    if not ship_type or ship_type in ["Unknown", "Journal not found", "Error", "Error - No Journal"]: return "?"
    ship_name_lower = ship_type.lower()
    if ship_name_lower in CUSTOM_SHIP_PAD_SIZES:
        pad_size = CUSTOM_SHIP_PAD_SIZES[ship_name_lower]
        if pad_size in [1, 2, 3]: return pad_size
    pad_size = SHIP_PAD_SIZE.get(ship_name_lower, '?')
    if pad_size == '?': logging.info(f"Unknown ship type for pad size: '{ship_type}'.")
    return pad_size

def get_ship_info(journal_dir_path):
    ship_type, cargo_capacity = "Unknown", 0
    try:
        if not isinstance(journal_dir_path, str) or not os.path.isdir(journal_dir_path):
            logging.error(f"Invalid journal directory path for get_ship_info: {journal_dir_path}")
            return "Error - No Journal", 0, "?"

        journal_files = [f for f in os.listdir(journal_dir_path) if f.startswith("Journal.") and f.endswith(".log")]
        journal_files.sort(key=lambda f: os.path.getmtime(os.path.join(journal_dir_path, f)))
        latest_loadout = None
        for fname in reversed(journal_files[-10:]):
            filepath = os.path.join(journal_dir_path, fname)
            try:
                 with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                     lines = f.readlines()
                     for line in reversed(lines):
                         try:
                             event = json.loads(line)
                             if event.get('event') == 'Loadout': latest_loadout = event; break
                         except json.JSONDecodeError: pass
            except Exception: pass
            if latest_loadout: break
        if latest_loadout:
            ship_type_raw = latest_loadout.get('Ship', 'Unknown')
            ship_type_loc = latest_loadout.get('Ship_Localised', ship_type_raw)
            ship_type = ship_type_loc.replace('_', ' ').title() if ship_type_loc else ship_type_raw.replace('_', ' ').title()
            cargo_capacity = latest_loadout.get('CargoCapacity', 0)
            if not isinstance(cargo_capacity, (int, float)) or cargo_capacity < 0: cargo_capacity = 0
        else: ship_type = "Journal not found"
    except Exception as e:
        ship_type = "Error"
        logging.exception(f"Error in get_ship_info with directory {journal_dir_path}: {e}")
    pad_size = get_ship_pad_size(ship_type)
    return ship_type, cargo_capacity, pad_size

def parse_location(events):
    current_system, current_station, is_docked_flag = None, None, False
    for ev in reversed(events):
        event_type = ev.get("event")
        if event_type == "Docked": current_system, current_station, is_docked_flag = ev.get("StarSystem"), ev.get("StationName"), True; break
        elif event_type == "Location":
            if ev.get("Docked"): current_system, current_station, is_docked_flag = ev.get("StarSystem"), ev.get("StationName"), True; break
            else: current_system, current_station, is_docked_flag = ev.get("StarSystem"), None, False; break
        elif event_type in ["FSDJump", "CarrierJump", "Undocked"]: current_system, current_station, is_docked_flag = ev.get("StarSystem"), None, False; break
    final_system = current_system or "?"; final_station = current_station if is_docked_flag and current_station else "?"
    if final_station != "?" and final_system == "?": final_station = "?"
    return final_system, final_station

def get_current_location_and_ship_info():
    global EFFECTIVE_JOURNAL_DIR
    jdir_path, system, station, ship_type, cargo_capacity, pad_size = "?", "?", "?", "Unknown", 0, "?"
    try:
        preferred_custom_dir = APP_SETTINGS.get('custom_journal_dir')
        jdir_path = find_journal_dir(preferred_custom_dir)
        EFFECTIVE_JOURNAL_DIR = jdir_path
        logging.info(f"get_loc_ship: Effective journal dir '{jdir_path}'")

        evs = load_journal_events(jdir_path)
        logging.info(f"get_loc_ship: loaded {len(evs)} events from '{jdir_path}'.")
        if evs: system, station = parse_location(evs)
        ship_type, cargo_capacity, pad_size = get_ship_info(jdir_path)
    except FileNotFoundError as e:
        logging.warning(f"Journal directory error in get_current_location_and_ship_info: {e}")
        EFFECTIVE_JOURNAL_DIR = "Not Found"
        ship_type = "Error - No Journal"
        system, station, cargo_capacity, pad_size = "?", "?", 0, "?"
    except Exception as e:
        logging.exception("get_loc_ship major error")
        EFFECTIVE_JOURNAL_DIR = "Error processing journals"
        ship_type = "Error"
        system, station, cargo_capacity, pad_size = "?", "?", 0, "?"

    if root and journal_dir_label_var:
        update_journal_dir_label_text()

    logging.info(f"get_loc_ship: Sys='{system}', Station='{station}', Ship='{ship_type}', Pad='{pad_size}', Cargo='{cargo_capacity}', Effective Journal='{EFFECTIVE_JOURNAL_DIR}'")
    return system, station, ship_type, cargo_capacity, pad_size

APP_SETTINGS = load_settings()
CURRENT_SYSTEM, CURRENT_STATION, CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE = "?", "?", "Unknown", 0, "?"

async def fetch_json(session, url):
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as r: r.raise_for_status(); return await r.json()

async def download_departure(system, station):
    if not all([system, station]) or "?" in [system, station] or "Journal not found" in system or "Error" in system :
        logging.warning(f"Skip departure download for invalid system/station: {system}/{station}.")
        return
    async with aiohttp.ClientSession() as sess:
        try:
            urls = [f"{BASE_URL}system/name/{system}/commodities/exports", f"{BASE_URL}system/name/{system}/commodities/imports"]
            logging.info(f"Downloading departure data for {station} in {system}...")
            datas = await asyncio.gather(*(fetch_json(sess, url) for url in urls))
            offers = {}
            for item in datas[0] + datas[1]:
                if item.get('stationName') == station:
                    entry = offers.setdefault(item['commodityName'].lower(), {'commodityName': item['commodityName']})
                    for k in ['sellPrice', 'stock', 'buyPrice', 'maxLandingPadSize', 'distanceToArrival', 'stationType']:
                        if k in item: entry[k] = item[k]
                    if 'station' in item and isinstance(item['station'],dict):
                        if 'maxLandingPadSize' in item['station'] and 'maxLandingPadSize' not in entry: entry['maxLandingPadSize'] = item['station']['maxLandingPadSize']
                        if 'type' in item['station'] and 'stationType' not in entry: entry['stationType'] = item['station']['type']
                    entry.setdefault('sellPrice',0); entry.setdefault('stock',0); entry.setdefault('buyPrice',0); entry.setdefault('distanceToArrival',0.0)
                    entry.setdefault('stationType', 'Unknown')
            with open(DEPARTURE_DATA_FILE, 'w', encoding='utf-8') as f: json.dump({"system":system, "station":station, "offers":list(offers.values()), "updatedAt":datetime.now(timezone.utc).isoformat()}, f, indent=2)
            logging.info(f"Departure data for {station} saved.")
        except Exception: logging.exception(f"Error downloading departure data for {system}/{station}")

async def download_local(system, radius):
    if not system or "?" in system or "Journal not found" in system or "Error" in system:
        logging.warning(f"Skip local download for invalid system: '{system}'.");
        return None
    async with aiohttp.ClientSession() as sess:
        try:
            nearby_url = f"{BASE_URL}system/name/{system}/nearby?maxDistance={radius}"
            logging.info(f"Downloading nearby systems around {system} (radius {radius} LY)...")
            nearby_systems_list = await fetch_json(sess, nearby_url)
            sellers_data = {"sourceSystem":system, "radius":radius, "systems":{s['systemName']:{'distance':s['distance']} for s in nearby_systems_list}, "markets":{}, "updatedAt":datetime.now(timezone.utc).isoformat()}
            sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
            async def fetch_market(sys_name):
                async with sem:
                    try:
                        data = await fetch_json(sess, f"{BASE_URL}system/name/{sys_name}/commodities/exports")
                        for sd in data:
                            if 'maxLandingPadSize' not in sd and 'station' in sd and isinstance(sd['station'],dict) and 'maxLandingPadSize' in sd['station']: sd['maxLandingPadSize'] = sd['station']['maxLandingPadSize']
                            if 'distanceToArrival' not in sd: sd['distanceToArrival'] = None
                            if 'stationType' not in sd:
                                if 'station' in sd and isinstance(sd['station'], dict) and 'type' in sd['station']:
                                    sd['stationType'] = sd['station']['type']
                                else:
                                    sd['stationType'] = 'Unknown'
                        return sys_name, data
                    except Exception: logging.debug(f"Failed to fetch market for {sys_name}"); return sys_name, []
            tasks = [fetch_market(name) for name in sellers_data['systems'].keys()]
            count = 0
            for future in asyncio.as_completed(tasks):
                name, market_offers = await future
                if market_offers: sellers_data['markets'][name] = {'distance':sellers_data['systems'][name]['distance'], 'offers':market_offers}; count+=1
            logging.info(f"Market data for {count}/{len(sellers_data['systems'])} nearby systems saved.")
            with open(LOCAL_SELLERS_DATA_FILE, 'w', encoding='utf-8') as f: json.dump(sellers_data, f, indent=2)
            return sellers_data
        except Exception: logging.exception(f"Error downloading local data for {system}"); return None

def parse_missions(events):
    logging.info(f"parse_missions: Received {len(events)} events.")
    missions_dict = {}
    missions_event_found = False
    latest_missions_event = next((ev for ev in reversed(events) if ev.get('event') == 'Missions'), None)
    if latest_missions_event:
        missions_event_found = True
        logging.info(f"parse_missions: Found 'Missions' event with {len(latest_missions_event.get('Active',[]))} active entries.")
        for m_data in latest_missions_event.get('Active', []):
            m_id = m_data.get('MissionID')
            if not m_id or not m_data.get('Commodity') or not m_data.get('Count'): continue
            c_raw, c_loc = str(m_data['Commodity']), m_data.get('Commodity_Localised')
            c_clean = (re.search(r"\$([A-Za-z0-9_]+)_Name;", c_loc, re.I).group(1).lower() if isinstance(c_loc, str) and re.search(r"\$([A-Za-z0-9_]+)_Name;", c_loc, re.I)
                         else (re.search(r"\$([A-Za-z0-9_]+)_Name;", c_raw, re.I).group(1).lower() if isinstance(c_raw, str) and re.search(r"\$([A-Za-z0-9_]+)_Name;", c_raw, re.I)
                         else re.sub(r"[\$\;\_\s]", '', str(c_loc if isinstance(c_loc,str) else c_raw).replace("_Name","")).lower().strip()))
            if not c_clean: logging.warning(f"Mission {m_id} (Missions Evt): Empty commodity. Skipping."); continue
            missions_dict[m_id] = {'name':c_clean, 'total':m_data['Count'], 'delivered':m_data.get('DeliveredCount',0), 'completed':False, 'reward':m_data.get('Reward',0), 'destinationSystem':m_data.get('DestinationSystem',''), 'destinationStation':m_data.get('DestinationStation',''), 'source_event':'Missions'}
            logging.info(f"Mission {m_id} from 'Missions': {c_clean}, Need: {m_data['Count']-m_data.get('DeliveredCount',0)}")
    if not missions_event_found: logging.info("parse_missions: No 'Missions' event. Relying on 'MissionAccepted'.")
    accepted_count = 0; cargo_depot_deliver_count = 0
    for ev in events:
        event_type, m_id = ev.get('event'), ev.get('MissionID')
        if not m_id and event_type in ['MissionAccepted','CargoDepot','MissionCompleted','MissionFailed','MissionAbandoned']: continue
        if m_id in missions_dict and missions_dict[m_id].get('completed') and event_type not in ['MissionAccepted', 'CargoDepot']: continue
        if event_type == 'MissionAccepted':
            accepted_count+=1
            if ev.get('Commodity') and ev.get('Count') and m_id not in missions_dict:
                c_raw, c_loc = str(ev['Commodity']), ev.get('Commodity_Localised')
                c_clean = (re.search(r"\$([A-Za-z0-9_]+)_Name;", c_loc, re.I).group(1).lower() if isinstance(c_loc, str) and re.search(r"\$([A-Za-z0-9_]+)_Name;", c_loc, re.I)
                             else (re.search(r"\$([A-Za-z0-9_]+)_Name;", c_raw, re.I).group(1).lower() if isinstance(c_raw, str) and re.search(r"\$([A-Za-z0-9_]+)_Name;", c_raw, re.I)
                             else re.sub(r"[\$\;\_\s]", '', str(c_loc if isinstance(c_loc,str) else c_raw).replace("_Name","")).lower().strip()))
                if not c_clean: logging.warning(f"Accepted Mission {m_id}: Empty commodity. Skipping."); continue
                missions_dict[m_id] = {'name':c_clean, 'total':ev['Count'], 'delivered':0, 'completed':False, 'reward':ev.get('Reward',0), 'destinationSystem':ev.get('DestinationSystem',''), 'destinationStation':ev.get('DestinationStation',''), 'source_event':'MissionAccepted'}
                logging.info(f"Added new mission {m_id} from 'MissionAccepted': {c_clean}, Count: {ev['Count']}")
        elif event_type == 'CargoDepot' and m_id in missions_dict:
            if ev.get('UpdateType') == 'Deliver':
                cargo_depot_deliver_count += 1
                items_delivered_in_event = ev.get('ItemsDelivered', missions_dict[m_id].get('delivered', 0))
                if items_delivered_in_event > missions_dict[m_id].get('delivered', 0):
                     logging.info(f"CargoDepot (Deliver) for MissionID {m_id}: Updating delivered count from {missions_dict[m_id].get('delivered', 0)} to {items_delivered_in_event}.")
                     missions_dict[m_id]['delivered'] = items_delivered_in_event
        elif event_type == 'MissionCompleted' and m_id in missions_dict:
            logging.info(f"Mission {m_id} completed."); missions_dict[m_id]['completed']=True
            if missions_dict[m_id].get('total', 0) > missions_dict[m_id].get('delivered', 0):
                missions_dict[m_id]['delivered'] = missions_dict[m_id].get('total',0)
        elif event_type in ['MissionFailed','MissionAbandoned'] and m_id in missions_dict:
            logging.info(f"Mission {m_id} {event_type}."); missions_dict[m_id]['completed']=True; missions_dict[m_id]['failed_or_abandoned']=True
    logging.info(f"parse_missions: Processed {accepted_count} 'MissionAccepted' and {cargo_depot_deliver_count} 'CargoDepot (Deliver)' events.")
    remaining_needs = {}; total_reward_potential = 0
    for m_id, m_data in missions_dict.items():
        if not m_data.get('completed', False) and not m_data.get('failed_or_abandoned', False) :
            need_quantity = m_data.get('total', 0) - m_data.get('delivered', 0)
            if need_quantity > 0:
                commodity_name_to_use = m_data.get('name')
                if not commodity_name_to_use: logging.warning(f"Mission ID {m_id} no commodity name for final needs. Skipping."); continue
                remaining_needs[commodity_name_to_use] = remaining_needs.get(commodity_name_to_use, 0) + need_quantity
                total_reward_potential += m_data.get('reward', 0)
    if not remaining_needs: logging.info("parse_missions: No active collection missions with outstanding needs.")
    else: logging.info(f"parse_missions: Final needs: {remaining_needs}. Reward: {total_reward_potential:,.0f} CR.")
    return remaining_needs, total_reward_potential

def suggest(required_commodities, local_market_data, current_station_market_data, max_station_dist_ls_val, include_planetary_val):
    logging.debug("Generating suggestions...")
    station_candidates = {}
    ship_pad_size_val = CURRENT_PAD_SIZE
    logging.debug(f"Suggest: ship_pad={ship_pad_size_val}, max_dist_ls={max_station_dist_ls_val}, include_planetary={include_planetary_val}")

    def process_offers(offers_list, system_name_default, system_dist_ly, is_current_station=False):
        nonlocal station_candidates
        for offer in offers_list:
            comm_name_lower = offer.get('commodityName','').lower()
            if not comm_name_lower or comm_name_lower not in required_commodities: continue

            station_type = offer.get('stationType', 'Unknown')
            if not include_planetary_val and station_type in PLANETARY_STATION_TYPES:
                logging.debug(f"--> Skipping planetary station '{offer.get('stationName', 'Unknown')}' (type: {station_type}) as per filter.")
                continue

            needed_qty = required_commodities[comm_name_lower]
            station_pad_size_raw = offer.get('maxLandingPadSize')
            station_pad_size_int = STATION_PAD_SIZE_MAP.get(str(station_pad_size_raw).upper(), station_pad_size_raw if isinstance(station_pad_size_raw, int) and station_pad_size_raw in [1,2,3] else None)

            if ship_pad_size_val != '?' and (station_pad_size_int is None or station_pad_size_int < ship_pad_size_val):
                logging.debug(f"--> Skipping station '{offer.get('stationName', 'Unknown')}' ('{station_pad_size_raw}' -> {station_pad_size_int}) - Pad size too small for ship pad {ship_pad_size_val}.")
                continue

            dist_ls = offer.get('distanceToArrival')
            if dist_ls is None and not is_current_station : dist_ls = float('inf')
            elif is_current_station : dist_ls = 0.0
            try:
                dist_ls_float = float(dist_ls) if dist_ls is not None else float('inf')
            except ValueError:
                dist_ls_float = float('inf')

            if dist_ls_float > max_station_dist_ls_val :
                logging.debug(f"--> Skipping station '{offer.get('stationName', 'Unknown')}' - Dist LS {dist_ls_float:.0f} > max {max_station_dist_ls_val:.0f}.")
                continue

            # MODIFIÉ ICI: Accès sécurisé à 'stationName' et vérification
            station_name_from_offer = offer.get('stationName')
            if not station_name_from_offer:
                logging.warning(f"Offer in system '{offer.get('systemName', system_name_default)}' for commodity '{comm_name_lower}' is missing 'stationName'. Skipping offer. Data: {offer}")
                continue

            if offer.get('stock', 0) >= needed_qty and offer.get('sellPrice', 0) > 0:
                # Utiliser station_name_from_offer qui est maintenant vérifié
                st_key = (station_name_from_offer, offer.get('systemName', system_name_default))
                cand = station_candidates.setdefault(st_key, {'distance': system_dist_ly, 'commodities':{}, 'pad_size_int': station_pad_size_int, 'distance_to_arrival': dist_ls_float, 'stationType': station_type})
                cand['commodities'][comm_name_lower] = offer['sellPrice'] # sellPrice devrait exister si on arrive ici
                if cand['pad_size_int'] is None: cand['pad_size_int'] = station_pad_size_int
                if dist_ls_float is not None and dist_ls_float < cand.get('distance_to_arrival', float('inf')): cand['distance_to_arrival'] = dist_ls_float
                if cand.get('stationType', 'Unknown') == 'Unknown' and station_type != 'Unknown': cand['stationType'] = station_type

    if local_market_data and 'markets' in local_market_data:
        for sys_name, market_info in local_market_data['markets'].items(): process_offers(market_info.get('offers',[]), sys_name, market_info['distance'])
    if current_station_market_data and 'offers' in current_station_market_data:
        current_sys = current_station_market_data.get('system', CURRENT_SYSTEM)
        process_offers(current_station_market_data['offers'], current_sys, 0.0, is_current_station=True)

    full_opts, partial_opts, complement_opts_dict = [], [], {}
    for station_key, data in station_candidates.items():
        if all(comm in data['commodities'] for comm in required_commodities.keys()): full_opts.append((station_key, data))
        elif data['commodities']: partial_opts.append((station_key, data))

    partial_opts.sort(key=lambda x: (-len(x[1]['commodities']), x[1].get('distance_to_arrival', float('inf')), x[1]['distance']))

    if not full_opts and partial_opts:
        best_partial_station_key, best_partial_data = partial_opts[0]
        commodities_covered = set(best_partial_data['commodities'].keys())
        missing_commodities = {comm: qty for comm, qty in required_commodities.items() if comm not in commodities_covered}

        for comm_to_find, needed_qty_for_missing in missing_commodities.items():
            best_source_for_missing_comm = None
            for sk_comp, data_comp in station_candidates.items():
                if comm_to_find in data_comp['commodities']:
                    current_candidate_source = {
                        'station': sk_comp[0], 'system': sk_comp[1],
                        'distance': data_comp['distance'],
                        'price': data_comp['commodities'][comm_to_find],
                        'pad_size_int': data_comp.get('pad_size_int'),
                        'distance_to_arrival': data_comp.get('distance_to_arrival', float('inf')),
                        'stationType': data_comp.get('stationType', 'Unknown')
                    }
                    current_sort_key = (current_candidate_source.get('distance_to_arrival', float('inf')), current_candidate_source['distance'])
                    best_current_sort_key = (float('inf'), float('inf'))
                    if best_source_for_missing_comm:
                        best_current_sort_key = (best_source_for_missing_comm.get('distance_to_arrival', float('inf')), best_source_for_missing_comm['distance'])
                    if best_source_for_missing_comm is None or current_sort_key < best_current_sort_key:
                        best_source_for_missing_comm = current_candidate_source
            if best_source_for_missing_comm:
                complement_opts_dict[comm_to_find] = best_source_for_missing_comm
    return full_opts, partial_opts, complement_opts_dict

def get_last_db_update_time_str():
    if os.path.exists(LOCAL_SELLERS_DATA_FILE):
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            updated_at_iso = data.get("updatedAt")
            if updated_at_iso:
                try: dt_utc = datetime.fromisoformat(updated_at_iso.replace('Z', '+00:00'))
                except ValueError: dt_utc = datetime.fromisoformat(updated_at_iso); dt_utc = dt_utc.replace(tzinfo=timezone.utc) if dt_utc.tzinfo is None else dt_utc
                return f"Local DB: {dt_utc.astimezone(None).strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception: logging.exception("Error parsing DB update date"); return "Local DB: Date Error"
    return "Local DB: Not found"

def run_async_update(radius_str_val):
    global CURRENT_SYSTEM, CURRENT_STATION, root, status_lbl, text_out, update_btn, db_status_label, unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, progress_bar

    logging.info("Starting async DB update...")
    if CURRENT_SYSTEM == "?" or "Error" in CURRENT_SYSTEM or "Journal not found" in CURRENT_SYSTEM :
        logging.warning(f"Invalid current system ('{CURRENT_SYSTEM}') for DB update. Please refresh location/ship first.")
        if root and status_lbl: root.after(0, lambda: status_lbl.config(text="Invalid system for DB update. Refresh location."))
        if root and update_btn: root.after(0, lambda: update_btn.config(state=tk.NORMAL))
        if root and progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
        return

    try: radius_val = float(radius_str_val); assert radius_val > 0
    except (ValueError, AssertionError):
        msg = "Settings Error: Invalid radius for DB update."; logging.error(msg)
        if root:
            root.after(0, lambda: (text_out.insert(tk.END, msg + "\n"), status_lbl.config(text=msg), update_btn.config(state=tk.NORMAL)))
            if unknown_pad_frame and unknown_pad_frame.winfo_ismapped():
                if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
                if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.NORMAL))
            if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
        return

    if root and status_lbl: root.after(0, lambda: status_lbl.config(text="Updating DB..."))
    if root and progress_bar: root.after(0, lambda: (progress_bar.grid(column=0, row=6, columnspan=4, sticky="ew", pady=(2,5), padx=5), progress_bar.start()))

    async def update_task_wrapper():
        await _update_databases(radius_val)

    def run_in_thread():
        try:
            asyncio.run(update_task_wrapper())
            if root:
                 root.after(0, lambda: (status_lbl.config(text="DB Update finished."),
                                       db_status_label.config(text=get_last_db_update_time_str())))
        except Exception as e:
            logging.exception("Error running async update task:")
            msg = f"Async Update Error: {e}"
            if root:
                root.after(0, lambda: (status_lbl.config(text=msg), text_out.insert(tk.END, msg + "\n")))
        finally:
            if root:
                root.after(0, lambda: update_btn.config(state=tk.NORMAL))
                if unknown_pad_frame and unknown_pad_frame.winfo_ismapped():
                     if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
                     if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.NORMAL))
                if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))

    threading.Thread(target=run_in_thread, daemon=True).start()

async def _update_databases(radius_val):
    if not CURRENT_SYSTEM or CURRENT_SYSTEM == "?" or "Error" in CURRENT_SYSTEM or "Journal not found" in CURRENT_SYSTEM:
        logging.warning(f"DB Update: Current system ('{CURRENT_SYSTEM}') is invalid or unknown. Aborting DB update.")
        return
    logging.info(f"Updating databases for system {CURRENT_SYSTEM} with radius {radius_val} LY...")
    departure_task = download_departure(CURRENT_SYSTEM, CURRENT_STATION if CURRENT_STATION != "?" else None)
    local_task = download_local(CURRENT_SYSTEM, radius_val)
    results = await asyncio.gather(departure_task, local_task, return_exceptions=True)
    if isinstance(results[0], Exception): logging.error(f"Departure data download failed/errored: {results[0]}")
    else: logging.info("Departure data download attempt finished.")
    if isinstance(results[1], Exception) or results[1] is None: logging.error(f"Local data download failed/errored: {results[1]}")
    else: logging.info("Local data download successful.")

def run_analysis_thread(radius_str, age_str, station_dist_str, sort_by_str_gui, include_planetary_bool):
    global CURRENT_SYSTEM, CURRENT_STATION, CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE, root, status_lbl, text_out, db_status_label, progress_bar

    logging.info(f"run_analysis_thread: Starting with radius='{radius_str}', age='{age_str}', station_dist='{station_dist_str}', sort='{sort_by_str_gui}', include_planetary='{include_planetary_bool}'")
    try:
        radius = float(radius_str); max_data_age_days = int(age_str); max_station_dist_ls = float(station_dist_str)
        if radius <= 0: raise ValueError("Radius LY must be positive.")
        if max_data_age_days < 0: raise ValueError("DB Age must be >= 0.")
        if max_station_dist_ls < 0: raise ValueError("Station Distance LS must be >= 0.")
    except ValueError as e:
        logging.error(f"run_analysis_thread: Invalid numerical parameters: {e}")
        if root and status_lbl: root.after(0, lambda: status_lbl.config(text=f"Settings Error: {e}"))
        if root and progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
        return

    if CURRENT_SYSTEM == "?" or "Error" in CURRENT_SYSTEM or "Journal not found" in CURRENT_SYSTEM:
        msg = "Current location/ship unknown or invalid. Analysis impossible. Please refresh."; logging.error(f"run_analysis_thread: {msg}")
        if root and text_out: root.after(0, lambda: text_out.insert(tk.END, msg + "\n"))
        if root and status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        return

    logging.info("run_analysis_thread: Location/ship OK. Loading journal events for mission analysis.")
    try:
        if not EFFECTIVE_JOURNAL_DIR or EFFECTIVE_JOURNAL_DIR in ["Not Found", "Error processing journals", "Auto-detecting..."]:
            raise FileNotFoundError(f"Effective journal directory is not valid: {EFFECTIVE_JOURNAL_DIR}")
        journal_events = load_journal_events(EFFECTIVE_JOURNAL_DIR)
        logging.info(f"run_analysis_thread: Loaded {len(journal_events)} events from journal '{EFFECTIVE_JOURNAL_DIR}' for mission analysis.")
    except FileNotFoundError as e:
        logging.exception("run_analysis_thread: Error finding/accessing journal directory for mission analysis:")
        msg = f"Journal directory error: {e}"
        if root: root.after(0, lambda m=msg: (text_out.insert(tk.END, m + "\n"), status_lbl.config(text=m)))
        return
    except Exception as e:
        logging.exception("run_analysis_thread: Unexpected error during journal loading for mission analysis:")
        msg = f"Journal loading error: {e}"
        if root: root.after(0, lambda m=msg: (text_out.insert(tk.END, m + "\n"), status_lbl.config(text=m)))
        return

    if root and status_lbl: root.after(0, lambda: status_lbl.config(text="Loading/refreshing market data..."))

    departure_market_json, local_sellers_json = None, None
    refresh_departure = True
    if os.path.exists(DEPARTURE_DATA_FILE) and CURRENT_STATION != "?" and CURRENT_STATION is not None:
        try:
            with open(DEPARTURE_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            updated_at = datetime.fromisoformat(data['updatedAt'].replace('Z', '+00:00'))
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
            if data.get('system') == CURRENT_SYSTEM and data.get('station') == CURRENT_STATION and age_seconds < (max_data_age_days * 86400):
                departure_market_json = data; refresh_departure = False; logging.info(f"Using recent departure data from {DEPARTURE_DATA_FILE}.")
            else: logging.info("Departure data is old or for a different station/system. Will refresh.")
        except Exception as e_cache: logging.warning(f"Error reading departure cache from {DEPARTURE_DATA_FILE} ({e_cache}), will refresh.")

    if refresh_departure and (CURRENT_STATION != "?" and CURRENT_STATION is not None) and CURRENT_SYSTEM != "?" :
        if root and status_lbl: root.after(0, lambda: status_lbl.config(text=f"Refreshing departure data for {CURRENT_STATION}..."))
        try:
            asyncio.run(download_departure(CURRENT_SYSTEM, CURRENT_STATION))
            if os.path.exists(DEPARTURE_DATA_FILE):
                with open(DEPARTURE_DATA_FILE, 'r', encoding='utf-8') as f: departure_market_json = json.load(f)
                logging.info(f"Fresh departure data successfully re-loaded from {DEPARTURE_DATA_FILE} after download.")
            else: logging.error(f"DEPARTURE_DATA_FILE not found after download for {CURRENT_STATION}."); departure_market_json = None
        except Exception as e_download: logging.exception(f"Failed to refresh departure data for {CURRENT_STATION}: {e_download}"); departure_market_json = None
    elif CURRENT_STATION == "?" or CURRENT_STATION is None:
        logging.info("Skipping departure data refresh: current station is unknown.")
        departure_market_json = None

    refresh_local = True
    if os.path.exists(LOCAL_SELLERS_DATA_FILE) and CURRENT_SYSTEM != "?":
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            updated_at = datetime.fromisoformat(data['updatedAt'].replace('Z', '+00:00'))
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
            if data.get('sourceSystem') == CURRENT_SYSTEM and data.get('radius', 0) >= radius and age_seconds < (max_data_age_days * 86400):
                local_sellers_json = data; refresh_local = False; logging.info(f"Using recent local data from {LOCAL_SELLERS_DATA_FILE} (radius {data.get('radius',0)} LY).")
            else: logging.info("Local data is old, different system, or insufficient radius. Will refresh.")
        except Exception as e_cache: logging.warning(f"Error reading local cache from {LOCAL_SELLERS_DATA_FILE} ({e_cache}), will refresh.")

    if refresh_local and CURRENT_SYSTEM != "?":
        if root and status_lbl: root.after(0, lambda: status_lbl.config(text=f"Refreshing local data ({radius} LY)..."))
        try:
            local_sellers_json = asyncio.run(download_local(CURRENT_SYSTEM, radius))
            if local_sellers_json is None: logging.error("Local data download failed or returned None.")
            else: logging.info("Fresh local data downloaded and assigned.")
            if root and db_status_label: root.after(0, lambda: db_status_label.config(text=get_last_db_update_time_str()))
        except Exception as e_download: logging.exception(f"Error during local data refresh for {CURRENT_SYSTEM}: {e_download}"); local_sellers_json = None
    elif CURRENT_SYSTEM == "?":
        logging.info("Skipping local data refresh: current system is unknown.")
        local_sellers_json = None

    if not local_sellers_json or not local_sellers_json.get('markets'):
        msg = "Could not get valid local seller data. Check API connection or current system."; logging.error(f"run_analysis_thread: {msg}")
        if root: root.after(0, lambda m=msg: (text_out.insert(tk.END, m + "\n"), status_lbl.config(text="Error: Local market data.")));
        return

    logging.info("run_analysis_thread: Market data OK. Calling parse_missions.")
    if root and status_lbl: root.after(0, lambda: status_lbl.config(text="Parsing missions..."))
    needs, total_rewards = parse_missions(journal_events)
    logging.info(f"run_analysis_thread: parse_missions returned {len(needs)} needed types. Rewards: {total_rewards}")

    if not needs:
        msg = "No active collection missions requiring commodities found."; logging.info(f"run_analysis_thread: {msg}")
        if root: root.after(0, lambda m=msg: (text_out.insert(tk.END, m + "\n"), status_lbl.config(text=m), update_commodities_display({})));
        return

    if root and status_lbl: root.after(0, lambda: (update_commodities_display(needs), status_lbl.config(text="Analyzing options...")))

    logging.info(f"run_analysis_thread: Calling suggest with max_station_dist_ls = {max_station_dist_ls}, include_planetary = {include_planetary_bool}.")
    full_opts, partial_opts, complement_opts_result = suggest(needs, local_sellers_json, departure_market_json, max_station_dist_ls, include_planetary_bool)

    output_lines = [f"Needs for {len(needs)} type(s) ({sum(needs.values())}u). Reward: {total_rewards:,.0f} CR.",
                    f"Ship: {CURRENT_SHIP_TYPE} (Pad {CURRENT_PAD_SIZE}), Cargo: {CURRENT_CARGO_CAPACITY} t.",
                    f"Estimated trips: {math.ceil(sum(needs.values()) / CURRENT_CARGO_CAPACITY) if CURRENT_CARGO_CAPACITY > 0 else 'N/A'}",
                    f"Station distance filter: max {max_station_dist_ls:.0f} LS.",
                    f"Planetary stations: {'Included' if include_planetary_bool else 'Excluded'}.",
                    "—" * 40]
    profit_calc = lambda data: total_rewards - sum(needs.get(cn,0) * cp for cn,cp in data['commodities'].items())
    sort_key_map = {'s': lambda x: (x[1].get('distance_to_arrival', float('inf')), x[1]['distance']),
                    'b': lambda x: -profit_calc(x[1]),
                    'd': lambda x: x[1]['distance']}
    full_opts.sort(key=sort_key_map[sort_by_str_gui])

    if full_opts:
        output_lines.append("FULL Supply Options:")
        for (st_name, sy_name), data in full_opts[:5]:
            dist_ls_info = f" ({data.get('distance_to_arrival', float('inf')):.0f} LS)" if data.get('distance_to_arrival', float('inf')) != float('inf') else " (? LS)"
            pad_info = f" (Pad {data.get('pad_size_int', '?')})"
            cost = sum(needs.get(cn,0) * cp for cn, cp in data['commodities'].items())
            profit = total_rewards - cost
            output_lines.append(f"  Station: {st_name}{dist_ls_info}{pad_info} ({sy_name})")
            output_lines.append(f"    Distance LY: {data['distance']:.1f} | Cost: {cost:,.0f} CR | Profit: {profit:,.0f} CR")
            output_lines.append("")
    else: output_lines.extend([f"No single station for FULL supply.", "—" * 40])

    output_lines.append(f"PARTIAL Supply Options (Max 3 displayed, sorted by coverage then distance):")
    if not partial_opts: output_lines.append("  No partial options found.")
    for i, ((st_name, sy_name), data) in enumerate(partial_opts[:3]):
        dist_ls_info = f" ({data.get('distance_to_arrival', float('inf')):.0f} LS)" if data.get('distance_to_arrival', float('inf')) != float('inf') else " (? LS)"
        pad_info = f" (Pad {data.get('pad_size_int', '?')})"
        num_covered = len(data['commodities']); cost_partial = sum(needs[cn] * cp for cn, cp in data['commodities'].items() if cn in needs)
        output_lines.append(f"  Option {i+1}: {st_name}{dist_ls_info}{pad_info} ({sy_name})")
        output_lines.append(f"    Distance LY: {data['distance']:.1f} | Covers {num_covered}/{len(needs)} types.")
        output_lines.append(f"    Commodities (partial cost for these: {cost_partial:,.0f} CR):")
        for comm, price_val in data['commodities'].items():
             if comm in needs: output_lines.append(f"      - {comm.title()}: {needs[comm]} @ {price_val:,.0f} CR/u")
        missing_from_this_partial = {c:q for c,q in needs.items() if c not in data['commodities']}
        if missing_from_this_partial: output_lines.append(f"    Still Missing: {', '.join(m.title() for m in missing_from_this_partial.keys())}")
        output_lines.append("")

    if complement_opts_result and partial_opts:
        output_lines.extend(["—" * 40, f"Complementary Sources (based on best partial option above):"])
        (bp_st_name, bp_sy_name), bp_data = partial_opts[0]
        bp_cost = sum(needs[cn] * cp for cn, cp in bp_data['commodities'].items() if cn in needs and cp is not None)

        output_lines.append(f"  From Best Partial: {bp_st_name} ({bp_sy_name}) supplies:")
        for comm, price_val_bp in bp_data['commodities'].items():
            if comm in needs: output_lines.append(f"    - {comm.title()}: {needs[comm]} @ {price_val_bp if price_val_bp else 'N/A':,.0f} CR/u")

        total_complement_cost = 0
        all_items_covered_by_complement = True
        missing_after_best_partial = {
            comm: qty for comm, qty in needs.items()
            if comm not in bp_data['commodities']
        }

        if missing_after_best_partial:
            output_lines.append(f"  To complete, from other stations:")
            for comm_needed, info_complement in complement_opts_result.items():
                if comm_needed in missing_after_best_partial:
                    comp_pad = f" (Pad {info_complement.get('pad_size_int', '?')})"
                    comp_dist_ls = f" ({info_complement.get('distance_to_arrival', float('inf')):.0f} LS)" if info_complement.get('distance_to_arrival', float('inf')) != float('inf') else " (? LS)"
                    output_lines.append(f"    For {comm_needed.title()}: visit {info_complement['station']}{comp_dist_ls}{comp_pad} ({info_complement['system']}) at {info_complement['distance']:.1f} LY")
                    cost_this_complement = needs[comm_needed] * info_complement['price'] if info_complement['price'] is not None else 0
                    output_lines.append(f"      - {comm_needed.title()}: {needs[comm_needed]} @ {info_complement['price'] if info_complement['price'] else 'N/A':,.0f} CR/u (Cost: {cost_this_complement:,.0f} CR)")
                    total_complement_cost += cost_this_complement
            for comm_still_missing in missing_after_best_partial:
                if comm_still_missing not in complement_opts_result:
                    all_items_covered_by_complement = False
                    output_lines.append(f"    Could not find a complementary source for: {comm_still_missing.title()}")
                    break
            if all_items_covered_by_complement and missing_after_best_partial:
                total_combined_cost = bp_cost + total_complement_cost
                output_lines.extend([f"  Total Combined Cost (Best Partial + Complements): {total_combined_cost:,.0f} CR",
                                     f"  Total Combined Profit: {total_rewards - total_combined_cost:,.0f} CR"])
            elif not missing_after_best_partial:
                 output_lines.append("  (Best partial option already covers all needs - no complements needed from other stations for it)")
            else:
                 output_lines.append("  (Could not find complementary sources for all remaining items from the best partial)")
        elif not missing_after_best_partial and partial_opts:
            output_lines.append(f"  Best partial option ({bp_st_name}) already covers all needs.")
            total_combined_cost = bp_cost
            output_lines.extend([f"  Total Cost (from best partial): {bp_cost:,.0f} CR",
                                 f"  Total Profit: {total_rewards - bp_cost:,.0f} CR"])

    final_output_str = "\n".join(output_lines)
    if root: root.after(0, lambda: (text_out.delete('1.0', tk.END), text_out.insert(tk.END, final_output_str + "\n\n"), status_lbl.config(text="Analysis finished.")))
    logging.info("run_analysis_thread: Analysis display updated. Thread finished.")


# ---- GUI & Styling ----
root = None; global_label = None; ship_label = None; cargo_label = None; db_status_label = None
status_lbl = None; text_out = None; commod_list = None; total_lbl = None
radius_var = None; age_var = None; station_dist_var = None; sort_var = None
include_planetary_var = None
update_btn = None; launch_btn = None; refresh_loc_btn = None; save_settings_btn = None
unknown_pad_frame = None; unknown_pad_entry = None; save_pad_size_btn = None; unknown_pad_ship_label = None
journal_dir_label_var = None
change_journal_dir_btn = None
restore_defaults_btn = None
progress_bar = None

def update_journal_dir_label_text():
    global EFFECTIVE_JOURNAL_DIR
    if journal_dir_label_var:
        path_to_display = APP_SETTINGS.get('custom_journal_dir')
        if path_to_display:
            journal_dir_label_var.set(f"Journal Dir: {path_to_display}")
        else:
            if EFFECTIVE_JOURNAL_DIR and EFFECTIVE_JOURNAL_DIR not in ["Auto-detecting...", "Not Found", "Error processing journals"]:
                 journal_dir_label_var.set(f"Journal Dir (Auto): {EFFECTIVE_JOURNAL_DIR}")
            elif EFFECTIVE_JOURNAL_DIR == "Not Found":
                 journal_dir_label_var.set("Journal Dir: Not Found (Auto-detect failed)")
            elif EFFECTIVE_JOURNAL_DIR == "Error processing journals":
                 journal_dir_label_var.set("Journal Dir: Error during processing (Auto)")
            else:
                 journal_dir_label_var.set("Journal Dir: Auto-detect")

def create_gui():
    global root, global_label, ship_label, cargo_label, db_status_label, status_lbl, text_out, commod_list, total_lbl
    global radius_var, age_var, station_dist_var, sort_var, include_planetary_var
    global update_btn, launch_btn, refresh_loc_btn, save_settings_btn
    global unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, unknown_pad_ship_label
    global journal_dir_label_var, change_journal_dir_btn, restore_defaults_btn
    global progress_bar

    logging.debug("Creating GUI.")
    root = tk.Tk(); root.title("Elite: Dangerous Mission Optimizer"); root.configure(bg='#1a1a1a')
    style = ttk.Style(root); style.theme_use('clam')
    ed_orange = '#FF8C00'; ed_dark_grey = '#1c1c1c'; ed_medium_grey = '#2c2c2c'; ed_light_grey_text = '#c0c0c0'; ed_white_text = '#FFFFFF'; ed_button_bg = '#3c3c3c'
    style.configure('.', background=ed_dark_grey, foreground=ed_orange, font=('Segoe UI', 10))
    style.configure('TFrame', background=ed_dark_grey)
    style.configure('TLabel', background=ed_dark_grey, foreground=ed_orange)
    style.configure('Header.TLabel', font=('Segoe UI', 11, 'bold'))
    style.configure('Status.TLabel', foreground=ed_light_grey_text, font=('Segoe UI', 9, 'italic'))
    style.configure('Path.TLabel', foreground=ed_light_grey_text, font=('Segoe UI', 8))
    style.configure('TButton', background=ed_button_bg, foreground=ed_orange, font=('Segoe UI', 10, 'bold'), borderwidth=1, relief='flat')
    style.map('TButton', background=[('active', '#4c4c4c'), ('pressed', '#5c4c4c')], relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
    style.configure('TRadiobutton', background=ed_dark_grey, foreground=ed_orange, indicatorcolor=ed_button_bg)
    style.map('TRadiobutton', background=[('active', ed_medium_grey)], indicatorcolor=[('selected', ed_orange), ('pressed', ed_orange)])
    style.configure('TCheckbutton', background=ed_dark_grey, foreground=ed_orange, indicatorcolor=ed_button_bg)
    style.map('TCheckbutton', background=[('active', ed_medium_grey)], indicatorcolor=[('selected', ed_orange), ('pressed', ed_orange)])
    style.configure('TEntry', fieldbackground=ed_medium_grey, foreground=ed_white_text, insertcolor=ed_white_text, borderwidth=1, relief='flat')
    style.configure('Horizontal.TProgressbar', troughcolor=ed_medium_grey, background=ed_orange, lightcolor=ed_orange, darkcolor=ed_orange, bordercolor=ed_dark_grey)


    frm = ttk.Frame(root, padding="10 10 10 10"); frm.pack(fill=tk.BOTH, expand=True)
    frm.columnconfigure(0, weight=1); frm.columnconfigure(1, weight=1); frm.columnconfigure(2, weight=1); frm.columnconfigure(3, weight=0)

    top_info_frame = ttk.Frame(frm); top_info_frame.grid(column=0, row=0, columnspan=4, sticky="ew", pady=(0,5))
    for i in range(6): top_info_frame.columnconfigure(i, weight=1 if i < 3 else 0)
    global_label = ttk.Label(top_info_frame, text=f"Location: {CURRENT_SYSTEM} / {CURRENT_STATION}", style='Header.TLabel'); global_label.grid(column=0, row=0, sticky=tk.W, padx=5)
    ship_label = ttk.Label(top_info_frame, text=f"Ship: {CURRENT_SHIP_TYPE} (Pad {CURRENT_PAD_SIZE})"); ship_label.grid(column=1, row=0, sticky=tk.W, padx=5)
    cargo_label = ttk.Label(top_info_frame, text=f"Cargo Capacity: {CURRENT_CARGO_CAPACITY} t"); cargo_label.grid(column=2, row=0, sticky=tk.W, padx=5)
    db_status_label = ttk.Label(top_info_frame, text=get_last_db_update_time_str()); db_status_label.grid(column=3, row=0, columnspan=3, sticky=tk.E, padx=5)

    journal_frame = ttk.Frame(frm); journal_frame.grid(column=0, row=1, columnspan=4, sticky="ew", pady=(0,5))
    journal_frame.columnconfigure(0, weight=1); journal_frame.columnconfigure(1, weight=0)
    journal_dir_label_var = tk.StringVar()
    update_journal_dir_label_text()
    journal_dir_display_label = ttk.Label(journal_frame, textvariable=journal_dir_label_var, style='Path.TLabel', anchor=tk.W);
    journal_dir_display_label.grid(column=0, row=0, sticky=tk.EW, padx=5)
    change_journal_dir_btn = ttk.Button(journal_frame, text="Change Journal Dir", command=on_select_journal_dir_pressed, width=20)
    change_journal_dir_btn.grid(column=1, row=0, sticky=tk.E, padx=5)

    params_frame = ttk.Frame(frm); params_frame.grid(column=0, row=2, columnspan=4, sticky="ew", pady=5)
    params_frame.columnconfigure(1, weight=1); params_frame.columnconfigure(3, weight=1); params_frame.columnconfigure(5, weight=1); params_frame.columnconfigure(7, weight=0); params_frame.columnconfigure(8, weight=1)
    radius_var = tk.StringVar(value=str(APP_SETTINGS.get('radius', DEFAULT_RADIUS)))
    age_var = tk.StringVar(value=str(APP_SETTINGS.get('max_age_days', DEFAULT_MAX_AGE_DAYS)))
    station_dist_var = tk.StringVar(value=str(APP_SETTINGS.get('max_station_distance_ls', DEFAULT_MAX_STATION_DISTANCE_LS)))
    include_planetary_var = tk.BooleanVar(value=APP_SETTINGS.get('include_planetary', DEFAULT_INCLUDE_PLANETARY))
    sort_var = tk.StringVar(value=APP_SETTINGS.get('sort_option', RESET_DEFAULT_SORT_OPTION))
    ttk.Label(params_frame, text="Radius (LY):").grid(column=0, row=0, sticky=tk.W, padx=(0,2)); ttk.Entry(params_frame, width=7, textvariable=radius_var).grid(column=1, row=0, sticky=tk.EW, padx=(0,5))
    ttk.Label(params_frame, text="DB Age (d):").grid(column=2, row=0, sticky=tk.W, padx=(5,2)); ttk.Entry(params_frame, width=4, textvariable=age_var).grid(column=3, row=0, sticky=tk.EW, padx=(0,5))
    ttk.Label(params_frame, text="Sta. Dist (LS):").grid(column=4, row=0, sticky=tk.W, padx=(5,2)); ttk.Entry(params_frame, width=7, textvariable=station_dist_var).grid(column=5, row=0, sticky=tk.EW, padx=(0,10))
    planetary_cb = ttk.Checkbutton(params_frame, text="Include Planetary", variable=include_planetary_var)
    planetary_cb.grid(column=6, row=0, sticky=tk.W, padx=(10,5))
    update_btn = ttk.Button(params_frame, text="Update DB", command=on_update_db_pressed, width=10); update_btn.grid(column=7, row=0, sticky=tk.E, padx=5)

    actions_frame = ttk.Frame(frm); actions_frame.grid(column=0, row=3, columnspan=4, sticky="ew", pady=5)
    col_weights_actions = {0:1, 1:2, 2:0}; {actions_frame.columnconfigure(c, weight=w) for c,w in col_weights_actions.items()}
    sort_options_frame = ttk.Frame(actions_frame); sort_options_frame.grid(column=0, row=0, sticky="w", padx=(0,10)); ttk.Label(sort_options_frame, text="Sort by:").pack(side=tk.LEFT, anchor=tk.W)
    ttk.Radiobutton(sort_options_frame, text='Dist. LY', variable=sort_var, value='d').pack(side=tk.LEFT, anchor=tk.W, padx=2)
    ttk.Radiobutton(sort_options_frame, text='Profit', variable=sort_var, value='b').pack(side=tk.LEFT, anchor=tk.W, padx=2)
    ttk.Radiobutton(sort_options_frame, text='Dist. LS', variable=sort_var, value='s').pack(side=tk.LEFT, anchor=tk.W, padx=2)
    commod_display_frame = ttk.Frame(actions_frame); commod_display_frame.grid(column=1, row=0, sticky="ew")
    col_weights_commod = {0:0, 1:1, 2:0}; {commod_display_frame.columnconfigure(c, weight=w) for c,w in col_weights_commod.items()}
    ttk.Label(commod_display_frame, text='To Collect:').grid(row=0, column=0, sticky="w", padx=(0,5))
    commod_list = tk.Listbox(commod_display_frame, height=3, bg=ed_medium_grey, fg=ed_white_text, highlightbackground=ed_dark_grey, relief='flat', borderwidth=1, exportselection=False); commod_list.grid(row=0, column=1, sticky="ew")
    total_lbl = ttk.Label(commod_display_frame, text='Total: 0'); total_lbl.grid(row=0, column=2, sticky="w", padx=(5,0))
    launch_btn = ttk.Button(actions_frame, text="🚀 Launch", command=on_launch_pressed); launch_btn.grid(column=2, row=0, sticky="e", padx=5, ipady=2)

    management_frame = ttk.Frame(frm); management_frame.grid(column=0, row=4, columnspan=4, sticky="ew", pady=(5,5))
    management_frame.columnconfigure(0, weight=1); management_frame.columnconfigure(1, weight=0); management_frame.columnconfigure(2, weight=0); management_frame.columnconfigure(3, weight=0)
    refresh_loc_btn = ttk.Button(management_frame, text="🔄 Refresh Loc/Ship", width=20, command=refresh_location_and_ship_display); refresh_loc_btn.grid(column=1, row=0, sticky=tk.E, padx=5)
    save_settings_btn = ttk.Button(management_frame, text="💾 Save Settings", width=15, command=on_save_settings_pressed); save_settings_btn.grid(column=2, row=0, sticky=tk.E, padx=5)
    restore_defaults_btn = ttk.Button(management_frame, text="Restore Defaults", width=18, command=on_restore_defaults_pressed); restore_defaults_btn.grid(column=3, row=0, sticky=tk.E, padx=5)

    status_lbl = ttk.Label(frm, text="Ready.", style='Status.TLabel'); status_lbl.grid(column=0, row=5, columnspan=4, sticky=tk.EW, pady=(5,0), padx=5)

    progress_bar = ttk.Progressbar(frm, orient=tk.HORIZONTAL, length=200, mode='indeterminate', style='Horizontal.TProgressbar')

    unknown_pad_frame = ttk.Frame(frm)
    unknown_pad_ship_label = ttk.Label(unknown_pad_frame, text="Unknown ship:"); unknown_pad_ship_label.pack(side=tk.LEFT, padx=5)
    ttk.Label(unknown_pad_frame, text="Pad Size (1/2/3):").pack(side=tk.LEFT, padx=5);
    unknown_pad_entry = ttk.Entry(unknown_pad_frame, width=5); unknown_pad_entry.pack(side=tk.LEFT, padx=5)
    save_pad_size_btn = ttk.Button(unknown_pad_frame, text="Save Pad", command=on_save_pad_size_pressed); save_pad_size_btn.pack(side=tk.LEFT, padx=5)

    text_out = ScrolledText(frm, width=100, height=25, bg=ed_medium_grey, fg=ed_white_text, insertbackground=ed_white_text, relief='flat', borderwidth=1, wrap=tk.WORD)
    text_out.grid(column=0, row=8, columnspan=4, sticky="nsew", pady=(5,0), padx=5); frm.rowconfigure(8, weight=1)


    if root:
        root.after(100, refresh_location_and_ship_display)

    logging.debug("Starting Tkinter mainloop.")
    root.mainloop()
    logging.debug("Tkinter mainloop finished.")


def refresh_location_and_ship_display():
    global CURRENT_SYSTEM, CURRENT_STATION, CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE
    global global_label, ship_label, cargo_label, status_lbl, refresh_loc_btn, root
    global unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, unknown_pad_ship_label, progress_bar

    if not all([root, global_label, ship_label, cargo_label]):
        logging.warning("GUI elements not ready for location/ship refresh."); return

    if refresh_loc_btn: root.after(0, lambda: refresh_loc_btn.config(state=tk.DISABLED))
    if status_lbl: root.after(0, lambda: status_lbl.config(text="Refreshing location/ship..."))
    if progress_bar: root.after(0, lambda: (progress_bar.grid(column=0, row=6, columnspan=4, sticky="ew", pady=(2,5), padx=5), progress_bar.start()))


    def _task():
        cs, cst, ship_t, cargo_c, pad_s = get_current_location_and_ship_info()
        if root: root.after(0, lambda: _update_gui_loc_ship_from_thread_results(cs, cst, ship_t, cargo_c, pad_s))

    threading.Thread(target=_task, daemon=True).start()

def _update_gui_loc_ship_from_thread_results(current_sys_val, current_sta_val, ship_type_val, cargo_cap_val, pad_size_val):
    global CURRENT_SYSTEM, CURRENT_STATION, CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE
    global global_label, ship_label, cargo_label, status_lbl, refresh_loc_btn
    global unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, unknown_pad_ship_label, progress_bar

    CURRENT_SYSTEM, CURRENT_STATION = current_sys_val, current_sta_val
    CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE = ship_type_val, cargo_cap_val, pad_size_val

    if not all([root, global_label, ship_label, cargo_label]):
        logging.warning("GUI elements not ready for _update_gui_loc_ship."); return

    update_journal_dir_label_text()

    if CURRENT_SYSTEM == "Journal not found" or CURRENT_SYSTEM == "Error - No Journal":
        global_label.config(text="Location: Journal Error/Not Found");
        ship_label.config(text="Ship: ? (Pad ?)");
        cargo_label.config(text="Cargo Capacity: ?")
        if status_lbl: status_lbl.config(text="Error: Journal directory issue or no journal found.")
        if unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid_remove()
    else:
        global_label.config(text=f"Location: {CURRENT_SYSTEM} / {CURRENT_STATION if CURRENT_STATION and CURRENT_STATION != '?' else 'N/A'}")
        ship_label.config(text=f"Ship: {CURRENT_SHIP_TYPE} (Pad {CURRENT_PAD_SIZE})")
        cargo_label.config(text=f"Cargo Capacity: {CURRENT_CARGO_CAPACITY} t")
        status_msg = "Location and Ship refreshed."

        if CURRENT_PAD_SIZE == '?':
            status_msg = "Ship detected, pad size unknown. Enter it below."
            if unknown_pad_frame:
                if unknown_pad_ship_label: unknown_pad_ship_label.config(text=f"Unknown ship '{CURRENT_SHIP_TYPE}':")
                if not unknown_pad_frame.winfo_ismapped():
                    unknown_pad_frame.grid(column=0, row=7, columnspan=4, sticky="ew", pady=5)
                if unknown_pad_entry: unknown_pad_entry.delete(0, tk.END); unknown_pad_entry.focus_set(); unknown_pad_entry.config(state=tk.NORMAL)
                if save_pad_size_btn: save_pad_size_btn.config(state=tk.NORMAL)
        else:
            if unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid_remove()

        if status_lbl: status_lbl.config(text=status_msg)

    if refresh_loc_btn: root.after(0, lambda: refresh_loc_btn.config(state=tk.NORMAL))
    if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
    logging.info(f"_update_gui_loc_ship: GUI updated with Sys='{CURRENT_SYSTEM}', Ship='{CURRENT_SHIP_TYPE}'.")


def update_commodities_display(needs_dict):
    global commod_list, total_lbl, root
    if not all([root, commod_list, total_lbl]): logging.warning("GUI commod_list/total_lbl not ready."); return
    def _update():
        if not commod_list or not total_lbl : return
        commod_list.delete(0, tk.END)
        if needs_dict:
            commod_list.config(height=max(1, min(len(needs_dict), 5)))
            total_units = sum(needs_dict.values())
            for name, qty in needs_dict.items(): commod_list.insert(tk.END, f"{name.title()}: {qty}")
            total_lbl.config(text=f"Total: {total_units} u. ({len(needs_dict)} types)")
        else:
            commod_list.config(height=1); commod_list.insert(tk.END, "No active missions"); total_lbl.config(text="Total: 0")
    if root: root.after(0, _update)

def on_update_db_pressed():
    global update_btn, radius_var, root, status_lbl, text_out, unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, progress_bar

    if not all([root, update_btn, radius_var, status_lbl, text_out]):
        logging.warning("GUI elements not ready for on_update_db_pressed."); return

    if CURRENT_SYSTEM == "?" or "Error" in CURRENT_SYSTEM or "Journal not found" in CURRENT_SYSTEM:
        msg = "Cannot update DB: Current system is unknown or invalid. Please refresh location/ship first."
        logging.warning(msg)
        if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        if text_out: root.after(0, lambda: text_out.insert(tk.END, msg + "\n"))
        return

    root.after(0, lambda: update_btn.config(state=tk.DISABLED))
    if unknown_pad_frame and unknown_pad_frame.winfo_ismapped():
        if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.DISABLED))
        if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.DISABLED))

    if status_lbl: root.after(0, lambda: status_lbl.config(text="Validating settings for DB Update..."))
    try:
        radius_val = float(radius_var.get())
        if radius_val <= 0: raise ValueError("Radius must be positive.")
        threading.Thread(target=run_async_update, args=(radius_var.get(),), daemon=True).start()
    except ValueError as e:
        msg = f"Settings Error: Invalid radius for DB update: {e}"; logging.error(msg)
        if root:
            root.after(0, lambda: (text_out.insert(tk.END, msg + "\n"), status_lbl.config(text=msg), update_btn.config(state=tk.NORMAL)))
            if unknown_pad_frame and unknown_pad_frame.winfo_ismapped():
                 if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
                 if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.NORMAL))
            if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))

def on_launch_pressed():
    global launch_btn, update_btn, refresh_loc_btn, text_out, status_lbl, root, save_settings_btn, radius_var, age_var, station_dist_var, sort_var, include_planetary_var, db_status_label, unknown_pad_frame, unknown_pad_entry, save_pad_size_btn, change_journal_dir_btn, restore_defaults_btn, progress_bar

    if not all([root, launch_btn, radius_var, age_var, station_dist_var, sort_var, include_planetary_var, text_out, status_lbl]):
        logging.warning("GUI elements not ready for on_launch_pressed."); return

    refresh_location_and_ship_display()

    def _actual_launch_logic():
        if CURRENT_SYSTEM == "?" or "Error" in CURRENT_SYSTEM or "Journal not found" in CURRENT_SYSTEM:
            msg = "Cannot launch analysis: Current system is unknown or invalid. Please ensure location/ship is correctly detected."
            logging.warning(msg)
            if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
            if text_out: root.after(0, lambda: text_out.insert(tk.END, msg + "\n"))
            for btn in buttons_to_disable:
                if btn and btn.winfo_exists(): root.after(0, lambda b=btn: b.config(state=tk.NORMAL))
            if unknown_pad_entry and unknown_pad_frame.winfo_ismapped() and unknown_pad_entry.winfo_exists():
                root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
            if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
            return

        if text_out: root.after(0, lambda: (text_out.delete('1.0', tk.END), text_out.insert(tk.END, "Starting analysis...\n")))
        if status_lbl: root.after(0, lambda: status_lbl.config(text="Validating settings for analysis..."))
        if progress_bar: root.after(0, lambda: (progress_bar.grid(column=0, row=6, columnspan=4, sticky="ew", pady=(2,5), padx=5), progress_bar.start()))


        try:
            r = float(radius_var.get()); a = int(age_var.get()); sd = float(station_dist_var.get())
            if r <= 0: raise ValueError("Radius LY > 0.")
            if a < 0: raise ValueError("DB Age >= 0.")
            if sd < 0: raise ValueError("Station Distance LS >= 0.")
        except ValueError as e:
            msg = f"Settings Error: {e}"; logging.error(msg)
            if root:
                root.after(0, lambda: (status_lbl.config(text=msg), text_out.insert(tk.END, msg + "\n")))
                for btn in buttons_to_disable:
                     if btn and btn.winfo_exists(): root.after(0, lambda b=btn: b.config(state=tk.NORMAL))
                if unknown_pad_entry and unknown_pad_frame.winfo_ismapped() and unknown_pad_entry.winfo_exists():
                    root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
                if progress_bar: root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))
            return

        if status_lbl: root.after(0, lambda: status_lbl.config(text="Preparing analysis... This may take some time."))

        def _task_completed_callback():
            logging.info("Analysis thread (outer) task_completed_callback: Re-enabling buttons.")
            if root:
                for btn_cb in buttons_to_disable:
                     if btn_cb and btn_cb.winfo_exists(): root.after(0, lambda b=btn_cb: b.config(state=tk.NORMAL))
                if unknown_pad_entry and unknown_pad_frame.winfo_ismapped() and unknown_pad_entry.winfo_exists():
                    root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
                if db_status_label and db_status_label.winfo_exists():
                    root.after(0, lambda: db_status_label.config(text=get_last_db_update_time_str()))
                if progress_bar and progress_bar.winfo_exists() : root.after(0, lambda: (progress_bar.stop(), progress_bar.grid_remove()))


        def _threaded_task_for_analysis():
            logging.info("Analysis thread (_threaded_task_for_analysis) started.")
            try:
                run_analysis_thread(radius_var.get(), age_var.get(), station_dist_var.get(), sort_var.get(), include_planetary_var.get())
            except Exception as e_thread:
                logging.exception("Critical error in analysis thread (_threaded_task_for_analysis):")
                msg_thread = f"Critical error: {e_thread}\nConsult {LOG_FILE}."
                if root and text_out and status_lbl:
                     if text_out.winfo_exists() and status_lbl.winfo_exists():
                        root.after(0, lambda: (text_out.insert(tk.END, msg_thread + "\n"),status_lbl.config(text="Critical error during analysis.")))
            finally:
                if root: root.after(0, _task_completed_callback)
                logging.info("Analysis thread (_threaded_task_for_analysis) finished.")

        threading.Thread(target=_threaded_task_for_analysis, daemon=True).start()

    buttons_to_disable = [launch_btn, update_btn, refresh_loc_btn, save_settings_btn, change_journal_dir_btn, restore_defaults_btn]
    if unknown_pad_frame.winfo_ismapped(): buttons_to_disable.append(save_pad_size_btn)
    for btn in buttons_to_disable:
        if btn: root.after(0, lambda b=btn: b.config(state=tk.DISABLED))
    if unknown_pad_entry and unknown_pad_frame.winfo_ismapped() :
        root.after(0, lambda: unknown_pad_entry.config(state=tk.DISABLED))

    if root: root.after(500, _actual_launch_logic)


def on_select_journal_dir_pressed():
    global APP_SETTINGS, EFFECTIVE_JOURNAL_DIR
    initial_browse_dir = APP_SETTINGS.get('custom_journal_dir')
    if not initial_browse_dir and EFFECTIVE_JOURNAL_DIR and EFFECTIVE_JOURNAL_DIR not in ["Auto-detecting...", "Not Found", "Error processing journals"]:
        initial_browse_dir = os.path.dirname(EFFECTIVE_JOURNAL_DIR)
    if not initial_browse_dir or not os.path.isdir(initial_browse_dir):
        initial_browse_dir = os.path.expanduser("~")

    new_dir = filedialog.askdirectory(initialdir=initial_browse_dir, title="Select Elite Dangerous Journal Directory")
    if new_dir:
        APP_SETTINGS['custom_journal_dir'] = new_dir
        EFFECTIVE_JOURNAL_DIR = new_dir
        logging.info(f"Custom journal directory selected: {new_dir}")
        update_journal_dir_label_text()
        if status_lbl: status_lbl.config(text=f"Journal dir set. Press 'Save Settings' or 'Launch' to use.")
        refresh_location_and_ship_display()
    else:
        logging.info("Journal directory selection cancelled.")

def on_restore_defaults_pressed():
    global APP_SETTINGS, CUSTOM_SHIP_PAD_SIZES
    global radius_var, age_var, station_dist_var, include_planetary_var, sort_var, EFFECTIVE_JOURNAL_DIR

    if tkinter.messagebox.askyesno("Restore Defaults",
                                   "Are you sure you want to restore all settings to their default values?\n"
                                   "This includes journal directory, search parameters, and custom ship pad sizes."):
        logging.info("Restoring default settings.")

        if radius_var: radius_var.set(str(RESET_DEFAULT_RADIUS))
        if age_var: age_var.set(str(RESET_DEFAULT_MAX_AGE_DAYS))
        if station_dist_var: station_dist_var.set(str(RESET_DEFAULT_MAX_STATION_DISTANCE_LS))
        if include_planetary_var: include_planetary_var.set(RESET_DEFAULT_INCLUDE_PLANETARY)
        if sort_var: sort_var.set(RESET_DEFAULT_SORT_OPTION)

        APP_SETTINGS['custom_journal_dir'] = RESET_DEFAULT_CUSTOM_JOURNAL_DIR
        EFFECTIVE_JOURNAL_DIR = "Auto-detecting..."

        CUSTOM_SHIP_PAD_SIZES.clear()

        if save_settings(
            RESET_DEFAULT_RADIUS,
            RESET_DEFAULT_MAX_AGE_DAYS,
            RESET_DEFAULT_MAX_STATION_DISTANCE_LS,
            RESET_DEFAULT_INCLUDE_PLANETARY,
            RESET_DEFAULT_CUSTOM_JOURNAL_DIR,
            {},
            RESET_DEFAULT_SORT_OPTION
        ):
            if status_lbl: status_lbl.config(text="Default settings restored and saved.")
        else:
            if status_lbl: status_lbl.config(text="Failed to save restored default settings.")

        update_journal_dir_label_text()
        if unknown_pad_frame.winfo_ismapped():
            unknown_pad_frame.grid_remove()
        refresh_location_and_ship_display()


def on_save_settings_pressed():
    global radius_var, age_var, station_dist_var, include_planetary_var, sort_var, root, status_lbl, save_settings_btn, APP_SETTINGS, CUSTOM_SHIP_PAD_SIZES
    if not all([root, radius_var, age_var, station_dist_var, include_planetary_var, sort_var, status_lbl, save_settings_btn]):
        logging.warning("GUI elements not ready for save settings."); return

    root.after(0, lambda: save_settings_btn.config(state=tk.DISABLED))
    if status_lbl: root.after(0, lambda: status_lbl.config(text="Saving settings..."))
    try:
        r, a, sd = float(radius_var.get()), int(age_var.get()), float(station_dist_var.get())
        ip = include_planetary_var.get()
        sv = sort_var.get()
        current_custom_journal_dir = APP_SETTINGS.get('custom_journal_dir')
        current_custom_pad_sizes = CUSTOM_SHIP_PAD_SIZES.copy()

        if r <= 0 or a < 0 or sd < 0: raise ValueError("Invalid numerical values for saving.")
        if sv not in ['d', 'b', 's']: raise ValueError("Invalid sort option.")

        if save_settings(r, a, sd, ip, current_custom_journal_dir, current_custom_pad_sizes, sv):
            if status_lbl: root.after(0, lambda: status_lbl.config(text="Settings saved."))
        else:
            if status_lbl: root.after(0, lambda: status_lbl.config(text="Failed to save settings."))
    except ValueError as e: msg = f"Validation error: {e}"; logging.error(msg); status_lbl.config(text=msg)
    except Exception as e: logging.exception("Error saving settings:"); msg=f"Error: {e}"; status_lbl.config(text=msg)
    finally:
        if save_settings_btn: root.after(0, lambda: save_settings_btn.config(state=tk.NORMAL))


def on_save_pad_size_pressed():
    global CURRENT_SHIP_TYPE, CUSTOM_SHIP_PAD_SIZES, root, status_lbl, unknown_pad_entry, save_pad_size_btn, unknown_pad_frame
    global CURRENT_PAD_SIZE, CURRENT_SYSTEM, CURRENT_STATION, CURRENT_CARGO_CAPACITY
    global radius_var, age_var, station_dist_var, include_planetary_var, sort_var, APP_SETTINGS

    if not all([root, unknown_pad_entry, status_lbl, save_pad_size_btn, unknown_pad_frame]):
        logging.warning("GUI elements not ready for save pad size."); return

    for widget in [save_pad_size_btn, unknown_pad_entry]:
        if widget: root.after(0, lambda w=widget: w.config(state=tk.DISABLED))
    if status_lbl: root.after(0, lambda: status_lbl.config(text="Saving pad size..."))

    ship_type_to_save, entered_size_str = CURRENT_SHIP_TYPE, unknown_pad_entry.get().strip()
    if not ship_type_to_save or ship_type_to_save in ["Unknown", "Journal not found", "Error", "Error - No Journal"]:
        msg = "Error: Current ship type unknown."; logging.error(msg)
        if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.NORMAL))
        if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))
        return
    else:
        try:
            pad_size_int = int(entered_size_str)
            if pad_size_int not in [1, 2, 3]: raise ValueError("Pad size must be 1, 2, or 3.")

            CUSTOM_SHIP_PAD_SIZES[ship_type_to_save.lower()] = pad_size_int
            logging.info(f"Custom pad size for '{ship_type_to_save}': {pad_size_int} added to CUSTOM_SHIP_PAD_SIZES.")

            r_set, a_set, sd_set, ip_set, sv_set = float(radius_var.get()), int(age_var.get()), float(station_dist_var.get()), include_planetary_var.get(), sort_var.get()
            current_custom_journal_dir = APP_SETTINGS.get('custom_journal_dir')

            if save_settings(r_set, a_set, sd_set, ip_set, current_custom_journal_dir, CUSTOM_SHIP_PAD_SIZES.copy(), sv_set):
                msg = f"Pad size ({pad_size_int}) for '{ship_type_to_save}' saved (with other settings)."
                logging.info(msg); CURRENT_PAD_SIZE = pad_size_int
                if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
                if root: root.after(0, lambda: _update_gui_loc_ship_from_thread_results(CURRENT_SYSTEM, CURRENT_STATION, CURRENT_SHIP_TYPE, CURRENT_CARGO_CAPACITY, CURRENT_PAD_SIZE ))
                if unknown_pad_frame.winfo_ismapped(): unknown_pad_frame.grid_remove()
            else:
                msg = "Failed to save settings (after pad size update)."; logging.error(msg)
                if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        except (ValueError, TypeError) as ve:
            msg = f"Pad size validation/save error: {ve}"; logging.error(msg)
            if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        except Exception as ex:
            logging.exception("Unexpected error saving pad size:"); msg=f"Error: {ex}"
            if status_lbl: root.after(0, lambda: status_lbl.config(text=msg))
        finally:
            if save_pad_size_btn: root.after(0, lambda: save_pad_size_btn.config(state=tk.NORMAL))
            if unknown_pad_entry: root.after(0, lambda: unknown_pad_entry.config(state=tk.NORMAL))


if __name__ == "__main__":
    logging.info("Application started.")
    try:
        APP_SETTINGS = load_settings()
        create_gui()
    except Exception as e:
         logging.critical("Critical error during application startup:", exc_info=True)
         print(f"Critical application startup error: {e}\nConsult the log file ({LOG_FILE}) for details.", file=sys.stderr)
         try:
             temp_root_for_error = tk.Tk(); temp_root_for_error.withdraw()
             tkinter.messagebox.showerror("Critical Startup Error", f"A critical error occurred on startup:\n{e}\n\nConsult {LOG_FILE} for details.\nThe application will close.")
             temp_root_for_error.destroy()
         except Exception: pass
         sys.exit(1)
