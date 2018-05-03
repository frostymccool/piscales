#!/bin/sh
#https://github.com/frostymccool/piscales

# wii fit bluetooth smartscale
# continuously polling for scale enabled via the bluetooth connect button
# disconnects and sleeps for 10ish secs, enough time for balance board to turn off
# then goes back to looping to look for it
# weight's logged up to ifttt / fitbit or wherever


USER="pi"
USER_HOME="/home/$USER"
BASE_NAME="wiiboard-scale3"
DAEMON_ROOT="$USER_HOME/smart-scale"
# disabled the direct pass of the MAC - seems to not block up 2.4G so much :)
#DAEMON="$DAEMON_ROOT/$BASE_NAME.py MA:CA:DD:RE:ES:SS"
DAEMON="$DAEMON_ROOT/$BASE_NAME.py"
PIDFILE=$DAEMON_ROOT/$BASE_NAME.pid

case "$1" in
start)
        echo "Starting"
        /sbin/start-stop-daemon --start --background --pidfile $PIDFILE --make-pidfile -d $DAEMON_ROOT --exec $DAEMON
        echo "."
        ;;
debug)
        echo "Debug mode: no backgrounding"
        /sbin/start-stop-daemon --start --pidfile $PIDFILE --make-pidfile -d $DAEMON_ROOT --exec $DAEMON
        echo "."
        ;;
stop)
        echo "Stopping"
        /sbin/start-stop-daemon --stop --pidfile $PIDFILE
        echo "."
        ;;
restart)
        echo "Restarting"
        /sbin/start-stop-daemon --stop --pidfile $PIDFILE
        /sbin/start-stop-daemon --start --pidfile $PIDFILE --make-pidfile --background -d $DAEMON_ROOT --exec $DAEMON
        echo "."
        ;;


    *)
        echo "Usage: $0 {start|stop|restart|debug}" >&2
        exit 1
        ;;
    esac
    exit

