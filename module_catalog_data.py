#!/usr/bin/env python3
import logging
import re
from constants import OUTFITTING_CATEGORIES_DISPLAY, MODULE_CLASSES_DISPLAY_ORDER, MODULE_MOUNTS_DISPLAY

logger = logging.getLogger(__name__)

DYNAMIC_MODULE_DETAILS_CATALOG = {}
UI_MODULE_SELECTION_CATALOG = {}


def extract_size_from_id_or_name(module_id: str | None, module_name: str | None) -> int | None:
    if isinstance(module_id, str):
        size_match_id = re.search(r"_size(\d+)_", module_id)
        if size_match_id: return int(size_match_id.group(1))
    if isinstance(module_name, str):
        name_size_class_match = re.match(r"^(\d)([A-IE])\s", module_name)
        if name_size_class_match: return int(name_size_class_match.group(1))
        if isinstance(module_id, str):
            if "_tiny" in module_id or " 0" in module_name: return 0
            if "_small" in module_id: return 1
            if "_medium" in module_id: return 2
            if "_large" in module_id: return 3
            if "_huge" in module_id: return 4
        name_prefix_size_match = re.match(r"([a-zA-Z\s()]+)\s?(\d)[A-H]\b", module_name)
        if name_prefix_size_match:
            try: return int(name_prefix_size_match.group(2))
            except ValueError: pass
    return None

def extract_class_from_id_or_name(module_id: str | None, module_name: str | None) -> str | None:
    if isinstance(module_id, str):
        class_match_id = re.search(r"_class([a-e1-5])", module_id, re.IGNORECASE)
        if class_match_id:
            class_val = class_match_id.group(1).upper()
            if class_val.isdigit():
                class_map_from_digit = {"1": "E", "2": "D", "3": "C", "4": "B", "5": "A"}
                return class_map_from_digit.get(class_val)
            return class_val
    if isinstance(module_name, str):
        name_size_class_match = re.match(r"^(\d)([A-IE])\s", module_name)
        if name_size_class_match: return name_size_class_match.group(2).upper()
        name_suffix_class_match = re.search(r"\b(\d)([A-IE])$", module_name)
        if name_suffix_class_match: return name_suffix_class_match.group(2).upper()
        # Pour les blindages qui ont souvent "1I Lightweight Alloy"
        if " I " in module_name.upper() or module_name.upper().endswith("I") or re.match(r"^\dI\s", module_name.upper()):
             return "I" # Si "I" est trouvé comme classe probable pour blindage
    return None

