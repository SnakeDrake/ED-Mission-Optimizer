#!/usr/bin/env python3

# ---- Configuration API Ardent Insight ----
BASE_URL = "https://api.ardent-insight.com/v2/"
HEADERS = {"User-Agent": "MissionOptimizer/3.0 (wdsnakedrake@gmail.com)"}
CONCURRENCY_LIMIT = 20

# ---- Configuration API EDSM ----
EDSM_BASE_URL = "https://www.edsm.net/"
EDSM_HEADERS = {"User-Agent": "MissionOptimizer/2.1 (wdsnakedrake@gmail.com) ShipyardFeature"}

# ---- Noms de Fichiers ----
DEPARTURE_DATA_FILE = 'departure_market_data.json'
LOCAL_SELLERS_DATA_FILE = 'local_sellers_data.json'
SHIPYARD_DATA_FILE = 'shipyard_data.json' # Pour l'onglet Chantier Naval
OUTFITTING_DATA_FILE = 'outfitting_data.json'
SETTINGS_FILE = 'settings.json'
LOG_FILE = 'mission_optimizer.log'
MULTI_HOP_ROUTE_CACHE_FILE = 'multihop_route_cache.json' # <<< NOUVELLE LIGNE

# ---- Paramètres par Défaut ----
DEFAULT_RADIUS = 80.0
DEFAULT_MAX_AGE_DAYS = 1
DEFAULT_MAX_STATION_DISTANCE_LS = 5000.0
DEFAULT_INCLUDE_PLANETARY = True
DEFAULT_INCLUDE_FLEET_CARRIERS = True # S'applique à la fois à l'analyse du marché et au chantier naval par défaut
DEFAULT_CUSTOM_JOURNAL_DIR = None
DEFAULT_NUM_JOURNAL_FILES_MISSIONS = 25
DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS = 5
DEFAULT_MAX_GENERAL_TRADE_ROUTES = 5
DEFAULT_TOP_N_IMPORTS_FILTER = 30
DEFAULT_LANGUAGE = "en"
DEFAULT_SHIPYARD_RADIUS_LY = 50.0 # Rayon spécifique pour la recherche de chantiers navals
DEFAULT_SHIPYARD_MAX_AGE_DAYS = 7 # Peut être différent pour la BD des chantiers navals
DEFAULT_OUTFITTING_RADIUS_LY = 50.0
DEFAULT_OUTFITTING_MAX_AGE_DAYS = 7 

# ---- Paramètres de Réinitialisation ----
RESET_DEFAULT_RADIUS = 80.0
RESET_DEFAULT_MAX_AGE_DAYS = 1
RESET_DEFAULT_MAX_STATION_DISTANCE_LS = 5000.0
RESET_DEFAULT_INCLUDE_PLANETARY = True
RESET_DEFAULT_INCLUDE_FLEET_CARRIERS = True
RESET_DEFAULT_SORT_OPTION = 'd'
RESET_DEFAULT_CUSTOM_JOURNAL_DIR = None
RESET_DEFAULT_NUM_JOURNAL_FILES_MISSIONS = 25
RESET_DEFAULT_MAX_STATIONS_FOR_TRADE_LOOPS = 5
RESET_DEFAULT_MAX_GENERAL_TRADE_ROUTES = 5
RESET_DEFAULT_TOP_N_IMPORTS_FILTER = 30
RESET_DEFAULT_LANGUAGE = "en"
# RESET_DEFAULT_SHIPYARD_RADIUS_LY = 50.0 # Si on l'ajoute aux settings persistants

# ---- Types de Stations et Vaisseaux ----
PLANETARY_STATION_TYPES = [
    "CraterOutpost", "OnFootSettlement", "CraterPort",
    "PlanetaryOutpost", "PlanetaryPort", "OdysseySettlement", "null",
    "Planetary Outpost", "Planetary Port" # Versions avec espaces pour correspondre à EDSM
]
FLEET_CARRIER_STATION_TYPES = [
    "FleetCarrier", "DrakeFleetCarrier",
    "Fleet Carrier" # Version avec espace pour correspondre à EDSM
]

