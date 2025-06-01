#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
import threading

from constants import (
    EDSM_HEADERS, SHIPYARD_DATA_FILE,
    CONCURRENCY_LIMIT # Assurez-vous qu'elle est définie dans constants.py
)
import edsm_api_handler
from edsm_api_handler import OperationCancelledError

logger = logging.getLogger(__name__)

async def download_regional_shipyard_data(
    center_system_name: str,
    radius_ly: int,
    cancel_event: threading.Event = None,
    progress_callback=None
):
    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Téléchargement des données de chantier naval régional annulé (début).")

    logger.info(f"Début du téléchargement des données de chantier naval régionales. Centre: {center_system_name}, Rayon: {radius_ly} AL.")
    if progress_callback:
        progress_callback(f"Recherche des systèmes à moins de {radius_ly} AL de {center_system_name}...", 0)

    # Structure de stockage :
    # {
    #   "sourceSystem": "Sol", "radius": 50, "updatedAt": "...",
    #   "systems_with_shipyards": {
    #     "LHS 20": {
    #       "coords": {"x": 0, "y": 0, "z": 0}, # Optionnel
    #       "stations": [
    #         {"stationName": "Gohar Station", "marketId": 123, "ships": ["Cobra Mk III", ...], "distanceToArrival": 100, "type": "Orbis Starport"},
    #         ...
    #       ]
    #     }, ...
    #   }
    # }
    all_shipyards_data = {
        "sourceSystem": center_system_name,
        "radius": radius_ly,
        "systems_with_shipyards": {},
        "updatedAt": None
    }
    
    timeout = aiohttp.ClientTimeout(total=180) # Augmenté pour les opérations potentiellement longues
    async with aiohttp.ClientSession(headers=EDSM_HEADERS, timeout=timeout) as session:
        try:
            sphere_systems = await edsm_api_handler.get_systems_in_sphere(
                session,
                system_name=center_system_name,
                radius=radius_ly,
                show_information=False, # Moins crucial maintenant que nous avons get_stations_in_system
                show_coordinates=True, # Utile pour stocker les coordonnées
                cancel_event=cancel_event
            )

            if not sphere_systems:
                logger.warning(f"Aucun système trouvé dans la sphère autour de {center_system_name} (rayon {radius_ly} AL).")
                if progress_callback: progress_callback("Aucun système trouvé dans la sphère.", 100)
                # Sauvegarder un fichier vide structuré pour indiquer que la recherche a eu lieu
                all_shipyards_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
                with open(SHIPYARD_DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_shipyards_data, f, indent=2)
                return all_shipyards_data


            total_systems_in_sphere = len(sphere_systems)
            if progress_callback:
                progress_callback(f"{total_systems_in_sphere} systèmes trouvés. Récupération des stations...", 5)

            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
            systems_processed_count = 0

            async def process_system(system_info_from_sphere):
                nonlocal systems_processed_count
                system_name_iter = system_info_from_sphere.get("name")
                system_coords_iter = system_info_from_sphere.get("coords") # Peut être None

                if not system_name_iter:
                    systems_processed_count += 1
                    return None

                stations_with_shipyards_in_system = []
                try:
                    async with semaphore:
                        if cancel_event and cancel_event.is_set():
                            raise OperationCancelledError(f"Annulation avant get_stations_in_system pour {system_name_iter}")
                        
                        all_stations_in_system = await edsm_api_handler.get_stations_in_system(session, system_name_iter, cancel_event)

                        stations_having_shipyard = [
                            st for st in all_stations_in_system if st.get("haveShipyard")
                        ]
                        
                        logger.debug(f"Système {system_name_iter}: {len(all_stations_in_system)} stations au total, {len(stations_having_shipyard)} avec 'haveShipyard:true'.")

                        for station_data in stations_having_shipyard:
                            station_name_iter = station_data.get("name")
                            market_id_iter = station_data.get("marketId")
                            dist_to_arrival_iter = station_data.get("distanceToArrival")
                            station_type_iter = station_data.get("type")

                            if not station_name_iter:
                                continue

                            if cancel_event and cancel_event.is_set():
                                raise OperationCancelledError(f"Annulation avant get_shipyard_at_station pour {station_name_iter}")
                            
                            # Nouvel appel avec sémaphore pour get_shipyard_at_station aussi
                            # async with semaphore: # Déjà dans une sémaphore, pas besoin de la ré-imbriquer pour le même thread logique
                            shipyard_content = await edsm_api_handler.get_shipyard_at_station(session, system_name_iter, station_name_iter, cancel_event)
                            
                            if shipyard_content and shipyard_content.get("ships"):
                                ships_list = [s.get("name") for s in shipyard_content.get("ships", []) if s.get("name")]
                                if ships_list: # Seulement si des vaisseaux sont effectivement listés
                                    stations_with_shipyards_in_system.append({
                                        "stationName": station_name_iter,
                                        "marketId": market_id_iter or shipyard_content.get("marketId"), # marketId peut aussi être dans shipyard_content
                                        "ships": ships_list,
                                        "distanceToArrival": dist_to_arrival_iter,
                                        "type": station_type_iter
                                    })
                except OperationCancelledError:
                    raise # Laisser asyncio.gather la récupérer
                except Exception as e_proc:
                    logger.error(f"Erreur lors du traitement du système {system_name_iter}: {e_proc}")
                finally:
                    systems_processed_count += 1
                    if progress_callback:
                        base_progress = 5 # Après la recherche initiale des systèmes
                        progress_per_system = (95 - base_progress) / total_systems_in_sphere if total_systems_in_sphere > 0 else 0
                        current_progress = base_progress + int(systems_processed_count * progress_per_system)
                        progress_callback(f"Système {systems_processed_count}/{total_systems_in_sphere} ({system_name_iter}) analysé.", current_progress)
                
                if stations_with_shipyards_in_system:
                    return {"systemName": system_name_iter, "coords": system_coords_iter, "stations": stations_with_shipyards_in_system}
                return None

            tasks = [process_system(sys_info) for sys_info in sphere_systems]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res_item in results:
                if isinstance(res_item, OperationCancelledError):
                    raise res_item
                if isinstance(res_item, Exception):
                    logger.error(f"Exception dans une tâche gather (process_system): {res_item}")
                    continue
                if res_item and res_item.get("systemName") and res_item.get("stations"):
                    all_shipyards_data["systems_with_shipyards"][res_item["systemName"]] = {
                        "coords": res_item.get("coords"),
                        "stations": res_item["stations"]
                    }
            
            all_shipyards_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
            with open(SHIPYARD_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_shipyards_data, f, indent=2)
            
            logger.info(f"Données régionales des chantiers navals sauvegardées dans {SHIPYARD_DATA_FILE}.")
            if progress_callback:
                num_systems_found_with_shipyards = len(all_shipyards_data["systems_with_shipyards"])
                progress_callback(f"Données sauvegardées. {num_systems_found_with_shipyards} systèmes avec chantiers navals trouvés.", 100)
            
            return all_shipyards_data

        except OperationCancelledError:
            logger.info("Téléchargement des données de chantier naval régional annulé.")
            if progress_callback: progress_callback("Opération annulée.", 100)
            raise
        except Exception as e:
            logger.exception(f"Erreur majeure lors du téléchargement des données de chantier naval régional: {e}")
            if progress_callback: progress_callback(f"Erreur: {e}", 100)
            return None # Ou lever l'exception


