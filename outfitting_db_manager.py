#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
import threading

# Importer depuis les autres modules de l'application
from constants import (
    EDSM_HEADERS, # Partagé avec edsm_api_handler
    OUTFITTING_DATA_FILE,
    CONCURRENCY_LIMIT,
    # DEFAULT_OUTFITTING_RADIUS_LY # Non utilisé directement ici, mais pour info
)
import edsm_api_handler # Pour les appels API EDSM
# S'assurer d'importer la bonne exception OperationCancelledError
# Si edsm_api_handler définit sa propre OperationCancelledError, il faut l'importer.
# Sinon, si elle est globale (ex: définie dans api_handler.py et réutilisée), c'est bon.
# Pour l'instant, on suppose que edsm_api_handler peut lever sa propre OperationCancelledError ou une compatible.
from edsm_api_handler import OperationCancelledError as EdsOperationCancelledError


logger = logging.getLogger(__name__)

async def download_regional_outfitting_data(
    center_system_name: str,
    radius_ly: int,
    cancel_event: threading.Event = None,
    progress_callback=None
):
    """
    Télécharge les données d'équipement pour tous les systèmes dans un rayon donné
    autour d'un système central.
    """
    if cancel_event and cancel_event.is_set():
        raise EdsOperationCancelledError("Téléchargement des données d'équipement régional annulé (début).")

    logger.info(f"Début du téléchargement des données d'équipement régionales. Centre: {center_system_name}, Rayon: {radius_ly} AL.")
    if progress_callback:
        progress_callback(f"Recherche des systèmes à moins de {radius_ly} AL de {center_system_name}...", 0)

    # Structure de stockage :
    # {
    #   "sourceSystem": "Sol", "radius": 50, "updatedAt": "...",
    #   "systems_with_outfitting": { // Renommé pour clarté
    #     "LHS 20": {
    #       "coords": {"x": 0, "y": 0, "z": 0},
    #       "stations": [
    #         {
    #           "stationName": "Gohar Station", "marketId": 123, 
    #           "type": "Orbis Starport", "distanceToArrival": 100,
    #           "modules": [{"id": "...", "name": "..."}, ...] 
    #         },
    #         // ... autres stations avec outfitting
    #       ]
    #     }, 
    #     // ... autres systèmes
    #   }
    # }
    all_outfitting_data = {
        "sourceSystem": center_system_name,
        "radius": radius_ly,
        "systems_with_outfitting": {}, # Modifié de systems_with_shipyards
        "updatedAt": None
    }
    
    # Utiliser les EDSM_HEADERS définis dans constants.py
    timeout = aiohttp.ClientTimeout(total=180) # Timeout pour les opérations longues
    async with aiohttp.ClientSession(headers=EDSM_HEADERS, timeout=timeout) as session:
        try:
            # 1. Obtenir les systèmes dans la sphère
            sphere_systems = await edsm_api_handler.get_systems_in_sphere(
                session,
                system_name=center_system_name,
                radius=radius_ly,
                show_coordinates=True, # Utile pour stocker les coordonnées et calculer les distances plus tard
                show_information=False, # Moins critique car get_stations_in_system donne haveOutfitting
                cancel_event=cancel_event
            )

            if not sphere_systems:
                logger.warning(f"Aucun système trouvé dans la sphère autour de {center_system_name} (rayon {radius_ly} AL) pour l'équipement.")
                if progress_callback: progress_callback("Aucun système trouvé dans la sphère.", 100)
                all_outfitting_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
                # Sauvegarder un fichier vide structuré pour indiquer que la recherche a eu lieu
                with open(OUTFITTING_DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_outfitting_data, f, indent=2)
                return all_outfitting_data # Retourner les données vides structurées

            total_systems_in_sphere = len(sphere_systems)
            if progress_callback:
                progress_callback(f"{total_systems_in_sphere} systèmes trouvés. Récupération des stations et équipements...", 5)

            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT) # Limiter les appels concurrents
            systems_processed_count = 0

            async def process_system_for_outfitting(system_info_from_sphere):
                nonlocal systems_processed_count
                system_name_iter = system_info_from_sphere.get("name")
                system_coords_iter = system_info_from_sphere.get("coords")

                if not system_name_iter:
                    systems_processed_count += 1 # Compter même si le nom est manquant pour la progression
                    return None

                stations_with_modules_in_system = []
                try:
                    async with semaphore: # Acquérir le sémaphore avant les appels API pour ce système
                        if cancel_event and cancel_event.is_set():
                            raise EdsOperationCancelledError(f"Annulation avant get_stations_in_system pour {system_name_iter}")
                        
                        all_stations_in_system = await edsm_api_handler.get_stations_in_system(session, system_name_iter, cancel_event)

                        stations_having_outfitting = [
                            st for st in all_stations_in_system if st.get("haveOutfitting") # Vérifier le flag
                        ]
                        
                        logger.debug(f"Système {system_name_iter}: {len(all_stations_in_system)} stations au total, {len(stations_having_outfitting)} avec 'haveOutfitting:true'.")

                        for station_data in stations_having_outfitting:
                            station_name_iter = station_data.get("name")
                            market_id_iter = station_data.get("marketId") # Peut être utile
                            dist_to_arrival_iter = station_data.get("distanceToArrival")
                            station_type_iter = station_data.get("type")

                            if not station_name_iter:
                                continue # Passer à la station suivante si le nom est manquant

                            if cancel_event and cancel_event.is_set():
                                raise EdsOperationCancelledError(f"Annulation avant get_outfitting_at_station pour {station_name_iter}")
                            
                            # Pas besoin de ré-acquérir le sémaphore ici car on est déjà dans une tâche par système
                            modules_at_station = await edsm_api_handler.get_outfitting_at_station(session, system_name_iter, station_name_iter, cancel_event)
                            
                            if modules_at_station: # Si la liste n'est pas vide
                                stations_with_modules_in_system.append({
                                    "stationName": station_name_iter,
                                    "marketId": market_id_iter, # ou celui de la réponse outfitting si différent/plus fiable
                                    "type": station_type_iter,
                                    "distanceToArrival": dist_to_arrival_iter,
                                    "modules": modules_at_station # Liste des dicts {"id": ..., "name": ...}
                                })
                except EdsOperationCancelledError:
                    raise # Laisser asyncio.gather la récupérer
                except Exception as e_proc_sys:
                    # Ne pas bloquer tout le processus pour un seul système en erreur
                    logger.error(f"Erreur lors du traitement du système {system_name_iter} pour l'équipement: {e_proc_sys}", exc_info=True)
                finally:
                    systems_processed_count += 1
                    if progress_callback:
                        base_progress = 5 # Après la recherche initiale des systèmes
                        progress_per_system = (95 - base_progress) / total_systems_in_sphere if total_systems_in_sphere > 0 else 0
                        current_progress = base_progress + int(systems_processed_count * progress_per_system)
                        progress_callback(f"Système (équipement) {systems_processed_count}/{total_systems_in_sphere} ({system_name_iter}) analysé.", current_progress)
                
                if stations_with_modules_in_system:
                    return {"systemName": system_name_iter, "coords": system_coords_iter, "stations": stations_with_modules_in_system}
                return None # Si aucune station avec équipement n'a été trouvée ou si erreur

            # Collecter toutes les tâches pour les exécuter en parallèle (limitées par le sémaphore)
            tasks = [process_system_for_outfitting(sys_info) for sys_info in sphere_systems]
            results_per_system = await asyncio.gather(*tasks, return_exceptions=True)

            # Traiter les résultats
            for res_item in results_per_system:
                if isinstance(res_item, EdsOperationCancelledError):
                    raise res_item # Propager l'annulation pour arrêter tout le processus
                if isinstance(res_item, Exception):
                    # Logguer l'erreur spécifique d'une tâche mais continuer avec les autres
                    logger.error(f"Exception dans une tâche gather (process_system_for_outfitting): {res_item}", exc_info=True)
                    continue
                if res_item and res_item.get("systemName") and res_item.get("stations"):
                    # Ajouter les données du système au dictionnaire principal
                    all_outfitting_data["systems_with_outfitting"][res_item["systemName"]] = {
                        "coords": res_item.get("coords"),
                        "stations": res_item["stations"]
                    }
            
            all_outfitting_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
            with open(OUTFITTING_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_outfitting_data, f, indent=2)
            
            logger.info(f"Données régionales d'équipement sauvegardées dans {OUTFITTING_DATA_FILE}.")
            if progress_callback:
                num_systems_found_with_outfitting = len(all_outfitting_data["systems_with_outfitting"])
                progress_callback(f"Données d'équipement sauvegardées. {num_systems_found_with_outfitting} systèmes avec équipement trouvés.", 100)
            
            return all_outfitting_data

        except EdsOperationCancelledError:
            logger.info("Téléchargement des données d'équipement régional annulé.")
            if progress_callback: progress_callback("Opération annulée.", 100) # Ou un état spécifique
            raise # Propager pour que l'appelant (GUI) sache
        except Exception as e:
            logger.exception(f"Erreur majeure lors du téléchargement des données d'équipement régional: {e}")
            if progress_callback: progress_callback(f"Erreur: {e}", 100) # Marquer comme terminé avec erreur
            # Ne pas retourner None, mais plutôt propager l'erreur pour une meilleure gestion dans la GUI
            raise


