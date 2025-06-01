#!/usr/bin/env python3
import logging
import math

from constants import (
    PURCHASABLE_SHIPS_LIST,
    PLANETARY_STATION_TYPES,
    FLEET_CARRIER_STATION_TYPES,
    # STATION_PAD_SIZE_MAP, # Non utilisé directement ici, mais utile pour référence
    STATION_TYPE_TO_PAD_SIZE_LETTER # NOUVEL IMPORT
)

logger = logging.getLogger(__name__)

def normalize_ship_name(name: str) -> str:
    """Normalise un nom de vaisseau pour la comparaison."""
    if not isinstance(name, str):
        return ""
    return name.lower().replace(" ", "").replace("-", "").replace("_", "").replace("mk", "mark")

def find_stations_selling_ship(
    ship_name_to_find: str,
    all_shipyard_data: dict,
    current_player_system_coords: dict = None,
    max_distance_ly_filter: float = None,
    include_planetary: bool = True,
    include_fleet_carriers: bool = True,
    max_station_dist_ls: float = None
):
    """
    Trouve les stations vendant un vaisseau spécifique, avec filtres optionnels.
    Ajoute la taille de pad déduite.
    """
    if not all_shipyard_data or "systems_with_shipyards" not in all_shipyard_data:
        logger.warning("find_stations_selling_ship: Pas de données de chantier naval fournies ou format incorrect.")
        return []

    found_stations = []
    normalized_target_ship_display_name = normalize_ship_name(ship_name_to_find)
    
    # Trouver la clé EDSM correspondante pour le nom d'affichage sélectionné
    normalized_target_ship_edsm_name = ""
    for edsm_key, display_name in PURCHASABLE_SHIPS_LIST.items():
        if normalize_ship_name(display_name) == normalized_target_ship_display_name:
            normalized_target_ship_edsm_name = normalize_ship_name(edsm_key) # Normaliser la clé EDSM aussi
            break
    
    if not normalized_target_ship_edsm_name:
         # Fallback si le nom d'affichage est déjà une clé EDSM ou un nom EDSM normalisé
        if normalize_ship_name(ship_name_to_find) in [normalize_ship_name(k) for k in PURCHASABLE_SHIPS_LIST.keys()]:
            normalized_target_ship_edsm_name = normalize_ship_name(ship_name_to_find)
        else:
            logger.warning(f"Nom de vaisseau cible '{ship_name_to_find}' non trouvé dans PURCHASABLE_SHIPS_LIST après normalisation pour obtenir la clé EDSM.")
            # On peut essayer de continuer avec le nom normalisé directement, au cas où
            normalized_target_ship_edsm_name = normalized_target_ship_display_name


    logger.info(f"Recherche du vaisseau normalisé (EDSM key/name): '{normalized_target_ship_edsm_name}' (basé sur la sélection: '{ship_name_to_find}')")

    for system_name, system_data in all_shipyard_data["systems_with_shipyards"].items():
        system_coords = system_data.get("coords")
        distance_ly = float('inf')

        if current_player_system_coords and system_coords:
            try:
                dx = system_coords["x"] - current_player_system_coords["x"]
                dy = system_coords["y"] - current_player_system_coords["y"]
                dz = system_coords["z"] - current_player_system_coords["z"]
                distance_ly = math.sqrt(dx*dx + dy*dy + dz*dz)
            except (TypeError, KeyError) as e:
                logger.warning(f"Impossible de calculer la distance pour le système {system_name}: {e}")
                distance_ly = float('inf')
        
        if max_distance_ly_filter is not None and distance_ly > max_distance_ly_filter:
            continue

        for station_details in system_data.get("stations", []):
            station_name = station_details.get("stationName")
            station_type = station_details.get("type")
            dist_ls_val = station_details.get("distanceToArrival")

            # Déduction de la taille du pad
            deduced_pad_size_letter = STATION_TYPE_TO_PAD_SIZE_LETTER.get(station_type, "?")

            # Filtre planétaire
            if not include_planetary and station_type in PLANETARY_STATION_TYPES:
                # logger.debug(f"Skipping planetary station {station_name} in {system_name} due to filter.")
                continue
            
            # Filtre Fleet Carrier
            if not include_fleet_carriers and station_type in FLEET_CARRIER_STATION_TYPES:
                # logger.debug(f"Skipping Fleet Carrier {station_name} in {system_name} due to filter.")
                continue

            # Filtre distance à l'étoile
            if max_station_dist_ls is not None and dist_ls_val is not None and dist_ls_val > max_station_dist_ls:
                # logger.debug(f"Skipping station {station_name} (Dist LS: {dist_ls_val}) due to filter (Max LS: {max_station_dist_ls}).")
                continue
                
            ships_sold_at_station = station_details.get("ships", [])
            for ship_sold_entry in ships_sold_at_station:
                ship_sold_name_edsm = ""
                # L'API EDSM retourne parfois une liste de chaînes, parfois une liste de dicts
                if isinstance(ship_sold_entry, str):
                    ship_sold_name_edsm = ship_sold_entry
                elif isinstance(ship_sold_entry, dict) and "name" in ship_sold_entry:
                    # C'est le format attendu si EDSM retourne plus de détails, bien que non documenté pour cet endpoint.
                    ship_sold_name_edsm = ship_sold_entry.get("name")
                
                if not isinstance(ship_sold_name_edsm, str) or not ship_sold_name_edsm: # S'assurer que c'est une chaîne non vide
                    # logger.warning(f"Entrée de vaisseau invalide à {station_name}: {ship_sold_entry}")
                    continue

                normalized_ship_sold_edsm = normalize_ship_name(ship_sold_name_edsm)

                if normalized_ship_sold_edsm == normalized_target_ship_edsm_name:
                    found_stations.append({
                        "systemName": system_name,
                        "stationName": station_name,
                        "distanceLy": distance_ly,
                        "distanceToArrival": dist_ls_val,
                        "stationType": station_type,
                        "marketId": station_details.get("marketId"),
                        "deducedPadSize": deduced_pad_size_letter # Ajout de la taille de pad déduite
                    })
                    break # On a trouvé le vaisseau dans cette station, pas besoin de vérifier les autres vaisseaux ici
    
    # Trier les stations trouvées par distance en LY (croissant)
    found_stations.sort(key=lambda x: x.get("distanceLy", float('inf')))
    logger.info(f"Retour de {len(found_stations)} stations vendant '{ship_name_to_find}'.")
    return found_stations