SHIP_PAD_SIZE = {
    'sidewinder': 1, 'eagle': 1, 'viper mk iii': 1, 'viper mk iv': 1,'cobra mk iii': 1, 'cobra mk iv': 1, 'hauler': 1, 'adder': 1,'diamondback scout': 1, 'diamondback explorer': 1, 'vulture': 1,'imperial courier': 1, 'federal dropship': 2, 'federal gunship': 2,'federal assault ship': 2, 'asp scout': 2, 'asp explorer': 2,'type-6 transporter': 2, 'type-7 transporter': 3,'type-9 heavy': 3, 'type-10 defender': 3, 'keelback': 2,'fer-de-lance': 2, 'python': 2, 'anaconda': 3, 'imperial clipper': 2,'imperial cutter': 3, 'orca': 2, 'beluga liner': 3, 'dolphin': 1,'mamba': 2, 'krait mk ii': 2, 'krait phantom': 2, 'alliance chieftain': 2,'alliance challenger': 2, 'alliance crusader': 2, 'type9': 3, 'federal corvette': 3
}
STATION_PAD_SIZE_MAP = {'S': 1, 'M': 2, 'L': 3}

PURCHASABLE_SHIPS_LIST = {
    "sidewinder": "Sidewinder Mk I", "eagle": "Eagle Mk II", "hauler": "Hauler",
    "adder": "Adder", "viper_mk_iii": "Viper Mk III", "cobra_mk_iii": "Cobra Mk III",
    "type_6_transporter": "Type-6 Transporter", "dolphin": "Dolphin",
    "diamondback_scout": "Diamondback Scout", "viper_mk_iv": "Viper Mk IV",
    "asp_scout": "Asp Scout", "keelback": "Keelback", "vulture": "Vulture",
    "federal_dropship": "Federal Dropship", "type_7_transporter": "Type-7 Transporter",
    "alliance_chieftain": "Alliance Chieftain", "asp_explorer": "Asp Explorer",
    "imperial_courier": "Imperial Courier", "federal_assault_ship": "Federal Assault Ship",
    "krait_phantom": "Krait Phantom", "python": "Python", "fer_de_lance": "Fer-de-Lance",
    "mamba": "Mamba", "krait_mk_ii": "Krait Mk II", "federal_gunship": "Federal Gunship",
    "alliance_crusader": "Alliance Crusader", "alliance_challenger": "Alliance Challenger",
    "type_9_heavy": "Type-9 Heavy", "orca": "Orca", "imperial_clipper": "Imperial Clipper",
    "beluga_liner": "Beluga Liner", "type_10_defender": "Type-10 Defender",
    "anaconda": "Anaconda", "federal_corvette": "Federal Corvette", "imperial_cutter": "Imperial Cutter",
    # Nouveaux vaisseaux potentiels basés sur les données de shipyard_data.json
    "Type-8 Transporter": "Type-8 Transporter", # Assurez-vous que la clé correspond à ce que EDSM retourne ou à votre normalisation
    "Corsair": "Corsair",
    "Imperial Eagle": "Imperial Eagle", # EDSM semble retourner "Imperial Eagle"
    "Python Mk II": "Python Mk II",
    "Mandalay": "Mandalay",
    "Cobra Mk V": "Cobra Mk V"
}


# ---- Clés pour APP_SETTINGS ----
KEY_RADIUS = 'radius'
KEY_MAX_AGE_DAYS = 'max_age_days'
KEY_MAX_STATION_DISTANCE_LS = 'max_station_distance_ls'
KEY_INCLUDE_PLANETARY = 'include_planetary'
KEY_INCLUDE_FLEET_CARRIERS = 'include_fleet_carriers'
KEY_CUSTOM_JOURNAL_DIR = 'custom_journal_dir'
KEY_CUSTOM_PAD_SIZES = 'custom_pad_sizes'
KEY_SORT_OPTION = 'sort_option'
KEY_NUM_JOURNAL_FILES_MISSIONS = 'num_journal_files_for_missions'
KEY_MAX_STATIONS_FOR_TRADE_LOOPS = 'max_stations_for_trade_loops'
KEY_MAX_GENERAL_TRADE_ROUTES = 'max_general_trade_routes'
KEY_TOP_N_IMPORTS_FILTER = 'top_n_imports_filter'
KEY_LANGUAGE = 'language'
# KEY_SHIPYARD_RADIUS = 'shipyard_radius' # À décommenter si vous voulez un setting séparé pour le rayon du chantier

# ---- Constantes de Style pour GUI (utilisées par gui_analysis_tab) ----
REWARD_COLOR = '#FF8C00'
COST_COLOR = '#FF4136'
PROFIT_COLOR = '#2ECC40'