def load_shipyard_data_from_file():
    # ... (code inchangé) ...
    if os.path.exists(SHIPYARD_DATA_FILE):
        try:
            with open(SHIPYARD_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Données de chantier naval chargées depuis {SHIPYARD_DATA_FILE}.")
            return data
        except Exception as e:
            logger.exception(f"Erreur lors du chargement de {SHIPYARD_DATA_FILE}: {e}")
            return None
    logger.info(f"Le fichier de données de chantier naval {SHIPYARD_DATA_FILE} n'existe pas.")
    return None

def get_shipyard_db_update_time_str():
    # ... (code inchangé) ...
    data = load_shipyard_data_from_file()
    if data and "updatedAt" in data:
        try:
            updated_at_iso = data["updatedAt"]
            if 'Z' in updated_at_iso:
                dt_utc = datetime.fromisoformat(updated_at_iso.replace('Z', '+00:00'))
            else:
                dt_utc = datetime.fromisoformat(updated_at_iso)
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            return f"BD Chantiers: {dt_utc.astimezone(None).strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception as e_date:
            logger.error(f"Erreur de format de date pour updatedAt ('{data['updatedAt']}') dans {SHIPYARD_DATA_FILE}: {e_date}")
            return "BD Chantiers: Erreur Date"
    return "BD Chantiers: Non trouvée"