def load_outfitting_data_from_file():
    """Charge les données d'équipement depuis le fichier local."""
    if os.path.exists(OUTFITTING_DATA_FILE):
        try:
            with open(OUTFITTING_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Données d'équipement chargées depuis {OUTFITTING_DATA_FILE}.")
            return data
        except json.JSONDecodeError as e_json:
            logger.error(f"Erreur de décodage JSON lors du chargement de {OUTFITTING_DATA_FILE}: {e_json}. Le fichier est peut-être corrompu.")
            return None # Ou lever une exception personnalisée
        except Exception as e:
            logger.exception(f"Erreur lors du chargement de {OUTFITTING_DATA_FILE}: {e}")
            return None
    logger.info(f"Le fichier de données d'équipement {OUTFITTING_DATA_FILE} n'existe pas.")
    return None

def get_outfitting_db_update_time_str():
    """Retourne la date de dernière mise à jour de la BD d'équipement en format lisible."""
    data = load_outfitting_data_from_file()
    if data and "updatedAt" in data:
        try:
            updated_at_iso = data["updatedAt"]
            # Gestion des formats de date ISO (avec ou sans Z/offset)
            if 'Z' in updated_at_iso:
                dt_utc = datetime.fromisoformat(updated_at_iso.replace('Z', '+00:00'))
            else:
                dt_utc = datetime.fromisoformat(updated_at_iso)
                if dt_utc.tzinfo is None: # Si pas de timezone, supposer UTC
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            
            # Convertir en fuseau horaire local pour l'affichage
            return f"BD Équip.: {dt_utc.astimezone(None).strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception as e_date:
            logger.error(f"Erreur de format de date pour updatedAt ('{data.get('updatedAt')}') dans {OUTFITTING_DATA_FILE}: {e_date}")
            return "BD Équip.: Erreur Date"
    return "BD Équip.: Non trouvée"