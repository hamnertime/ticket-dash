#!/usr/bin/env python3

import os
import json
import datetime
import time
import logging
from pyluxafor import LuxaforFlag

# --- Configuration ---
TICKETS_DIR = "./tickets"
OPEN_TICKET_STATUS_ID = 2
WAITING_ON_AGENT = 26

UPDATE_INTERVAL_SECONDS = 10
# DEVICE_CHECK_INTERVAL_SECONDS = 60 # No longer needed for timed reconnect

# --- Luxafor Color Definitions ---
COLOR_RED = (255, 0, 0)
COLOR_YELLOW = (255, 180, 0)
COLOR_GREEN = (0, 255, 0)
COLOR_MAGENTA = (255, 0, 255) # For errors
COLOR_OFF = (0, 0, 0)

STROBE_SPEED = 15
STROBE_REPEATS = 0

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def parse_datetime_utc(dt_str):
    """Safely parses ISO format datetime strings, returning None on failure."""
    if not dt_str: return None
    try:
        return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        logging.warning(f"Could not parse datetime string: {dt_str}")
        return None

# --- Core Logic ---

def get_simplified_ticket_states(tickets_dir):
    """
    Loads tickets and counts states relevant to the simplified logic.
    Returns dict: {'open': count, 'waiting_agent': count, 'fr_overdue': count, 'error': count}
    """
    # (Function remains the same as the previous version)
    states = {"open": 0, "waiting_agent": 0, "fr_overdue": 0, "error": 0}
    if not os.path.isdir(tickets_dir):
        logging.error(f"Tickets directory '{tickets_dir}' not found.")
        states["error"] = 1
        return states
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for filename in os.listdir(tickets_dir):
        if filename.endswith(".txt") and filename[:-4].isdigit():
            file_path = os.path.join(tickets_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
                status_raw = data.get('status')
                if status_raw == OPEN_TICKET_STATUS_ID:
                    states["open"] += 1
                    stats = data.get('stats', {})
                    first_responded_at_str = stats.get('first_responded_at')
                    fr_due_by_str = data.get('fr_due_by')
                    first_responded_at_dt = parse_datetime_utc(first_responded_at_str)
                    fr_due_by_dt = parse_datetime_utc(fr_due_by_str)
                    if first_responded_at_dt is None and fr_due_by_dt and fr_due_by_dt < now_utc:
                        states["fr_overdue"] += 1
                elif status_raw == WAITING_ON_AGENT:
                    states["waiting_agent"] += 1
            except json.JSONDecodeError:
                logging.error(f"JSON decode error for {filename}")
                states["error"] += 1
            except Exception as e:
                logging.error(f"Error processing {filename}: {e}", exc_info=False)
                states["error"] += 1
    return states


def update_luxafor_simplified(flag, states):
    """
    Sets the Luxafor flag based on the simplified logic.
    Returns True on success, False on failure (e.g., device communication error).
    """
    # (Function remains the same as the previous version, still returns True/False)
    try:
        # Priority Order: Error > FR Overdue > Open > Waiting > Green
        if states["error"] > 0:
            logging.warning("Error reading ticket files. Setting light to SOLID MAGENTA.")
            flag.off()
            flag.do_static_colour(leds=LuxaforFlag.LED_ALL, r=COLOR_MAGENTA[0], g=COLOR_MAGENTA[1], b=COLOR_MAGENTA[2])
        elif states["fr_overdue"] > 0:
            logging.info(f"FR Overdue tickets ({states['fr_overdue']}). Setting light to STROBE RED.")
            flag.off()
            flag.do_strobe_colour(leds=LuxaforFlag.LED_ALL, r=COLOR_RED[0], g=COLOR_RED[1], b=COLOR_RED[2], speed=STROBE_SPEED, repeat=STROBE_REPEATS)
        elif states["open"] > 0:
            logging.info(f"Open tickets ({states['open']}). Setting light to SOLID RED.")
            flag.off()
            flag.do_static_colour(leds=LuxaforFlag.LED_ALL, r=COLOR_RED[0], g=COLOR_RED[1], b=COLOR_RED[2])
        elif states["waiting_agent"] > 0:
            logging.info(f"Waiting on Agent tickets ({states['waiting_agent']}). Setting light to SOLID YELLOW.")
            flag.off()
            flag.do_static_colour(leds=LuxaforFlag.LED_ALL, r=COLOR_YELLOW[0], g=COLOR_YELLOW[1], b=COLOR_YELLOW[2])
        else:
            logging.info("No actionable tickets requiring attention. Setting light to SOLID GREEN.")
            flag.off()
            flag.do_static_colour(leds=LuxaforFlag.LED_ALL, r=COLOR_GREEN[0], g=COLOR_GREEN[1], b=COLOR_GREEN[2])
    except Exception as e:
        # This now indicates a likely communication problem
        logging.error(f"Failed to update Luxafor flag: {e}. Assuming disconnection.")
        # Don't try flag.off() here as it will likely fail too.
        return False # Signal failure
    return True # Signal success

def connect_luxafor():
    """Attempts to connect to the Luxafor device."""
    try:
        logging.info("Attempting to connect to Luxafor Flag...")
        device = LuxaforFlag()
        # Brief connection test blink
        device.do_static_colour(leds=LuxaforFlag.LED_ALL, r=20, g=20, b=20); time.sleep(0.1); device.off()
        logging.info("Luxafor Flag connected successfully.")
        return device
    except Exception as e:
        logging.error(f"Could not connect to Luxafor Flag: {e}.")
        return None

def main():
    """Main loop to check tickets and update the Luxafor flag."""
    flag = connect_luxafor() # Initial connection attempt

    while True:
        # --- Reconnection Logic ---
        if flag is None:
            logging.info("No active Luxafor connection. Will attempt to reconnect...")
            time.sleep(UPDATE_INTERVAL_SECONDS) # Wait before retrying connection
            flag = connect_luxafor()
            if flag is None:
                # Still couldn't connect, wait for the next full loop iteration
                continue # Skip the rest of the loop

        # --- Ticket Processing and Update Logic ---
        if flag: # Proceed only if we have a valid connection
            logging.debug("Checking ticket states...")
            states = get_simplified_ticket_states(TICKETS_DIR)
            logging.debug(f"Ticket states: {states}")

            success = update_luxafor_simplified(flag, states)

            if not success:
                # The update command failed, assume device disconnected
                logging.warning("Luxafor command failed. Setting connection status to disconnected.")
                # Attempt to close the potentially broken handle, ignore errors
                try: flag.off()
                except Exception: pass
                flag = None # This will trigger reconnect attempt on the next loop

        # Wait before the next cycle
        time.sleep(UPDATE_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Define flag_to_close in a scope accessible by finally
    # It will hold the *last known good* flag object for cleanup
    flag_to_close = None
    try:
        # Assign the initial connection attempt result to flag_to_close
        # This is slightly redundant with the 'flag' in main, but ensures
        # we have a reference for the finally block even if the loop never runs.
        # Revisit this if it causes issues, the flag variable from main's scope
        # might be sufficient if handled carefully in finally.
        # Let's try keeping it simple and using the 'flag' from main's scope
        # directly in finally (assuming it's accessible, which it should be).
        main() # This now contains the connection logic internally
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. Shutting down.")
    except Exception as e:
        logging.error(f"An unexpected error occurred outside the main loop: {e}", exc_info=True)
    finally:
        logging.info("Attempting to turn off Luxafor light on exit.")
        # Access the 'flag' variable from the scope where main was called
        # This relies on how variable scoping works with function calls.
        # A cleaner way might involve main returning the flag object on exit.
        # Let's try a potentially safer approach: connect anew for cleanup.
        try:
            cleanup_flag = LuxaforFlag()
            cleanup_flag.off()
            logging.info("Luxafor light turned off via new handle.")
        except Exception as e:
            # This might fail if the device is unplugged or rules are wrong
            logging.warning(f"Could not turn off Luxafor light on exit via new handle: {e}")
        logging.info("Script finished.")