def parse_edsm_module_id(module_id_edsm: str | None, module_name_edsm: str | None) -> dict:
    safe_module_name_edsm = module_name_edsm if isinstance(module_name_edsm, str) else ""
    safe_module_id_edsm = module_id_edsm if isinstance(module_id_edsm, str) else ""

    details = {
        "id": safe_module_id_edsm, "name_edsm": safe_module_name_edsm, "display_name_ui": safe_module_name_edsm,
        "category_key": "UNKNOWN",
        "size": extract_size_from_id_or_name(safe_module_id_edsm, safe_module_name_edsm),
        "class_rating": extract_class_from_id_or_name(safe_module_id_edsm, safe_module_name_edsm),
        "module_type": None, "mount": None, "ship_restriction": None
    }
    id_lower = safe_module_id_edsm.lower()

    if "_armour_" in id_lower or "armour_" in id_lower :
        details["category_key"] = "ARMOUR"
        ship_match = re.match(r"([a-zA-Z0-9_]+)_armour_", id_lower)
        if ship_match: details["ship_restriction"] = ship_match.group(1).replace('_', ' ')
        temp_module_type = safe_module_name_edsm
        if details["size"] is not None and details["class_rating"] is not None: # Enlever TailleClasse du nom si présentes
            temp_module_type = re.sub(rf"^{details['size']}{details['class_rating']}\s*", "", temp_module_type, flags=re.IGNORECASE).strip()
        details["module_type"] = temp_module_type
        if details["size"] is None: details["size"] = 1 
        if details["class_rating"] is None : details["class_rating"] = "I" # Les blindages sont souvent classe I
    elif id_lower.startswith("int_"):
        details["category_key"] = "OPTIONAL"
        core_map = { "powerplant": "Power Plant", "engine": "Thrusters", "thruster": "Thrusters", 
                     "hyperdrive": "Frame Shift Drive", "fsd": "Frame Shift Drive", "lifesupport": "Life Support",
                     "powerdistributor": "Power Distributor", "sensors": "Sensors", "fueltank": "Fuel Tank" }
        for key, val in core_map.items():
            if key in id_lower: details["category_key"] = "CORE"; details["module_type"] = val; break
        if not details["module_type"]:
            opt_map = { "shieldgenerator": "Shield Generator", "cargorack": "Cargo Rack", "fuelscoop": "Fuel Scoop",
                        "refinery": "Refinery", "repairer": "Auto Field-Maintenance Unit", "buggybay": "Planetary Vehicle Hangar",
                        "fighterbay": "Fighter Hangar", "dockingcomputer": "Docking Computer", 
                        "supercruiseassist": "Supercruise Assist", "fsdinterdictor": "FSD Interdictor",
                        "hullreinforcement": "Hull Reinforcement Package", "modulereinforcement": "Module Reinforcement Package",
                        "detailedsurfacescanner": "Detailed Surface Scanner", "shieldcellbank": "Shield Cell Bank",
                        "guardianfsdbooster": "Guardian FSD Booster", "metalloyhull": "Meta-Alloy Hull Reinforcement",
                        "passengercabin": "Passenger Cabin"}
            for key, val in opt_map.items():
                if key in id_lower: details["module_type"] = val; break
            if "dronecontrol" in id_lower:
                details["module_type"] = "Limpet Controller" # Générique
                limpet_types = {"collection": "Collector", "prospector": "Prospector", "fueltransfer": "Fuel Transfer",
                                "repair": "Repair", "resourcesiphon": "Hatch Breaker", "decontamination": "Decontamination",
                                "recon": "Recon"}
                for l_key, l_val in limpet_types.items():
                    if l_key in id_lower: details["module_type"] = f"{l_val} Limpet Controller"; break
                if "multidronecontrol" in id_lower or "universal" in id_lower or "operations" in id_lower or "rescue" in id_lower or ("mining" in id_lower and "multi" in id_lower) : 
                    details["module_type"] = "Multi Limpet Controller" # Peut être affiné par le nom EDSM
                    if "mining" in safe_module_name_edsm.lower(): details["module_type"] = "Mining Multi Limpet Controller"
                    elif "rescue" in safe_module_name_edsm.lower(): details["module_type"] = "Rescue Multi Limpet Controller"
                    elif "operations" in safe_module_name_edsm.lower(): details["module_type"] = "Operations Multi Limpet Controller"
    elif id_lower.startswith("hpt_"):
        details["category_key"] = "UTILITY" # Défaut pour hpt_
        util_map = { "heatsinklauncher": "Heat Sink Launcher", "chafflauncher": "Chaff Launcher",
                     "plasmapointdefence": "Point Defence", "pointdefence": "Point Defence", 
                     "electroniccountermeasure": "Electronic Countermeasure",
                     "cargoscanner": "Manifest Scanner", "cloudscanner": "Wake Scanner", 
                     "crimescanner": "Kill Warrant Scanner", "shieldbooster": "Shield Booster",
                     "mrascanner": "Pulse Wave Analyser", "shutdownfieldneutraliser": "Shutdown Field Neutraliser",
                     "xenoscanner": "Xeno Scanner", "pulsescanner":"Discovery Scanner" }
        is_utility = False
        for key, val in util_map.items():
            if key in id_lower: details["module_type"] = val; is_utility = True; break
        
        if not is_utility: # Si pas un utilitaire identifié, alors c'est un Hardpoint
            details["category_key"] = "HARDPOINT"
            wpn_map = { "beamlaser": "Beam Laser", "pulselaserburst": "Burst Laser", "pulselaser": "Pulse Laser",
                        "multicannon": "Multi-Cannon", "cannon": "Cannon", "plasmaaccelerator": "Plasma Accelerator",
                        "railgun": "Railgun", "missilerack": "Missile Rack", "dumbfiremissilerack": "Missile Rack (Dumbfire)", 
                        "advancedtorppylon": "Torpedo Pylon", "torpedo": "Torpedo Pylon",
                        "minelauncher": "Mine Launcher", "shockmine": "Shock Mine Launcher",
                        "slugshot": "Fragment Cannon", "mininglaser": "Mining Laser",
                        "mining_abrblstr": "Abrasion Blaster", 
                        "mining_seismchrgwarhd": "Seismic Charge Launcher",
                        "mining_subsurfdispmisle": "Sub-surface Disp. Missile",
                        "flakmortar": "Flak Launcher", "gausscannon": "Guardian Gauss Cannon",
                        "plasmacharger": "Guardian Plasma Charger", "shardcannon": "Guardian Shard Cannon" }
            for key, val in wpn_map.items():
                if key in id_lower: details["module_type"] = val; break
            
            if "_fixed" in id_lower or "(fixed)" in safe_module_name_edsm.lower(): details["mount"] = "Fixed"
            elif "_gimbal" in id_lower or "(gimbal)" in safe_module_name_edsm.lower(): details["mount"] = "Gimballed"
            elif "_turret" in id_lower or "(turret)" in safe_module_name_edsm.lower(): details["mount"] = "Turreted"
    
    if not details["module_type"]: # Fallback si le type n'a pas été clairement identifié
        cleaned_name = safe_module_name_edsm
        if details["size"] is not None and details["class_rating"] is not None:
             cleaned_name = re.sub(rf"^{details['size']}{details['class_rating']}\s*", "", cleaned_name, flags=re.IGNORECASE).strip()
        if details["mount"] and details["category_key"] == "HARDPOINT":
            cleaned_name = cleaned_name.replace(f"({details['mount']})", "").replace(f"({details['mount'].lower()})", "").strip()
        details["module_type"] = cleaned_name if cleaned_name and cleaned_name != str(details["size"])+str(details["class_rating"]) else safe_module_name_edsm


    ui_name_parts = []
    if details["size"] is not None: ui_name_parts.append(str(details["size"]))
    if details["class_rating"] is not None: ui_name_parts.append(details["class_rating"])
    
    type_for_ui = details["module_type"] if details["module_type"] else safe_module_name_edsm
    
    prefix_to_remove = ""
    if details["size"] is not None: prefix_to_remove += str(details["size"])
    if details["class_rating"] is not None: prefix_to_remove += details["class_rating"]
    
    # Nettoyer le type_for_ui si le préfixe taille/classe est déjà au début
    if prefix_to_remove and type_for_ui.upper().startswith(prefix_to_remove + " "):
        type_for_ui = type_for_ui[len(prefix_to_remove):].strip()
    elif prefix_to_remove and type_for_ui.upper().startswith(prefix_to_remove): # Sans espace
        type_for_ui = type_for_ui[len(prefix_to_remove):].strip()

    if type_for_ui: ui_name_parts.append(type_for_ui)

    if details["mount"] and details["category_key"] == "HARDPOINT": ui_name_parts.append(f"({details['mount']})")
    if details["ship_restriction"] and details["category_key"] == "ARMOUR": ui_name_parts.append(f"[{details['ship_restriction'].replace('_', ' ').title()}]")

    final_display_name = " ".join(filter(None,ui_name_parts)).replace("  ", " ").strip()
    # Si après tout ça, le nom est vide, utiliser le nom EDSM original
    details["display_name_ui"] = final_display_name if final_display_name else safe_module_name_edsm
    
    return details

