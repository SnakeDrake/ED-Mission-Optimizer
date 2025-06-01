#!/usr/bin/env python3
import json
import os
import re
import logging
from datetime import datetime, timezone # Import timezone
# Assurez-vous que constants.py contient KEY_CUSTOM_JOURNAL_DIR, SHIP_PAD_SIZE, etc.
# et les nouvelles constantes de matériaux (MATERIAL_CATEGORIES, MATERIALS_LOOKUP, get_material_limit)
from constants import (
    SHIP_PAD_SIZE, STATION_PAD_SIZE_MAP, KEY_CUSTOM_JOURNAL_DIR,
    MATERIAL_CATEGORIES, MATERIALS_LOOKUP # get_material_limit est utilisé implicitement via MATERIALS_LOOKUP ici
)
import settings_manager

logger = logging.getLogger(__name__)

EFFECTIVE_JOURNAL_DIR = "Auto-detecting..."


def find_journal_dir(preferred_dir=None):
    if preferred_dir:
        logger.info(f"find_journal_dir: Vérification du chemin préféré : '{preferred_dir}'")
        if os.path.isdir(preferred_dir):
            logger.info(f"find_journal_dir: Utilisation du chemin préféré valide : {preferred_dir}")
            return preferred_dir
        else:
            logger.warning(f"find_journal_dir: Le chemin préféré '{preferred_dir}' N'EST PAS un répertoire valide. Tentative d'auto-détection.")
    else:
        logger.info("find_journal_dir: Aucun chemin préféré fourni, tentative d'auto-détection.")

    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        path_windows = os.path.join(user_profile, "Saved Games", "Frontier Developments", "Elite Dangerous")
        if os.path.isdir(path_windows):
            logger.debug(f"Auto-detected Journal dir (Windows): {path_windows}")
            return path_windows

    home_dir = os.getenv("HOME")
    if home_dir:
        steam_path_segment = os.path.join("drive_c", "users", "steamuser", "Saved Games", "Frontier Developments", "Elite Dangerous")
        proton_prefixes = [
            ".local/share/Steam/steamapps/compatdata/359320/pfx",
            ".steam/steam/steamapps/compatdata/359320/pfx",
        ]
        for p_prefix in proton_prefixes:
            proton_path = os.path.join(home_dir, p_prefix, steam_path_segment)
            if os.path.isdir(proton_path):
                logger.debug(f"Auto-detected Journal dir (Proton): {proton_path}")
                return proton_path

        native_linux_path = os.path.join(home_dir, ".local/share/FrontierDevelopments/EliteDangerous")
        if os.path.isdir(native_linux_path):
            logger.debug(f"Auto-detected Journal dir (Native Linux): {native_linux_path}")
            return native_linux_path
        
        older_native_linux_path = os.path.join(home_dir, ".local/share/Frontier Developments/Elite Dangerous")
        if os.path.isdir(older_native_linux_path):
            logger.debug(f"Auto-detected Journal dir (Older Native Linux): {older_native_linux_path}")
            return older_native_linux_path

        path_macos = os.path.join(home_dir, "Library/Application Support/Frontier Developments/Elite Dangerous")
        if os.path.isdir(path_macos):
            logger.debug(f"Auto-detected Journal dir (macOS): {path_macos}")
            return path_macos
            
    logger.error("Elite Dangerous journal directory not found by auto-detection.")
    return None