# ---- Constantes de Style pour GUI (utilisées par les modules GUI) ----
ED_MAT_DARK_RED = "#8B0000"      # Rouge foncé (pour < 10%)
ED_MAT_RED = "#CC0000"           # Rouge (pour 10-29%)
ED_MAT_DARK_ORANGE = "#FF8C00"   # Orange foncé (pour 30-49%)
ED_ORANGE = '#FF8C00'            # ED_ORANGE est déjà défini, nous l'utiliserons pour 50-69%
ED_MAT_YELLOW_GREEN = "#9ACD32"  # Vert-jaune / Olive (pour 70-89%)
ED_MAT_GREEN_MEDIUM = "#008000"  # Vert moyen (pour 90-99%)
ED_MAT_GREEN_BRIGHT = "#32CD32"  # Vert citron / Vert vif (pour 100%)
ED_DARK_GREY = '#1c1c1c'
ED_MEDIUM_GREY = '#2c2c2c'
ED_LIGHT_GREY_TEXT = '#c0c0c0'
ED_WHITE_TEXT = '#FFFFFF'
ED_BUTTON_BG = '#3c3c3c'
ED_BUTTON_ACTIVE_BG = '#4c4c4c'
ED_BUTTON_PRESSED_BG = '#5c5c5c'
ED_MAT_TEXT_ON_DARK = ED_WHITE_TEXT  # Ex: Texte blanc sur rouge foncé
ED_MAT_TEXT_ON_LIGHT = ED_DARK_GREY # Ex: Texte foncé sur vert clair/orange

ED_INPUT_BG = ED_MEDIUM_GREY # Ou une autre nuance de gris
ED_INPUT_TEXT = ED_WHITE_TEXT
ED_HIGHLIGHT_BG = ED_ORANGE # Pour les sélections
ED_HIGHLIGHT_TEXT = ED_DARK_GREY # Texte sur la sélection

TAG_REWARD = "reward_style"
TAG_COST = "cost_style"
TAG_PROFIT = "profit_style"
TAG_HEADER = "header_style"
TAG_SUBHEADER = "subheader_style"
TAG_TOTAL_PROFIT_LEG = "total_profit_leg_style"

BASE_FONT_FAMILY = 'Consolas'
BASE_FONT_SIZE = 9

# Cartographie pour déduire la taille de pad à partir du type de station (approximatif)
# 'L' pour Large, 'M' pour Medium, 'S' pour Small, '?' pour inconnu/variable
# Ceci est une heuristique et pourrait nécessiter des ajustements.
STATION_TYPE_TO_PAD_SIZE_LETTER = {
    # Grands Pads (L)
    "Orbis Starport": "L",
    "Coriolis Starport": "L",
    "Ocellus Starport": "L",
    "Asteroid base": "L",
    "Mega ship": "L",
    "FleetCarrier": "L", # De FLEET_CARRIER_STATION_TYPES
    "DrakeFleetCarrier": "L", # De FLEET_CARRIER_STATION_TYPES
    "Fleet Carrier": "L", # Version avec espace de FLEET_CARRIER_STATION_TYPES
    "Planetary Port": "L", # Les ports planétaires peuvent avoir L
    "CraterPort": "L", # Spécifique

    # Pads Moyens (M) max - Peut aussi avoir S
    "Outpost": "M", # Terme générique pour divers avant-postes
    "Civilian Outpost": "M",
    "Military Outpost": "M",
    "Industrial Outpost": "M",
    "Mining Outpost": "M",
    "Planetary Outpost": "M", # De PLANETARY_STATION_TYPES
    "CraterOutpost": "M", # De PLANETARY_STATION_TYPES

    # OnFootSettlement et OdysseySettlement n'ont pas de pads pour vaisseaux.
    # On peut les marquer comme 'S' ou '?' ou les exclure si on filtre sur les pads pour vaisseaux.
    "OnFootSettlement": "?", # Ou exclure
    "OdysseySettlement": "?", # Ou exclure

    # Par défaut ou inconnu
    "Unknown": "?",
    "null": "?" # Si EDSM retourne "null" pour un type
}

# ---- Pour l'onglet Outfitting ----
OUTFITTING_DATA_FILE = 'outfitting_data.json'

# Catégories d'équipement (Clé interne -> Nom affichable)
# Les clés internes seront utilisées dans module_catalog_data.py
OUTFITTING_CATEGORIES_DISPLAY = {
    "HARDPOINT": "Hardpoints",
    "UTILITY": "Utility Mounts",
    "CORE": "Core Internals",
    "OPTIONAL": "Optional Internals",
    "ARMOUR": "Armour" # Les blindages sont souvent spécifiques aux vaisseaux
}