def build_dynamic_catalogs_from_db(outfitting_data_json: dict):
    global DYNAMIC_MODULE_DETAILS_CATALOG, UI_MODULE_SELECTION_CATALOG
    DYNAMIC_MODULE_DETAILS_CATALOG = {}
    UI_MODULE_SELECTION_CATALOG = {cat_key: {} for cat_key in OUTFITTING_CATEGORIES_DISPLAY.keys()}
    if not outfitting_data_json or "systems_with_outfitting" not in outfitting_data_json:
        logger.warning("build_dynamic_catalogs_from_db: Données d'équipement non valides ou vides."); return
    unique_edsm_modules = {}
    for system_name, system_content in outfitting_data_json["systems_with_outfitting"].items():
        for station_details in system_content.get("stations", []):
            for module_api_entry in station_details.get("modules", []):
                if isinstance(module_api_entry, dict):
                    module_id, module_name = module_api_entry.get("id"), module_api_entry.get("name")
                    if module_id is None: 
                        logger.warning(f"Module trouvé avec ID None à la station {station_details.get('stationName', 'Unknown')} dans {system_name}. Module: {module_api_entry}")
                        continue
                    if module_id not in unique_edsm_modules: 
                        unique_edsm_modules[module_id] = module_name if module_name is not None else ""
    if not unique_edsm_modules: 
        logger.info("build_dynamic_catalogs_from_db: Aucun module valide trouvé dans les données locales."); return
    logger.info(f"build_dynamic_catalogs_from_db: Parsing de {len(unique_edsm_modules)} modules EDSM uniques...")
    for edsm_id, edsm_name in unique_edsm_modules.items():
        parsed_info = parse_edsm_module_id(edsm_id, edsm_name)
        DYNAMIC_MODULE_DETAILS_CATALOG[edsm_id] = parsed_info
        category_key, ui_display_name_from_parser = parsed_info.get("category_key"), parsed_info.get("display_name_ui")
        if category_key and category_key != "UNKNOWN" and ui_display_name_from_parser:
            if category_key not in UI_MODULE_SELECTION_CATALOG: UI_MODULE_SELECTION_CATALOG[category_key] = {}
            
            final_ui_name_for_selection = ui_display_name_from_parser
            original_ui_name = ui_display_name_from_parser
            counter = 1
            # S'assurer que la clé (nom affiché pour l'UI) est unique dans sa catégorie
            while final_ui_name_for_selection in UI_MODULE_SELECTION_CATALOG[category_key]:
                # Si l'ID EDSM est le même, c'est le même module, pas besoin de renommer
                if UI_MODULE_SELECTION_CATALOG[category_key][final_ui_name_for_selection] == edsm_id:
                    break 
                
                # Tentative de différenciation plus intelligente
                suffix_parts = []
                if parsed_info.get("size") is not None: suffix_parts.append(f"S{parsed_info['size']}")
                if parsed_info.get("class_rating") is not None: suffix_parts.append(parsed_info['class_rating'])
                if parsed_info.get("mount") and parsed_info.get("category_key") == "HARDPOINT": suffix_parts.append(parsed_info['mount'][:1]) # F, G, ou T
                
                if suffix_parts:
                    potential_new_name = f"{original_ui_name} ({','.join(suffix_parts)})"
                    if potential_new_name not in UI_MODULE_SELECTION_CATALOG[category_key]:
                        final_ui_name_for_selection = potential_new_name
                        break # Nom unique trouvé
                
                # Fallback avec un compteur si la différenciation intelligente échoue ou est toujours dupliquée
                final_ui_name_for_selection = f"{original_ui_name} ({counter})"
                counter += 1
                if counter > 10: # Limite pour éviter une boucle infinie
                    final_ui_name_for_selection = f"{original_ui_name} [{edsm_id[-5:]}]" # Utiliser une partie de l'ID
                    if final_ui_name_for_selection in UI_MODULE_SELECTION_CATALOG[category_key]: # Encore dupliqué, très improbable
                        final_ui_name_for_selection = edsm_id # Utiliser l'ID EDSM complet comme clé UI
                    break 
            UI_MODULE_SELECTION_CATALOG[category_key][final_ui_name_for_selection] = edsm_id

    for category_key in UI_MODULE_SELECTION_CATALOG:
        UI_MODULE_SELECTION_CATALOG[category_key] = dict(sorted(UI_MODULE_SELECTION_CATALOG[category_key].items()))
    logger.info(f"Catalogue dynamique des modules construit. {len(DYNAMIC_MODULE_DETAILS_CATALOG)} modules détaillés.")