def load_journal_events(journal_dir_path, num_files_to_check=10):
    events = []
    if not journal_dir_path or not os.path.isdir(journal_dir_path):
        logger.error(f"load_journal_events: Invalid or non-existent journal directory: {journal_dir_path}")
        return []
    logger.info(f"load_journal_events: Reading from {journal_dir_path}")
    try:
        journal_files = [f for f in os.listdir(journal_dir_path) if f.startswith("Journal.") and f.endswith(".log")]
        journal_files.sort(key=lambda f: os.path.getmtime(os.path.join(journal_dir_path, f)), reverse=True)
        logger.info(f"load_journal_events: Found {len(journal_files)} journal files.")
    except Exception as e:
        logger.exception(f"load_journal_events: Error accessing {journal_dir_path}: {e}")
        return []
    
    files_to_process = journal_files[:num_files_to_check] 
    logger.info(f"load_journal_events: Will attempt to read last {len(files_to_process)} journal files: {files_to_process}")
    for fname in reversed(files_to_process): 
        filepath = os.path.join(journal_dir_path, fname)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line_content in f:
                    try:
                        events.append(json.loads(line_content))
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid JSON line in {fname}")
        except Exception as e:
            logger.exception(f"Error reading or parsing {fname}: {e}")
    logger.info(f"load_journal_events: Total events loaded: {len(events)} from {len(files_to_process)} files.");
    return events


def get_ship_pad_size(ship_type_name):
    current_custom_ship_pad_sizes = settings_manager.get_custom_pad_sizes() 
    if not ship_type_name or ship_type_name in ["Unknown", "Journal not found", "Error", "Error - No Journal"]:
        return "?"
    ship_name_lower = ship_type_name.lower()
    if ship_name_lower in current_custom_ship_pad_sizes:
        pad_size = current_custom_ship_pad_sizes[ship_name_lower]
        if pad_size in [1, 2, 3]:
            logger.debug(f"Using custom pad size {pad_size} for ship '{ship_type_name}'.")
            return pad_size
        else:
            logger.warning(f"Invalid custom pad size '{pad_size}' for ship '{ship_type_name}'. Falling back.")
    pad_size_default = SHIP_PAD_SIZE.get(ship_name_lower)
    if pad_size_default is not None:
        return pad_size_default
    logger.info(f"Unknown ship type for pad size: '{ship_type_name}'. Returning '?'.")
    return "?"


def get_latest_ship_info(journal_dir_path):
    ship_type, cargo_capacity = "Unknown", 0
    if not journal_dir_path or not os.path.isdir(journal_dir_path):
        logger.error(f"Invalid journal directory path for get_latest_ship_info: {journal_dir_path}")
        return "Error - No Journal", 0, "?"
    try:
        journal_files = [f for f in os.listdir(journal_dir_path) if f.startswith("Journal.") and f.endswith(".log")]
        journal_files.sort(key=lambda f: os.path.getmtime(os.path.join(journal_dir_path, f)))
    except Exception as e:
        logger.exception(f"Error listing journal files in get_latest_ship_info: {e}")
        return "Error", 0, "?"

    latest_loadout_event = None
    for fname in reversed(journal_files[-5:]): 
        filepath = os.path.join(journal_dir_path, fname)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            for line in reversed(lines): 
                try:
                    event = json.loads(line)
                    if event.get('event') == 'Loadout':
                        latest_loadout_event = event
                        logger.debug(f"Found Loadout event in {fname}")
                        break 
                except json.JSONDecodeError:
                    continue
            if latest_loadout_event:
                break
        except Exception as e:
            logger.warning(f"Error reading or processing file {fname} for Loadout event: {e}")
            continue
    
    if latest_loadout_event:
        ship_type_raw = latest_loadout_event.get('Ship', 'Unknown')
        if ship_type_raw == 'Unknown' and 'ShipName' in latest_loadout_event:
            ship_type_raw = latest_loadout_event.get('ShipName')

        ship_type_loc = latest_loadout_event.get('Ship_Localised', ship_type_raw)
        
        if ship_type_loc:
            ship_type = str(ship_type_loc).replace('_', ' ').title()
        elif ship_type_raw :
            ship_type = str(ship_type_raw).replace('_', ' ').title()
        else:
            ship_type = "Unknown"

        cargo_capacity_raw = latest_loadout_event.get('CargoCapacity', 0)
        try: 
            cargo_capacity = int(cargo_capacity_raw)
            if cargo_capacity < 0: cargo_capacity = 0 
        except (ValueError, TypeError): 
            logger.warning(f"Invalid cargo capacity value '{cargo_capacity_raw}', defaulting to 0.")
            cargo_capacity = 0
        logger.info(f"Ship from Loadout: {ship_type}, Cargo: {cargo_capacity}")
    else:
        ship_type = "Journal not found"
        logger.warning("No Loadout event found in recent journal files.")
        
    pad_size = get_ship_pad_size(ship_type)
    return ship_type, cargo_capacity, pad_size


