#!/usr/bin/env python3
import logging
import math
import os
import json
from datetime import datetime, timezone
import asyncio # Peut être nécessaire si find_best_outbound_trades_for_hop fait des appels asynchrones
from collections import defaultdict
import threading

from constants import (
    LOCAL_SELLERS_DATA_FILE, PLANETARY_STATION_TYPES, STATION_PAD_SIZE_MAP,
    FLEET_CARRIER_STATION_TYPES,
    KEY_TOP_N_IMPORTS_FILTER, DEFAULT_TOP_N_IMPORTS_FILTER,
    KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES
)
# api_handler n'est pas importé ici directement, mais find_best_outbound_trades_for_hop
# pourrait en avoir besoin si on décide qu'il fait ses propres appels API pour des données manquantes.
# Pour l'instant, on suppose qu'il travaille avec les données fournies.
# import api_handler
from api_handler import OperationCancelledError # Si utilisé
import settings_manager

logger = logging.getLogger(__name__)

def get_last_db_update_time_str():
    # ... (fonction existante inchangée)
    if os.path.exists(LOCAL_SELLERS_DATA_FILE):
        try:
            with open(LOCAL_SELLERS_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            updated_at_iso = data.get("updatedAt")
            if updated_at_iso:
                try:
                    if 'Z' in updated_at_iso:
                        dt_utc = datetime.fromisoformat(updated_at_iso.replace('Z', '+00:00'))
                    else: 
                        dt_utc = datetime.fromisoformat(updated_at_iso)
                        if dt_utc.tzinfo is None: 
                            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                except ValueError as ve_date:
                    logger.error(f"Date format error for updatedAt ('{updated_at_iso}'): {ve_date}")
                    return "Local DB: Date Format Error"
                return f"Local DB: {dt_utc.astimezone(None).strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception as e:
            logger.exception(f"Error parsing DB update date from {LOCAL_SELLERS_DATA_FILE}: {e}")
            return "Local DB: Date Read Error"
    return "Local DB: Not found"

def generate_purchase_suggestions(
    required_commodities,
    local_market_data_new_struct,
    current_station_market_data,
    current_player_pad_size,
    max_station_dist_ls,
    include_planetary_stations,
    include_fleet_carriers, 
    current_player_system_name_for_fallback,
    cancel_event: threading.Event = None
):
    # ... (fonction existante inchangée)
    logger.debug("Generating purchase suggestions for mission items...")
    station_candidates = {}
    try:
        player_pad_size_int = int(current_player_pad_size) if str(current_player_pad_size).isdigit() else None
    except ValueError: player_pad_size_int = None

    logger.debug(f"Suggest Params: Pad: {player_pad_size_int}, LS: {max_station_dist_ls}, Planet: {include_planetary_stations}, FC: {include_fleet_carriers}")

    def _process_source_offers(source_offers_list, system_name, station_name, dist_ly, station_details_from_cache, is_from_current_station_raw_data_param=False):
        nonlocal station_candidates
        if not isinstance(source_offers_list, list): return

        for offer_idx, offer in enumerate(source_offers_list):
            if cancel_event and cancel_event.is_set() and offer_idx % 20 == 0: 
                raise OperationCancelledError("Purchase suggestion generation cancelled.")

            commodity_name_original = offer.get('commodityName', '')
            commodity_name_lower = commodity_name_original.lower()
            if not commodity_name_lower or commodity_name_lower not in required_commodities: continue

            station_type = offer.get('stationType', station_details_from_cache.get('stationType', 'Unknown'))
            if not include_planetary_stations and station_type in PLANETARY_STATION_TYPES: continue
            if not include_fleet_carriers and station_type in FLEET_CARRIER_STATION_TYPES: continue


            station_pad_raw = offer.get('maxLandingPadSize', station_details_from_cache.get('maxLandingPadSize'))
            station_pad_int = STATION_PAD_SIZE_MAP.get(str(station_pad_raw).upper(), station_pad_raw if isinstance(station_pad_raw, int) else None)
            if player_pad_size_int is not None and (station_pad_int is None or station_pad_int < player_pad_size_int): continue

            dist_ls_val = offer.get('distanceToArrival', station_details_from_cache.get('distanceToArrival'))
            dist_ls_float = float('inf')
            if is_from_current_station_raw_data_param: 
                dist_ls_float = 0.0
            elif dist_ls_val is not None:
                try: dist_ls_float = float(dist_ls_val)
                except (ValueError, TypeError): pass

            if dist_ls_float > max_station_dist_ls: continue

            needed_qty = required_commodities[commodity_name_lower]
            player_cost_to_buy = 0
            station_stock_available = 0

            if is_from_current_station_raw_data_param: 
                player_cost_to_buy = offer.get('buyPrice', 0)
                station_stock_available = offer.get('stock', 0)
            else: 
                player_cost_to_buy = offer.get('price', 0) 
                station_stock_available = offer.get('stock', offer.get('quantity_at_station',0))


            if station_stock_available >= needed_qty and player_cost_to_buy > 0:
                station_key = (station_name, system_name)
                candidate_station = station_candidates.setdefault(station_key, {
                    'distance_ly': dist_ly, 'commodities': {},
                    'pad_size_int': station_pad_int, 'distance_ls': dist_ls_float,
                    'stationType': station_type
                })
                candidate_station['commodities'][commodity_name_lower] = player_cost_to_buy

    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Purchase suggestion generation cancelled.")

    if local_market_data_new_struct and isinstance(local_market_data_new_struct.get('station_markets'), dict):
        for system_name, system_market_detail in local_market_data_new_struct['station_markets'].items():
            if cancel_event and cancel_event.is_set():
                raise OperationCancelledError("Purchase suggestion generation cancelled processing local markets.")
            dist_ly = system_market_detail.get('distance', float('inf'))
            if isinstance(system_market_detail.get('stations_data'), dict):
                for station_name, station_data_content in system_market_detail['stations_data'].items():
                    if isinstance(station_data_content.get('sells_to_player'), list):
                        _process_source_offers(
                            station_data_content['sells_to_player'],
                            system_name, station_name, dist_ly,
                            station_data_content.get('details', {}), 
                            is_from_current_station_raw_data_param=False
                        )

    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Purchase suggestion generation cancelled.")

    if current_station_market_data and isinstance(current_station_market_data.get('offers'), list):
        current_sys_name_to_use = current_station_market_data.get('system', current_player_system_name_for_fallback)
        current_sta_name_to_use = current_station_market_data.get('station', "?")
        
        station_details_current = {'distanceToArrival': 0.0} 
        if current_station_market_data['offers']:
            first_offer = current_station_market_data['offers'][0]
            station_details_current['stationType'] = first_offer.get('stationType', 'Unknown')
            station_details_current['maxLandingPadSize'] = first_offer.get('maxLandingPadSize')


        _process_source_offers(
            current_station_market_data['offers'],
            current_sys_name_to_use,
            current_sta_name_to_use,
            0.0, 
            station_details_current,
            is_from_current_station_raw_data_param=True
        )

    full_supply_options = []; partial_supply_options = []
    for station_key_tuple, data_dict in station_candidates.items():
        if all(comm_name in data_dict['commodities'] for comm_name in required_commodities.keys()): full_supply_options.append({'station_name': station_key_tuple[0], 'system_name': station_key_tuple[1], **data_dict})
        elif data_dict['commodities']: partial_supply_options.append({'station_name': station_key_tuple[0], 'system_name': station_key_tuple[1], **data_dict})
    
    partial_supply_options.sort(key=lambda x: (-len(x['commodities']), x.get('distance_ls', float('inf')), x['distance_ly']))

    complementary_sources_for_best_partial = {}
    if not full_supply_options and partial_supply_options:
        best_partial_option = partial_supply_options[0]; commodities_covered_by_best_partial = set(best_partial_option['commodities'].keys())
        missing_commodities_after_best_partial = {comm: qty for comm, qty in required_commodities.items() if comm not in commodities_covered_by_best_partial}
        if missing_commodities_after_best_partial:
            logger.debug(f"Best partial option covers {len(commodities_covered_by_best_partial)} items. Missing: {missing_commodities_after_best_partial.keys()}")
            for comm_to_find, needed_qty_for_missing in missing_commodities_after_best_partial.items():
                if cancel_event and cancel_event.is_set():
                    raise OperationCancelledError("Purchase suggestion (complementary) cancelled.")
                best_source_for_this_missing_commodity = None
                for sk_comp_tuple, data_comp_dict in station_candidates.items():
                    if comm_to_find in data_comp_dict['commodities']:
                        current_candidate_source_details = {'station_name': sk_comp_tuple[0],'system_name': sk_comp_tuple[1],'distance_ly': data_comp_dict['distance_ly'],'price': data_comp_dict['commodities'][comm_to_find],'pad_size_int': data_comp_dict.get('pad_size_int'),'distance_ls': data_comp_dict.get('distance_ls', float('inf')),'stationType': data_comp_dict.get('stationType', 'Unknown')}
                        current_sort_key = (current_candidate_source_details.get('distance_ls', float('inf')), current_candidate_source_details['distance_ly'])
                        best_current_sort_key = (best_source_for_this_missing_commodity.get('distance_ls', float('inf')), best_source_for_this_missing_commodity['distance_ly']) if best_source_for_this_missing_commodity else (float('inf'), float('inf'))
                        if best_source_for_this_missing_commodity is None or current_sort_key < best_current_sort_key: best_source_for_this_missing_commodity = current_candidate_source_details
                if best_source_for_this_missing_commodity:
                    complementary_sources_for_best_partial[comm_to_find] = best_source_for_this_missing_commodity
                    logger.debug(f"Found complementary source for {comm_to_find}: {best_source_for_this_missing_commodity['station_name']} in {best_source_for_this_missing_commodity['system_name']}")

    logger.info(f"Mission item suggestions: Found {len(full_supply_options)} full, {len(partial_supply_options)} partial options.")
    return full_supply_options, partial_supply_options, complementary_sources_for_best_partial

def calculate_profitable_trades(player_buys_from_source_offers, player_sells_to_destination_offers, available_cargo_tons, cancel_event: threading.Event = None):
    # ... (fonction existante inchangée)
    profitable_trades = []
    if not player_buys_from_source_offers or not player_sells_to_destination_offers or available_cargo_tons <= 0:
        logger.debug(f"calculate_profitable_trades: Initial conditions not met or zero cargo. Buys offers: {len(player_buys_from_source_offers if player_buys_from_source_offers else [])}, Sells offers: {len(player_sells_to_destination_offers if player_sells_to_destination_offers else [])}, Cargo: {available_cargo_tons}")
        return []

    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Trade calculation cancelled.")

    destination_player_revenue_map = {
        item['commodityName'].lower(): {
            'price': item['price'], 
            'demand_at_dest': item.get('quantity_at_station', item.get('demand', float('inf'))),
            'commodity_localised': item.get('commodity_localised', item['commodityName'])
            }
        for item in player_sells_to_destination_offers if item.get('price', 0) > 0
    }

    potential_trades = []
    for source_idx, source_item_player_buys in enumerate(player_buys_from_source_offers):
        if cancel_event and cancel_event.is_set() and source_idx % 50 == 0:
            raise OperationCancelledError("Trade calculation (potential trades) cancelled.")
        
        source_comm_lower = source_item_player_buys['commodityName'].lower()
        player_cost_at_source = source_item_player_buys.get('price',0) 
        if not player_cost_at_source > 0 : continue


        if source_comm_lower in destination_player_revenue_map:
            dest_info_for_player_sale = destination_player_revenue_map[source_comm_lower]
            player_revenue_at_dest = dest_info_for_player_sale['price']

            if player_revenue_at_dest > player_cost_at_source:
                profit_per_unit = player_revenue_at_dest - player_cost_at_source
                potential_trades.append({
                    'commodityName': source_item_player_buys['commodityName'],
                    'commodity_localised': source_item_player_buys.get('commodity_localised', source_item_player_buys['commodityName']),
                    'player_cost_at_source': player_cost_at_source,
                    'player_revenue_at_dest': player_revenue_at_dest,
                    'profit_per_unit': profit_per_unit,
                    'stock_at_source': source_item_player_buys.get('quantity_at_station', source_item_player_buys.get('stock', float('inf'))),
                    'demand_at_dest': dest_info_for_player_sale.get('demand_at_dest', float('inf'))
                })

    potential_trades.sort(key=lambda x: x['profit_per_unit'], reverse=True)
    logger.debug(f"calculate_profitable_trades: Found {len(potential_trades)} potential trade items, sorted by profit per unit.")

    remaining_cargo = float(available_cargo_tons)
    for trade_idx, trade in enumerate(potential_trades):
        if cancel_event and cancel_event.is_set() and trade_idx % 20 == 0: 
            raise OperationCancelledError("Trade calculation (filling cargo) cancelled.")
        if remaining_cargo <= 0: logger.debug("calculate_profitable_trades: No remaining cargo space."); break

        qty_possible_by_stock = float(trade['stock_at_source']) if trade['stock_at_source'] is not None else float('inf')
        qty_possible_by_demand = float(trade['demand_at_dest']) if trade['demand_at_dest'] is not None else float('inf')

        qty_to_trade = min(qty_possible_by_stock, qty_possible_by_demand, remaining_cargo)

        if qty_to_trade > 0:
            profitable_trades.append({
                'commodityName': trade['commodityName'],
                'commodity_localised': trade['commodity_localised'],
                'quantity': int(qty_to_trade),
                'buy_price_at_source': trade['player_cost_at_source'],
                'sell_price_at_dest': trade['player_revenue_at_dest'],
                'profit_per_unit': trade['profit_per_unit'],
                'total_profit': int(qty_to_trade * trade['profit_per_unit'])
            })
            remaining_cargo -= qty_to_trade
            logger.debug(f"Added trade for {trade['commodityName']}, Qty: {int(qty_to_trade)}. Remaining cargo: {remaining_cargo}")

    logger.debug(f"calculate_profitable_trades: Generated {len(profitable_trades)} trade suggestions.")
    return profitable_trades

async def suggest_round_trip_opportunities(
    http_session, # Nécessaire si on doit faire des appels API pour des données manquantes
    current_station_system_name, current_station_name,
    pickup_station_system_name, pickup_station_name,
    mission_commodities_volume_tons, # Pour calculer la soute restante au retour
    total_ship_cargo_capacity_tons,
    raw_departure_station_market_offers, # Ce que la station A (current) vend (player buys) et achète (player sells)
    player_buys_from_pickup_station_offers, # Ce que la station B (pickup) vend (player buys)
    local_market_data, # Cache local pour les importations de B si disponibles
    max_days_ago: int, # Pour les appels API si B n'est pas dans le cache
    include_fleet_carriers_setting: bool, # Pour les appels API si B n'est pas dans le cache
    cancel_event: threading.Event = None
):
    # ... (fonction existante inchangée)
    outbound_trades = []; return_trades = []

    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Round trip opportunity suggestion cancelled.")

    player_buys_at_A_normalized = []
    if raw_departure_station_market_offers:
        for offer in raw_departure_station_market_offers:
            if offer.get('buyPrice', 0) > 0 and offer.get('stock', 0) > 0:
                player_buys_at_A_normalized.append({
                    'commodityName': offer.get('commodityName'),
                    'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),
                    'price': offer.get('buyPrice'), 
                    'quantity_at_station': offer.get('stock')
                })
    
    player_sells_at_B_normalized = []
    station_b_is_current_station_a = (pickup_station_system_name == current_station_system_name and \
                                      pickup_station_name == current_station_name)

    if not station_b_is_current_station_a and local_market_data and \
       pickup_station_system_name in local_market_data.get('station_markets', {}) and \
       pickup_station_name in local_market_data['station_markets'][pickup_station_system_name].get('stations_data', {}):
        
        station_detail_B = local_market_data['station_markets'][pickup_station_system_name]['stations_data'][pickup_station_name]
        player_sells_at_B_normalized = station_detail_B.get('buys_from_player', [])
        logger.info(f"Round trip (A->B): Used local 'buys_from_player' data for {pickup_station_name}@{pickup_station_system_name} ({len(player_sells_at_B_normalized)} items).")
    elif station_b_is_current_station_a:
        if raw_departure_station_market_offers:
            player_sells_at_B_normalized = [ 
                {
                    'commodityName': offer.get('commodityName'),
                    'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),
                    'price': offer.get('sellPrice'), 
                    'quantity_at_station': offer.get('demand')
                }
                for offer in raw_departure_station_market_offers if offer.get('sellPrice', 0) > 0 and offer.get('demand', 0) > 0
            ]
            logger.info(f"Round trip (A->B): B is current station A. Used departure_data for imports of A ({len(player_sells_at_B_normalized)} items).")
    else: 
        logger.warning(f"Round trip (A->B): Data for B ({pickup_station_name}@{pickup_station_system_name}) imports not in local cache. Fetching via API.")
        # Assurez-vous que api_handler est importé si vous utilisez cette ligne
        import api_handler as round_trip_api_handler 
        player_sells_at_B_normalized = await round_trip_api_handler.get_station_specific_market_data(
            http_session, pickup_station_system_name, pickup_station_name,
            max_days_ago=max_days_ago,
            include_fleet_carriers=include_fleet_carriers_setting,
            player_action='sell', cancel_event=cancel_event
        )
        if player_sells_at_B_normalized is None: player_sells_at_B_normalized = []


    if player_buys_at_A_normalized and player_sells_at_B_normalized:
        outbound_trades = calculate_profitable_trades(
            player_buys_at_A_normalized, player_sells_at_B_normalized,
            total_ship_cargo_capacity_tons, cancel_event=cancel_event
        )
        logger.info(f"Outbound (A->B) MissionTrip: Found {len(outbound_trades)} profitable trades.")
    else:
        logger.info(f"Outbound (A->B) MissionTrip: Insufficient data for trade. Player buys at A: {len(player_buys_at_A_normalized)}, Player sells at B: {len(player_sells_at_B_normalized)}")


    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Round trip opportunity suggestion (return leg) cancelled.")
    
    player_sells_at_A_normalized = []
    if raw_departure_station_market_offers: 
        for offer in raw_departure_station_market_offers:
            if offer.get('sellPrice', 0) > 0 and offer.get('demand', 0) > 0 :
                player_sells_at_A_normalized.append({
                    'commodityName': offer.get('commodityName'),
                    'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),
                    'price': offer.get('sellPrice'), 
                    'quantity_at_station': offer.get('demand')
                })

    if player_buys_from_pickup_station_offers and player_sells_at_A_normalized:
        logger.info(f"Return (B->A) MissionTrip: Player can buy {len(player_buys_from_pickup_station_offers if player_buys_from_pickup_station_offers else [])} items at {pickup_station_name}. Player can sell {len(player_sells_at_A_normalized)} types at {current_station_name}.")
        remaining_cargo_for_return = max(0, float(total_ship_cargo_capacity_tons) - float(mission_commodities_volume_tons))
        logger.info(f"Return (B->A) MissionTrip: Remaining cargo capacity: {remaining_cargo_for_return}t.")
        if remaining_cargo_for_return > 0:
            return_trades = calculate_profitable_trades(
                player_buys_from_pickup_station_offers, player_sells_at_A_normalized,
                remaining_cargo_for_return, cancel_event=cancel_event
            )
            logger.info(f"Return (B->A) MissionTrip: Found {len(return_trades)} profitable trades.")
        else: logger.info(f"Return (B->A) MissionTrip: No cargo space for return trades.")
    else:
        logger.info(f"Return (B->A) MissionTrip: Insufficient data for trade. Player buys at B: {len(player_buys_from_pickup_station_offers if player_buys_from_pickup_station_offers else [])}, Player sells at A: {len(player_sells_at_A_normalized)}")
        
    return outbound_trades, return_trades

async def find_general_market_trades(
    http_session, # Pour les appels API si des données manquent
    current_system_name, current_station_name,      
    raw_departure_station_market_offers, # Ce que la station A (actuelle) vend (achats joueur) et achète (ventes joueur)           
    local_market_data, # Cache local des marchés environnants (structure : {system_name: {distance, stations_data: {station_name: {sells_to_player, buys_from_player, details}}}})
    cargo_capacity_tons,
    max_station_dist_ls_filter: float, # max_station_dist_ls depuis les settings
    include_planetary_filter: bool,                 
    include_fleet_carriers_filter: bool,             
    current_player_pad_size_int: int, # Taille de pad du joueur (1,2,3 ou None)
    max_days_ago_api_param: int, # Pour les appels API si données manquantes
    include_fleet_carriers_api_param: bool, # Pour les appels API si données manquantes
    cancel_event: threading.Event = None
):
    # ... (fonction existante inchangée)
    all_profitable_routes_unmerged = []
    max_routes_to_display = int(settings_manager.get_setting(KEY_MAX_GENERAL_TRADE_ROUTES, DEFAULT_MAX_GENERAL_TRADE_ROUTES))
    top_n_imports_filter = int(settings_manager.get_setting(KEY_TOP_N_IMPORTS_FILTER, DEFAULT_TOP_N_IMPORTS_FILTER))
    logger.info(f"Finding general market trades. Max routes: {max_routes_to_display}. Top N imports: {top_n_imports_filter}. Filters: LS Max={max_station_dist_ls_filter}, Planetary={include_planetary_filter}, FC (client)={include_fleet_carriers_filter}, Pad={current_player_pad_size_int}, API maxDaysAgo={max_days_ago_api_param}, API includeFC for new calls={include_fleet_carriers_api_param}")
    
    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("General market trade search cancelled at start.")

    player_buys_at_A_normalized = []
    if raw_departure_station_market_offers:
        for offer in raw_departure_station_market_offers:
            if offer.get('buyPrice', 0) > 0 and offer.get('stock', 0) > 0: 
                player_buys_at_A_normalized.append({'commodityName': offer.get('commodityName'),'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),'price': offer.get('buyPrice'), 'quantity_at_station': offer.get('stock') })

    player_sells_to_A_normalized = []
    if raw_departure_station_market_offers:
        for offer in raw_departure_station_market_offers:
            if offer.get('sellPrice', 0) > 0 and offer.get('demand', 0) > 0 : 
                player_sells_to_A_normalized.append({'commodityName': offer.get('commodityName'), 'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),'price': offer.get('sellPrice'), 'quantity_at_station': offer.get('demand')})

    if player_buys_at_A_normalized and local_market_data and isinstance(local_market_data.get('station_markets'), dict):
        logger.info(f"General Trades (A->X): Current station {current_station_name} offers {len(player_buys_at_A_normalized)} items for player to buy.")
        for system_idx, (nearby_system_name_X, system_market_content_X) in enumerate(local_market_data['station_markets'].items()):
            if cancel_event and cancel_event.is_set() and system_idx % 5 == 0 : 
                raise OperationCancelledError("General market trade search (A->X) cancelled.")
            distance_ly_to_system_X = system_market_content_X.get('distance', float('inf'))
            if isinstance(system_market_content_X.get('stations_data'), dict):
                for nearby_station_name_X, station_data_X in system_market_content_X['stations_data'].items():
                    details_X = station_data_X.get('details', {})
                    station_type_X = details_X.get('stationType', 'Unknown')
                    if not include_planetary_filter and station_type_X in PLANETARY_STATION_TYPES: continue
                    if not include_fleet_carriers_filter and station_type_X in FLEET_CARRIER_STATION_TYPES: continue
                    
                    station_pad_raw_X = details_X.get('maxLandingPadSize'); station_pad_int_X = STATION_PAD_SIZE_MAP.get(str(station_pad_raw_X).upper(), station_pad_raw_X if isinstance(station_pad_raw_X, int) else None)
                    if current_player_pad_size_int is not None and (station_pad_int_X is None or station_pad_int_X < current_player_pad_size_int): continue
                    
                    dist_ls_X_val = details_X.get('distanceToArrival'); dist_ls_X = float(dist_ls_X_val) if dist_ls_X_val is not None else float('inf')
                    try: dist_ls_X = float(dist_ls_X)
                    except (ValueError, TypeError): dist_ls_X = float('inf')
                    if dist_ls_X > max_station_dist_ls_filter: continue

                    player_sells_to_X_from_cache = station_data_X.get('buys_from_player', []) 
                    if player_sells_to_X_from_cache:
                        player_sells_to_X_from_cache.sort(key=lambda item: item.get('price', 0), reverse=True)
                        player_sells_to_X_filtered = player_sells_to_X_from_cache[:top_n_imports_filter]
                        if player_sells_to_X_filtered:
                            trades = calculate_profitable_trades(
                                player_buys_at_A_normalized, player_sells_to_X_filtered,
                                cargo_capacity_tons, cancel_event=cancel_event
                            )
                            for trade in trades:
                                all_profitable_routes_unmerged.append({
                                    'route_type_display': f"{current_station_name or current_system_name} -> {nearby_station_name_X} ({nearby_system_name_X})",
                                    'is_A_to_X': True,
                                    'source_system': current_system_name,
                                    'source_station': current_station_name or "Current Location",
                                    'dest_system': nearby_system_name_X,
                                    'dest_station': nearby_station_name_X,
                                    'dest_ly_dist': distance_ly_to_system_X,
                                    'dest_ls_dist': dist_ls_X,
                                    **trade })

    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("General market trade search (mid-point) cancelled.")

    if player_sells_to_A_normalized and local_market_data and isinstance(local_market_data.get('station_markets'), dict):
        logger.info(f"General Trades (X->A): Current station {current_station_name} might buy {len(player_sells_to_A_normalized)} items from player.")
        for system_idx, (nearby_system_name_X, system_market_content_X) in enumerate(local_market_data['station_markets'].items()):
            if cancel_event and cancel_event.is_set() and system_idx % 5 == 0:
                raise OperationCancelledError("General market trade search (X->A) cancelled.")
            distance_ly_to_system_X = system_market_content_X.get('distance', float('inf'))
            if isinstance(system_market_content_X.get('stations_data'), dict):
                for nearby_station_name_X, station_data_X in system_market_content_X['stations_data'].items():
                    details_X = station_data_X.get('details', {})
                    station_type_X_src = details_X.get('stationType', 'Unknown')
                    if not include_planetary_filter and station_type_X_src in PLANETARY_STATION_TYPES: continue
                    if not include_fleet_carriers_filter and station_type_X_src in FLEET_CARRIER_STATION_TYPES: continue

                    station_pad_raw_X_src = details_X.get('maxLandingPadSize'); station_pad_int_X_src = STATION_PAD_SIZE_MAP.get(str(station_pad_raw_X_src).upper(), station_pad_raw_X_src if isinstance(station_pad_raw_X_src, int) else None)
                    if current_player_pad_size_int is not None and (station_pad_int_X_src is None or station_pad_int_X_src < current_player_pad_size_int): continue
                    
                    dist_ls_X_source_val = details_X.get('distanceToArrival'); dist_ls_X_source = float(dist_ls_X_source_val) if dist_ls_X_source_val is not None else float('inf')
                    try: dist_ls_X_source = float(dist_ls_X_source)
                    except (ValueError, TypeError): dist_ls_X_source = float('inf')
                    if dist_ls_X_source > max_station_dist_ls_filter: continue

                    player_buys_from_X_from_cache = station_data_X.get('sells_to_player', []) 
                    if player_buys_from_X_from_cache:
                        trades = calculate_profitable_trades(
                            player_buys_from_X_from_cache, player_sells_to_A_normalized,
                            cargo_capacity_tons, cancel_event=cancel_event
                        )
                        for trade in trades:
                            all_profitable_routes_unmerged.append({
                                'route_type_display': f"{nearby_station_name_X} ({nearby_system_name_X}) -> {current_station_name or current_system_name}",
                                'is_A_to_X': False,
                                'source_system': nearby_system_name_X,
                                'source_station': nearby_station_name_X,
                                'source_ly_dist': distance_ly_to_system_X,
                                'source_ls_dist': dist_ls_X_source,
                                'dest_system': current_system_name,
                                'dest_station': current_station_name or "Current Location",
                                **trade
                            })

    all_profitable_routes_unmerged.sort(key=lambda x: x.get('total_profit', 0), reverse=True)
    top_routes_for_display = all_profitable_routes_unmerged[:max_routes_to_display]

    final_routes_output = []
    if top_routes_for_display :
        for route_idx, route_data in enumerate(top_routes_for_display):
            if cancel_event and cancel_event.is_set() and route_idx % 2 == 0: 
                raise OperationCancelledError("General market trade search (finalizing routes) cancelled.")
            enriched_route_data = route_data.copy()
            if not route_data.get('is_A_to_X', True) and player_buys_at_A_normalized:
                prelim_dest_system = route_data['source_system'] 
                prelim_dest_station = route_data['source_station']

                logger.info(f"General Trades: Finding preliminary outbound leg A -> {prelim_dest_station} ({prelim_dest_system}) for main X->A route.")

                player_sells_to_prelim_dest_data = []
                if local_market_data and prelim_dest_system in local_market_data.get('station_markets', {}) and \
                   prelim_dest_station in local_market_data['station_markets'][prelim_dest_system].get('stations_data', {}):
                    station_data_for_prelim_dest = local_market_data['station_markets'][prelim_dest_system]['stations_data'][prelim_dest_station]
                    player_sells_to_prelim_dest_data = station_data_for_prelim_dest.get('buys_from_player', [])
                    logger.debug(f"Used cached import data (buys_from_player) for {prelim_dest_station} for prelim leg.")
                else: 
                    if prelim_dest_system == current_system_name and prelim_dest_station == current_station_name:
                         if raw_departure_station_market_offers:
                            player_sells_to_prelim_dest_data = [ 
                                {'commodityName': offer.get('commodityName'), 'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')), 'price': offer.get('sellPrice'), 'quantity_at_station': offer.get('demand')}
                                for offer in raw_departure_station_market_offers if offer.get('sellPrice',0) > 0 and offer.get('demand',0) > 0
                            ]
                            logger.debug(f"Prelim leg: Used current station departure data for imports to {prelim_dest_station}.")
                    else: # Fallback API call
                        logger.warning(f"No/Insufficient cached import data for {prelim_dest_station} for prelim leg, fetching via API...")
                        # Assurez-vous que api_handler est importé ou que http_session est disponible
                        import api_handler as general_trade_api_handler
                        api_data_for_prelim_dest = await general_trade_api_handler.get_station_specific_market_data(
                            http_session, prelim_dest_system, prelim_dest_station,
                            max_days_ago=max_days_ago_api_param,
                            include_fleet_carriers=include_fleet_carriers_api_param, 
                            player_action='sell', cancel_event=cancel_event
                        )
                        if api_data_for_prelim_dest:
                            player_sells_to_prelim_dest_data = api_data_for_prelim_dest

                if player_sells_to_prelim_dest_data:
                    player_sells_to_prelim_dest_data.sort(key=lambda x: x.get('price', 0), reverse=True)
                    player_sells_to_prelim_dest_filtered = player_sells_to_prelim_dest_data[:top_n_imports_filter]
                    if player_sells_to_prelim_dest_filtered:
                        preliminary_outbound_trades = calculate_profitable_trades(
                            player_buys_at_A_normalized, 
                            player_sells_to_prelim_dest_filtered,
                            cargo_capacity_tons,
                            cancel_event=cancel_event
                        )
                        if preliminary_outbound_trades:
                            enriched_route_data['preliminary_outbound_leg'] = preliminary_outbound_trades[:1]
                            logger.info(f"Found {len(preliminary_outbound_trades)} prelim trades for A -> {prelim_dest_station}, took top 1.")
            final_routes_output.append(enriched_route_data)

    logger.info(f"Generated {len(final_routes_output)} general trade routes to display with potential outbound legs.")
    return final_routes_output


# --- NOUVELLE FONCTION pour le planificateur Multi-Hop ---
async def find_best_outbound_trades_for_hop(
    http_session, # Pour d'éventuels appels API si les données manquent (non utilisé pour l'instant)
    source_system_name: str,
    source_station_name: str,
    player_cargo_capacity: int,
    player_pad_size_int: int, # Taille de pad du joueur (1,2,3 ou None)
    max_ly_per_hop_radius: float,
    max_station_dist_ls_filter: float,
    include_planetary_filter: bool,
    include_fleet_carriers_filter: bool,
    departure_data_for_source, # Ce que la station source vend (liste d'offres)
    local_market_data, # Données complètes des marchés locaux (incluant les importations des autres stations)
    cancel_event: threading.Event = None
):
    """
    Trouve les X meilleures transactions sortantes (une marchandise par station de destination)
    depuis une station source donnée vers des stations environnantes.

    Args:
        http_session: Session aiohttp (peut être None si toutes les données sont supposées être dans local_market_data).
        source_system_name: Nom du système de départ.
        source_station_name: Nom de la station de départ.
        player_cargo_capacity: Capacité de soute du joueur.
        player_pad_size_int: Taille de pad du vaisseau du joueur (1=S, 2=M, 3=L, None=inconnu/pas de filtre).
        max_ly_per_hop_radius: Rayon de recherche max en AL pour les stations de destination.
        max_station_dist_ls_filter: Distance max en SL de l'étoile pour les stations de destination.
        include_planetary_filter: Inclure les stations planétaires.
        include_fleet_carriers_filter: Inclure les Fleet Carriers.
        departure_data_for_source: Données de ce que la station source vend (achats joueur).
                                   Format attendu : liste de dicts comme dans LOCAL_SELLERS_DATA_FILE[sys][sta]['sells_to_player']
                                   ou comme departure_market_data['offers'].
                                   Ex: [{'commodityName': 'Gold', 'commodity_localised': 'Or', 'price': 10000, 'stock': 500, ...}]
        local_market_data: Données complètes du cache local (LOCAL_SELLERS_DATA_FILE).
                           Utilisé pour trouver ce que les stations de destination achètent.
        cancel_event: Événement pour annuler l'opération.

    Returns:
        Une liste des (jusqu'à) 5 meilleures options de commerce, où chaque option est un dictionnaire
        représentant la meilleure transaction vers une station de destination unique.
        Chaque dict: {
            'dest_system': str, 'dest_station': str, 'commodity_to_buy': str, 'commodity_localised': str,
            'buy_price_at_source': float, 'sell_price_at_dest': float, 'profit_per_unit': float,
            'est_total_profit': float (pour cargo plein de cette marchandise),
            'distance_ly': float, 'landing_pad': str, 'dist_to_star': float,
            'stock_at_source': int, 'demand_at_dest': int
        }
    """
    logger.info(f"MultiHop: Finding best outbound trades from {source_station_name} ({source_system_name}). Radius: {max_ly_per_hop_radius} LY.")
    
    if cancel_event and cancel_event.is_set():
        raise OperationCancelledError("Finding best outbound trades cancelled.")

    if not departure_data_for_source or not isinstance(departure_data_for_source, list):
        logger.warning(f"No departure (export) data provided for source station {source_station_name}.")
        return []
    
    if not local_market_data or not isinstance(local_market_data.get('station_markets'), dict):
        logger.warning("Local market data is missing or invalid for finding trades.")
        return []

    # Normaliser les offres de la station source (ce que le joueur peut y acheter)
    player_buys_at_source_station = []
    for offer in departure_data_for_source:
        # Le format de departure_data_for_source doit être cohérent.
        # S'il vient de 'sells_to_player', les clés sont 'price', 'stock'.
        # S'il vient de 'departure_market_data['offers']', les clés sont 'buyPrice', 'stock'.
        price_key = 'price' if 'price' in offer else 'buyPrice' # Adapter selon la source
        
        if offer.get(price_key, 0) > 0 and offer.get('stock', 0) > 0:
            player_buys_at_source_station.append({
                'commodityName': offer.get('commodityName'),
                'commodity_localised': offer.get('commodity_localised', offer.get('commodityName')),
                'price': offer.get(price_key),
                'stock': offer.get('stock')
            })

    if not player_buys_at_source_station:
        logger.info(f"Source station {source_station_name} has no commodities to sell to player.")
        return []

    potential_trades_to_dest_stations = []

    for dest_system_name, system_content in local_market_data['station_markets'].items():
        if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Trade finding loop cancelled (systems).")
        
        dist_ly = system_content.get('distance', float('inf'))
        if dist_ly > max_ly_per_hop_radius:
            continue # Système trop éloigné

        for dest_station_name, station_data in system_content.get('stations_data', {}).items():
            if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Trade finding loop cancelled (stations).")

            # Appliquer les filtres de station de destination
            dest_details = station_data.get('details', {})
            station_type = dest_details.get('stationType', 'Unknown')
            if not include_planetary_filter and station_type in PLANETARY_STATION_TYPES: continue
            if not include_fleet_carriers_filter and station_type in FLEET_CARRIER_STATION_TYPES: continue

            dest_pad_raw = dest_details.get('maxLandingPadSize')
            dest_pad_int = STATION_PAD_SIZE_MAP.get(str(dest_pad_raw).upper(), dest_pad_raw if isinstance(dest_pad_raw, int) else None)
            if player_pad_size_int is not None and (dest_pad_int is None or dest_pad_int < player_pad_size_int): continue
            
            dest_dist_ls_val = dest_details.get('distanceToArrival')
            try: dest_dist_ls = float(dest_dist_ls_val if dest_dist_ls_val is not None else float('inf'))
            except (ValueError, TypeError): dest_dist_ls = float('inf')
            if dest_dist_ls > max_station_dist_ls_filter: continue

            # Ce que cette station de destination achète au joueur
            player_sells_to_dest_station = station_data.get('buys_from_player', [])
            if not player_sells_to_dest_station:
                continue

            # Pour cette station de destination, trouver la meilleure marchandise unique à lui vendre
            best_commodity_for_this_dest = None
            max_profit_per_unit_for_this_dest = -1

            for source_commodity_offer in player_buys_at_source_station: # Ce que je peux acheter à ma source
                if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Trade finding loop cancelled (source commodities).")
                
                source_comm_name_lower = source_commodity_offer['commodityName'].lower()
                source_buy_price = source_commodity_offer['price']
                source_stock = source_commodity_offer['stock']

                for dest_buy_offer in player_sells_to_dest_station: # Ce que la destination achète
                    if cancel_event and cancel_event.is_set(): raise OperationCancelledError("Trade finding loop cancelled (dest commodities).")

                    dest_comm_name_lower = dest_buy_offer['commodityName'].lower()
                    if source_comm_name_lower == dest_comm_name_lower:
                        dest_sell_price = dest_buy_offer['price']
                        dest_demand = dest_buy_offer.get('quantity_at_station', dest_buy_offer.get('demand', float('inf')))
                        
                        profit_unit = dest_sell_price - source_buy_price
                        if profit_unit > max_profit_per_unit_for_this_dest:
                            max_profit_per_unit_for_this_dest = profit_unit
                            best_commodity_for_this_dest = {
                                'dest_system': dest_system_name,
                                'dest_station': dest_station_name,
                                'commodity_to_buy': source_commodity_offer['commodityName'], # Nom original pour affichage
                                'commodity_localised': source_commodity_offer.get('commodity_localised', source_commodity_offer['commodityName']),
                                'buy_price_at_source': source_buy_price,
                                'sell_price_at_dest': dest_sell_price,
                                'profit_per_unit': profit_unit,
                                'distance_ly': dist_ly,
                                'landing_pad': str(dest_pad_raw or '?').upper(), # Afficher S, M, L ou ?
                                'dist_to_star': dest_dist_ls,
                                'stock_at_source': source_stock,
                                'demand_at_dest': dest_demand
                            }
                        break # Trouvé la marchandise correspondante, passer à la suivante de la source

            if best_commodity_for_this_dest:
                # Calculer le profit total estimé pour cette meilleure marchandise
                qty_to_trade = min(player_cargo_capacity, best_commodity_for_this_dest['stock_at_source'], best_commodity_for_this_dest['demand_at_dest'])
                best_commodity_for_this_dest['est_total_profit'] = qty_to_trade * best_commodity_for_this_dest['profit_per_unit']
                potential_trades_to_dest_stations.append(best_commodity_for_this_dest)

    # Trier toutes les options de (station destination + meilleure marchandise) par profit total estimé
    potential_trades_to_dest_stations.sort(key=lambda x: x['est_total_profit'], reverse=True)
    
    logger.info(f"Found {len(potential_trades_to_dest_stations)} potential destination stations with profitable trades for multi-hop.")
    return potential_trades_to_dest_stations[:5] # Retourner les 5 meilleures