#!/bin/sh

# Adapted from PeerDB v0.37.17: the upstream script tried once after a fixed 5s sleep,
# which races Temporal's startup and leaves PeerDB unable to start any mirror.
until temporal operator search-attribute list >/dev/null 2>&1; do
    echo "waiting for Temporal..."
    sleep 2
done

# Check if MirrorName attribute exists
if ! temporal operator search-attribute list | grep -w MirrorName >/dev/null 2>&1; then
    # If not, create MirrorName attribute
    until temporal operator search-attribute create --name MirrorName --type Text --namespace default; do
        sleep 2
    done
fi

tini -s -- sleep infinity