def get_current_location_from_events(events):
    current_system, current_station, is_docked_flag = None, None, False
    for event_data in reversed(events): 
        event_type = event_data.get("event")
        if event_type == "Docked":
            current_system = event_data.get("StarSystem")
            current_station = event_data.get("StationName")
            is_docked_flag = True
            break 
        elif event_type == "Location":
            current_system = event_data.get("StarSystem")
            if event_data.get("Docked", False):
                current_station = event_data.get("StationName")
                is_docked_flag = True
            else: 
                current_station = None 
                is_docked_flag = False
            break 
        elif event_type in ["FSDJump", "CarrierJump", "Undocked", "Liftoff"]:
            current_system = event_data.get("StarSystem")
            current_station = None 
            is_docked_flag = False
            break
            
    final_system = current_system if current_system else "?"
    final_station = current_station if is_docked_flag and current_station else "?"
    
    if final_system == "?" and final_station != "?":
        final_station = "?"
        
    logger.info(f"Location from events: System='{final_system}', Station='{final_station}', Docked='{is_docked_flag}'")
    return final_system, final_station

def get_current_materials_from_events(events):
    logger.info("get_current_materials_from_events: Searching for 'Materials' event.")
    latest_materials_event = None
    for event_data in reversed(events):
        if event_data.get("event") == "Materials":
            latest_materials_event = event_data
            logger.info(f"Found 'Materials' event at timestamp: {event_data.get('timestamp')}")
            break

    current_materials = {
        "Raw": {}, "Manufactured": {}, "Encoded": {}, "timestamp": None
    }

    if latest_materials_event:
        current_materials["timestamp"] = latest_materials_event.get("timestamp")
        for category_key in MATERIAL_CATEGORIES: 
            if category_key in latest_materials_event:
                for mat_entry in latest_materials_event[category_key]:
                    mat_name_journal = mat_entry.get("Name") 
                    if not mat_name_journal:
                        logger.warning(f"Material entry in category {category_key} is missing 'Name'. Entry: {mat_entry}")
                        continue
                    
                    mat_name_internal_lower = mat_name_journal.lower()

                    current_materials[category_key][mat_name_internal_lower] = {
                        "Name": mat_name_journal, 
                        "Name_Localised": mat_entry.get("Name_Localised", mat_name_journal),
                        "Count": mat_entry.get("Count", 0)
                    }
        logger.info(f"Processed materials data: {len(current_materials['Raw'])} Raw, {len(current_materials['Manufactured'])} Manufactured, {len(current_materials['Encoded'])} Encoded.")
    else:
        logger.warning("No 'Materials' event found in the provided events.")
    
    return current_materials

