#!/usr/bin/env python3
import tkinter as tk
import tkinter.messagebox
import logging # Importation de logging standard
import sys
import os # Ajout pour la gestion des chemins de log

# 1. Configurer le logging dès que possible, AVANT les autres imports de l'application
# pour capturer les erreurs d'importation potentielles.
# Déplacer la configuration du logger ici pour qu'elle soit la première chose après les imports standards.

# --- Configuration Manuelle Minimale du Logging (avant logger_setup) ---
# Ceci est un fallback si logger_setup lui-même a un problème ou n'est pas trouvé.
LOG_FILE_FALLBACK = 'mission_optimizer_startup.log'
try:
    # S'assurer que le répertoire du log existe (si LOG_FILE est dans un sous-répertoire)
    log_dir = os.path.dirname(LOG_FILE_FALLBACK)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(module)s - %(funcName)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE_FALLBACK, mode='a', encoding='utf-8'), # 'a' pour append
            logging.StreamHandler(sys.stdout) # Afficher aussi sur la console
        ]
    )
    logging.info("--- Fallback Basic Logging Initialized ---")
except Exception as e:
    print(f"CRITICAL: Failed to initialize fallback logging: {e}", file=sys.stderr)
    # Si même ça échoue, il n'y a plus grand-chose à faire pour le logging.

# --- Fin Configuration Manuelle Minimale du Logging ---

# Maintenant, tenter d'importer et d'utiliser la configuration de logging plus avancée
try:
    import logger_setup
    logger_setup.setup_logging() # Ceci va reconfigurer le root logger avec RotatingFileHandler, etc.
    # Obtenir un logger pour ce module APRÈS la configuration
    logger = logging.getLogger(__name__)
    logger.info("--- Advanced Logging Initialized via logger_setup.py ---")
except ImportError as e_log_setup:
    logging.critical(f"Failed to import logger_setup: {e_log_setup}. Using fallback basicConfig logging.", exc_info=True)
    logger = logging.getLogger(__name__) # Utiliser le logger configuré par basicConfig
    logger.warning("Using fallback basicConfig logging due to logger_setup import error.")
except Exception as e_log_setup_generic:
    logging.critical(f"An error occurred during logger_setup.setup_logging(): {e_log_setup_generic}. Using fallback basicConfig logging.", exc_info=True)
    logger = logging.getLogger(__name__)
    logger.warning("Using fallback basicConfig logging due to logger_setup execution error.")


# --- Importer les autres modules de l'application APRÈS le logging ---
try:
    import settings_manager
    # Attention: L'import de gui_main va déclencher les imports de ses sous-modules (gui_analysis_tab, etc.)
    # et ceux-ci importeront constants. Si constants.py a une erreur, elle surviendra ici.
    import gui_main
    from constants import LOG_FILE as CONST_LOG_FILE, KEY_LANGUAGE, DEFAULT_LANGUAGE # Renommer pour éviter conflit avec LOG_FILE_FALLBACK
    import language as lang_module
except ImportError as e_import:
    logger.critical(f"Failed to import a core application module: {e_import}", exc_info=True)
    # Afficher une erreur simple si Tkinter n'est pas encore prêt
    print(f"Critical import error: {e_import}\nConsult {LOG_FILE_FALLBACK} or {CONST_LOG_FILE if 'CONST_LOG_FILE' in globals() else 'mission_optimizer.log'}", file=sys.stderr)
    try: # Tenter d'afficher une messagebox même si l'UI complète ne peut se charger
        error_root_tk = tk.Tk()
        error_root_tk.withdraw()
        tkinter.messagebox.showerror("Critical Import Error",
                                     f"Could not import a required module:\n{e_import}\n\n"
                                     f"Consult logs for details.\nThe application will now close.")
        error_root_tk.destroy()
    except Exception:
        pass # L'erreur console devra suffire
    sys.exit(1) # Quitter si un import critique échoue
except Exception as e_generic_import_phase:
    logger.critical(f"A non-ImportError exception occurred during the import phase: {e_generic_import_phase}", exc_info=True)
    print(f"Critical error during import phase: {e_generic_import_phase}\nConsult {LOG_FILE_FALLBACK} or {CONST_LOG_FILE if 'CONST_LOG_FILE' in globals() else 'mission_optimizer.log'}", file=sys.stderr)
    sys.exit(1)


def main():
    logger.info("Application main() function starting...")

    # 2. Charger les paramètres
    try:
        settings_manager.load_settings()
        saved_lang = settings_manager.get_setting(KEY_LANGUAGE, DEFAULT_LANGUAGE)
        lang_module.set_language(saved_lang)
        logger.info(f"Settings loaded successfully. Language set to: {saved_lang}")
    except Exception as e_settings:
        logger.critical("Failed to load settings on startup:", exc_info=True)
        try:
            error_root_tk = tk.Tk()
            error_root_tk.withdraw()
            tkinter.messagebox.showerror("Critical Settings Error",
                                         f"Could not load settings:\n{e_settings}\n\n"
                                         f"The application might not function correctly or will use defaults.\n"
                                         f"Consult {CONST_LOG_FILE} for details.")
            error_root_tk.destroy()
        except Exception:
            pass

    # 3. Créer la fenêtre principale Tkinter
    root = tk.Tk()
    logger.info("Tkinter root window created.")

    # 4. Initialiser l'interface graphique (passe le root)
    try:
        gui_main.create_main_window(root) # Appel à la fonction du nouveau module gui_main
        logger.info("GUI created successfully via gui_main.create_main_window().")
    except Exception as e_gui:
        logger.critical("Failed to create GUI via gui_main.create_main_window():", exc_info=True)
        try:
            # Retirer la fenêtre root si elle a été créée mais que l'UI a échoué
            if root and root.winfo_exists():
                root.withdraw()
            tkinter.messagebox.showerror("Critical GUI Error",
                                         f"Could not create the main application window:\n{e_gui}\n\n"
                                         f"Consult {CONST_LOG_FILE} for details.\nThe application will now close.")
            if root and root.winfo_exists():
                root.destroy()
        except Exception as e_msgbox:
            logger.error(f"Failed to show GUI error messagebox: {e_msgbox}")
        sys.exit(1)


    # 5. Démarrer la boucle principale de Tkinter
    try:
        logger.info("Starting Tkinter mainloop.")
        root.mainloop()
        logger.info("Tkinter mainloop finished.")
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (KeyboardInterrupt).")
    except Exception as e_mainloop:
        logger.critical("Unhandled exception in Tkinter mainloop:", exc_info=True)
    finally:
        logger.info("Application shutting down.")

if __name__ == "__main__":
    # Assurer que le logger de plus haut niveau est prêt avant d'appeler main()
    if 'logger' not in globals() or not isinstance(logger, logging.Logger):
        # Si logger_setup a échoué de manière catastrophique, et que le fallback aussi.
        print("CRITICAL: Logger was not initialized before main. Exiting.", file=sys.stderr)
        sys.exit(1)
    
    logger.info("Starting main_app.py execution from __main__ guard.")
    main()