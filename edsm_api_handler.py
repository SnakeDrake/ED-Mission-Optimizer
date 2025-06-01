#!/usr/bin/env python3
import asyncio
import aiohttp
import logging
import threading

# Importer les constantes nécessaires
from constants import EDSM_BASE_URL, EDSM_HEADERS # Assurez-vous qu'elles sont définies dans constants.py

logger = logging.getLogger(__name__)

class OperationCancelledError(Exception):
    """Exception personnalisée pour les opérations annulées."""
    pass

async def fetch_edsm_json(session, url, params: dict = None, cancel_event: threading.Event = None):
    """
    Fonction pour récupérer des données JSON depuis l'API EDSM.
    """
    if cancel_event and cancel_event.is_set():
        logger.info(f"Operation cancelled before fetching EDSM URL {url}")
        raise OperationCancelledError(f"Fetching EDSM URL cancelled: {url}")

    log_params = f" with params: {params}" if params else ""
    logger.debug(f"Fetching EDSM URL: {url}{log_params}")
    try:
        # Utiliser EDSM_HEADERS ici
        async with session.get(url, headers=EDSM_HEADERS, params=params, timeout=aiohttp.ClientTimeout(total=60)) as response:
            if cancel_event and cancel_event.is_set():
                logger.info(f"Operation cancelled during fetching EDSM URL {url}")
                raise OperationCancelledError(f"Fetching EDSM URL cancelled: {url}")
            
            response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP 4xx/5xx
            
            # EDSM retourne parfois un array vide [] ou un objet vide {} comme réponse valide
            content = await response.json()
            return content
            
    except aiohttp.ClientResponseError as e:
        logger.error(f"EDSM API ClientResponseError for {url}{log_params}: {e.status} {e.message}")
        try:
            error_content = await e.response.json() # Tenter de lire le corps de l'erreur
            logger.error(f"EDSM Error content: {error_content}")
        except Exception:
            # Impossible de parser le corps de l'erreur ou pas de JSON
            logger.error(f"EDSM Error content for {url}{log_params}: Could not parse error response body. Raw response: {await e.response.text()}")
        raise # Relancer l'exception d'origine pour que l'appelant la gère
    except aiohttp.ClientConnectorError as e:
        logger.error(f"EDSM API ClientConnectorError for {url}{log_params}: {e}")
        raise
    except asyncio.TimeoutError:
        logger.error(f"EDSM API Timeout (60s) for {url}{log_params}")
        raise
    except OperationCancelledError:
        raise # Relancer directement
    except Exception as e: # Inclut json.JSONDecodeError si la réponse n'est pas du JSON valide
        logger.error(f"Unexpected error fetching EDSM URL {url}{log_params}: {e}", exc_info=True)
        raise

async def get_systems_in_sphere(
    session: aiohttp.ClientSession,
    system_name: str = None,
    coordinates: dict = None, # attend un dict {'x': val, 'y': val, 'z': val}
    min_radius: int = 0,
    radius: int = 50,
    show_id: bool = False,
    show_coordinates: bool = False,
    show_permit: bool = False,
    show_information: bool = False, 
    show_primary_star: bool = False,
    cancel_event: threading.Event = None
):
    """
    Récupère les systèmes dans une sphère autour d'un système ou de coordonnées.
    """
    api_endpoint = "api-v1/sphere-systems"
    url = f"{EDSM_BASE_URL.rstrip('/')}/{api_endpoint}" # Assurer un seul /
    
    params = {
        "minRadius": min_radius,
        "radius": radius,
        "showId": 1 if show_id else 0,
        "showCoordinates": 1 if show_coordinates else 0,
        "showPermit": 1 if show_permit else 0,
        "showInformation": 1 if show_information else 0, 
        "showPrimaryStar": 1 if show_primary_star else 0
    }
    if system_name:
        params["systemName"] = system_name
    elif coordinates and all(k in coordinates for k in ('x', 'y', 'z')):
        params.update(coordinates)
    else:
        logger.error("get_systems_in_sphere: systemName ou coordinates valide requis.")
        return [] 

    logger.info(f"Requesting systems in sphere: Center='{system_name or coordinates}', Radius={radius} LY, Params={params}")
    
    try:
        systems_data = await fetch_edsm_json(session, url, params, cancel_event)
        if isinstance(systems_data, list):
            logger.info(f"Found {len(systems_data)} systems in sphere.")
            return systems_data
        else: # EDSM retourne {} si systemName non trouvé, ce qui n'est pas une liste
            logger.warning(f"Unexpected response type for sphere systems (expected list): {type(systems_data)}. Data: {systems_data}")
            return []
            
    except OperationCancelledError:
        logger.info("get_systems_in_sphere operation cancelled.")
        raise
    except Exception as e:
        logger.exception(f"Error in get_systems_in_sphere for '{system_name or coordinates}': {e}")
        return [] 

async def get_stations_in_system(
    session: aiohttp.ClientSession,
    system_name: str,
    cancel_event: threading.Event = None
):
    """
    Récupère toutes les stations d'un système donné.
    """
    api_endpoint = "api-system-v1/stations"
    url = f"{EDSM_BASE_URL.rstrip('/')}/{api_endpoint}"
    params = {"systemName": system_name}

    logger.info(f"Requesting stations for system: '{system_name}'")
    try:
        response_data = await fetch_edsm_json(session, url, params, cancel_event)
        if isinstance(response_data, dict) and "stations" in response_data:
            logger.info(f"Found {len(response_data.get('stations',[]))} stations in system '{system_name}'.")
            return response_data.get("stations", [])
        elif isinstance(response_data, list) and not response_data: 
            logger.info(f"System '{system_name}' not found by EDSM stations endpoint or no stations (returned empty list).")
            return []
        else:
            logger.warning(f"Unexpected response type or structure for stations in system '{system_name}'. Data: {str(response_data)[:200]}")
            return []
            
    except OperationCancelledError:
        logger.info(f"get_stations_in_system for '{system_name}' cancelled.")
        raise
    except Exception as e:
        logger.error(f"Error in get_stations_in_system for '{system_name}': {e}", exc_info=True)
        raise