def get_player_state_data():
    global EFFECTIVE_JOURNAL_DIR
    system, station = "?", "?"
    ship_type, cargo_capacity, pad_size = "Unknown", 0, "?"
    materials_data = {"Raw": {}, "Manufactured": {}, "Encoded": {}, "timestamp": None}

    preferred_custom_dir = settings_manager.get_setting(KEY_CUSTOM_JOURNAL_DIR) 
    logger.info(f"get_player_state_data: Preferred custom journal directory: '{preferred_custom_dir}'")
    
    temp_journal_dir = find_journal_dir(preferred_custom_dir)
    
    if temp_journal_dir:
        EFFECTIVE_JOURNAL_DIR = temp_journal_dir
        logger.info(f"Effective journal directory set to: {EFFECTIVE_JOURNAL_DIR}")
        
        all_events = load_journal_events(EFFECTIVE_JOURNAL_DIR, num_files_to_check=10) 
        
        if all_events:
            system, station = get_current_location_from_events(all_events)
            materials_data = get_current_materials_from_events(all_events)
        else:
            logger.warning("No journal events loaded for state parsing.")
            system, station = "No Events", "No Events"
            
        ship_type, cargo_capacity, pad_size = get_latest_ship_info(EFFECTIVE_JOURNAL_DIR)
    else:
        EFFECTIVE_JOURNAL_DIR = "Not Found"
        logger.error("Journal directory could not be determined (custom or auto).")
        system, station = "No Journal Dir", "No Journal Dir"
        ship_type, cargo_capacity, pad_size = "Error - No Journal", 0, "?"
        
    logger.info(f"Player State Data: Sys='{system}', Station='{station}', Ship='{ship_type}', Pad='{pad_size}', Cargo='{cargo_capacity}'")
    logger.info(f"Materials Timestamp (from state data): {materials_data.get('timestamp')}")
    
    return system, station, ship_type, cargo_capacity, pad_size, EFFECTIVE_JOURNAL_DIR, materials_data


def _clean_commodity_name(commodity_field_value, commodity_localised_value=None):
    """
    Nettoie le nom de la marchandise pour obtenir le nom interne.
    Priorise le champ 'Commodity' (souvent de la forme $xxxx_Name;).
    """
    cleaned_name = ""
    # Essayer d'abord avec commodity_field_value (qui devrait être event_data['Commodity'])
    if isinstance(commodity_field_value, str):
        match = re.search(r"^\$?([a-zA-Z0-9_]+?)(?:_name)?(;)?$", commodity_field_value, re.I)
        if match:
            cleaned_name = match.group(1).lower()
            logger.debug(f"Cleaned name from '$..._Name;' pattern: '{commodity_field_value}' -> '{cleaned_name}'")
        else: # Si pas de motif $..._Name;, utiliser la valeur telle quelle (après nettoyage basique)
            cleaned_name = re.sub(r"[\s\-_]", '', commodity_field_value).lower()
            logger.debug(f"Cleaned name by basic replace: '{commodity_field_value}' -> '{cleaned_name}'")
    
    if not cleaned_name and isinstance(commodity_localised_value, str):
        # Fallback sur commodity_localised_value si le premier nettoyage a échoué et que _localised existe
        # Ceci est moins idéal car on veut le nom interne, mais c'est un fallback.
        logger.debug(f"Could not determine internal name from '{commodity_field_value}', trying basic clean on localised '{commodity_localised_value}' as fallback.")
        cleaned_name = re.sub(r"[\s\-_]", '', commodity_localised_value).lower()

    return cleaned_name if cleaned_name else commodity_field_value.lower() # Dernier recours, la valeur brute en minuscules


