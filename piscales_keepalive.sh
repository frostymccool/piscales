#!/bin/bash
#https://github.com/frostymccool/piscales

# wii fit bluetooth smartscale
# continuously polling for scale enabled via the bluetooth connect button
# disconnects and sleeps for 10ish secs, enough time for balance board to turn off
# then goes back to looping to look for it
# weight's logged up to initscale

# this enable script called from crontab needs to check it already running, if not then re-run
# daily will also restart the process - for any cleaning :)



USER="pi"
USER_HOME="/home/$USER"
BASE_NAME="wiiboard-scale3"
DAEMON_ROOT="$USER_HOME/smart-scale"
DAEMON="$DAEMON_ROOT/$BASE_NAME.py"
DAEMON_START_SCRIPT="$DAEMON_ROOT/$BASE_NAME.sh"
PIDFILE="$DAEMON_ROOT/$BASE_NAME.pid"

processName="$BASE_NAME.py"

processPID=$(ps -aux | grep -w python | grep -w ${processName} | grep -v grep | awk '{print $2}')

echo "hubot PID: ${processPID}"

if [ -n "${processPID// }" ] ; then
    echo "`date`: $processName service running, everything is fine"
else
    echo "`date`: $processName service NOT running, starting service."
    cd ${DAEMON_ROOT}
    ${DAEMON_START_SCRIPT} start > /dev/null
fi