def get_ui_categories():
    if not UI_MODULE_SELECTION_CATALOG: return []
    ordered_display_categories = []
    for cat_key in OUTFITTING_CATEGORIES_DISPLAY.keys():
        if cat_key in UI_MODULE_SELECTION_CATALOG and UI_MODULE_SELECTION_CATALOG[cat_key]:
            ordered_display_categories.append(OUTFITTING_CATEGORIES_DISPLAY[cat_key])
    return ordered_display_categories

def get_category_key_from_display_name(display_name: str) -> str | None: # FONCTION AJOUTÉE
    """Trouve la clé de catégorie interne à partir du nom affichable."""
    for key, val in OUTFITTING_CATEGORIES_DISPLAY.items():
        if val == display_name:
            return key
    logger.warning(f"Clé de catégorie non trouvée pour le nom affiché : '{display_name}'")
    return None

def get_ui_modules_for_category(category_display_name: str, size_filter=None, class_filter=None, mount_filter=None):
    category_key = get_category_key_from_display_name(category_display_name)
    if not category_key or category_key not in UI_MODULE_SELECTION_CATALOG: return []
    filtered_module_display_names = []
    for display_name, edsm_id in UI_MODULE_SELECTION_CATALOG[category_key].items():
        details = DYNAMIC_MODULE_DETAILS_CATALOG.get(edsm_id)
        if not details: continue
        if size_filter is not None and details.get("size") != size_filter: continue
        if class_filter is not None and details.get("class_rating") != class_filter: continue
        if category_key == "HARDPOINT" and mount_filter is not None and details.get("mount") != mount_filter: continue
        filtered_module_display_names.append(display_name)
    return filtered_module_display_names # Déjà trié car UI_MODULE_SELECTION_CATALOG est trié

