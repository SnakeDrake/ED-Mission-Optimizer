#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
from collections import defaultdict
import threading

from constants import (
    BASE_URL, HEADERS, CONCURRENCY_LIMIT,
    DEPARTURE_DATA_FILE, LOCAL_SELLERS_DATA_FILE,
    FLEET_CARRIER_STATION_TYPES # Bien que non utilisé ici, il est bon de savoir qu'il existe pour optimizer_logic
)

logger = logging.getLogger(__name__)

class OperationCancelledError(Exception):
    """Exception personnalisée pour les opérations annulées."""
    pass

async def fetch_json(session, url, params: dict = None, cancel_event: threading.Event = None):
    if cancel_event and cancel_event.is_set():
        logger.info(f"Operation cancelled before fetching {url}")
        raise OperationCancelledError(f"Fetching URL cancelled: {url}")

    log_params = f" with params: {params}" if params else ""
    logger.debug(f"Fetching URL: {url}{log_params}")
    try:
        async with session.get(url, headers=HEADERS, params=params, timeout=aiohttp.ClientTimeout(total=45)) as response: # Timeout augmenté
            if cancel_event and cancel_event.is_set():
                logger.info(f"Operation cancelled during fetching {url}")
                raise OperationCancelledError(f"Fetching URL cancelled: {url}")
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientResponseError as e:
        logger.error(f"API ClientResponseError for {url}{log_params}: {e.status} {e.message}")
        raise
    except aiohttp.ClientConnectorError as e:
        logger.error(f"API ClientConnectorError for {url}{log_params}: {e}")
        raise
    except asyncio.TimeoutError:
        logger.error(f"API Timeout (45s) for {url}{log_params}")
        raise
    except OperationCancelledError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}{log_params}: {e}")
        raise