# Tailles et Classes pour les filtres (si on veut des menus déroulants pour ça)
MODULE_SIZES = [1, 2, 3, 4, 5, 6, 7, 8]
MODULE_CLASSES_DISPLAY_ORDER = ["A", "B", "C", "D", "E", "I"] # 'I' pour les blindages, par exemple
MODULE_MOUNTS_DISPLAY = ["Fixed", "Gimballed", "Turreted"] # Pour les Hardpoints

# --- Engineering Materials Data ---
MATERIAL_CATEGORIES = ["Raw", "Manufactured", "Encoded"]

MATERIAL_LIMITS = {
    "Raw": {1: 300, 2: 250, 3: 200, 4: 150, 5: 100},
    "Manufactured": {1: 300, 2: 250, 3: 200, 4: 150, 5: 100},
    "Encoded": {1: 300, 2: 250, 3: 200, 4: 150, 5: 100}
}

ALL_MATERIALS_DATA = {
    "Raw": [
        # Grade 1
        {"Name": "carbon", "Name_Localised": "Carbon", "Grade": 1},
        {"Name": "phosphorus", "Name_Localised": "Phosphorus", "Grade": 1},
        {"Name": "sulphur", "Name_Localised": "Sulphur", "Grade": 1},
        {"Name": "iron", "Name_Localised": "Iron", "Grade": 1},
        {"Name": "nickel", "Name_Localised": "Nickel", "Grade": 1},
        {"Name": "lead", "Name_Localised": "Lead", "Grade": 1}, # Added from common G1 list
        {"Name": "rhenium", "Name_Localised": "Rhenium", "Grade": 1}, # Added from common G1 list

        # Grade 2
        {"Name": "vanadium", "Name_Localised": "Vanadium", "Grade": 2},
        {"Name": "germanium", "Name_Localised": "Germanium", "Grade": 2},
        {"Name": "chromium", "Name_Localised": "Chromium", "Grade": 2},
        {"Name": "manganese", "Name_Localised": "Manganese", "Grade": 2},
        {"Name": "zinc", "Name_Localised": "Zinc", "Grade": 2},
        {"Name": "niobium", "Name_Localised": "Niobium", "Grade": 2}, # Added from common G2 list

        # Grade 3
        {"Name": "selenium", "Name_Localised": "Selenium", "Grade": 3},
        {"Name": "molybdenum", "Name_Localised": "Molybdenum", "Grade": 3},
        {"Name": "cadmium", "Name_Localised": "Cadmium", "Grade": 3},
        {"Name": "tungsten", "Name_Localised": "Tungsten", "Grade": 3},
        {"Name": "yttrium", "Name_Localised": "Yttrium", "Grade": 3}, # Added from common G3 list (was grade 4 by mistake, corrected)
        {"Name": "tin", "Name_Localised": "Tin", "Grade": 3}, # Added G3 (was G2 in a prev thought, corrected)

        # Grade 4
        {"Name": "zirconium", "Name_Localised": "Zirconium", "Grade": 4},
        {"Name": "mercury", "Name_Localised": "Mercury", "Grade": 4},
        {"Name": "polonium", "Name_Localised": "Polonium", "Grade": 4}, # Corrected Grade (was 5)
        {"Name": "arsenic", "Name_Localised": "Arsenic", "Grade": 4},
        {"Name": "tellurium", "Name_Localised": "Tellurium", "Grade": 4},
        {"Name": "ruthenium", "Name_Localised": "Ruthenium", "Grade": 4},


        # Grade 5
        {"Name": "technetium", "Name_Localised": "Technetium", "Grade": 5},
        {"Name": "antimony", "Name_Localised": "Antimony", "Grade": 5},
        {"Name": "boron", "Name_Localised": "Boron", "Grade": 5}, # Added G5 (was G4 in a prev thought, corrected)
        {"Name": "lanthanum", "Name_Localised": "Lanthanum", "Grade": 5}, # Added G5
        {"Name": "ytterbium", "Name_Localised": "Ytterbium", "Grade": 5}, # Added G5

    ],
    "Manufactured": [
        # Grade 1
        {"Name": "basicconductors", "Name_Localised": "Basic Conductors", "Grade": 1},
        {"Name": "chemicalstorageunits", "Name_Localised": "Chemical Storage Units", "Grade": 1},
        {"Name": "compactcomposites", "Name_Localised": "Compact Composites", "Grade": 1},
        {"Name": "heatconductionwiring", "Name_Localised": "Heat Conduction Wiring", "Grade": 1},
        {"Name": "mechanicalscrap", "Name_Localised": "Mechanical Scrap", "Grade": 1},
        {"Name": "gridresistors", "Name_Localised": "Grid Resistors", "Grade": 1},
        {"Name": "salvagedalloys", "Name_Localised": "Salvaged Alloys", "Grade": 1}, # Added G1

        # Grade 2
        {"Name": "chemicalprocessors", "Name_Localised": "Chemical Processors", "Grade": 2},
        {"Name": "conductivecomponents", "Name_Localised": "Conductive Components", "Grade": 2},
        {"Name": "heatresistantceramics", "Name_Localised": "Heat-Resistant Ceramics", "Grade": 2},
        {"Name": "mechanicalequipment", "Name_Localised": "Mechanical Equipment", "Grade": 2},
        {"Name": "wornshieldemitters", "Name_Localised": "Worn Shield Emitters", "Grade": 2}, # Added G2

        # Grade 3
        {"Name": "chemicaldistillery", "Name_Localised": "Chemical Distillery", "Grade": 3},
        {"Name": "conductiveceramics", "Name_Localised": "Conductive Ceramics", "Grade": 3},
        {"Name": "electrochemicalarrays", "Name_Localised": "Electrochemical Arrays", "Grade": 3},
        {"Name": "heatdispersionplate", "Name_Localised": "Heat Dispersion Plate", "Grade": 3},
        {"Name": "mechanicalcomponents", "Name_Localised": "Mechanical Components", "Grade": 3},
        {"Name": "shieldemitters", "Name_Localised": "Shield Emitters", "Grade": 3}, # Added G3

        # Grade 4
        {"Name": "chemicalmanipulators", "Name_Localised": "Chemical Manipulators", "Grade": 4},
        {"Name": "conductivepolymers", "Name_Localised": "Conductive Polymers", "Grade": 4},
        {"Name": "configurablecomponents", "Name_Localised": "Configurable Components", "Grade": 4},
        {"Name": "heatexchangers", "Name_Localised": "Heat Exchangers", "Grade": 4},
        {"Name": "highdensitycomposites", "Name_Localised": "High Density Composites", "Grade": 4},
        {"Name": "phasealloys", "Name_Localised": "Phase Alloys", "Grade": 4},
        {"Name": "focuscrystals", "Name_Localised": "Focus Crystals", "Grade": 4}, # Added G4

        # Grade 5
        {"Name": "biotechconductors", "Name_Localised": "Biotech Conductors", "Grade": 5},
        {"Name": "exquisitefocuscrystals", "Name_Localised": "Exquisite Focus Crystals", "Grade": 5},
        {"Name": "imperialshielding", "Name_Localised": "Imperial Shielding", "Grade": 5},
        {"Name": "improvisedcomponents", "Name_Localised": "Improvised Components", "Grade": 5},
        {"Name": "militarygradealloys", "Name_Localised": "Military Grade Alloys", "Grade": 5},
        {"Name": "militarysupercapacitors", "Name_Localised": "Military Supercapacitors", "Grade": 5},
        {"Name": "pharmaceuticalisolators", "Name_Localised": "Pharmaceutical Isolators", "Grade": 5},
        {"Name": "protolightalloys", "Name_Localised": "Proto Light Alloys", "Grade": 5},
        {"Name": "protoradiolicalloys", "Name_Localised": "Proto Radiolic Alloys", "Grade": 5},
        {"Name": "reinforcedmountingplate", "Name_Localised": "Reinforced Mounting Plate", "Grade": 5}, # Added G5
        {"Name": "thermicalloys", "Name_Localised": "Thermic Alloys", "Grade": 5} # Added G5
    ],
    "Encoded": [
        # Grade 1
        {"Name": "bulkscandata", "Name_Localised": "Bulk Scan Data", "Grade": 1},
        {"Name": "scrambledemissiondata", "Name_Localised": "Scrambled Emission Data", "Grade": 1},
        {"Name": "shieldcyclerecordings", "Name_Localised": "Shield Cycle Recordings", "Grade": 1},
        {"Name": "wakeexceptions", "Name_Localised": "Exceptional Scrambled Emission Data", "Grade": 1}, # Name needs check, often "Exceptional Scrambled Emission Data"
        {"Name": "archivedemissiondata", "Name_Localised": "Archived Emission Data", "Grade": 1}, # Added G1

        # Grade 2
        {"Name": "disruptedwakeechoes", "Name_Localised": "Disrupted Wake Echoes", "Grade": 2},
        {"Name": "industrialfirmware", "Name_Localised": "Industrial Firmware", "Grade": 2},
        {"Name": "shieldsoakanalysis", "Name_Localised": "Shield Soak Analysis", "Grade": 2},
        {"Name": "emissiondata", "Name_Localised": "Emission Data", "Grade": 2}, # Added G2 (was "Anomalous Bulk Scan Data")

        # Grade 3
        {"Name": "fsdtelemetry", "Name_Localised": "FSD Telemetry", "Grade": 3}, # Corrected (was "Anomalous FSD Telemetry")
        {"Name": "consumerfirmware", "Name_Localised": "Consumer Firmware", "Grade": 3}, # Added G3
        {"Name": "shielddensityreports", "Name_Localised": "Shield Density Reports", "Grade": 3},
        {"Name": "legacyfirmware", "Name_Localised": "Legacy Firmware", "Grade": 3}, # Added G3 (was "Security Firmware")

        # Grade 4
        {"Name": "classifiedscandata", "Name_Localised": "Classified Scan Data", "Grade": 4},
        {"Name": "compactemissionsdata", "Name_Localised": "Compact Emissions Data", "Grade": 4}, # Added G4 (was "Cracked Industrial Firmware")
        {"Name": "shieldpatternanalysis", "Name_Localised": "Shield Pattern Analysis", "Grade": 4},
        {"Name": "decodedemissiondata", "Name_Localised": "Decoded Emission Data", "Grade": 4},
        {"Name": "embeddedfirmware", "Name_Localised": "Embedded Firmware", "Grade": 4}, # Added G4

        # Grade 5
        {"Name": "adaptiveencryptors", "Name_Localised": "Adaptive Encryptors", "Grade": 5},
        {"Name": "dataminedwake", "Name_Localised": "Datamined Wake Exceptions", "Grade": 5},
        {"Name": "modifiedconsumerfirmware", "Name_Localised": "Modified Consumer Firmware", "Grade": 5},
        {"Name": "modifiedembeddedfirmware", "Name_Localised": "Modified Embedded Firmware", "Grade": 5},
        {"Name": "peculiarpresidemics", "Name_Localised": "Peculiar Shield Frequency Data", "Grade": 5},
        {"Name": "specialisedlegacyfirmware", "Name_Localised": "Specialised Legacy Firmware", "Grade": 5}, # Added G5
        {"Name": "ancientguardianblueprint", "Name_Localised": "Guardian Blueprint Fragment", "Grade": 5}, # Category might vary (Guardian)
        {"Name": "tg_technologyblueprint", "Name_Localised": "Thargoid Technology Blueprint", "Grade": 5} # Category might vary (Thargoid)

    ]
}

