#!/usr/bin/env python3
import logging
import math

from constants import (
    PLANETARY_STATION_TYPES,
    FLEET_CARRIER_STATION_TYPES,
    STATION_TYPE_TO_PAD_SIZE_LETTER # Nécessaire pour la déduction
)
# module_catalog_data n'est pas utilisé ici car on attend des ID EDSM
# et la déduction de pad se base sur le type de station, pas sur le module.

logger = logging.getLogger(__name__)

def find_stations_with_modules(
    requested_module_ids: list[str],
    all_outfitting_data: dict,
    current_player_system_coords: dict = None,
    max_distance_ly_filter: float = None,
    include_planetary: bool = True,
    include_fleet_carriers: bool = True,
    max_station_dist_ls: float = None
):
    """
    Recherche les stations vendant TOUS les modules spécifiés.
    Ajoute la taille de pad déduite à chaque station trouvée.
    """
    found_stations_details = []
    if not requested_module_ids:
        logger.info("find_stations_with_modules: Aucune ID de module demandée.")
        return found_stations_details
    
    if not all_outfitting_data or "systems_with_outfitting" not in all_outfitting_data:
        logger.warning("find_stations_with_modules: Données d'équipement non valides ou vides.")
        return found_stations_details

    logger.info(f"Recherche des stations vendant les modules EDSM IDs: {requested_module_ids}")
    requested_module_ids_set = set(requested_module_ids)

    for system_name, system_data in all_outfitting_data["systems_with_outfitting"].items():
        system_coords = system_data.get("coords")
        distance_ly = float('inf')

        if current_player_system_coords and system_coords and \
           all(k in system_coords for k in ['x', 'y', 'z']) and \
           all(k in current_player_system_coords for k in ['x', 'y', 'z']):
            try:
                dist_x = system_coords['x'] - current_player_system_coords['x']
                dist_y = system_coords['y'] - current_player_system_coords['y']
                dist_z = system_coords['z'] - current_player_system_coords['z']
                distance_ly = math.sqrt(dist_x**2 + dist_y**2 + dist_z**2)
            except (TypeError, KeyError) as e:
                logger.warning(f"Impossible de calculer la distance pour le système {system_name}: {e}")
        
        if max_distance_ly_filter is not None and distance_ly > max_distance_ly_filter:
            continue

        for station_entry in system_data.get("stations", []):
            station_name = station_entry.get("stationName")
            station_type = station_entry.get("type") # Type de station EDSM
            dist_ls_val = station_entry.get("distanceToArrival")

            # Déduction de la taille du pad (comme pour le chantier naval)
            deduced_pad_size_letter = STATION_TYPE_TO_PAD_SIZE_LETTER.get(station_type, "?")

            if not include_planetary and station_type in PLANETARY_STATION_TYPES:
                continue
            if not include_fleet_carriers and station_type in FLEET_CARRIER_STATION_TYPES:
                continue
            if max_station_dist_ls is not None and dist_ls_val is not None:
                try:
                    if float(dist_ls_val) > max_station_dist_ls:
                        continue
                except ValueError:
                    pass 

            station_modules_raw = station_entry.get("modules", [])
            station_module_ids_set = set()
            for module_data in station_modules_raw:
                if isinstance(module_data, dict) and "id" in module_data:
                    station_module_ids_set.add(module_data["id"])
            
            if requested_module_ids_set.issubset(station_module_ids_set):
                modules_found_at_station_names = []
                for mod_id in requested_module_ids_set:
                    for mod_data in station_modules_raw:
                        if mod_data.get("id") == mod_id:
                            modules_found_at_station_names.append(mod_data.get("name", mod_id))
                            break
                
                found_stations_details.append({
                    "systemName": system_name,
                    "stationName": station_name,
                    "distanceLy": distance_ly,
                    "distanceToArrival": dist_ls_val,
                    "stationType": station_type,
                    "marketId": station_entry.get("marketId"),
                    "modulesMatched": modules_found_at_station_names,
                    "deducedPadSize": deduced_pad_size_letter # Ajout de la taille de pad
                })
    
    found_stations_details.sort(key=lambda x: (x.get("distanceLy", float('inf')), x.get("distanceToArrival", float('inf')) if x.get("distanceToArrival") is not None else float('inf')))
    
    logger.info(f"Trouvé {len(found_stations_details)} stations vendant tous les modules demandés.")
    return found_stations_details