async def get_shipyard_at_station(
    session: aiohttp.ClientSession,
    system_name: str,
    station_name: str,
    cancel_event: threading.Event = None
):
    """
    Récupère les vaisseaux vendus à une station spécifique dans un système donné.
    Retourne un dictionnaire si trouvé, ou un dictionnaire vide sinon.
    """
    api_endpoint = "api-system-v1/stations/shipyard"
    url = f"{EDSM_BASE_URL.rstrip('/')}/{api_endpoint}"
    params = {
        "systemName": system_name,
        "stationName": station_name
    }
    
    logger.info(f"Requesting shipyard data for station: '{station_name}' in system: '{system_name}'")
    
    try:
        shipyard_data = await fetch_edsm_json(session, url, params, cancel_event)
        
        if isinstance(shipyard_data, dict):
            if "ships" in shipyard_data and "name" in shipyard_data and "id" in shipyard_data: 
                logger.info(f"Shipyard data found for '{station_name}' in '{system_name}': {len(shipyard_data.get('ships',[]))} ship(s). MarketID: {shipyard_data.get('id')}")
            elif not shipyard_data: 
                 logger.info(f"No shipyard data (empty dict response from EDSM) for '{station_name}' in '{system_name}'.")
            else: 
                logger.warning(f"Unexpected dict structure for shipyard data for '{station_name}' in '{system_name}': {str(shipyard_data)[:200]}")
            return shipyard_data 
        else:
            logger.error(f"Unexpected response type for shipyard data (expected dict): {type(shipyard_data)}. Data: {str(shipyard_data)[:200]}")
            return {} 

    except OperationCancelledError:
        logger.info(f"get_shipyard_at_station for '{station_name}' cancelled.")
        raise
    except Exception as e:
        logger.error(f"Error processing shipyard data for '{station_name}' in '{system_name}': {e}", exc_info=True)
        raise


async def get_outfitting_at_station( # NOUVELLE FONCTION
    session: aiohttp.ClientSession,
    system_name: str,
    station_name: str,
    cancel_event: threading.Event = None
):
    """
    Récupère les modules d'équipement vendus à une station spécifique.
    Documentation EDSM: https://www.edsm.net/api-system-v1/stations/outfitting
    Retourne une liste de modules (chacun un dict {"id": ..., "name": ...}) si trouvés, ou une liste vide.
    """
    api_endpoint = "api-system-v1/stations/outfitting"
    url = f"{EDSM_BASE_URL.rstrip('/')}/{api_endpoint}"
    params = {
        "systemName": system_name,
        "stationName": station_name
        # "marketId": market_id # Alternative si on a marketId
    }
    
    logger.info(f"Requesting outfitting data for station: '{station_name}' in system: '{system_name}'")
    
    try:
        response_data = await fetch_edsm_json(session, url, params, cancel_event)
        
        # EDSM retourne un dictionnaire avec une clé "outfitting" qui contient la liste des modules.
        # Si la station n'a pas d'équipement ou si station/système non trouvé, EDSM retourne {} (dict vide).
        if isinstance(response_data, dict) and "outfitting" in response_data:
            modules = response_data.get("outfitting", []) # La valeur de "outfitting" est la liste
            if isinstance(modules, list):
                logger.info(f"Outfitting data found for '{station_name}' in '{system_name}': {len(modules)} module(s).")
                return modules # Ceci est une liste de dicts comme {"id": "...", "name": "..."}
            else:
                # Ce cas ne devrait pas arriver si l'API est cohérente, mais par prudence
                logger.warning(f"Outfitting key found but its value is not a list for station '{station_name}'. Type: {type(modules)}. Data: {str(modules)[:200]}")
                return []
        elif isinstance(response_data, dict) and not response_data: # Dict vide {}
             logger.info(f"No outfitting data (empty dict response from EDSM) for '{station_name}' in '{system_name}'. Likely no outfitting service or station not found by this specific EDSM endpoint.")
             return []
        else:
            # Cas où la réponse n'est pas un dict (ex: une liste vide si le système est inconnu, ou autre)
            # ou un dict mais sans la clé "outfitting".
            logger.error(f"Unexpected response type or structure for outfitting data at '{station_name}' (expected dict with 'outfitting' key, or empty dict if no service). Type: {type(response_data)}. Data: {str(response_data)[:200]}")
            return []

    except OperationCancelledError:
        logger.info(f"get_outfitting_at_station for '{station_name}' cancelled.")
        raise # Propager pour que l'appelant (outfitting_db_manager) le gère
    except Exception as e:
        # fetch_edsm_json devrait déjà logger les erreurs HTTP/connexion.
        # Ici, on loggue les erreurs qui pourraient survenir après un fetch réussi mais lors du traitement.
        logger.error(f"Error processing outfitting data for station '{station_name}' in system '{system_name}': {e}", exc_info=True)
        raise # Propager pour que l'appelant le gère


# --- PLACEHOLDER POUR OBTENIR LA LISTE DE TOUS LES VAISSEAUX (si jamais EDSM le fournit) ---
# async def get_all_ships_from_edsm( 
#     session: aiohttp.ClientSession,
#     cancel_event: threading.Event = None
# ):
#     logger.warning("PLACEHOLDER: get_all_ships_from_edsm appelé.")
#     return None