async def download_departure_market_data(
    system_name,
    station_name,
    max_days_ago: int, # Non utilisé pour l'appel API, conservé pour la signature
    include_fleet_carriers: bool, # Non utilisé pour l'appel API, conservé pour la signature
    cancel_event: threading.Event = None,
    progress_callback=None
):
    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Departure market data download cancelled.")
    if not all([system_name, station_name]) or "?" in [system_name, station_name] or \
       "Journal not found" in system_name or "Error" in system_name:
        logger.warning(f"Skipping departure download for invalid system/station: {system_name}/{station_name}.")
        return None

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            # Appel V2 SANS les filtres serveur maxDaysAgo et fleetCarriers
            urls_with_params = [
                (f"{BASE_URL}system/name/{system_name}/commodities/exports", None),
                (f"{BASE_URL}system/name/{system_name}/commodities/imports", None)
            ]
            logger.info(f"Downloading ALL departure market data (no API filters) for {station_name} in {system_name}")

            if progress_callback: progress_callback("Downloading market data (start)...", 0)

            tasks = [fetch_json(session, url, params=p, cancel_event=cancel_event) for url, p in urls_with_params]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if progress_callback: progress_callback("Processing market data (start)...", 50)

            offers = {}
            combined_data = []
            for i, res in enumerate(results):
                if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Departure market data processing cancelled.")
                if isinstance(res, OperationCancelledError): raise res
                if isinstance(res, Exception): logger.error(f"Error fetching departure data part from {urls_with_params[i][0]}: {res}")
                elif isinstance(res, list): combined_data.extend(res)
                else: logger.warning(f"Unexpected data format from {urls_with_params[i][0]}: {type(res)}")
            
            # On stocke toutes les données reçues pour la station spécifiée.
            # Le filtrage (ex: par Fleet Carrier) sera fait par optimizer_logic.py.
            for item in combined_data:
                if item.get('stationName') == station_name:
                    commodity_name_lower = item['commodityName'].lower()
                    existing_entry = offers.get(commodity_name_lower, {'commodityName': item['commodityName']})
                    for key, value in item.items():
                        if value is not None and (isinstance(value, (int, float)) and value != 0 or isinstance(value, str) and value):
                             existing_entry[key] = value
                    
                    existing_entry.setdefault('buyPrice', 0)
                    existing_entry.setdefault('sellPrice', 0)
                    existing_entry.setdefault('stock', 0)
                    existing_entry.setdefault('demand', 0)
                    existing_entry.setdefault('commodity_localised', existing_entry.get('commodityLocalisedName', existing_entry['commodityName']))
                    
                    station_details_from_item = item.get('station', {}) if isinstance(item.get('station'), dict) else {}
                    existing_entry.setdefault('maxLandingPadSize', item.get('maxLandingPadSize', station_details_from_item.get('maxLandingPadSize')))
                    existing_entry.setdefault('distanceToArrival', item.get('distanceToArrival', station_details_from_item.get('distanceToArrival'))) 
                    existing_entry.setdefault('stationType', item.get('stationType', station_details_from_item.get('type', 'Unknown')))
                    
                    offers[commodity_name_lower] = existing_entry
            
            departure_data = {
                "system": system_name, "station": station_name,
                "offers": list(offers.values()),
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
            with open(DEPARTURE_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(departure_data, f, indent=2)
            logger.info(f"Raw (unfiltered by client at save time) departure market data for {station_name} saved to {DEPARTURE_DATA_FILE}.")
            if progress_callback: progress_callback("Starting data saved.", 100)
            return departure_data
        except OperationCancelledError:
            logger.info("Departure market data download was cancelled.")
            raise
        except Exception as e:
            logger.exception(f"Error in download_departure_market_data for {system_name}/{station_name}: {e}")
            return None


async def download_local_sellers_data(
    system_name,
    radius_ly,
    max_days_ago: int,                 # Non utilisé pour l'appel API, conservé pour info
    include_fleet_carriers: bool,    # Non utilisé pour l'appel API, conservé pour info
    cancel_event: threading.Event = None,
    progress_callback=None
):
    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Local sellers data download cancelled.")
    if not system_name or "?" in system_name or "Journal not found" in system_name or "Error" in system_name:
        logger.warning(f"Skipping local market data download for invalid system: '{system_name}'.")
        return None

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            nearby_api_params = {"maxDistance": radius_ly}
            nearby_url = f"{BASE_URL}system/name/{system_name}/nearby"
            logger.info(f"Downloading nearby systems around {system_name} (radius {radius_ly} LY) using V2...")
            if progress_callback: progress_callback(f"Search for systems close to {system_name}...", 0)
            
            nearby_systems_list = await fetch_json(session, nearby_url, params=nearby_api_params, cancel_event=cancel_event)
            if not isinstance(nearby_systems_list, list):
                 logger.error(f"Failed to fetch nearby systems for {system_name}. Received: {nearby_systems_list}")
                 return None
            
            if progress_callback: progress_callback(f"{len(nearby_systems_list)} nearby systems found.", 10)

            local_market_overview = {
                "sourceSystem": system_name, "radius": radius_ly,
                "systems": {s['systemName']: {'distance': s['distance']} for s in nearby_systems_list if 'systemName' in s and 'distance' in s},
                "station_markets": {},
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
            total_systems_to_fetch = len(local_market_overview['systems'])
            processed_systems_count = 0

            async def fetch_full_market_for_system(sys_name_to_fetch, current_progress_base):
                nonlocal processed_systems_count
                if cancel_event and cancel_event.is_set():
                    raise OperationCancelledError(f"Market data fetch cancelled for {sys_name_to_fetch}")

                async with semaphore:
                    if cancel_event and cancel_event.is_set():
                        raise OperationCancelledError(f"Market data fetch cancelled for {sys_name_to_fetch} (post-semaphore)")
                    
                    system_station_data = defaultdict(lambda: {'sells_to_player': [], 'buys_from_player': [], 'details': {}})
                    try:
                        # URLs V2 SANS les paramètres de filtrage serveur
                        exports_url = f"{BASE_URL}system/name/{sys_name_to_fetch}/commodities/exports"
                        api_exports = await fetch_json(session, exports_url, params=None, cancel_event=cancel_event)
                        if isinstance(api_exports, list):
                            for item in api_exports:
                                # On stocke tout, le filtrage se fera par optimizer_logic
                                station_name = item.get('stationName')
                                if not station_name: continue
                                player_cost = item.get('buyPrice', 0) 
                                stock = item.get('stock', 0)
                                if player_cost > 0 and stock > 0:
                                    station_entry = system_station_data[station_name]
                                    station_entry['sells_to_player'].append({
                                        'commodityName': item.get('commodityName'),
                                        'commodity_localised': item.get('commodityLocalisedName', item.get('commodityName')),
                                        'price': player_cost, 
                                        'stock': stock,
                                        'quantity_at_station': stock 
                                    })
                                    station_details_from_item = item.get('station', {}) if isinstance(item.get('station'), dict) else {}
                                    station_entry['details'].setdefault('maxLandingPadSize', item.get('maxLandingPadSize', station_details_from_item.get('maxLandingPadSize')))
                                    station_entry['details'].setdefault('distanceToArrival', item.get('distanceToArrival', station_details_from_item.get('distanceToArrival')))
                                    station_entry['details'].setdefault('stationType', item.get('stationType', station_details_from_item.get('type', 'Unknown')))


                        imports_url = f"{BASE_URL}system/name/{sys_name_to_fetch}/commodities/imports"
                        api_imports = await fetch_json(session, imports_url, params=None, cancel_event=cancel_event)
                        if isinstance(api_imports, list):
                            for item in api_imports:
                                # On stocke tout
                                station_name = item.get('stationName')
                                if not station_name: continue
                                player_revenue = item.get('sellPrice', 0) 
                                demand = item.get('demand', 0)
                                if player_revenue > 0 and demand > 0:
                                    station_entry = system_station_data[station_name]
                                    station_entry['buys_from_player'].append({
                                        'commodityName': item.get('commodityName'),
                                        'commodity_localised': item.get('commodityLocalisedName', item.get('commodityName')),
                                        'price': player_revenue, 
                                        'demand': demand,
                                        'quantity_at_station': demand
                                    })
                                    station_details_from_item = item.get('station', {}) if isinstance(item.get('station'), dict) else {}
                                    station_entry['details'].setdefault('maxLandingPadSize', item.get('maxLandingPadSize', station_details_from_item.get('maxLandingPadSize')))
                                    station_entry['details'].setdefault('distanceToArrival', item.get('distanceToArrival', station_details_from_item.get('distanceToArrival')))
                                    if 'stationType' not in station_entry['details']:
                                         station_entry['details']['stationType'] = item.get('stationType', station_details_from_item.get('type', 'Unknown'))
                        
                        return sys_name_to_fetch, dict(system_station_data)
                    except OperationCancelledError:
                        raise
                    except Exception as fetch_exc:
                        logger.warning(f"Failed to fetch full market data for {sys_name_to_fetch}: {fetch_exc}")
                        return sys_name_to_fetch, {}

            tasks = []
            current_progress_base = 10
            progress_per_system = (90 - current_progress_base) / total_systems_to_fetch if total_systems_to_fetch > 0 else 0

            for i, name in enumerate(local_market_overview['systems'].keys()):
                 tasks.append(fetch_full_market_for_system(name, current_progress_base + (i * progress_per_system)))
            
            markets_processed_count = 0
            for i, future in enumerate(asyncio.as_completed(tasks)):
                if cancel_event and cancel_event.is_set():
                    for task_to_cancel in tasks:
                        if not task_to_cancel.done():
                            task_to_cancel.cancel()
                    raise OperationCancelledError("Local market data collection cancelled during processing.")
                
                system_name_result, system_market_data_result = await future
                processed_systems_count += 1
                if progress_callback:
                    current_iter_progress = current_progress_base + (processed_systems_count * progress_per_system)
                    progress_callback(f"Local data: {system_name_result} ({processed_systems_count}/{total_systems_to_fetch})", int(current_iter_progress))

                if system_market_data_result:
                    # On stocke toutes les stations qui ont au moins une offre (achat ou vente)
                    filtered_station_data = {
                        sta_name: sta_data for sta_name, sta_data in system_market_data_result.items()
                        if sta_data.get('sells_to_player') or sta_data.get('buys_from_player')
                    }
                    if filtered_station_data:
                        local_market_overview['station_markets'][system_name_result] = {
                            'distance': local_market_overview['systems'][system_name_result]['distance'],
                            'stations_data': filtered_station_data
                        }
                        markets_processed_count +=1
                    else:
                        logger.debug(f"No market data kept for system {system_name_result} (all stations empty).")


            logger.info(f"Full local market data (unfiltered by client at save time) for {markets_processed_count}/{len(local_market_overview['systems'])} nearby systems saved.")
            if progress_callback: progress_callback("Local data saved.", 100)
            with open(LOCAL_SELLERS_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_market_overview, f, indent=2)
            return local_market_overview
        except OperationCancelledError:
            logger.info("Local sellers data download was cancelled.")
            raise
        except Exception as e:
            logger.exception(f"Error in download_local_sellers_data: {e}")
            if progress_callback: progress_callback(f"Erreur: {e}", 100)
            return None

async def update_databases_if_needed(
    http_session, 
    current_system,
    current_station,
    radius_val,
    max_age_days_param: int,        
    include_fleet_carriers_val: bool, # Utilisé par optimizer_logic pour filtrer les données lues du cache
    cancel_event: threading.Event = None,
    progress_callback_main=None,
    force_refresh: bool = False
):
    logger.info(f"Checking/Updating databases for system {current_system} with radius {radius_val} LY, max age {max_age_days_param} days. Force refresh: {force_refresh}. GUI FC filter setting: {include_fleet_carriers_val} (will be applied by consumer of data).")
    departure_market_json, local_market_json_new_structure = None, None
    
    def create_prefixed_callback(prefix, main_callback, base_progress_start=0, base_progress_end=100):
        if not main_callback: return None
        def prefixed_callback(message, percentage):
            scaled_percentage = base_progress_start + (percentage / 100) * (base_progress_end - base_progress_start)
            main_callback(f"{prefix}: {message}", int(scaled_percentage))
        return prefixed_callback

    refresh_departure = True
    if force_refresh:
        logger.info("Forcing refresh of departure data due to user request.")
    elif os.path.exists(DEPARTURE_DATA_FILE) and current_station and current_station != "?":
        try:
            with open(DEPARTURE_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            updated_at_str = data.get('updatedAt')
            if updated_at_str:
                updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
                if data.get('system') == current_system and data.get('station') == current_station and age_seconds < (max_age_days_param * 86400):
                    departure_market_json = data; refresh_departure = False
                    logger.info(f"Using recent departure data from {DEPARTURE_DATA_FILE}.")
                    if progress_callback_main: progress_callback_main("Recent departure data found.", 5)
                else: logger.info(f"Departure data is old (age {age_seconds/86400:.1f}d > {max_age_days_param}d), or for a different station/system. Will refresh.")
            else: logger.info("Departure data cache is missing 'updatedAt'. Will refresh.")
        except Exception as e_cache: logger.warning(f"Error reading departure cache {DEPARTURE_DATA_FILE} ({e_cache}), will refresh.")

    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Database update cancelled.")

    if refresh_departure and current_station and current_station != "?" and current_system and current_system != "?":
        logger.info(f"Refreshing departure data for {current_station} in {current_system}.")
        departure_market_json = await download_departure_market_data(
            current_system, current_station,
            max_days_ago=max_age_days_param, 
            include_fleet_carriers=include_fleet_carriers_val, 
            cancel_event=cancel_event,
            progress_callback=create_prefixed_callback("Start", progress_callback_main, 0, 10)
        )
    elif (not current_station or current_station == "?") and os.path.exists(DEPARTURE_DATA_FILE):
        try:
            with open(DEPARTURE_DATA_FILE, 'r', encoding='utf-8') as f: departure_market_json = json.load(f)
        except: pass 
    elif not current_station or current_station == "?":
         logger.info("Skipping departure data refresh: current station is unknown.")


    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Database update cancelled.")

    refresh_local = True
    if force_refresh:
        logger.info("Forcing refresh of local sellers data due to user request.")
    elif os.path.exists(LOCAL_SELLERS_DATA_FILE) and current_system and current_system != "?":
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            if "station_markets" not in data or "systems" not in data: 
                logger.info("Old or incompatible local_sellers_data.json structure detected. Forcing refresh.")
            else: 
                updated_at_str = data.get('updatedAt')
                if updated_at_str:
                    updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
                    if data.get('sourceSystem') == current_system and data.get('radius', 0) >= radius_val and age_seconds < (max_age_days_param * 86400):
                        local_market_json_new_structure = data; refresh_local = False
                        logger.info(f"Using recent local data (new structure) from {LOCAL_SELLERS_DATA_FILE} (radius {data.get('radius',0)} LY).")
                        if progress_callback_main: progress_callback_main("Données locales récentes trouvées.", 15)
                    else: logger.info(f"Local data (new structure) is old (age {age_seconds/86400:.1f}d > {max_age_days_param}d), different system, or insufficient radius ({data.get('radius',0)} < {radius_val}). Will refresh.")
                else: logger.info("Local data cache (new structure) is missing 'updatedAt'. Will refresh.")
        except Exception as e_cache: logger.warning(f"Error reading local cache {LOCAL_SELLERS_DATA_FILE} ({e_cache}), will refresh.")


    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Database update cancelled.")

    if refresh_local and current_system and current_system != "?":
        logger.info(f"Refreshing local data for {current_system} (radius {radius_val} LY).")
        local_market_json_new_structure = await download_local_sellers_data(
            current_system, radius_val,
            max_days_ago=max_age_days_param,
            include_fleet_carriers=include_fleet_carriers_val,
            cancel_event=cancel_event,
            progress_callback=create_prefixed_callback("Local", progress_callback_main, 10, 100)
        )
    elif (not current_system or current_system == "?") and os.path.exists(LOCAL_SELLERS_DATA_FILE):
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                if "station_markets" in loaded_data:
                    local_market_json_new_structure = loaded_data
        except: pass
    elif not current_system or current_system == "?":
        logger.info("Skipping local data refresh: current system is unknown.")

    return departure_market_json, local_market_json_new_structure


async def get_station_specific_market_data(
    session,
    system_name,
    station_name,
    max_days_ago: int,
    include_fleet_carriers: bool,
    player_action='buy',
    cancel_event: threading.Event = None
):
    # Cette fonction conserve l'utilisation des filtres API (maxDaysAgo, fleetCarriers)
    # car elle est destinée à des appels ciblés où la précision est importante
    # et l'impact sur la performance d'un seul appel est moins critique.
    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError(f"get_station_specific_market_data for {station_name} cancelled.")

    api_endpoint_type = '' 
    api_price_field_for_player_transaction = '' 
    relevant_station_quantity_field = '' 

    if player_action == 'buy': 
        api_endpoint_type = 'exports' 
        api_price_field_for_player_transaction = 'buyPrice' 
        relevant_station_quantity_field = 'stock'
    elif player_action == 'sell': 
        api_endpoint_type = 'imports' 
        api_price_field_for_player_transaction = 'sellPrice'
        relevant_station_quantity_field = 'demand'
    else:
        logger.error(f"Invalid player_action '{player_action}' requested for {station_name} in {system_name}.")
        return None

    url = f"{BASE_URL}system/name/{system_name}/commodities/{api_endpoint_type}"
    
    api_params = {"maxDaysAgo": max_days_ago}
    if not include_fleet_carriers: # Si False, on veut exclure les FC
        api_params["fleetCarriers"] = "0"
    # Si include_fleet_carriers est True, on ne spécifie pas le paramètre 'fleetCarriers'
    # pour que l'API V2 retourne tout (y compris FC), et le filtrage se fera par optimizer_logic
    # sur la base de la case cochée dans la GUI.
    # Cependant, pour être cohérent avec la doc API V2/V3:
    # "If not specified, or set to any other value, the response will include results for all stations"
    # Donc, ne pas envoyer le paramètre si include_fleet_carriers est True est correct pour inclure tout.
    # Envoyer fleetCarriers=0 pour exclure.
    # Envoyer fleetCarriers=1 pour UNIQUEMENT FC (non utilisé actuellement).
        
    try:
        system_commodities_raw = await fetch_json(session, url, params=api_params, cancel_event=cancel_event)
        if not isinstance(system_commodities_raw, list):
            logger.warning(f"Expected a list of commodities from {url} for {system_name} (params: {api_params}), got {type(system_commodities_raw)}")
            return None

        station_transaction_offers = []
        for item_from_api in system_commodities_raw:
            if cancel_event and cancel_event.is_set():
                raise OperationCancelledError(f"Processing specific market data for {station_name} cancelled.")
            
            if item_from_api.get('stationName') == station_name:
                player_transaction_price = item_from_api.get(api_price_field_for_player_transaction, 0)
                station_quantity = item_from_api.get(relevant_station_quantity_field, 0)

                if player_transaction_price > 0 and (player_action == 'sell' or (player_action == 'buy' and station_quantity > 0)):
                    station_transaction_offers.append({
                        'commodityName': item_from_api.get('commodityName'),
                        'commodity_localised': item_from_api.get('commodityLocalisedName', item_from_api.get('commodityName')),
                        'price': player_transaction_price, 
                        'quantity_at_station': station_quantity, 
                        'stock': item_from_api.get('stock', 0) if player_action == 'buy' else 0,
                        'demand': item_from_api.get('demand', 0) if player_action == 'sell' else 0,
                        'maxLandingPadSize': item_from_api.get('maxLandingPadSize'),
                        'distanceToArrival': item_from_api.get('distanceToArrival'),
                        'stationType': item_from_api.get('stationType', item_from_api.get('station', {}).get('type', 'Unknown'))
                    })
        
        logger.info(f"Found {len(station_transaction_offers)} relevant offers for player action '{player_action}' at {station_name} in {system_name} with params {api_params}.")
        return station_transaction_offers
    except OperationCancelledError:
        raise
    except Exception as e:
        logger.error(f"Error in get_station_specific_market_data for {station_name}/{system_name} (player_action: {player_action}, params: {api_params}): {e}")
        return None