def get_module_id_from_ui_selection(category_display_name: str, module_ui_name: str):
    category_key = get_category_key_from_display_name(category_display_name)
    if category_key and category_key in UI_MODULE_SELECTION_CATALOG:
        return UI_MODULE_SELECTION_CATALOG[category_key].get(module_ui_name)
    logger.warning(f"ID non trouvé pour cat='{category_display_name}', mod='{module_ui_name}'")
    return None

def get_distinct_sizes_for_category(category_display_name: str):
    category_key = get_category_key_from_display_name(category_display_name)
    if not category_key: return []
    sizes = set()
    for edsm_id in UI_MODULE_SELECTION_CATALOG.get(category_key, {}).values():
        details = DYNAMIC_MODULE_DETAILS_CATALOG.get(edsm_id)
        if details and details.get("size") is not None:
            sizes.add(details["size"])
    return sorted(list(s for s in sizes if isinstance(s, int)))

def get_distinct_classes_for_category(category_display_name: str, size_filter=None):
    category_key = get_category_key_from_display_name(category_display_name)
    if not category_key: return []
    classes = set()
    for edsm_id in UI_MODULE_SELECTION_CATALOG.get(category_key, {}).values():
        details = DYNAMIC_MODULE_DETAILS_CATALOG.get(edsm_id)
        if details and details.get("class_rating") is not None:
            if size_filter is not None and details.get("size") != size_filter: continue
            classes.add(details["class_rating"])
    ordered_classes = [c for c in MODULE_CLASSES_DISPLAY_ORDER if c in classes]
    return ordered_classes

def get_distinct_mounts_for_category(category_display_name: str, size_filter=None, class_filter=None):
    category_key = get_category_key_from_display_name(category_display_name)
    if category_key != "HARDPOINT": return []
    mounts_found = set()
    for edsm_id in UI_MODULE_SELECTION_CATALOG.get(category_key, {}).values():
        details = DYNAMIC_MODULE_DETAILS_CATALOG.get(edsm_id)
        if details and details.get("mount") is not None:
            if size_filter is not None and details.get("size") != size_filter: continue
            if class_filter is not None and details.get("class_rating") != class_filter: continue
            mounts_found.add(details["mount"])
    return [m for m in MODULE_MOUNTS_DISPLAY if m in mounts_found]
    
def get_category_key_from_display_name(display_name: str) -> str | None: # FONCTION AJOUTÉE
    """Trouve la clé de catégorie interne à partir du nom affichable."""
    for key, val in OUTFITTING_CATEGORIES_DISPLAY.items():
        if val == display_name:
            return key
    logger.warning(f"Clé de catégorie non trouvée pour le nom affiché : '{display_name}'")
    return None