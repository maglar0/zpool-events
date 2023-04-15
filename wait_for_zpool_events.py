#!/usr/bin/env python3

import logging
import queue
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict



# Set up the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)



def is_scrub_in_progress():
    # Run the zpool status command and capture its output
    cmd = ['zpool', 'status']
    output = subprocess.check_output(cmd).decode('utf-8')

    # Look for a line in the output indicating that a scrub is in progress
    for line in output.split('\n'):
        if 'scrub in progress' in line:
            return True

    # If we get here, there is no scrub in progress
    return False


# When the first event "ever" happens, we wait 10 seconds before sending
# a notification. That way, we can buffer up other notifications happening
# almost simultaneously and send them together. I don't think anything
# is lost by waiting 30 seconds...
# After the notification has been sent, the subsequent numbers say how long
# to wait until sending next event. So for example, after sending an event
# at least 10 minutes have to pass before sending another one. All events
# happening during that period will be queued up and sent together.
# Then we wait 30 minutes and so on.
# If no event has happend during those 30 minutes or whatever it is, we
# go back to initial state again and wait 30 seconds etc as described earlier.
SECONDS_BETWEEN_NOTIFICATIONS = [30, 5*60, 30*60, 2*3600, 12*3600, 24*3600, 48*3600]

# If no event has happend for this time, send a notification anyway
MAX_SECONDS_BETWEEN_NOTIFICATIONS = 86400*60


def send_zpool_status(text_to_add_to_notification):
    subprocess.run(['/root/ntfy/send_zpool_status.sh', text_to_add_to_notification], check=True)


event_queue = queue.Queue()


def send_events_thread():

    try:

        logger.info("send_events_queue starting up")

        while True:
            # Index into SECONDS_BETWEEN_NOTIFICATIONS "where we are at"
            # We can be in "3" states.
            # State "-1" means nothing has happened for a long time. As soon
            #            as something happens, we jump to state 0.
            # State "0" means an event has happened and we are waiting the
            #            SECONDS_BETWEEN_NOTIFICATIONS[0] seconds before sending
            #            the notification.
            # State ">=1" means that we have sent a notification and we are 
            #            waiting for SECONDS_BETWEEN_NOTIFICATION[notification_index]
            #            seconds before we can send next notification (if anything
            #            happens within that time).
            notification_index = -1

            next_send_time = time.time() + MAX_SECONDS_BETWEEN_NOTIFICATIONS
            last_send_time = 0   # Never, or so long ago it doesn't matter
            ready_to_send = defaultdict(lambda: 0) # {event: count}
            logger.debug(f"State -1")

            while True:
                timeout = next_send_time - time.time()
                if timeout > 0:
                    try:
                        logger.debug(f"Waiting up to {timeout=} seconds for new item")
                        item = event_queue.get(timeout=timeout)
                        logger.debug(f"Got event {item}")
                        ready_to_send[item] += 1
                        
                        if notification_index == -1:
                            next_send_time = time.time() + SECONDS_BETWEEN_NOTIFICATIONS[0]
                            notification_index = 0
                            logger.debug(f"We move from state -1 to state 0.")
                        
                        continue
                    
                    except queue.Empty:
                        logger.debug("Timeout, send any events we have gathered")

                if len(ready_to_send) == 0:
                    logger.debug("Nothing happened in the 'quiet period'. Return to state -1.")
                    break

                if max(ready_to_send.values()) == 1:
                    s = ", ".join(f"{event}" for event, count in sorted(ready_to_send.items()))
                else:
                    s = ", ".join(f"{event}:{count}" for event, count in sorted(ready_to_send.items()))
                logger.info(f"Send notification with text '{s}'")
                send_zpool_status(s)

                notification_index = min(notification_index+1, len(SECONDS_BETWEEN_NOTIFICATIONS)-1)
                next_send_time = time.time() + SECONDS_BETWEEN_NOTIFICATIONS[notification_index]
                ready_to_send = defaultdict(lambda: 0)
                logger.debug(f"New state is {notification_index=}, {next_send_time - time.time()} seconds from now")

    except Exception as e:
        logger.error("Caught exception in send_events_thread:", exc_info=True)
        sys.exit(1)


def main():

    send_zpool_status('zpool monitor script start')

    thread = threading.Thread(target=send_events_thread)
    thread.daemon = True  # Automatically stop when main thread stops
    thread.start()

    lines = subprocess.check_output(['zpool', 'events', '-H']).decode().splitlines()
    for event in subprocess.Popen(['zpool', 'events', '-f', '-H'], stdout=subprocess.PIPE).stdout:
        event = event.decode().strip()
        logger.info(f"Event: {event}")
        uninteresting_events = [
            'sysevent.fs.zfs.history_event',
            'sysevent.fs.zfs.trim_start',
            'sysevent.fs.zfs.trim_finish',
            'sysevent.fs.zfs.scrub_start',
            # keep this for now, but maybe uncomment later...
            # 'sysevent.fs.zfs.scrub_finish'
        ]
        if any(e in event for e in uninteresting_events):
            logger.debug(f"Uninteresting event '{event}', ignoring")
        elif 'sysevent.fs.zfs.scrub_finish' in event and is_scrub_in_progress():
            logger.info(f"Scrub finish event, but other scrub in progress. Ignore.")
        elif event in lines:
            logger.debug('Old event, ignoring')
        else:
            # event is a line similar to the following:
            # Feb  5 2023 00:24:01.695934806  sysevent.fs.zfs.trim_start
            # Cut away all the date/time and just keep the right-hand part.
            pattern = r'^\w{3}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\.\d{9}\s+'
            stripped_event = re.sub(pattern, '', event)
            logger.info("Adding event to send queue")
            event_queue.put(stripped_event)



if __name__ == '__main__':
    main()