def parse_active_missions(journal_events):
    logger.info(f"parse_active_missions: Received {len(journal_events)} events.")
    missions_dict = {}
    latest_missions_event = next((ev for ev in reversed(journal_events) if ev.get('event') == 'Missions'), None)

    if latest_missions_event:
        logger.info(f"parse_active_missions: Found 'Missions' event with {len(latest_missions_event.get('Active',[]))} active entries.")
        for mission_data in latest_missions_event.get('Active', []):
            mission_id = mission_data.get('MissionID')
            commodity_raw = mission_data.get('Commodity') # Ex: $gold_name;
            
            if not mission_id or not commodity_raw or not mission_data.get('Count'):
                continue
            
            commodity_loc = mission_data.get('Commodity_Localised') # Ex: Or
            
            # Utiliser la nouvelle fonction de nettoyage
            internal_commodity_name = _clean_commodity_name(commodity_raw)
            
            if not internal_commodity_name:
                logger.warning(f"Mission {mission_id} (from 'Missions' event): Empty internal commodity name after cleaning. Original Commodity: '{commodity_raw}', Localised: '{commodity_loc}'. Skipping.")
                continue

            missions_dict[mission_id] = {
                'name': internal_commodity_name, # Utiliser le nom interne nettoyé pour la logique
                'name_localised': commodity_loc or internal_commodity_name.capitalize(), # Pour affichage
                'total': mission_data['Count'],
                'delivered': mission_data.get('DeliveredCount', 0),
                'completed': False, 'failed_or_abandoned': False,
                'reward': mission_data.get('Reward', 0),
                'destinationSystem': mission_data.get('DestinationSystem', ''),
                'destinationStation': mission_data.get('DestinationStation', ''),
                'source_event': 'Missions'
            }
            logger.info(f"Mission {mission_id} (from 'Missions'): Internal Name '{internal_commodity_name}', Display '{missions_dict[mission_id]['name_localised']}', Total: {mission_data['Count']}, Delivered: {mission_data.get('DeliveredCount', 0)}")
    else:
        logger.info("parse_active_missions: No 'Missions' event found. Relying on individual events.")

    # Traitement des événements individuels (MissionAccepted, CargoDepot, etc.)
    # pour affiner les données ou capturer des missions non listées dans l'événement 'Missions' global
    for event_data in journal_events:
        event_type = event_data.get('event')
        mission_id = event_data.get('MissionID')

        if not mission_id and event_type in ['MissionAccepted', 'CargoDepot', 'MissionCompleted', 'MissionFailed', 'MissionAbandoned']:
            continue
        
        # Si la mission est déjà marquée comme terminée/échouée à partir de l'événement 'Missions' agrégé,
        # ignorer les événements individuels plus anciens, sauf s'il s'agit d'une nouvelle acceptation ou d'une mise à jour du dépôt de marchandises.
        if mission_id in missions_dict and \
           (missions_dict[mission_id].get('completed') or missions_dict[mission_id].get('failed_or_abandoned')) and \
           event_type not in ['MissionAccepted', 'CargoDepot']:
            continue
        
        if event_type == 'MissionAccepted':
            commodity_raw = event_data.get('Commodity')
            if commodity_raw and event_data.get('Count'):
                # Ajouter/mettre à jour uniquement si non présent depuis 'Missions' ou si c'est une acceptation plus récente
                # (difficile à déterminer sans timestamps par mission dans l'événement 'Missions')
                # Pour l'instant, on écrase si 'Missions' n'a pas fourni cette entrée, ou si on veut prioriser les events individuels.
                # Si elle vient de 'Missions', on ne la remplace que si c'est pertinent (ex: si 'Missions' est très vieux)
                # Décision : si 'Missions' est traité en premier, il est probablement plus à jour.
                # On ajoute ici si la mission N'EST PAS dans `missions_dict` (cas où 'Missions' n'a pas été trouvé ou est incomplet)
                if mission_id not in missions_dict:
                    commodity_loc = event_data.get('Commodity_Localised')
                    internal_commodity_name = _clean_commodity_name(commodity_raw)

                    if not internal_commodity_name:
                        logger.warning(f"Accepted Mission {mission_id}: Empty internal commodity name. Original: '{commodity_raw}', Localised: '{commodity_loc}'. Skipping.")
                        continue
                    
                    missions_dict[mission_id] = {
                        'name': internal_commodity_name,
                        'name_localised': commodity_loc or internal_commodity_name.capitalize(),
                        'total': event_data['Count'],
                        'delivered': 0, # Nouveau, donc 0 livré
                        'completed': False, 'failed_or_abandoned': False,
                        'reward': event_data.get('Reward', 0),
                        'destinationSystem': event_data.get('DestinationSystem', ''),
                        'destinationStation': event_data.get('DestinationStation', ''),
                        'source_event': 'MissionAccepted'
                    }
                    logger.info(f"Processed 'MissionAccepted' for ID {mission_id} (not found in 'Missions' event): Internal Name '{internal_commodity_name}', Count: {event_data['Count']}")
        
        elif event_type == 'CargoDepot' and mission_id in missions_dict:
            if event_data.get('UpdateType') == 'Deliver':
                mission_entry = missions_dict[mission_id]
                # ... (logique de mise à jour de 'delivered' comme avant) ...
                previous_delivered = mission_entry.get('delivered', 0)
                mission_total_quantity = mission_entry.get('total', float('inf')) 
                transactional_count = event_data.get('Count', 0)
                if transactional_count == 0 and 'ItemsDelivered' in event_data:
                    transactional_count = event_data.get('ItemsDelivered', 0)
                api_progress = event_data.get('Progress')
                api_total_items_in_event = event_data.get('TotalItemsToDeliver')
                new_delivered_cumulative = previous_delivered 
                if api_progress is not None and api_total_items_in_event is not None and api_progress > 0.0:
                    try:
                        if api_total_items_in_event != mission_total_quantity:
                            logger.warning(f"CargoDepot MissionID {mission_id}: TotalItemsToDeliver in event ({api_total_items_in_event}) != mission total ({mission_total_quantity}). Using mission total for progress.")
                        calculated_from_progress = round(float(mission_total_quantity) * float(api_progress))
                        if calculated_from_progress > previous_delivered:
                            new_delivered_cumulative = calculated_from_progress
                        elif transactional_count > 0: 
                            new_delivered_cumulative = previous_delivered + transactional_count
                    except ValueError:
                        if transactional_count > 0: new_delivered_cumulative = previous_delivered + transactional_count
                elif transactional_count > 0: 
                    new_delivered_cumulative = previous_delivered + transactional_count
                final_new_delivered_count = min(new_delivered_cumulative, mission_total_quantity)
                if final_new_delivered_count > previous_delivered:
                    mission_entry['delivered'] = final_new_delivered_count
                    logger.info(f"CargoDepot (Deliver) MissionID {mission_id}: Delivered count updated to {mission_entry['delivered']}.")

        elif event_type == 'MissionCompleted' and mission_id in missions_dict:
            logger.info(f"Mission {mission_id} completed.")
            missions_dict[mission_id]['completed'] = True
            if missions_dict[mission_id].get('total', 0) > missions_dict[mission_id].get('delivered', 0): 
                missions_dict[mission_id]['delivered'] = missions_dict[mission_id].get('total', 0)
        
        elif event_type in ['MissionFailed','MissionAbandoned'] and mission_id in missions_dict:
            logger.info(f"Mission {mission_id} marked as '{event_type}'.")
            missions_dict[mission_id]['completed'] = True 
            missions_dict[mission_id]['failed_or_abandoned'] = True

    remaining_needs = {}
    total_reward_potential = 0
    for mission_id, mission_data in missions_dict.items():
        if not mission_data.get('completed', False) and not mission_data.get('failed_or_abandoned', False):
            needed_quantity = mission_data.get('total', 0) - mission_data.get('delivered', 0)
            if needed_quantity > 0:
                # Utiliser le nom interne pour la logique des besoins
                internal_name_for_logic = mission_data.get('name')
                if not internal_name_for_logic: 
                    logger.warning(f"Mission ID {mission_id} has no internal commodity name for needs processing. Skipping."); continue
                remaining_needs[internal_name_for_logic] = remaining_needs.get(internal_name_for_logic, 0) + needed_quantity
                total_reward_potential += mission_data.get('reward', 0)
                
    if not remaining_needs:
        logger.info("parse_active_missions: No active collection missions with outstanding needs found.")
    else:
        logger.info(f"parse_active_missions: Final needs (internal names): {remaining_needs}. Total potential reward: {total_reward_potential:,.0f} CR.")
        
    # Retourner remaining_needs (basé sur les noms internes) et le potentiel de récompense.
    # L'affichage utilisera 'name_localised' stocké dans missions_dict si besoin.
    return remaining_needs, total_reward_potential