# Pour faciliter la recherche du grade et de la catégorie d'un matériau par son nom
MATERIALS_LOOKUP = {}
for category, materials_in_category in ALL_MATERIALS_DATA.items():
    for mat_data in materials_in_category:
        # Utilise le nom interne en minuscules comme clé primaire pour la recherche
        MATERIALS_LOOKUP[mat_data["Name"].lower()] = {
            "Category": category,
            "Grade": mat_data["Grade"],
            "Name_Localised": mat_data.get("Name_Localised", mat_data["Name"]) # Fournit un nom affichable
        }

# Fonction pour obtenir la limite d'un matériau spécifique
def get_material_limit(material_name_internal_lower, category=None, grade=None):
    # material_name_internal_lower est déjà en minuscules
    if category is None or grade is None:
        lookup = MATERIALS_LOOKUP.get(material_name_internal_lower)
        if not lookup:
            # logger is not defined here, but in a real scenario, you'd log this.
            # print(f"Warning: Material {material_name_internal_lower} not found in MATERIALS_LOOKUP for limit.")
            return 0 # Retourne 0 si le matériau n'est pas trouvé
        category = lookup["Category"]
        grade = lookup["Grade"]
    
    return MATERIAL_LIMITS.get(category, {}).get(grade, 0)

# --- Fin Engineering Materials Data ---